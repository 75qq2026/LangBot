from __future__ import annotations

import datetime
import io
import json
import re
import uuid
import zipfile
from xml.sax.saxutils import escape

import sqlalchemy
import langbot_plugin.api.entities.builtin.provider.message as provider_message

from ....core import app
from ....entity.persistence import customer as persistence_customer


class CustomerService:
    """Customer profile and conversation timeline service."""

    CUSTOMER_GUIDANCE_PROMPT = (
        'You are also responsible for customer intake. '
        'When the conversation indicates the speaker is a lead, prospect, or customer, '
        'politely collect any missing key facts such as name, phone number, company, and core requirements. '
        'Ask at most one or two focused follow-up questions at a time, avoid repeating questions for information '
        'that is already known, never fabricate personal data, and keep the reply natural in the user language.'
    )

    CUSTOMER_EXTRACTION_PROMPT = """
You extract structured customer information for a CRM from conversation transcripts.
Return strict JSON only, without markdown fences or extra prose.

Output schema:
{
  "customer_name": string | null,
  "phone": string | null,
  "company": string | null,
  "requirement_summary": string | null,
  "intent": string | null,
  "notes": string | null,
  "tags": string[]
}

Rules:
- Use null when a field is unknown.
- Do not invent facts.
- Prefer newer facts when the transcript contains conflicts.
- Keep requirement_summary and notes concise.
- Normalize phone numbers by preserving digits and a leading plus sign only.
""".strip()

    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    async def append_customer_collection_prompt(self, query) -> None:
        """Append customer collection guidance to the system prompt."""
        prompt = getattr(query, 'prompt', None)
        prompt_messages = getattr(prompt, 'messages', None)

        if not prompt_messages:
            return

        for message in prompt_messages:
            if getattr(message, 'role', None) != 'system':
                continue
            if not isinstance(message.content, str):
                continue
            if self.CUSTOMER_GUIDANCE_PROMPT in message.content:
                return

            message.content = f'{message.content.rstrip()}\n\n{self.CUSTOMER_GUIDANCE_PROMPT}'
            return

        prompt_messages.insert(
            0,
            provider_message.Message(
                role='system',
                content=self.CUSTOMER_GUIDANCE_PROMPT,
            ),
        )

    async def record_pipeline_interaction(
        self,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        runner_name: str | None = None,
        user_monitoring_message_id: str | None = None,
    ) -> None:
        """Persist a query turn and refresh the structured customer profile."""
        session_id = self._build_session_id(query)
        platform = getattr(query.launcher_type, 'value', str(query.launcher_type))
        user_id = str(getattr(query, 'sender_id', '') or getattr(query, 'launcher_id', '') or session_id)
        user_name = self._extract_sender_name(query)
        now = self._utcnow()

        customer = await self._get_or_create_customer(
            bot_id=bot_id,
            bot_name=bot_name,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            session_id=session_id,
            platform=platform,
            user_id=user_id,
            user_name=user_name,
            runner_name=runner_name,
            timestamp=now,
        )

        conversation_rows = self._build_conversation_rows(
            customer_id=customer.id,
            query=query,
            bot_id=bot_id,
            bot_name=bot_name,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            session_id=session_id,
            platform=platform,
            user_id=user_id,
            user_name=user_name,
            monitoring_message_id=user_monitoring_message_id,
            timestamp=now,
        )

        if conversation_rows:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.insert(persistence_customer.CustomerConversation).values(conversation_rows)
            )

        extracted_profile: dict | None = None
        extraction_model_name: str | None = None

        try:
            extracted_profile, extraction_model_name = await self._extract_customer_profile(customer, query)
        except Exception as e:
            self.ap.logger.warning(f'Failed to extract customer profile for session {session_id}: {e}')

        merged_profile = self._merge_profile_data(customer.profile_data, extracted_profile)
        update_values = {
            'updated_at': now,
            'last_contact_at': now,
            'bot_name': bot_name,
            'pipeline_id': pipeline_id,
            'pipeline_name': pipeline_name,
            'platform': platform,
            'source_runner': runner_name,
            'conversation_count': customer.conversation_count + len(conversation_rows),
        }

        if user_name:
            update_values['user_name'] = user_name

        if extraction_model_name:
            update_values['extraction_model'] = extraction_model_name

        if merged_profile:
            tags = self._normalize_tags(merged_profile.get('tags'))
            update_values['profile_data'] = json.dumps(merged_profile, ensure_ascii=False)
            update_values['customer_name'] = merged_profile.get('customer_name')
            update_values['phone'] = self._normalize_phone(merged_profile.get('phone'))
            update_values['company'] = merged_profile.get('company')
            update_values['requirement_summary'] = merged_profile.get('requirement_summary')
            update_values['intent'] = merged_profile.get('intent')
            update_values['notes'] = merged_profile.get('notes')
            update_values['tags'] = json.dumps(tags, ensure_ascii=False) if tags else None
            update_values['profile_status'] = self._build_profile_status(merged_profile)
        else:
            update_values['profile_status'] = customer.profile_status or 'new'

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_customer.Customer)
            .where(persistence_customer.Customer.id == customer.id)
            .values(update_values)
        )

    async def get_customers(
        self,
        keyword: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return paginated customer profiles."""
        conditions = self._build_customer_conditions(keyword, bot_ids, pipeline_ids)

        count_query = sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id))
        if conditions:
            count_query = count_query.where(sqlalchemy.and_(*conditions))

        total_result = await self.ap.persistence_mgr.execute_async(count_query)
        total = total_result.scalar() or 0

        query = sqlalchemy.select(persistence_customer.Customer).order_by(
            persistence_customer.Customer.last_contact_at.desc()
        )
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))

        query = query.limit(limit).offset(offset)
        result = await self.ap.persistence_mgr.execute_async(query)

        customers = []
        for row in result.all():
            customer = self._unwrap_row(row)
            customers.append(self._serialize_customer(customer))

        return customers, total

    async def get_customer_detail(self, customer_id: str) -> dict:
        """Return a single customer profile."""
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(persistence_customer.Customer.id == customer_id)
        )
        row = result.first()
        if not row:
            return {
                'found': False,
                'customer_id': customer_id,
            }

        customer = self._unwrap_row(row)
        return {
            'found': True,
            'customer': self._serialize_customer(customer),
        }

    async def get_customer_conversations(
        self,
        customer_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return a customer conversation timeline."""
        count_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.CustomerConversation.id)).where(
                persistence_customer.CustomerConversation.customer_id == customer_id
            )
        )
        total = count_result.scalar() or 0

        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer_id)
            .order_by(persistence_customer.CustomerConversation.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )

        conversations = []
        for row in result.all():
            conversation = self._unwrap_row(row)
            conversations.append(self._serialize_conversation(conversation))

        return conversations, total

    async def export_customers(
        self,
        keyword: str | None = None,
        bot_ids: list[str] | None = None,
        pipeline_ids: list[str] | None = None,
        limit: int = 100000,
    ) -> bytes:
        """Export customer profiles as an XLSX workbook."""
        customers, _ = await self.get_customers(
            keyword=keyword,
            bot_ids=bot_ids,
            pipeline_ids=pipeline_ids,
            limit=limit,
            offset=0,
        )

        headers = [
            'Customer ID',
            'Customer Name',
            'Phone',
            'Company',
            'Requirement Summary',
            'Intent',
            'Tags',
            'Profile Status',
            'Bot Name',
            'Pipeline Name',
            'Session ID',
            'User ID',
            'User Name',
            'Conversation Count',
            'Last Contact At',
            'Created At',
            'Updated At',
        ]

        rows = [
            [
                customer['id'],
                customer.get('customer_name') or '',
                customer.get('phone') or '',
                customer.get('company') or '',
                customer.get('requirement_summary') or '',
                customer.get('intent') or '',
                ', '.join(customer.get('tags') or []),
                customer.get('profile_status') or '',
                customer.get('bot_name') or '',
                customer.get('pipeline_name') or '',
                customer.get('session_id') or '',
                customer.get('user_id') or '',
                customer.get('user_name') or '',
                customer.get('conversation_count') or 0,
                customer.get('last_contact_at') or '',
                customer.get('created_at') or '',
                customer.get('updated_at') or '',
            ]
            for customer in customers
        ]

        return self._build_xlsx_workbook(sheet_name='Customers', headers=headers, rows=rows)

    async def _get_or_create_customer(
        self,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        session_id: str,
        platform: str,
        user_id: str,
        user_name: str | None,
        runner_name: str | None,
        timestamp: datetime.datetime,
    ) -> persistence_customer.Customer:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.Customer).where(
                sqlalchemy.and_(
                    persistence_customer.Customer.bot_id == bot_id,
                    persistence_customer.Customer.session_id == session_id,
                    persistence_customer.Customer.user_id == user_id,
                )
            )
        )
        row = result.first()
        if row:
            return self._unwrap_row(row)

        customer_data = {
            'id': str(uuid.uuid4()),
            'created_at': timestamp,
            'updated_at': timestamp,
            'last_contact_at': timestamp,
            'bot_id': bot_id,
            'bot_name': bot_name,
            'pipeline_id': pipeline_id,
            'pipeline_name': pipeline_name,
            'session_id': session_id,
            'platform': platform,
            'user_id': user_id,
            'user_name': user_name,
            'profile_status': 'new',
            'source_runner': runner_name,
            'conversation_count': 0,
        }

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_customer.Customer).values(customer_data)
        )
        return persistence_customer.Customer(**customer_data)

    def _build_conversation_rows(
        self,
        customer_id: str,
        query,
        bot_id: str,
        bot_name: str,
        pipeline_id: str,
        pipeline_name: str,
        session_id: str,
        platform: str,
        user_id: str,
        user_name: str | None,
        monitoring_message_id: str | None,
        timestamp: datetime.datetime,
    ) -> list[dict]:
        rows: list[dict] = []

        user_timestamp = timestamp
        event_time = getattr(getattr(query, 'message_event', None), 'time', None)
        if event_time:
            try:
                user_timestamp = datetime.datetime.fromtimestamp(int(event_time), tz=datetime.timezone.utc).replace(
                    tzinfo=None
                )
            except Exception:
                user_timestamp = timestamp

        user_content = self._serialize_message_content(getattr(query, 'message_chain', None))
        user_text = self._extract_message_text(user_content)
        if user_content:
            rows.append(
                {
                    'id': str(uuid.uuid4()),
                    'customer_id': customer_id,
                    'timestamp': user_timestamp,
                    'bot_id': bot_id,
                    'bot_name': bot_name,
                    'pipeline_id': pipeline_id,
                    'pipeline_name': pipeline_name,
                    'session_id': session_id,
                    'platform': platform,
                    'user_id': user_id,
                    'user_name': user_name,
                    'role': 'user',
                    'message_content': user_content,
                    'message_text': user_text,
                    'monitoring_message_id': monitoring_message_id,
                }
            )

        assistant_chain = self._get_last_assistant_chain(query)
        assistant_content = self._serialize_message_content(assistant_chain)
        assistant_text = self._extract_message_text(assistant_content)
        if assistant_content:
            rows.append(
                {
                    'id': str(uuid.uuid4()),
                    'customer_id': customer_id,
                    'timestamp': timestamp,
                    'bot_id': bot_id,
                    'bot_name': bot_name,
                    'pipeline_id': pipeline_id,
                    'pipeline_name': pipeline_name,
                    'session_id': session_id,
                    'platform': platform,
                    'user_id': user_id,
                    'user_name': user_name,
                    'role': 'assistant',
                    'message_content': assistant_content,
                    'message_text': assistant_text,
                    'monitoring_message_id': None,
                }
            )

        return rows

    async def _extract_customer_profile(self, customer, query) -> tuple[dict | None, str | None]:
        runtime_model = await self._resolve_extraction_model(query)
        if runtime_model is None:
            return None, None

        transcript_rows = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_customer.CustomerConversation)
            .where(persistence_customer.CustomerConversation.customer_id == customer.id)
            .order_by(persistence_customer.CustomerConversation.timestamp.desc())
            .limit(20)
        )
        conversations = [self._unwrap_row(row) for row in transcript_rows.all()]
        conversations.reverse()

        transcript = [
            {
                'timestamp': self._format_timestamp(item.timestamp),
                'role': item.role,
                'message_text': item.message_text or self._extract_message_text(item.message_content),
            }
            for item in conversations
            if item.message_text or item.message_content
        ]

        if not transcript:
            return None, None

        payload = {
            'current_profile': self._parse_json(customer.profile_data, {}),
            'conversation': transcript,
        }

        messages = [
            provider_message.Message(role='system', content=self.CUSTOMER_EXTRACTION_PROMPT),
            provider_message.Message(role='user', content=json.dumps(payload, ensure_ascii=False)),
        ]

        result = await runtime_model.provider.invoke_llm(
            query=query,
            model=runtime_model,
            messages=messages,
            funcs=[],
            extra_args=runtime_model.model_entity.extra_args,
            remove_think=True,
        )

        response_message = result[0] if isinstance(result, tuple) else result
        if not response_message or not getattr(response_message, 'content', None):
            return None, runtime_model.model_entity.name

        extracted = self._parse_extraction_response(response_message.content)
        if not extracted:
            return None, runtime_model.model_entity.name

        return extracted, runtime_model.model_entity.name

    async def _resolve_extraction_model(self, query):
        selected_runner = (
            query.pipeline_config.get('ai', {}).get('runner', {}).get('runner')
            if getattr(query, 'pipeline_config', None)
            else None
        )

        if selected_runner == 'local-agent':
            model_config = query.pipeline_config.get('ai', {}).get('local-agent', {}).get('model', {})
            model_uuid = model_config if isinstance(model_config, str) else model_config.get('primary')
            if model_uuid:
                try:
                    return await self.ap.model_mgr.get_model_by_uuid(model_uuid)
                except Exception:
                    self.ap.logger.warning(f'Customer extraction fallback: model {model_uuid} not found')

        llm_models = getattr(self.ap.model_mgr, 'llm_models', [])
        if llm_models:
            return llm_models[0]

        return None

    def _build_customer_conditions(
        self,
        keyword: str | None,
        bot_ids: list[str] | None,
        pipeline_ids: list[str] | None,
    ) -> list:
        conditions = []

        if keyword:
            search_term = f'%{keyword.strip()}%'
            conditions.append(
                sqlalchemy.or_(
                    persistence_customer.Customer.customer_name.ilike(search_term),
                    persistence_customer.Customer.phone.ilike(search_term),
                    persistence_customer.Customer.company.ilike(search_term),
                    persistence_customer.Customer.requirement_summary.ilike(search_term),
                    persistence_customer.Customer.user_name.ilike(search_term),
                    persistence_customer.Customer.user_id.ilike(search_term),
                )
            )

        if bot_ids:
            conditions.append(persistence_customer.Customer.bot_id.in_(bot_ids))

        if pipeline_ids:
            conditions.append(persistence_customer.Customer.pipeline_id.in_(pipeline_ids))

        return conditions

    async def get_customer_summary(self) -> dict:
        """Return lightweight summary metrics for the customer module."""
        total_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id))
        )
        complete_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id)).where(
                persistence_customer.Customer.profile_status == 'complete'
            )
        )
        partial_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.Customer.id)).where(
                persistence_customer.Customer.profile_status == 'partial'
            )
        )
        conversation_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count(persistence_customer.CustomerConversation.id))
        )

        return {
            'total_customers': total_result.scalar() or 0,
            'complete_profiles': complete_result.scalar() or 0,
            'partial_profiles': partial_result.scalar() or 0,
            'conversation_records': conversation_result.scalar() or 0,
        }

    def _serialize_customer(self, customer) -> dict:
        data = self.ap.persistence_mgr.serialize_model(persistence_customer.Customer, customer)
        data['tags'] = self._parse_json(data.get('tags'), [])
        data['profile_data'] = self._parse_json(data.get('profile_data'), {})
        return data

    def _serialize_conversation(self, conversation) -> dict:
        return self.ap.persistence_mgr.serialize_model(persistence_customer.CustomerConversation, conversation)

    def _merge_profile_data(self, existing_profile: str | None, new_profile: dict | None) -> dict:
        merged = self._parse_json(existing_profile, {})
        if not new_profile:
            return merged

        for key in ['customer_name', 'phone', 'company', 'requirement_summary', 'intent', 'notes']:
            value = new_profile.get(key)
            if isinstance(value, str):
                value = value.strip()
            if value:
                merged[key] = value

        merged['tags'] = self._merge_tags(merged.get('tags'), new_profile.get('tags'))
        return merged

    def _merge_tags(self, existing_tags, new_tags) -> list[str]:
        result: list[str] = []
        for tag in self._normalize_tags(existing_tags) + self._normalize_tags(new_tags):
            if tag not in result:
                result.append(tag)
        return result

    def _normalize_tags(self, tags) -> list[str]:
        if not tags:
            return []

        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [part.strip() for part in tags.split(',')]

        if not isinstance(tags, list):
            return []

        normalized = []
        for tag in tags:
            if not tag:
                continue
            tag_text = str(tag).strip()
            if tag_text and tag_text not in normalized:
                normalized.append(tag_text)
        return normalized

    def _build_profile_status(self, profile: dict) -> str:
        if not profile:
            return 'new'

        has_name = bool(profile.get('customer_name'))
        has_phone = bool(profile.get('phone'))
        has_requirement = bool(profile.get('requirement_summary'))

        if has_name and has_phone and has_requirement:
            return 'complete'
        if has_name or has_phone or has_requirement or profile.get('company') or profile.get('intent'):
            return 'partial'
        return 'new'

    def _parse_extraction_response(self, content) -> dict | None:
        if not isinstance(content, str):
            return None

        cleaned = content.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        if not cleaned.startswith('{'):
            json_match = re.search(r'\{.*\}', cleaned, flags=re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)

        try:
            data = json.loads(cleaned)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        return {
            'customer_name': self._clean_nullable_text(data.get('customer_name')),
            'phone': self._normalize_phone(data.get('phone')),
            'company': self._clean_nullable_text(data.get('company')),
            'requirement_summary': self._clean_nullable_text(data.get('requirement_summary')),
            'intent': self._clean_nullable_text(data.get('intent')),
            'notes': self._clean_nullable_text(data.get('notes')),
            'tags': self._normalize_tags(data.get('tags')),
        }

    def _clean_nullable_text(self, value) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _normalize_phone(self, phone) -> str | None:
        if phone is None:
            return None

        phone_text = str(phone).strip()
        if not phone_text:
            return None

        has_plus = phone_text.startswith('+')
        digits = re.sub(r'\D', '', phone_text)
        if not digits:
            return None
        return f'+{digits}' if has_plus else digits

    def _parse_json(self, payload, default):
        if not payload:
            return default
        if isinstance(payload, (dict, list)):
            return payload
        try:
            return json.loads(payload)
        except Exception:
            return default

    def _get_last_assistant_chain(self, query):
        if getattr(query, 'resp_message_chain', None):
            return query.resp_message_chain[-1]

        if getattr(query, 'resp_messages', None):
            last_message = query.resp_messages[-1]
            if hasattr(last_message, 'get_content_platform_message_chain'):
                try:
                    return last_message.get_content_platform_message_chain()
                except Exception:
                    return last_message
            return last_message

        return None

    def _serialize_message_content(self, message) -> str:
        if message is None:
            return ''

        try:
            if hasattr(message, 'model_dump'):
                return json.dumps(message.model_dump(), ensure_ascii=False, default=str)

            if isinstance(message, list):
                serialized = []
                for item in message:
                    if hasattr(item, 'model_dump'):
                        serialized.append(item.model_dump())
                    else:
                        serialized.append(item)
                return json.dumps(serialized, ensure_ascii=False, default=str)
        except Exception:
            pass

        return str(message)

    def _extract_message_text(self, message_content: str | None) -> str:
        if not message_content:
            return ''

        try:
            message_chain = json.loads(message_content)
        except Exception:
            return str(message_content)

        if not isinstance(message_chain, list):
            return str(message_content)

        parts = []
        for component in message_chain:
            if not isinstance(component, dict):
                continue

            component_type = component.get('type')
            if component_type == 'Plain':
                parts.append(component.get('text', ''))
            elif component_type == 'At':
                display = component.get('display') or component.get('target') or ''
                if display:
                    parts.append(f'@{display}')
            elif component_type == 'AtAll':
                parts.append('@All')
            elif component_type == 'Image':
                parts.append('[Image]')
            elif component_type == 'File':
                parts.append(f'[File: {component.get("name", "File")}]')
            elif component_type == 'Voice':
                parts.append('[Voice]')
            elif component_type == 'Quote':
                origin = component.get('origin', [])
                if isinstance(origin, list):
                    quoted = []
                    for item in origin:
                        if isinstance(item, dict) and item.get('type') == 'Plain':
                            quoted.append(item.get('text', ''))
                    if quoted:
                        parts.append('> ' + ''.join(quoted))
            else:
                if component_type:
                    parts.append(f'[{component_type}]')

        return ''.join(parts)

    def _build_session_id(self, query) -> str:
        return f'{query.launcher_type}_{query.launcher_id}'

    def _extract_sender_name(self, query) -> str | None:
        message_event = getattr(query, 'message_event', None)
        sender = getattr(message_event, 'sender', None)
        if sender is None:
            return None

        for attr in ['nickname', 'member_name', 'name']:
            value = getattr(sender, attr, None)
            if value:
                return str(value)

        return None

    def _unwrap_row(self, row):
        if isinstance(row, tuple):
            return row[0]
        if hasattr(row, '_mapping'):
            values = list(row._mapping.values())
            if len(values) == 1:
                return values[0]
        try:
            return row[0]
        except Exception:
            return row

    def _utcnow(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def _format_timestamp(self, value: datetime.datetime | None) -> str:
        if not value:
            return ''
        return value.strftime('%Y-%m-%d %H:%M:%S')

    def _build_xlsx_workbook(self, sheet_name: str, headers: list[str], rows: list[list]) -> bytes:
        worksheet_rows = [headers] + rows
        worksheet_xml = self._build_worksheet_xml(worksheet_rows)
        core_created = self._utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        workbook = io.BytesIO()
        with zipfile.ZipFile(workbook, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                '[Content_Types].xml',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/xl/workbook.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                    '<Override PartName="/xl/worksheets/sheet1.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    '<Override PartName="/xl/styles.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                    '<Override PartName="/docProps/core.xml" '
                    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                    '<Override PartName="/docProps/app.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                    '</Types>'
                ),
            )
            archive.writestr(
                '_rels/.rels',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                    'Target="xl/workbook.xml"/>'
                    '<Relationship Id="rId2" '
                    'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
                    'Target="docProps/core.xml"/>'
                    '<Relationship Id="rId3" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
                    'Target="docProps/app.xml"/>'
                    '</Relationships>'
                ),
            )
            archive.writestr(
                'docProps/app.xml',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
                    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
                    '<Application>LangBot</Application>'
                    '</Properties>'
                ),
            )
            archive.writestr(
                'docProps/core.xml',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:dcterms="http://purl.org/dc/terms/" '
                    'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
                    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                    '<dc:creator>LangBot</dc:creator>'
                    '<cp:lastModifiedBy>LangBot</cp:lastModifiedBy>'
                    f'<dcterms:created xsi:type="dcterms:W3CDTF">{core_created}</dcterms:created>'
                    f'<dcterms:modified xsi:type="dcterms:W3CDTF">{core_created}</dcterms:modified>'
                    '</cp:coreProperties>'
                ),
            )
            archive.writestr(
                'xl/workbook.xml',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    '<sheets>'
                    f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
                    '</sheets>'
                    '</workbook>'
                ),
            )
            archive.writestr(
                'xl/_rels/workbook.xml.rels',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    'Target="worksheets/sheet1.xml"/>'
                    '<Relationship Id="rId2" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                    'Target="styles.xml"/>'
                    '</Relationships>'
                ),
            )
            archive.writestr(
                'xl/styles.xml',
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
                    '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
                    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                    '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
                    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                    '</styleSheet>'
                ),
            )
            archive.writestr('xl/worksheets/sheet1.xml', worksheet_xml)

        return workbook.getvalue()

    def _build_worksheet_xml(self, rows: list[list]) -> str:
        xml_rows = []
        for row_index, row_values in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row_values, start=1):
                cell_ref = f'{self._excel_column_name(column_index)}{row_index}'
                cells.append(self._build_cell_xml(cell_ref, value))
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>'
            + ''.join(xml_rows)
            + '</sheetData>'
            '</worksheet>'
        )

    def _build_cell_xml(self, cell_ref: str, value) -> str:
        if value is None:
            return f'<c r="{cell_ref}" t="inlineStr"><is><t></t></is></c>'

        if isinstance(value, (int, float)):
            return f'<c r="{cell_ref}"><v>{value}</v></c>'

        text = escape(str(value))
        if text != text.strip() or '\n' in text:
            return (
                f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
            )

        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    def _excel_column_name(self, index: int) -> str:
        result = ''
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result
