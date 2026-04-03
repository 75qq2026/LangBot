# 企业微信外部群机器人实施方案

> 项目分支：`cursor/dify-enterprise-wechat-bot-exclusion-bc1a`  
> 创建时间：2026-04-03  
> 排除方案：Dify-Enterprise-WeChat-bot（收费且不支持独立部署）

---

## 一、需求概述

### 核心场景
微信群（企业内部 + 外部人员）机器人自动回答客户问题，无法回答时转人工，通过微信或企业微信私聊通知。

### 功能要求
1. **多端支持**：企业微信AI机器人、企业微信个人端、微信个人号均可使用
2. **知识库对接**：调用 Dify 知识库
3. **自定义工作流**：特殊工作流可代码单独处理
4. **权限管理**：多群管理、SaaS 模式、不同套餐设置机器人权限
5. **外部系统对接**：对接飞书、钉钉工作流及多维表格

---

## 二、LangBot 当前功能分析

### 已实现的企业微信支持

| 适配器文件 | 官方支持 | 适用场景 | 外部群支持 | 群聊消息 |
|-----------|---------|---------|-----------|---------|
| `wecom.py` | ✅ 官方API | 企业内部应用 | ❌ 仅内部 | ❌ 仅私聊 |
| `wecombot.py` | ✅ 官方WebSocket | 智能机器人 | ❌ 仅内部 | ✅ 支持（需@机器人） |
| `wecomcs.py` | ✅ 官方API | 客服场景 | ✅ 外部客户 | ❌ 仅一对一 |
| `openclaw_weixin.py` | ❌ 非官方协议 | 个人微信 | ✅ 任意群 | ✅ 支持 |

### 关键发现

**企业微信官方API支持客户群（外部群）管理**

根据企业微信开发者文档，官方提供了完整的客户群API：

```python
# 核心API接口
GET  /cgi-bin/externalcontact/groupchat/list      # 获取客户群列表
GET  /cgi-bin/externalcontact/groupchat/get       # 获取客户群详情
POST /cgi-bin/appchat/send                        # 发送群消息
```

**支持的功能**：
- ✅ 获取客户群列表及详情
- ✅ 监听成员入群/退群事件
- ✅ 获取群成员信息
- ✅ 通过应用发送群消息（需要创建群聊会话）
- ❌ 直接监听群消息（官方API不支持）

---

## 三、技术方案对比

### 方案A：官方客户群API（推荐 ⭐⭐⭐⭐⭐）

**技术栈**：
```
LangBot 扩展
  ├── wecom_external_contact.py (新增适配器)
  ├── 官方客户联系API
  └── 客户群管理API
```

**优势**：
- ✅ 官方支持，完全合规，无封号风险
- ✅ 支持外部群聊管理
- ✅ 可复用 LangBot 现有架构
- ✅ 支持群事件回调

**局限**：
- ⚠️ **无法直接监听群消息**，需要通过以下方式触发：
  1. 群成员主动@企业成员
  2. 企业成员在群内使用应用
  3. 通过群聊会话主动推送消息

**适用场景**：主动推送型机器人、定时通知、事件驱动型交互

---

### 方案B：智能机器人WebSocket长连接（推荐 ⭐⭐⭐⭐）

**技术栈**：
```
LangBot 扩展
  ├── wecombot.py (已有，需扩展)
  ├── WebSocket 长连接 (wss://openws.work.weixin.qq.com)
  └── 企业微信智能机器人
```

**核心优势**：
- ✅ 官方支持，无封号风险
- ✅ 无需公网IP、域名、SSL证书
- ✅ 支持群聊（通过@机器人触发）
- ✅ 实时消息推送，无5秒超时限制
- ✅ 支持流式回复、模板卡片
- ✅ LangBot 已实现 `wecombot.py`

**经过调研确认**：
- ✅ **支持内部群聊**（企业内部成员群）
- ⚠️ **不支持客户群**（包含外部联系人的群）
  - 官方文档明确：智能机器人仅支持内部群聊
  - 客户群需使用客户联系API

**触发方式**：
```
用户在群内@机器人 → WebSocket推送消息 → LangBot处理 → 回复群聊
```

**限制**：
- 主动推送：30条/分钟，1000条/小时
- 仅支持企业内部群，不支持包含外部联系人的群

---

### 方案C：OpenClaw 微信个人号（不推荐 ⭐⭐）

**技术栈**：
```
LangBot (已有 openclaw_weixin.py)
  ↓
OpenClaw 微信服务
  ↓
微信个人号（协议/Hook）
```

**优势**：
- ✅ 支持任意群聊（内部+外部）
- ✅ LangBot 已实现适配器

**劣势**：
- ❌ 非官方协议，高封号风险
- ❌ 不适合生产环境
- ❌ 协议不稳定

**适用场景**：仅用于内部测试或小范围验证

---

### 方案D：混合方案（推荐 ⭐⭐⭐⭐⭐）

**组合使用官方能力**：

```
┌─────────────────────────────────────────────────┐
│  企业内部群（仅内部成员）                        │
│  使用：智能机器人 WebSocket (wecombot.py)        │
│  特点：@触发，实时响应，流式回复                  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  客户群（包含外部联系人）                        │
│  使用：客户联系API (wecom_external_contact.py)   │
│  特点：事件驱动，主动推送，客户管理              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  一对一客服                                      │
│  使用：企业微信客服 (wecomcs.py) [已实现]        │
│  特点：官方客服API，支持人工接管                 │
└─────────────────────────────────────────────────┘
```

---

## 四、推荐实施方案

### 核心架构

```python
# 新增适配器：客户群管理
src/langbot/pkg/platform/sources/wecom_external_group.py

# 扩展现有适配器
src/langbot/pkg/platform/sources/wecombot.py  # 优化内部群支持

# 新增 SDK 库
src/langbot/libs/wecom_external_contact_api/
  ├── api.py                    # 客户联系 API 客户端
  ├── groupchat.py              # 客户群管理
  └── event.py                  # 事件处理
```

### 客户群API集成方案

#### 1. 创建客户群管理SDK

```python
# src/langbot/libs/wecom_external_contact_api/api.py

import httpx
from typing import List, Dict, Any

class WecomExternalContactClient:
    """企业微信客户联系API客户端"""
    
    def __init__(self, corpid: str, secret: str, logger=None):
        self.corpid = corpid
        self.secret = secret
        self.access_token = ''
        self.base_url = 'https://qyapi.weixin.qq.com/cgi-bin'
        self.logger = logger
    
    async def get_access_token(self) -> str:
        """获取access_token"""
        url = f'{self.base_url}/gettoken'
        params = {'corpid': self.corpid, 'corpsecret': self.secret}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if 'access_token' in data:
                self.access_token = data['access_token']
                return self.access_token
            raise Exception(f'获取access_token失败: {data}')
    
    async def get_groupchat_list(
        self, 
        status_filter: int = 0, 
        owner_filter: Dict = None,
        cursor: str = '',
        limit: int = 100
    ) -> Dict[str, Any]:
        """获取客户群列表
        
        Args:
            status_filter: 群状态过滤 0-所有 1-跟进中 2-已离职
            owner_filter: 群主过滤 {"userid_list": ["user1", "user2"]}
            cursor: 分页游标
            limit: 每页数量，最大1000
        
        Returns:
            {
                "group_chat_list": [
                    {
                        "chat_id": "wrOgQhDgAAcwMTB7YmDkbeBsgT_X",
                        "status": 0
                    }
                ],
                "next_cursor": "xxx"
            }
        """
        if not self.access_token:
            await self.get_access_token()
        
        url = f'{self.base_url}/externalcontact/groupchat/list?access_token={self.access_token}'
        
        payload = {
            'status_filter': status_filter,
            'limit': limit
        }
        
        if owner_filter:
            payload['owner_filter'] = owner_filter
        if cursor:
            payload['cursor'] = cursor
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            
            if data.get('errcode') in [40014, 42001]:
                await self.get_access_token()
                return await self.get_groupchat_list(status_filter, owner_filter, cursor, limit)
            
            if data.get('errcode', 0) != 0:
                raise Exception(f'获取客户群列表失败: {data}')
            
            return data
    
    async def get_groupchat_detail(self, chat_id: str, need_name: int = 0) -> Dict[str, Any]:
        """获取客户群详情
        
        Args:
            chat_id: 客户群ID
            need_name: 是否需要返回群成员名称 0-否 1-是
        
        Returns:
            {
                "group_chat": {
                    "chat_id": "xxx",
                    "name": "客户群名称",
                    "owner": "zhangsan",
                    "create_time": 1234567890,
                    "notice": "群公告",
                    "member_list": [
                        {
                            "userid": "zhangsan",
                            "type": 1,  # 1-企业成员 2-外部联系人
                            "join_time": 1234567890,
                            "join_scene": 1  # 1-直接邀请 2-扫码
                        }
                    ],
                    "admin_list": [
                        {"userid": "lisi"}
                    ]
                }
            }
        """
        if not self.access_token:
            await self.get_access_token()
        
        url = f'{self.base_url}/externalcontact/groupchat/get?access_token={self.access_token}'
        
        payload = {
            'chat_id': chat_id,
            'need_name': need_name
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            
            if data.get('errcode') in [40014, 42001]:
                await self.get_access_token()
                return await self.get_groupchat_detail(chat_id, need_name)
            
            if data.get('errcode', 0) != 0:
                raise Exception(f'获取客户群详情失败: {data}')
            
            return data
    
    async def send_appchat_message(
        self, 
        chatid: str, 
        msgtype: str, 
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """发送应用消息到群聊会话
        
        注意：需要先创建群聊会话（appchat），不是客户群（externalcontact groupchat）
        
        Args:
            chatid: 群聊会话ID
            msgtype: 消息类型 text/image/voice/file等
            content: 消息内容
        
        Returns:
            {"errcode": 0, "errmsg": "ok"}
        """
        if not self.access_token:
            await self.get_access_token()
        
        url = f'{self.base_url}/appchat/send?access_token={self.access_token}'
        
        payload = {
            'chatid': chatid,
            'msgtype': msgtype
        }
        payload.update(content)
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            
            if data.get('errcode') in [40014, 42001]:
                await self.get_access_token()
                return await self.send_appchat_message(chatid, msgtype, content)
            
            if data.get('errcode', 0) != 0:
                raise Exception(f'发送群消息失败: {data}')
            
            return data
```

#### 2. 创建适配器

```python
# src/langbot/pkg/platform/sources/wecom_external_group.py

from __future__ import annotations
import typing
import asyncio

from langbot.libs.wecom_external_contact_api.api import WecomExternalContactClient
import langbot_plugin.api.definition.abstract.platform.adapter as abstract_platform_adapter
import langbot_plugin.api.entities.builtin.platform.message as platform_message
import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.entities as platform_entities


class WecomExternalGroupAdapter(abstract_platform_adapter.AbstractMessagePlatformAdapter):
    """企业微信客户群适配器
    
    功能限制：
    - 无法直接监听群消息（官方API不支持）
    - 仅支持主动推送消息到群
    - 可监听群成员变更事件
    """
    
    def __init__(self, config: dict, logger):
        required_keys = ['corpid', 'secret']
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise Exception(f'企业微信客户群缺少配置项: {missing_keys}')
        
        bot = WecomExternalContactClient(
            corpid=config['corpid'],
            secret=config['secret'],
            logger=logger
        )
        
        super().__init__(
            config=config,
            logger=logger,
            bot=bot,
            bot_account_id=config['corpid']
        )
        
        self.poll_interval = config.get('poll_interval', 60)  # 轮询间隔（秒）
        self.monitored_groups = config.get('monitored_groups', [])  # 要监控的群chat_id列表
    
    async def send_message(
        self, 
        target_type: str, 
        target_id: str, 
        message: platform_message.MessageChain
    ):
        """发送消息到群聊
        
        Args:
            target_type: 'group'
            target_id: 群聊会话ID（appchat的chatid，非客户群chat_id）
            message: 消息链
        """
        if target_type != 'group':
            raise ValueError('仅支持发送到群聊')
        
        # 转换消息格式
        for msg in message:
            if isinstance(msg, platform_message.Plain):
                await self.bot.send_appchat_message(
                    chatid=target_id,
                    msgtype='text',
                    content={'text': {'content': msg.text}}
                )
    
    async def reply_message(
        self,
        message_source: platform_events.MessageEvent,
        message: platform_message.MessageChain,
        quote_origin: bool = False
    ):
        """回复消息（客户群场景下不适用，因为无法监听群消息）"""
        pass
    
    def register_listener(
        self,
        event_type: typing.Type[platform_events.Event],
        callback: typing.Callable
    ):
        """注册事件监听器（客户群API不支持实时回调，需要轮询）"""
        pass
    
    async def run_async(self):
        """保持运行"""
        async def keep_alive():
            while True:
                await asyncio.sleep(1)
        await keep_alive()
    
    async def kill(self) -> bool:
        return False
    
    async def is_muted(self, group_id: int) -> bool:
        return False
```

---

### 智能机器人WebSocket扩展方案

#### 扩展现有 wecombot.py

```python
# src/langbot/pkg/platform/sources/wecombot.py

# 在现有基础上增加以下功能：

class WecomBotAdapter(abstract_platform_adapter.AbstractMessagePlatformAdapter):
    """企业微信智能机器人适配器（WebSocket长连接）
    
    支持场景：
    - ✅ 企业内部群聊（@机器人触发）
    - ✅ 单聊
    - ❌ 客户群（包含外部联系人）- 官方限制
    """
    
    def __init__(self, config: dict, logger):
        # 现有代码...
        
        # 新增配置：群聊支持
        self.enable_group_chat = config.get('enable_group_chat', True)
        self.require_at = config.get('require_at', True)  # 是否需要@机器人
    
    async def handle_group_message(self, event):
        """处理群聊消息
        
        事件格式：
        {
            "msgtype": "text",
            "chatid": "群聊ID",
            "userid": "发送者ID",
            "content": "@机器人 你好",
            "msgid": "xxx"
        }
        """
        # 检查是否@机器人
        if self.require_at:
            if not self._is_at_bot(event['content']):
                return
        
        # 转换为 GroupMessage 事件
        group = platform_entities.Group(
            id=event['chatid'],
            name='',  # 需要额外接口获取群名
            permission=platform_entities.Permission.Member
        )
        
        sender = platform_entities.Member(
            id=event['userid'],
            member_name='',  # 需要额外接口获取用户名
            permission=platform_entities.Permission.Member,
            group=group
        )
        
        message_chain = await self._parse_message(event)
        
        group_msg = platform_events.GroupMessage(
            sender=sender,
            message_chain=message_chain,
            time=event.get('timestamp', 0),
            source_platform_object=event
        )
        
        # 触发回调
        for callback in self._group_message_callbacks:
            await callback(group_msg, self)
    
    def _is_at_bot(self, content: str) -> bool:
        """检查消息是否@机器人"""
        # 企业微信@格式：@机器人名称 消息内容
        # 需要根据实际机器人名称判断
        return content.startswith('@')
```

---

## 五、人工转接功能设计

### 架构方案

```python
# 新增 Pipeline Stage
src/langbot/pkg/pipeline/stages/human_transfer.py

class HumanTransferStage(stage.PipelineStage):
    """人工转接检测与处理阶段
    
    功能：
    1. 检测AI无法回答的情况
    2. 通知人工客服
    3. 标记会话状态
    4. 创建工单（可选）
    """
    
    async def initialize(self, pipeline_config: dict):
        self.config = pipeline_config.get('human-transfer', {})
        
        # 检测配置
        self.confidence_threshold = self.config.get('confidence-threshold', 0.6)
        self.trigger_keywords = self.config.get('trigger-keywords', [
            '转人工', '人工客服', '联系客服', '找客服'
        ])
        self.reject_keywords = self.config.get('reject-keywords', [
            '抱歉', '不知道', '无法回答', '不清楚'
        ])
        
        # 通知配置
        self.notification_platform = self.config.get('notification-platform', 'wecom')
        self.agent_user_ids = self.config.get('agent-user-ids', [])  # 客服人员列表
        
        # 工单配置（可选）
        self.enable_ticket = self.config.get('enable-ticket', False)
        self.ticket_api_url = self.config.get('ticket-api-url', '')
    
    async def process(
        self,
        query: pipeline_query.Query,
        stage_inst_name: str
    ) -> entities.StageProcessResult:
        """处理流程"""
        
        # 1. 检测是否需要转人工
        need_transfer = await self._should_transfer(query)
        
        if not need_transfer:
            return entities.StageProcessResult(
                result_type=entities.ResultType.CONTINUE,
                new_query=query
            )
        
        # 2. 通知人工客服
        await self._notify_agents(query)
        
        # 3. 标记会话状态
        await self._mark_session_manual(query)
        
        # 4. 创建工单（可选）
        if self.enable_ticket:
            await self._create_ticket(query)
        
        # 5. 回复用户
        transfer_message = self.config.get(
            'transfer-message',
            '已为您转接人工客服，请稍候...'
        )
        
        query.resp_messages = [
            platform_message.MessageChain([
                platform_message.Plain(text=transfer_message)
            ])
        ]
        
        return entities.StageProcessResult(
            result_type=entities.ResultType.INTERRUPT,
            new_query=query,
            console_notice='Transferred to human agent'
        )
    
    async def _should_transfer(self, query: pipeline_query.Query) -> bool:
        """判断是否需要转人工
        
        检测条件：
        1. 用户消息包含触发关键词
        2. AI回复包含拒绝关键词
        3. AI置信度低于阈值
        """
        user_message = str(query.user_message.content)
        
        # 检测用户触发关键词
        for keyword in self.trigger_keywords:
            if keyword in user_message:
                return True
        
        # 检测AI回复质量
        if hasattr(query, 'resp_messages') and query.resp_messages:
            ai_response = str(query.resp_messages[0])
            
            # 检测拒绝关键词
            for keyword in self.reject_keywords:
                if keyword in ai_response:
                    return True
        
        # 检测置信度（如果有）
        if hasattr(query, 'ai_confidence'):
            if query.ai_confidence < self.confidence_threshold:
                return True
        
        return False
    
    async def _notify_agents(self, query: pipeline_query.Query):
        """通知人工客服"""
        
        notification_text = f"""
🔔 新人工转接请求

客户信息：
- ID: {query.sender_id}
- 平台: {query.launcher_type.value}
- 来源: {query.launcher_id}

问题内容：
{query.user_message.content}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

请及时处理！
        """
        
        # 通过企业微信发送通知
        if self.notification_platform == 'wecom':
            for agent_id in self.agent_user_ids:
                await self.ap.platform_mgr.send_message(
                    platform='wecom',
                    target_type='person',
                    target_id=agent_id,
                    message=platform_message.MessageChain([
                        platform_message.Plain(text=notification_text)
                    ])
                )
    
    async def _mark_session_manual(self, query: pipeline_query.Query):
        """标记会话进入人工模式"""
        # 在数据库中记录会话状态
        # 可使用 Redis 或数据库
        pass
    
    async def _create_ticket(self, query: pipeline_query.Query):
        """创建工单（可选，对接芋道框架或其他工单系统）"""
        if not self.ticket_api_url:
            return
        
        ticket_data = {
            'customer_id': query.sender_id,
            'platform': query.launcher_type.value,
            'question': str(query.user_message.content),
            'created_at': datetime.now().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(self.ticket_api_url, json=ticket_data)
```

### Pipeline 配置示例

```yaml
# 在 LangBot 管理后台配置流水线

pipeline:
  stages:
    - name: bansess_check
      type: BanSessionCheckStage
    
    - name: ai_process
      type: AIProcessStage  # Dify 知识库查询
    
    - name: human_transfer  # 新增
      type: HumanTransferStage
      config:
        confidence-threshold: 0.6
        trigger-keywords:
          - "转人工"
          - "人工客服"
          - "找客服"
        reject-keywords:
          - "抱歉"
          - "不知道"
          - "无法回答"
        notification-platform: wecom
        agent-user-ids:
          - "zhangsan@company.com"
          - "lisi@company.com"
        transfer-message: "已为您转接人工客服，客服将尽快与您联系。"
        enable-ticket: true
        ticket-api-url: "http://yudao-gateway/api/ticket/create"
```

---

## 六、完整技术栈总结

### 推荐方案：混合架构

```
┌──────────────────────────────────────────────────────┐
│  前端：企业微信个人端 / 微信                          │
└───────────────┬──────────────────────────────────────┘
                │
    ┌───────────┴──────────┬──────────────┐
    │                      │              │
┌───▼────────┐  ┌──────────▼────┐  ┌─────▼────────┐
│ 内部群聊    │  │  客户群       │  │ 一对一客服   │
│ @机器人    │  │  事件驱动     │  │ 人工接管     │
│ wecombot   │  │  external_grp │  │ wecomcs      │
│ (已实现)   │  │  (待开发)     │  │ (已实现)     │
└───┬────────┘  └──────────┬────┘  └─────┬────────┘
    │                      │              │
    └───────────┬──────────┴──────────────┘
                │
        ┌───────▼────────┐
        │  LangBot 核心   │
        │  - Pipeline    │
        │  - Dify集成    │
        │  - 人工转接    │
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │  芋道框架(可选) │
        │  - 租户管理     │
        │  - 套餐系统     │
        │  - 工单系统     │
        └────────────────┘
```

### 开发工作量评估

| 模块 | 工作内容 | 复杂度 | 预计工作量 |
|------|---------|-------|----------|
| 客户群SDK | 实现客户联系API封装 | 中 | 2-3天 |
| 客户群适配器 | 创建 wecom_external_group.py | 中 | 2天 |
| 智能机器人扩展 | 完善 wecombot.py 群聊功能 | 低 | 1天 |
| 人工转接Stage | 实现检测与通知逻辑 | 中 | 3天 |
| 测试与调试 | 功能测试、联调 | 中 | 3-4天 |
| **总计** | | | **11-13天** |

---

## 七、实施步骤

### 阶段一：核心功能开发（优先级：高）

1. **创建客户群API SDK**（2-3天）
   - [x] 调研官方文档
   - [ ] 实现 `WecomExternalContactClient`
   - [ ] 单元测试

2. **创建客户群适配器**（2天）
   - [ ] 实现 `WecomExternalGroupAdapter`
   - [ ] 注册到平台管理器
   - [ ] 配置Web管理界面

3. **扩展智能机器人**（1天）
   - [ ] 完善 `wecombot.py` 群聊处理
   - [ ] 支持@机器人触发
   - [ ] 测试内部群聊功能

4. **实现人工转接**（3天）
   - [ ] 创建 `HumanTransferStage`
   - [ ] 实现检测逻辑
   - [ ] 实现通知逻辑
   - [ ] 集成到 Pipeline

5. **集成测试**（3-4天）
   - [ ] 创建测试企业微信应用
   - [ ] 测试内部群场景
   - [ ] 测试客户群场景（如果官方支持）
   - [ ] 测试人工转接流程

### 阶段二：SaaS 架构改造（优先级：中）

1. **多租户管理**
   - [ ] 数据库模型扩展（添加 tenant_id）
   - [ ] 租户认证中间件
   - [ ] 租户隔离逻辑

2. **套餐系统**
   - [ ] 套餐配置模型
   - [ ] 配额限制中间件
   - [ ] 计费接口对接

3. **芋道框架对接**（可选）
   - [ ] 租户API对接
   - [ ] 工单系统对接
   - [ ] 统一管理后台

### 阶段三：外部系统对接（优先级：低）

1. **飞书多维表格**
   - [ ] 调研飞书API
   - [ ] 实现表格操作SDK
   - [ ] 集成到工作流

2. **钉钉工作流**
   - [ ] 调研钉钉API
   - [ ] 实现工作流触发
   - [ ] 审批流程集成

---

## 八、关键风险与限制

### 官方API限制

**客户群API的重要限制**：
- ❌ **无法直接监听群消息**（官方API不支持）
- ✅ 仅支持获取群信息、成员列表、事件回调
- ✅ 可通过应用消息推送到群（需创建群聊会话）

**解决方案**：
1. **被动触发**：通过企业成员在群内使用应用触发
2. **主动推送**：定时推送、事件驱动推送
3. **内部群方案**：改用智能机器人WebSocket（支持@触发）

### 智能机器人限制

- ❌ **仅支持内部群**（不包含外部联系人）
- ✅ 支持@触发、实时响应
- ✅ 无需公网IP

**建议**：
- 企业内部群使用智能机器人
- 包含外部联系人的群使用其他方案

---

## 九、替代方案（如官方API无法满足）

### 方案1：企业微信侧边栏应用

通过侧边栏应用，在群聊中提供机器人入口：
```
用户在群聊打开侧边栏 → 选择AI助手 → 输入问题 → 获得回答
```

**优势**：
- ✅ 官方支持
- ✅ 支持客户群
- ✅ 良好的用户体验

**劣势**：
- ❌ 需要额外操作步骤
- ❌ 非群内直接对话

### 方案2：快捷回复插件

开发企业微信快捷回复插件：
```
用户在群内@企业成员 → 成员使用快捷回复插件 → 调用AI生成回复
```

**优势**：
- ✅ 支持客户群
- ✅ 辅助人工客服

**劣势**：
- ❌ 非完全自动化

---

## 十、总结

### 推荐实施路径

**第一阶段**（立即开始）：
1. ✅ 使用**智能机器人WebSocket**（`wecombot.py`）处理企业内部群
   - 优势：已实现、@触发、实时响应
   - 适用：内部沟通、团队协作

2. ✅ 开发**人工转接功能**（`HumanTransferStage`）
   - 优先级最高，满足核心需求
   - 通过企业微信通知客服

3. ✅ 使用**企业微信客服**（`wecomcs.py`）处理一对一场景
   - 已实现、官方支持人工接管

**第二阶段**（评估后决定）：
1. ⚠️ 评估是否真的需要在客户群内自动回复
   - 如果客户群主要用于通知、主动推送 → 使用客户群API
   - 如果需要实时对话 → 考虑侧边栏应用或人工客服

2. 🔍 根据实际业务场景选择技术方案：
   - **场景A**：内部群聊 → 智能机器人WebSocket ⭐⭐⭐⭐⭐
   - **场景B**：客户群通知 → 客户群API ⭐⭐⭐⭐
   - **场景C**：一对一客服 → 企业微信客服 ⭐⭐⭐⭐⭐

### 不推荐的方案

- ❌ Dify-Enterprise-WeChat-bot（收费且不支持独立部署）
- ❌ 微信个人号Hook方案（高封号风险，仅测试用）

---

## 附录

### 参考资料

1. [企业微信开发者中心 - 客户群API](https://developer.work.weixin.qq.com/document/path/92120)
2. [企业微信开发者中心 - 智能机器人](https://developer.work.weixin.qq.com/document/path/101463)
3. [wecom-aibot-sdk GitHub](https://github.com/WecomTeam/wecom-aibot-python-sdk)

### 配置示例

```yaml
# LangBot 企业微信配置示例

bots:
  - name: "内部群AI助手"
    platform: wecombot  # 智能机器人WebSocket
    config:
      corpid: "ww1234567890"
      secret: "xxx"
      bot_id: "xxx"
      enable_group_chat: true
      require_at: true
  
  - name: "客户服务助手"
    platform: wecomcs  # 企业微信客服
    config:
      corpid: "ww1234567890"
      secret: "xxx"
      token: "xxx"
      EncodingAESKey: "xxx"

pipelines:
  - name: "智能客服流水线"
    stages:
      - type: BanSessionCheckStage
      - type: DifyAIStage
        config:
          api_url: "https://api.dify.ai"
          api_key: "xxx"
      - type: HumanTransferStage
        config:
          trigger-keywords: ["转人工", "人工客服"]
          agent-user-ids: ["zhangsan", "lisi"]
```

---

**文档版本**：v1.0  
**最后更新**：2026-04-03  
**维护者**：LangBot 开发团队
