from __future__ import annotations

import datetime
import io
import json
import re
import uuid
from typing import Any

import pandas
import sqlalchemy

import langbot_plugin.api.entities.builtin.provider.message as provider_message

from ....core import app
from ....entity.persistence import customer as persistence_customer


CUSTOMER_EXTRACTION_PROMPT = """
You are a CRM extraction assistant.

Your task is to read a conversation transcript and return a single JSON object only.
Extract structured customer information when it is explicitly stated or can be inferred with high confidence.
If a field is unknown, use an empty string for strings and an empty array for tags.
Do not hallucinate.

Return this JSON schema:
{
  "name": "",
  "phone": "",
  "email": "",
  "company": "",
  "requirements": "",
  "notes": "",
  "tags": [],
  "summary": ""
}
""".strip()


class CustomerService:
    """Customer profile and conversation management service."""

    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    def _unwrap_row(self, row: Any) -> Any:
        if row is None:
            return None
        if isinstance(row, tuple):
            return row[0]
        return row

    def _get_session_id(self, query) -> str:
        return f'{query.launcher_type}_{query.launcher_id}'

    def _get_platform_name(self, query) -> str:
        adapter = getattr(query, 'adapter', None)
        if adapter is not None:
            adapter_name = getattr(adapter, 'name', None)
            if adapter_name:
                return str(adapter_name)
            class_name = adapter.__class__.__name__
            if class_name:
                return class_name
        launcher_type = getattr(query.launcher_type, 'value', None)
        return str(launcher_type or query.launcher_type)

    def _build_customer_key(self, query, platform_name: str) -> str:
        sender_id = str(getattr(query, 'sender_id', '') or '')
        if sender_id:
            return f'{platform_name}:{sender_id}'
        return f'{platform_name}:{self._get_session_id(query)}'

    def _normalize_text(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        cleaned = str(value).strip()
        return cleaned or None

    def _normalize_phone(self, value: Any) -> str | None:
        text = self._normalize_text(value)
        if not text:
            return None
        text = text.replace(' ', '')
        return text[:64]

    def _normalize_tags(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            items = re.split(r'[,\n/;|]+', value)
        elif isinstance(value, list):
            items = value
        else:
            items = [value]
        tags = []
        seen = set()
        for item in items:
            tag = self._normalize_text(item)
            if tag and tag not in seen:
                tags.append(tag)
                seen.add(tag)
        return tags

    def _merge_tags(self, current_tags: list[str] | None, new_tags: list[str]) -> list[str]:
        merged = list(current_tags or [])
        seen = set(merged)
        for tag in new_tags:
            if tag not in seen:
                merged.append(tag)
                seen.add(tag)
        return merged

    def _extract_message_text(self, message_content: str | None) -> str:
        if not message_content:
            return ''

        try:
            message_chain = json.loads(message_content)
        except (json.JSONDecodeError, TypeError):
            return str(message_content)

        if not isinstance(message_chain, list):
            return str(message_content)

        text_parts = []
        for component in message_chain:
            if not isinstance(component, dict):
                continue
            component_type = component.get('type')
            if component_type == 'Plain':
                text_parts.append(component.get('text', ''))
            elif component_type == 'At':
                display = component.get('display') or component.get('target') or ''
                if display:
                    text_parts.append(f'@{display}')
            elif component_type == 'AtAll':
                text_parts.append('@All')
            elif component_type == 'Image':
                text_parts.append('[Image]')
            elif component_type == 'Voice':
                length = component.get('length', 0)
                text_parts.append(f'[Voice {length}s]')
            elif component_type == 'File':
                name = component.get('name', 'File')
                text_parts.append(f'[File: {name}]')
            elif component_type == 'Quote':
                origin = component.get('origin', [])
                if isinstance(origin, list):
                    for item in origin:
                        if isinstance(item, dict) and item.get('type') == 'Plain':
                            text_parts.append(f'> {item.get("text", "")}')
            elif component_type == 'Source':
                continue
            elif component_type:
                text_parts.append(f'[{component_type}]')
        return ''.join(text_parts).strip()

    def _response_to_text(self, response: Any) -> str:
        content = getattr(response, 'content', None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                text = getattr(item, 'text', None)
                if text:
                    parts.append(text)
                    continue
                item_content = getattr(item, 'content', None)
                if isinstance(item_content, str):
                    parts.append(item_content)
                    continue
                parts.append(str(item))
            return ''.join(parts)
        return str(content or response or '')

    def _extract_json_block(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if not cleaned:
            return None

        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{.*\}', cleaned, flags=re.DOTALL)
        if not match:
            return None

        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            return None
        return None

    def _infer_profile_from_text(self, text: str) -> dict[str, Any]:
        inferred: dict[str, Any] = {}
        plain_text = self._normalize_text(text)
        if not plain_text:
            return inferred

        phone_match = re.search(
            r'((?:\+?\d[\d\-\s]{7,}\d)|(?:1[3-9]\d{9}))',
            plain_text,
        )
        if phone_match:
            inferred['phone'] = self._normalize_phone(phone_match.group(1))

        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', plain_text)
        if email_match:
            inferred['email'] = email_match.group(0)

        name_patterns = [
            r'(?:我叫|我是|姓名[:：]|名字[:：])\s*([A-Za-z\u4e00-\u9fa5]{2,20})',
            r'(?:联系人[:：]|客户[:：])\s*([A-Za-z\u4e00-\u9fa5]{2,20})',
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, plain_text)
            if name_match:
                inferred['name'] = name_match.group(1)
                break

        requirement_keywords = ['需求', '想要', '需要', '咨询', '预算', '租', '购买', '方案']
        if any(keyword in plain_text for keyword in requirement_keywords):
            inferred['requirements'] = plain_text[:1000]

        return inferred

    def _build_customer_updates(
        self,
        current_customer: dict[str, Any],
        extracted_profile: dict[str, Any] | None = None,
        now: datetime.datetime | None = None,
        increment_conversation_count: bool = False,
        session_id: str | None = None,
        platform: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
        pipeline_id: str | None = None,
        pipeline_name: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        set_extracted_at: bool = False,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        now = now or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        if session_id is not None:
            updates['session_id'] = session_id
        if platform is not None:
            updates['platform'] = platform
        if bot_id is not None:
            updates['bot_id'] = bot_id
        if bot_name is not None:
            updates['bot_name'] = bot_name
        if pipeline_id is not None:
            updates['pipeline_id'] = pipeline_id
        if pipeline_name is not None:
            updates['pipeline_name'] = pipeline_name
        if user_id is not None:
            updates['user_id'] = user_id
        if user_name is not None:
            updates['user_name'] = user_name

        updates['last_contact_at'] = now
        if increment_conversation_count:
            updates['conversation_count'] = (current_customer.get('conversation_count') or 0) + 1

        if extracted_profile:
            profile_data = dict(current_customer.get('profile_data') or {})
            normalized_tags = self._normalize_tags(extracted_profile.get('tags'))

            for field, normalizer in (
                ('name', self._normalize_text),
                ('phone', self._normalize_phone),
                ('email', self._normalize_text),
                ('company', self._normalize_text),
                ('requirements', self._normalize_text),
                ('notes', self._normalize_text),
            ):
                new_value = normalizer(extracted_profile.get(field))
                if new_value:
                    updates[field] = new_value
                    profile_data[field] = new_value

            if normalized_tags:
                merged_tags = self._merge_tags(current_customer.get('tags') or [], normalized_tags)
                updates['tags'] = merged_tags
                profile_data['tags'] = merged_tags

            summary = self._normalize_text(extracted_profile.get('summary'))
            if summary:
                updates['latest_summary'] = summary
                profile_data['summary'] = summary

            if extracted_profile:
                for key, value in extracted_profile.items():
                    if key in {'name', 'phone', 'email', 'company', 'requirements', 'notes', 'summary', 'tags'}:
                        continue
                    if value not in (None, '', [], {}):
                        profile_data[key] = value

            if profile_data:
                updates['profile_data'] = profile_data

            if set_extracted_at:
                updates['last_extracted_at'] = now

        return updates

    async def _get_customer_row(self, customer_id: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(persistence_customer.Customer.id == customer_id)
        )
        return self._unwrap_row(result.first())

    async def _get_customer_by_key(self, customer_key: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(
                persistence_customer.Customer.customer_key == customer_key
            )
        )
        return self._unwrap_row(result.first())

    async def _ensure_customer(
        self,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        user_name: str | None,
    ) -> dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        session_id = self._get_session_id(query)
        platform_name = self._get_platform_name(query)
        customer_key = self._build_customer_key(query, platform_name)

        existing_customer = await self._get_customer_by_key(customer_key)
        if existing_customer is not None:
            return self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, existing_customer)

        customer_id = str(uuid.uuid4())
        customer_data = {
            'id': customer_id,
            'customer_key': customer_key,
            'session_id': session_id,
            'platform': platform_name,
            'bot_id': bot_id,
            'bot_name': bot_name,
            'pipeline_id': pipeline_id,
            'pipeline_name': pipeline_name,
            'user_id': str(getattr(query, 'sender_id', '') or '') or None,
            'user_name': user_name,
            'conversation_count': 0,
            'first_contact_at': now,
            'last_contact_at': now,
        }

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_customer.Customer).values(customer_data)
        )
        return customer_data

    async def record_conversation(
        self,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        role: str,
        message_content: str,
        user_name: str | None = None,
    ) -> str:
        """Persist one customer conversation and upsert the customer profile."""
        customer = await self._ensure_customer(query, bot_id, bot_name, pipeline_id, pipeline_name, user_name)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        session_id = self._get_session_id(query)
        platform_name = self._get_platform_name(query)
        message_text = self._extract_message_text(message_content)
        extracted_profile = self._infer_profile_from_text(message_text) if role == 'user' else None

        conversation_data = {
            'id': str(uuid.uuid4()),
            'customer_id': customer['id'],
            'session_id': session_id,
            'platform': platform_name,
            'bot_id': bot_id,
            'bot_name': bot_name,
            'pipeline_id': pipeline_id,
            'pipeline_name': pipeline_name,
            'user_id': str(getattr(query, 'sender_id', '') or '') or None,
            'user_name': user_name,
            'role': role,
            'content_text': message_text or '',
            'raw_message_content': message_content,
            'created_at': now,
        }

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_customer.CustomerConversation).values(conversation_data)
        )

        updates = self._build_customer_updates(
            current_customer=customer,
            extracted_profile=extracted_profile,
            now=now,
            increment_conversation_count=True,
            session_id=session_id,
            platform=platform_name,
            bot_id=bot_id,
            bot_name=bot_name,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            user_id=str(getattr(query, 'sender_id', '') or '') or None,
            user_name=user_name,
        )

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.Customer)
            .where(persistence_customer.Customer.id == customer['id'])
            .values(**updates)
        )

        return customer['id']

    async def extract_customer_profile(self, customer_id: str, query) -> None:
        """Use the current pipeline model to extract structured customer data."""
        if not customer_id or not getattr(query, 'use_llm_model_uuid', None):
            return

        customer_row = await self._get_customer_row(customer_id)
        if customer_row is None:
            return

        customer = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, customer_row)

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer_id)
            .order_by(persistence_customer.CustomerConversation.created_at.desc())
            .limit(20)
        )
        conversation_rows = [self._unwrap_row(row) for row in result.all()]
        if not conversation_rows:
            return

        conversation_rows.reverse()
        transcript_lines = []
        for row in conversation_rows:
            timestamp = row.created_at.isoformat() if row.created_at else ''
            transcript_lines.append(f'[{timestamp}] {row.role}: {row.content_text}')
        transcript = '\n'.join(transcript_lines)

        runtime_model = await self.ap.model_mgr.get_model_by_uuid(query.use_llm_model_uuid)
        existing_profile = {
            'name': customer.get('name') or '',
            'phone': customer.get('phone') or '',
            'email': customer.get('email') or '',
            'company': customer.get('company') or '',
            'requirements': customer.get('requirements') or '',
            'notes': customer.get('notes') or '',
            'tags': customer.get('tags') or [],
            'summary': customer.get('latest_summary') or '',
        }
        prompt = (
            'Existing profile:\n'
            f'{json.dumps(existing_profile, ensure_ascii=False)}\n\n'
            'Conversation transcript:\n'
            f'{transcript}\n\n'
            'Return JSON only.'
        )
        response = await runtime_model.provider.invoke_llm(
            query=None,
            model=runtime_model,
            messages=[
                provider_message.Message(role='system', content=CUSTOMER_EXTRACTION_PROMPT),
                provider_message.Message(role='user', content=prompt),
            ],
            funcs=[],
            extra_args=runtime_model.model_entity.extra_args,
        )

        payload = self._extract_json_block(self._response_to_text(response))
        if not payload:
            return

        updates = self._build_customer_updates(
            current_customer=customer,
            extracted_profile=payload,
            now=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            set_extracted_at=True,
        )
        if not updates:
            return

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.Customer)
            .where(persistence_customer.Customer.id == customer_id)
            .values(**updates)
        )

        latest_conversation = conversation_rows[-1]
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.id == latest_conversation.id)
            .values(extracted_payload=payload)
        )

    async def get_customers(
        self,
        keyword: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get customer list with optional filters."""
        conditions = []
        if keyword:
            keyword_like = f'%{keyword.strip()}%'
            conditions.append(
                sqlalchemy.or_(
                    persistence_customer.Customer.name.ilike(keyword_like),
                    persistence_customer.Customer.phone.ilike(keyword_like),
                    persistence_customer.Customer.email.ilike(keyword_like),
                    persistence_customer.Customer.company.ilike(keyword_like),
                    persistence_customer.Customer.requirements.ilike(keyword_like),
                    persistence_customer.Customer.user_name.ilike(keyword_like),
                    persistence_customer.Customer.user_id.ilike(keyword_like),
                )
            )
        if bot_ids:
            conditions.append(persistence_customer.Customer.bot_id.in_(bot_ids))
        if pipeline_ids:
            conditions.append(persistence_customer.Customer.pipeline_id.in_(pipeline_ids))

        count_query = sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id))
        data_query = sqlalchemy.select(persistence_customer.Customer).order_by(
            persistence_customer.Customer.last_contact_at.desc()
        )
        if conditions:
            count_query = count_query.where(sqlalchemy.and_(*conditions))
            data_query = data_query.where(sqlalchemy.and_(*conditions))

        count_result = await self.ap.persistence_mgr.execute_async(count_query)
        total = count_result.scalar() or 0

        data_query = data_query.limit(limit).offset(offset)
        result = await self.ap.persistence_mgr.execute_async(data_query)
        rows = [self._unwrap_row(row) for row in result.all()]

        customers = []
        for row in rows:
            customer = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, row)
            customer['display_name'] = customer.get('name') or customer.get('user_name') or customer.get('user_id') or '-'
            customers.append(customer)
        return customers, total

    async def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Get customer detail."""
        customer_row = await self._get_customer_row(customer_id)
        if customer_row is None:
            return None
        customer = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, customer_row)
        customer['display_name'] = customer.get('name') or customer.get('user_name') or customer.get('user_id') or '-'
        return customer

    async def get_customer_conversations(
        self,
        customer_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get conversations for one customer."""
        count_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.CustomerConversation.id)).where(
                persistence_customer.CustomerConversation.customer_id == customer_id
            )
        )
        total = count_result.scalar() or 0

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer_id)
            .order_by(persistence_customer.CustomerConversation.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = [self._unwrap_row(row) for row in result.all()]
        return [
            self.ap.persistence_mgr.serialize_model(persistence_customer.CustomerConversation, row) for row in rows
        ], total

    def _normalize_excel_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value

    async def export_customers_excel(
        self,
        keyword: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
    ) -> bytes:
        """Export customers and their conversations as an Excel file."""
        customers, _ = await self.get_customers(
            keyword=keyword,
            bot_ids=bot_ids,
            pipeline_ids=pipeline_ids,
            limit=100000,
            offset=0,
        )
        customer_ids = [customer['id'] for customer in customers]

        conversation_rows: list[dict[str, Any]] = []
        if customer_ids:
            result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_customer.CustomerConversation)
                .where(persistence_customer.CustomerConversation.customer_id.in_(customer_ids))
                .order_by(persistence_customer.CustomerConversation.created_at.asc())
            )
            for row in result.all():
                conversation = self.ap.persistence_mgr.serialize_model(
                    persistence_customer.CustomerConversation, self._unwrap_row(row)
                )
                conversation_rows.append(
                    {key: self._normalize_excel_value(value) for key, value in conversation.items()}
                )

        customer_rows = [
            {key: self._normalize_excel_value(value) for key, value in customer.items()} for customer in customers
        ]

        output = io.BytesIO()
        with pandas.ExcelWriter(output, engine='openpyxl') as writer:
            pandas.DataFrame(customer_rows).to_excel(writer, sheet_name='Customers', index=False)
            pandas.DataFrame(conversation_rows).to_excel(writer, sheet_name='Conversations', index=False)
        return output.getvalue()
