"""Dify-on-WeChat (wework) bridge adapter.

LangBot runs the pipeline; a Windows-side bridge receives AI replies via HTTP
and forwards them to the WeChat Work client. Incoming messages are POSTed to
LangBot ingest API (see dow_relay HTTP routes).
"""

from __future__ import annotations

import asyncio
import typing

import httpx
import pydantic

import langbot_plugin.api.definition.abstract.platform.adapter as abstract_platform_adapter
import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message


class DowRelayAdapter(abstract_platform_adapter.AbstractMessagePlatformAdapter):
    """HTTP-outbound bridge; no inbound socket — ingest uses HTTP API."""

    listeners: dict[
        typing.Type[platform_events.Event],
        typing.Callable[[platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], None],
    ] = pydantic.Field(default_factory=dict, exclude=True)

    bridge_bot_uuid: str = pydantic.Field(default='', exclude=True)
    relay_http_client: httpx.AsyncClient | None = pydantic.Field(default=None, exclude=True)

    def set_bot_uuid(self, bot_uuid: str) -> None:
        self.bridge_bot_uuid = bot_uuid

    def _client(self) -> httpx.AsyncClient:
        if self.relay_http_client is None:
            timeout = float(self.config.get('http_timeout_seconds', 60))
            self.relay_http_client = httpx.AsyncClient(timeout=timeout)
        return self.relay_http_client

    def _send_url(self) -> str:
        base = (self.config.get('bridge_base_url') or '').rstrip('/')
        path = self.config.get('send_path', '/send')
        if not path.startswith('/'):
            path = '/' + path
        return f'{base}{path}' if base else ''

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {'Content-Type': 'application/json'}
        secret = self.config.get('bridge_secret')
        if secret:
            h['X-Bridge-Secret'] = str(secret)
        return h

    async def send_message(self, target_type: str, target_id: str, message: platform_message.MessageChain) -> dict:
        return await self._post_outbound(
            {
                'action': 'send',
                'chat_type': target_type,
                'target_id': str(target_id),
                'message_chain': [c.model_dump() for c in message],
            }
        )

    async def reply_message(
        self,
        message_source: platform_events.MessageEvent,
        message: platform_message.MessageChain,
        quote_origin: bool = False,
    ) -> dict:
        payload: dict[str, typing.Any] = {
            'action': 'reply',
            'quote_origin': quote_origin,
            'message_chain': [c.model_dump() for c in message],
        }
        if isinstance(message_source, platform_events.GroupMessage):
            payload['chat_type'] = 'group'
            payload['group_id'] = str(message_source.group.id)
            payload['sender_id'] = str(message_source.sender.id)
        elif isinstance(message_source, platform_events.FriendMessage):
            payload['chat_type'] = 'person'
            payload['sender_id'] = str(message_source.sender.id)
        else:
            payload['chat_type'] = 'unknown'
        return await self._post_outbound(payload)

    async def reply_message_chunk(
        self,
        message_source: platform_events.MessageEvent,
        bot_message: dict,
        message: platform_message.MessageChain,
        quote_origin: bool = False,
        is_final: bool = False,
    ) -> dict:
        payload: dict[str, typing.Any] = {
            'action': 'reply_chunk',
            'quote_origin': quote_origin,
            'is_final': is_final,
            'bot_message': bot_message,
            'message_chain': [c.model_dump() for c in message],
        }
        if isinstance(message_source, platform_events.GroupMessage):
            payload['chat_type'] = 'group'
            payload['group_id'] = str(message_source.group.id)
            payload['sender_id'] = str(message_source.sender.id)
        elif isinstance(message_source, platform_events.FriendMessage):
            payload['chat_type'] = 'person'
            payload['sender_id'] = str(message_source.sender.id)
        return await self._post_outbound(payload)

    async def _post_outbound(self, body: dict) -> dict:
        url = self._send_url()
        if not url:
            self.logger.error('dow-relay: bridge_base_url is not configured; cannot send')
            return {'ok': False, 'error': 'bridge_base_url missing'}
        body['bot_uuid'] = self.bridge_bot_uuid
        try:
            resp = await self._client().post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            return data if isinstance(data, dict) else {'data': data}
        except Exception as e:
            self.logger.error(f'dow-relay outbound failed: {e}')
            return {'ok': False, 'error': str(e)}

    def register_listener(
        self,
        event_type: typing.Type[platform_events.Event],
        func: typing.Callable[
            [platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], typing.Awaitable[None]
        ],
    ):
        self.listeners[event_type] = func

    def unregister_listener(
        self,
        event_type: typing.Type[platform_events.Event],
        func: typing.Callable[
            [platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], typing.Awaitable[None]
        ],
    ):
        self.listeners.pop(event_type, None)

    async def run_async(self):
        while True:
            await asyncio.sleep(3600)

    async def kill(self) -> bool:
        if self.relay_http_client:
            await self.relay_http_client.aclose()
            self.relay_http_client = None
        return True

    async def is_stream_output_supported(self) -> bool:
        return bool(self.config.get('stream_to_bridge', True))
