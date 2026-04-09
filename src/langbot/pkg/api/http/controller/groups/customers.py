from __future__ import annotations

import datetime

import quart

from .. import group


@group.group_class('customers', '/api/v1/customers')
class CustomersRouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        @self.route('', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_customers() -> str:
            keyword = quart.request.args.get('keyword')
            bot_ids = quart.request.args.getlist('botId')
            pipeline_ids = quart.request.args.getlist('pipelineId')
            limit = int(quart.request.args.get('limit', 50))
            offset = int(quart.request.args.get('offset', 0))

            customers, total = await self.ap.customer_service.get_customers(
                keyword=keyword,
                bot_ids=bot_ids if bot_ids else None,
                pipeline_ids=pipeline_ids if pipeline_ids else None,
                limit=limit,
                offset=offset,
            )

            return self.success(
                data={
                    'customers': customers,
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                }
            )

        @self.route('/<customer_id>', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_customer(customer_id: str) -> str:
            detail = await self.ap.customer_service.get_customer_detail(customer_id)
            if not detail.get('found'):
                return self.http_status(404, -1, f'Customer {customer_id} not found')

            return self.success(data=detail)

        @self.route('/<customer_id>/conversations', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def get_customer_conversations(customer_id: str) -> str:
            limit = int(quart.request.args.get('limit', 200))
            offset = int(quart.request.args.get('offset', 0))

            conversations, total = await self.ap.customer_service.get_customer_conversations(
                customer_id=customer_id,
                limit=limit,
                offset=offset,
            )

            return self.success(
                data={
                    'customer_id': customer_id,
                    'conversations': conversations,
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                }
            )

        @self.route('/export', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
        async def export_customers() -> tuple[quart.Response, int]:
            keyword = quart.request.args.get('keyword')
            bot_ids = quart.request.args.getlist('botId')
            pipeline_ids = quart.request.args.getlist('pipelineId')
            limit = int(quart.request.args.get('limit', 100000))

            payload = await self.ap.customer_service.export_customers(
                keyword=keyword,
                bot_ids=bot_ids if bot_ids else None,
                pipeline_ids=pipeline_ids if pipeline_ids else None,
                limit=limit,
            )

            response = await quart.make_response(payload)
            response.headers[
                'Content-Type'
            ] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = (
                f'attachment; filename="customers-{int(datetime.datetime.now().timestamp())}.xlsx"'
            )

            return response, 200
