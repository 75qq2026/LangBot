"""HTTP bridge for Dify-on-WeChat (WeCom): ingest + upstream proxy."""

from __future__ import annotations

import datetime

import langbot_plugin.api.entities.builtin.platform.entities as platform_entities
import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message
import langbot_plugin.api.entities.builtin.provider.session as provider_session
import httpx

from ....core import app


class DowRelayService:
    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    async def _get_runtime_bot(self, bot_uuid: str):
        return await self.ap.platform_mgr.get_bot_by_uuid(bot_uuid)

    def _adapter_config(self, runtime_bot) -> dict:
        cfg = runtime_bot.bot_entity.adapter_config
        return cfg if isinstance(cfg, dict) else {}

    def _verify_ingest_secret(self, runtime_bot, header_secret: str | None) -> bool:
        expected = self._adapter_config(runtime_bot).get('ingest_secret')
        if not expected:
            return False
        return header_secret == str(expected)

    async def ingest(
        self,
        bot_uuid: str,
        header_secret: str | None,
        payload: dict,
    ) -> dict:
        runtime_bot = await self._get_runtime_bot(bot_uuid)
        if not runtime_bot or not runtime_bot.enable:
            raise ValueError('Bot not found or disabled')
        if runtime_bot.bot_entity.adapter != 'dow-relay':
            raise ValueError('Bot is not a dow-relay bot')
        if not self._verify_ingest_secret(runtime_bot, header_secret):
            raise PermissionError('Invalid or missing ingest secret')

        chat_type = (payload.get('chat_type') or payload.get('chatType') or 'group').lower()
        message_chain_raw = payload.get('message_chain') or payload.get('messageChain')
        if message_chain_raw:
            chain = platform_message.MessageChain.model_validate(message_chain_raw)
        else:
            chain = self._payload_to_chain(payload)

        msg_id = payload.get('message_id', payload.get('messageId', -1))
        ts = payload.get('time') or payload.get('timestamp')
        if ts is not None:
            try:
                t = float(ts)
                msg_time = datetime.datetime.fromtimestamp(t)
            except (TypeError, ValueError, OSError):
                msg_time = datetime.datetime.now()
        else:
            msg_time = datetime.datetime.now()

        rest = list(chain)
        if rest and isinstance(rest[0], platform_message.Source):
            src = rest[0]
            rest = rest[1:]
        else:
            src = platform_message.Source(id=msg_id, time=msg_time)
        full_chain = platform_message.MessageChain([src] + rest)

        time_val: float | None = None
        if ts is not None:
            try:
                time_val = float(ts)
            except (TypeError, ValueError):
                time_val = None

        if chat_type == 'group':
            gid = str(payload.get('group_id') or payload.get('groupId') or '')
            gname = str(payload.get('group_name') or payload.get('groupName') or 'Group')
            sid = str(payload.get('sender_id') or payload.get('senderId') or '')
            sname = str(payload.get('sender_name') or payload.get('senderName') or sid)
            group = platform_entities.Group(
                id=gid,
                name=gname,
                permission=platform_entities.Permission.Member,
            )
            sender = platform_entities.GroupMember(
                id=sid,
                member_name=sname,
                permission=platform_entities.Permission.Member,
                group=group,
            )
            event = platform_events.GroupMessage(sender=sender, message_chain=full_chain, time=time_val)
        else:
            uid = str(payload.get('sender_id') or payload.get('senderId') or '')
            uname = str(payload.get('sender_name') or payload.get('senderName') or uid)
            friend = platform_entities.Friend(id=uid, nickname=uname, remark=None)
            event = platform_events.FriendMessage(sender=friend, message_chain=full_chain, time=time_val)

        launcher_id = (
            str(payload.get('group_id') or payload.get('groupId') or '')
            if chat_type == 'group'
            else str(payload.get('sender_id') or payload.get('senderId') or '')
        )
        await self.ap.msg_aggregator.add_message(
            bot_uuid=bot_uuid,
            launcher_type=provider_session.LauncherTypes.GROUP
            if chat_type == 'group'
            else provider_session.LauncherTypes.PERSON,
            launcher_id=launcher_id,
            sender_id=str(payload.get('sender_id') or payload.get('senderId') or ''),
            message_event=event,
            message_chain=full_chain,
            adapter=runtime_bot.adapter,
            pipeline_uuid=runtime_bot.bot_entity.use_pipeline_uuid,
        )
        return {'accepted': True}

    def _payload_to_chain(self, payload: dict) -> platform_message.MessageChain:
        mtype = (payload.get('message_type') or payload.get('messageType') or 'text').lower()
        parts: list = []

        if mtype in ('text', 'plain'):
            text = payload.get('text') or payload.get('content') or ''
            parts.append(platform_message.Plain(text=str(text)))
        elif mtype == 'image':
            url = payload.get('url') or ''
            b64 = payload.get('base64') or payload.get('base_64')
            if b64:
                parts.append(platform_message.Image(base64=str(b64)))
            else:
                parts.append(platform_message.Image(url=str(url)))
        elif mtype in ('file', 'document'):
            parts.append(
                platform_message.File(
                    name=str(payload.get('name') or 'file'),
                    url=str(payload.get('url') or ''),
                    size=int(payload.get('size') or 0),
                )
            )
        elif mtype in ('gif', 'gif_image'):
            url = payload.get('url') or ''
            b64 = payload.get('base64') or ''
            if b64:
                parts.append(platform_message.Image(base64=str(b64)))
            else:
                parts.append(platform_message.Image(url=str(url)))
        elif mtype in ('emoji', 'sticker', 'wechat_emoji'):
            parts.append(
                platform_message.WeChatEmoji(
                    emoji_md5=str(payload.get('emoji_md5') or payload.get('emojiMd5') or ''),
                    emoji_size=int(payload.get('emoji_size') or payload.get('emojiSize') or 0),
                )
            )
        else:
            parts.append(platform_message.Plain(text=str(payload.get('text') or '')))

        return platform_message.MessageChain(parts)

    async def proxy_groups(self, bot_uuid: str, header_secret: str | None) -> dict | list:
        runtime_bot = await self._get_runtime_bot(bot_uuid)
        if not runtime_bot or not runtime_bot.enable:
            raise ValueError('Bot not found or disabled')
        if not self._verify_ingest_secret(runtime_bot, header_secret):
            raise PermissionError('Invalid or missing ingest secret')
        cfg = self._adapter_config(runtime_bot)
        base = (cfg.get('upstream_base_url') or '').rstrip('/')
        if not base:
            raise ValueError('upstream_base_url is not configured on this bot')
        path = cfg.get('groups_path') or '/groups'
        if not path.startswith('/'):
            path = '/' + path
        url = f'{base}{path}'
        headers = self._upstream_headers(cfg)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()

    async def proxy_group_members(self, bot_uuid: str, group_id: str, header_secret: str | None) -> dict | list:
        runtime_bot = await self._get_runtime_bot(bot_uuid)
        if not runtime_bot or not runtime_bot.enable:
            raise ValueError('Bot not found or disabled')
        if not self._verify_ingest_secret(runtime_bot, header_secret):
            raise PermissionError('Invalid or missing ingest secret')
        cfg = self._adapter_config(runtime_bot)
        base = (cfg.get('upstream_base_url') or '').rstrip('/')
        if not base:
            raise ValueError('upstream_base_url is not configured on this bot')
        tmpl = cfg.get('members_path_template') or '/groups/{group_id}/members'
        path = tmpl.replace('{group_id}', group_id)
        if not path.startswith('/'):
            path = '/' + path
        url = f'{base}{path}'
        headers = self._upstream_headers(cfg)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()

    def _upstream_headers(self, cfg: dict) -> dict[str, str]:
        h: dict[str, str] = {}
        secret = cfg.get('upstream_secret') or cfg.get('bridge_secret')
        if secret:
            h['X-Bridge-Secret'] = str(secret)
        return h
