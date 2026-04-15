from __future__ import annotations

import datetime
import io
import json
import re
import uuid
import sqlalchemy.sql.functions
import sqlalchemy
import langbot_plugin.api.entities.builtin.provider.message as provider_message

from ....core import app
from ....entity.persistence import customer as persistence_customer


class CustomerService:
    """Customer profile and conversation service."""

    ap: app.Application

    default_profile_extraction_prompt = """You are a CRM extraction assistant.
Extract customer profile data from conversation timeline.
Return ONLY valid JSON object, no markdown, no explanation.

JSON schema:
{
  "name": "string | null",
  "phone": "string | null",
  "requirement": "string | null",
  "company": "string | null",
  "address": "string | null",
  "intention": "string | null",
  "tags": ["string"]
}

Rules:
- Keep unknown fields as null.
- Do not guess if information is missing.
- tags should be concise and business-relevant.
- Keep response strictly in JSON.
"""

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    def _utc_now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def _safe_json_dumps(self, data: object) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def _extract_message_text(self, message_content: str | None) -> str:
        """Extract plain text from message chain JSON payload."""
        if not message_content:
            return ''

        try:
            message_chain = json.loads(message_content)
            if not isinstance(message_chain, list):
                return str(message_chain)

            text_parts = []
            for component in message_chain:
                if not isinstance(component, dict):
                    continue
                component_type = component.get('type')
                if component_type == 'Plain':
                    text_parts.append(component.get('text', ''))
                elif component_type == 'At':
                    display = component.get('display', '')
                    target = component.get('target', '')
                    text_parts.append(f'@{display or target}')
                elif component_type == 'Image':
                    text_parts.append('[Image]')
                elif component_type == 'File':
                    text_parts.append(f'[File: {component.get("name", "File")}]')
                elif component_type == 'Voice':
                    text_parts.append('[Voice]')
            return ''.join(text_parts).strip()
        except (TypeError, ValueError, KeyError):
            return message_content

    def _strip_markdown_json_fence(self, content: str) -> str:
        if not content:
            return ''
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\s*```$', '', content)
        return content.strip()

    def _parse_json_object(self, content: str) -> dict | None:
        if not content:
            return None

        cleaned = self._strip_markdown_json_fence(content)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass

        matched = re.search(r'\{[\s\S]*\}', cleaned)
        if not matched:
            return None

        try:
            parsed = json.loads(matched.group(0))
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            return None

        return None

    def _resolve_message_time(self, query, fallback: datetime.datetime) -> datetime.datetime:
        try:
            if hasattr(query, 'message_event') and getattr(query.message_event, 'time', None):
                ts = int(query.message_event.time)
                return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            pass
        return fallback

    async def _get_or_create_customer(
        self,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        timestamp: datetime.datetime,
    ) -> str:
        session_id = f'{query.launcher_type}_{query.launcher_id}'
        launcher_type = query.launcher_type.value if hasattr(query.launcher_type, 'value') else str(query.launcher_type)

        sender_name = None
        if hasattr(query, 'variables') and query.variables:
            sender_name = query.variables.get('sender_name')

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(persistence_customer.Customer.session_id == session_id)
        )
        row = result.first()
        if row:
            customer = row[0] if isinstance(row, tuple) else row
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_customer.Customer)
                .where(persistence_customer.Customer.id == customer.id)
                .values(
                    bot_id=bot_id,
                    bot_name=bot_name,
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_name,
                    launcher_type=launcher_type,
                    launcher_id=str(query.launcher_id),
                    sender_id=str(query.sender_id) if query.sender_id else None,
                    sender_name=sender_name or customer.sender_name,
                    updated_at=self._utc_now(),
                    last_conversation_at=timestamp,
                )
            )
            return customer.id

        customer_id = str(uuid.uuid4())
        now = self._utc_now()
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_customer.Customer).values(
                id=customer_id,
                session_id=session_id,
                bot_id=bot_id,
                bot_name=bot_name,
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_name,
                launcher_type=launcher_type,
                launcher_id=str(query.launcher_id),
                sender_id=str(query.sender_id) if query.sender_id else None,
                sender_name=sender_name,
                created_at=now,
                updated_at=now,
                last_conversation_at=timestamp,
            )
        )
        return customer_id

    def _load_extraction_prompt(self, query) -> str | None:
        config = (
            (query.pipeline_config or {})
            .get('ai', {})
            .get('local-agent', {})
            .get('customer-profile-extraction', {})
        )
        if isinstance(config, dict) and config.get('enabled', True) is False:
            return None
        return config.get('system-prompt') if isinstance(config, dict) else None

    async def ingest_conversation(
        self,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        role: str,
        message_content: str,
        message_id: str | None = None,
        runner_name: str | None = None,
        trigger_extraction: bool = False,
    ) -> str:
        """Ingest one conversation message and optionally refresh profile."""
        if not message_content:
            return ''

        now = self._utc_now()
        timestamp = self._resolve_message_time(query, now) if role == 'user' else now
        customer_id = await self._get_or_create_customer(
            query=query,
            bot_id=bot_id,
            bot_name=bot_name,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            timestamp=timestamp,
        )

        launcher_type = query.launcher_type.value if hasattr(query.launcher_type, 'value') else str(query.launcher_type)
        metadata_payload = {
            'query_id': getattr(query, 'query_id', None),
            'runner_name': runner_name,
            'status': 'success',
        }

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_customer.CustomerConversation).values(
                id=str(uuid.uuid4()),
                customer_id=customer_id,
                session_id=f'{query.launcher_type}_{query.launcher_id}',
                message_id=message_id,
                role=role,
                message_content=message_content,
                message_text=self._extract_message_text(message_content),
                timestamp=timestamp,
                bot_id=bot_id,
                bot_name=bot_name,
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_name,
                launcher_type=launcher_type,
                launcher_id=str(query.launcher_id),
                sender_id=str(query.sender_id) if query.sender_id else None,
                sender_name=(query.variables or {}).get('sender_name') if hasattr(query, 'variables') else None,
                metadata_json=self._safe_json_dumps(metadata_payload),
            )
        )

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.Customer)
            .where(persistence_customer.Customer.id == customer_id)
            .values(last_conversation_at=timestamp, updated_at=self._utc_now())
        )

        if trigger_extraction:
            await self._extract_and_merge_profile(query, customer_id)

        return customer_id

    async def _extract_and_merge_profile(self, query, customer_id: str) -> None:
        prompt = self._load_extraction_prompt(query) or self.default_profile_extraction_prompt

        model_uuid = getattr(query, 'use_llm_model_uuid', None)
        if not model_uuid:
            model_config = (query.pipeline_config or {}).get('ai', {}).get('local-agent', {}).get('model', {})
            if isinstance(model_config, str):
                model_uuid = model_config
            elif isinstance(model_config, dict):
                model_uuid = model_config.get('primary')

        if not model_uuid:
            return

        try:
            model = await self.ap.model_mgr.get_model_by_uuid(model_uuid)
        except Exception:
            return

        conv_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer_id)
            .order_by(persistence_customer.CustomerConversation.timestamp.desc())
            .limit(20)
        )
        conv_rows = conv_result.all()
        if not conv_rows:
            return

        timeline_lines = []
        for row in reversed(conv_rows):
            item = row[0] if isinstance(row, tuple) else row
            role = item.role or 'user'
            message_text = item.message_text or self._extract_message_text(item.message_content)
            if message_text:
                timeline_lines.append(f'[{role}] {message_text}')

        if not timeline_lines:
            return

        extraction_input = (
            'Conversation timeline:\n'
            + '\n'.join(timeline_lines)
            + '\n\nExtract customer structured profile with the required JSON schema.'
        )

        try:
            resp = await model.provider.invoke_llm(
                query=query,
                model=model,
                messages=[
                    provider_message.Message(role='system', content=prompt),
                    provider_message.Message(role='user', content=extraction_input),
                ],
                funcs=[],
                extra_args=model.model_entity.extra_args,
                remove_think=True,
            )
        except Exception:
            return

        content = resp.content if hasattr(resp, 'content') else str(resp)
        if not isinstance(content, str):
            content = str(content)

        profile = self._parse_json_object(content)
        if not profile:
            return

        await self._merge_profile(customer_id, profile)

    async def _merge_profile(self, customer_id: str, profile: dict) -> None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(persistence_customer.Customer.id == customer_id)
        )
        row = result.first()
        if not row:
            return

        customer = row[0] if isinstance(row, tuple) else row

        def normalize_string(value) -> str | None:
            if value is None:
                return None
            if not isinstance(value, str):
                value = str(value)
            value = value.strip()
            return value or None

        tags_value = profile.get('tags')
        if isinstance(tags_value, list):
            tags_normalized = [str(tag).strip() for tag in tags_value if str(tag).strip()]
            tags_json = self._safe_json_dumps(tags_normalized) if tags_normalized else None
        else:
            tags_json = None

        update_values = {
            'customer_name': normalize_string(profile.get('name')) or customer.customer_name,
            'phone': normalize_string(profile.get('phone')) or customer.phone,
            'requirement': normalize_string(profile.get('requirement')) or customer.requirement,
            'company': normalize_string(profile.get('company')) or customer.company,
            'address': normalize_string(profile.get('address')) or customer.address,
            'intention': normalize_string(profile.get('intention')) or customer.intention,
            'tags': tags_json or customer.tags,
            'structured_profile': self._safe_json_dumps(profile),
            'updated_at': self._utc_now(),
        }

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.Customer)
            .where(persistence_customer.Customer.id == customer_id)
            .values(**update_values)
        )

    async def get_customers(
        self,
        search: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conditions = []
        if search:
            pattern = f'%{search.strip()}%'
            conditions.append(
                sqlalchemy.or_(
                    persistence_customer.Customer.customer_name.ilike(pattern),
                    persistence_customer.Customer.phone.ilike(pattern),
                    persistence_customer.Customer.requirement.ilike(pattern),
                    persistence_customer.Customer.sender_name.ilike(pattern),
                    persistence_customer.Customer.session_id.ilike(pattern),
                )
            )
        if bot_ids:
            conditions.append(persistence_customer.Customer.bot_id.in_(bot_ids))
        if pipeline_ids:
            conditions.append(persistence_customer.Customer.pipeline_id.in_(pipeline_ids))

        count_query = sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id))
        if conditions:
            count_query = count_query.where(sqlalchemy.and_(*conditions))
        count_result = await self.ap.persistence_mgr.execute_async(count_query)
        total = count_result.scalar() or 0

        query = sqlalchemy.select(persistence_customer.Customer).order_by(
            persistence_customer.Customer.last_conversation_at.desc()
        )
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))
        query = query.limit(limit).offset(offset)

        result = await self.ap.persistence_mgr.execute_async(query)
        rows = result.all()

        customers = []
        customer_ids = []
        for row in rows:
            customer = row[0] if isinstance(row, tuple) else row
            customers.append(customer)
            customer_ids.append(customer.id)

        count_map: dict[str, int] = {}
        if customer_ids:
            conv_counts_result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(
                    persistence_customer.CustomerConversation.customer_id,
                    sqlalchemy.func.count(persistence_customer.CustomerConversation.id).label('cnt'),
                )
                .where(persistence_customer.CustomerConversation.customer_id.in_(customer_ids))
                .group_by(persistence_customer.CustomerConversation.customer_id)
            )
            for row in conv_counts_result.all():
                count_map[str(row.customer_id)] = int(row.cnt or 0)

        serialized = []
        for customer in customers:
            item = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, customer)
            item['conversation_count'] = count_map.get(customer.id, 0)
            serialized.append(item)

        return serialized, total

    async def get_customer(self, customer_id: str) -> dict | None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(persistence_customer.Customer.id == customer_id)
        )
        row = result.first()
        if not row:
            return None

        customer = row[0] if isinstance(row, tuple) else row
        item = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, customer)
        conv_count_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.CustomerConversation.id)).where(
                persistence_customer.CustomerConversation.customer_id == customer.id
            )
        )
        item['conversation_count'] = conv_count_result.scalar() or 0
        return item

    async def get_customer_conversations(
        self,
        customer_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        count_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.CustomerConversation.id)).where(
                persistence_customer.CustomerConversation.customer_id == customer_id
            )
        )
        total = count_result.scalar() or 0

        query = (
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer_id)
            .order_by(persistence_customer.CustomerConversation.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.ap.persistence_mgr.execute_async(query)
        rows = result.all()
        conversations = [
            self.ap.persistence_mgr.serialize_model(
                persistence_customer.CustomerConversation,
                row[0] if isinstance(row, tuple) else row,
            )
            for row in rows
        ]
        return conversations, total

    async def export_customers_excel(
        self,
        search: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
    ) -> bytes:
        try:
            from openpyxl import Workbook
        except Exception as e:
            raise RuntimeError(f'openpyxl is required for Excel export: {e}')

        customers, _ = await self.get_customers(
            search=search,
            bot_ids=bot_ids,
            pipeline_ids=pipeline_ids,
            limit=100000,
            offset=0,
        )

        wb = Workbook()
        ws_customers = wb.active
        ws_customers.title = 'Customers'
        ws_customers.append(
            [
                'id',
                'customer_name',
                'phone',
                'requirement',
                'company',
                'address',
                'intention',
                'tags',
                'bot_name',
                'pipeline_name',
                'sender_name',
                'session_id',
                'conversation_count',
                'last_conversation_at',
                'updated_at',
            ]
        )
        for item in customers:
            ws_customers.append(
                [
                    item.get('id'),
                    item.get('customer_name'),
                    item.get('phone'),
                    item.get('requirement'),
                    item.get('company'),
                    item.get('address'),
                    item.get('intention'),
                    item.get('tags'),
                    item.get('bot_name'),
                    item.get('pipeline_name'),
                    item.get('sender_name'),
                    item.get('session_id'),
                    item.get('conversation_count'),
                    item.get('last_conversation_at'),
                    item.get('updated_at'),
                ]
            )

        ws_conversations = wb.create_sheet('Conversations')
        ws_conversations.append(
            [
                'id',
                'customer_id',
                'session_id',
                'role',
                'message_text',
                'timestamp',
                'bot_name',
                'pipeline_name',
                'sender_name',
            ]
        )

        customer_ids = [item.get('id') for item in customers if item.get('id')]
        if customer_ids:
            result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_customer.CustomerConversation)
                .where(persistence_customer.CustomerConversation.customer_id.in_(customer_ids))
                .order_by(persistence_customer.CustomerConversation.timestamp.asc())
            )
            rows = result.all()
            for row in rows:
                conv = row[0] if isinstance(row, tuple) else row
                ws_conversations.append(
                    [
                        conv.id,
                        conv.customer_id,
                        conv.session_id,
                        conv.role,
                        conv.message_text,
                        conv.timestamp.isoformat() if conv.timestamp else None,
                        conv.bot_name,
                        conv.pipeline_name,
                        conv.sender_name,
                    ]
                )

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()
