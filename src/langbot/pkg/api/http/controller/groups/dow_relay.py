from __future__ import annotations

import quart

from .. import group


@group.group_class('dow_relay', '/api/v1/dow-relay')
class DowRelayRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('/bots/<bot_uuid>/ingest', methods=['POST'], auth_type=group.AuthType.NONE)
        async def ingest(bot_uuid: str):
            secret = quart.request.headers.get('X-DOW-Relay-Secret', '')
            try:
                data = await quart.request.get_json() or {}
            except Exception:
                return self.http_status(400, -1, 'Invalid JSON body')
            try:
                result = await self.ap.dow_relay_service.ingest(bot_uuid, secret or None, data)
                return self.success(data=result)
            except PermissionError as e:
                return self.http_status(403, -1, str(e))
            except ValueError as e:
                return self.http_status(400, -1, str(e))
            except Exception as e:
                return self.http_status(500, -2, str(e))

        @self.route('/bots/<bot_uuid>/groups', methods=['GET'], auth_type=group.AuthType.NONE)
        async def list_groups(bot_uuid: str):
            secret = quart.request.headers.get('X-DOW-Relay-Secret', '')
            try:
                data = await self.ap.dow_relay_service.proxy_groups(bot_uuid, secret or None)
                return self.success(data=data)
            except PermissionError as e:
                return self.http_status(403, -1, str(e))
            except ValueError as e:
                return self.http_status(400, -1, str(e))
            except Exception as e:
                return self.http_status(500, -2, str(e))

        @self.route('/bots/<bot_uuid>/groups/<path:group_id>/members', methods=['GET'], auth_type=group.AuthType.NONE)
        async def list_members(bot_uuid: str, group_id: str):
            secret = quart.request.headers.get('X-DOW-Relay-Secret', '')
            try:
                data = await self.ap.dow_relay_service.proxy_group_members(bot_uuid, group_id, secret or None)
                return self.success(data=data)
            except PermissionError as e:
                return self.http_status(403, -1, str(e))
            except ValueError as e:
                return self.http_status(400, -1, str(e))
            except Exception as e:
                return self.http_status(500, -2, str(e))
