# LangBot AI 客服平台 — 部署与配置指南

> 面向实施与运维人员的完整部署手册

---

## 目录

1. [系统架构概览](#1-系统架构概览)
2. [环境要求](#2-环境要求)
3. [部署步骤](#3-部署步骤)
4. [三种企微 AI 客服对比](#4-三种企微-ai-客服能力与限制对比)
5. [各通道详细配置指南](#5-各通道详细配置指南)
6. [AI 模型配置](#6-ai-模型配置)
7. [管道（Pipeline）配置](#7-管道pipeline配置)
8. [常见问题排查](#8-常见问题排查)
9. [运维手册](#9-运维手册)

---

## 1. 系统架构概览

```
                     ┌─────────────────────────┐
                     │   LangBot Web 管理后台    │
                     │   (Next.js, 端口 3000)   │
                     └──────────┬──────────────┘
                                │
                     ┌──────────▼──────────────┐
                     │   LangBot 后端服务        │
                     │   (Quart/Python, 端口5300)│
                     ├──────────────────────────┤
                     │  ┌─────┐ ┌──────┐       │
                     │  │SQLite│ │ChromaDB│     │ ← 数据存储
                     │  └─────┘ └──────┘       │
                     ├──────────────────────────┤
                     │  ┌────────────────────┐  │
                     │  │   Pipeline 引擎     │  │ ← AI 处理
                     │  │  (LLM + RAG + MCP) │  │
                     │  └────────────────────┘  │
                     ├──────────────────────────┤
                     │  消息平台适配器             │
                     │  ┌────────┐ ┌────────┐  │
                     │  │wecombot│ │wecomcs │  │
                     │  │(WS长连)│ │(Webhook)│  │
                     │  └────┬───┘ └────┬───┘  │
                     └───────┼──────────┼──────┘
                             │          │
              ┌──────────────▼┐   ┌─────▼────────────┐
              │企微智能机器人   │   │  公网回调地址       │
              │(WebSocket直连) │   │(Cloudflare/Nginx) │
              │无需公网IP      │   │需要公网IP/域名     │
              └───────────────┘   └──────────────────┘
```

---

## 2. 环境要求

### 2.1 服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB (含知识库) |
| 系统 | Ubuntu 20.04+ / CentOS 8+ | Ubuntu 22.04 LTS |
| Python | 3.11+ | 3.12 |
| Node.js | 18+ | 22 LTS |

### 2.2 网络要求

| 通道类型 | 公网 IP | 域名 | HTTPS | 备注 |
|---------|---------|------|-------|------|
| 企微智能机器人 (wecombot) | ❌ 不需要 | ❌ 不需要 | ❌ 不需要 | WebSocket 主动外连 |
| 微信客服 (wecomcs) | ✅ 需要 | ✅ 建议 | ✅ 必须 | 企微服务器推送消息到回调 URL |
| 企微自建应用 (wecom) | ✅ 需要 | ✅ 建议 | ✅ 必须 | 企微服务器推送消息到回调 URL |

### 2.3 企业微信要求

| 项目 | 要求 |
|------|------|
| 企业微信版本 | 已注册企业微信，管理员权限 |
| 企业认证 | 建议已认证（未认证客服限 100 人） |
| 自建应用 | 至少创建 1 个自建应用 |
| 可信 IP | Webhook 模式需配置服务器出口 IP |

---

## 3. 部署步骤

### 3.1 方式一：直接部署（推荐开发/测试）

```bash
# 1. 克隆代码
git clone https://github.com/75qq2026/LangBot.git
cd LangBot
git checkout wending

# 2. 安装后端依赖
pip install uv
uv sync --dev

# 3. 安装前端依赖
cd web
cp .env.example .env
pnpm install
cd ..

# 4. 启动后端（端口 5300）
uv run main.py

# 5. 启动前端（另一个终端，端口 3000）
cd web && pnpm dev
```

### 3.2 方式二：Docker 部署（推荐生产）

```bash
git clone https://github.com/75qq2026/LangBot.git
cd LangBot
git checkout wending

# 使用 docker-compose
cd docker
docker compose up -d
```

### 3.3 首次初始化

1. 访问 `http://<服务器IP>:3000`
2. 注册管理员账号（首次访问自动进入注册页面）
3. 按顺序配置：模型 → 管道 → 机器人

### 3.4 公网暴露（Webhook 模式必需）

**方式 A：Nginx 反向代理（推荐生产）**

```nginx
server {
    listen 443 ssl;
    server_name bot.yourdomain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5300;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**方式 B：Cloudflare Tunnel（无需公网 IP）**

```bash
# 安装
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# 快速隧道（临时测试）
cloudflared tunnel --url http://localhost:5300

# 正式使用：配置命名隧道 + 自定义域名
cloudflared tunnel login
cloudflared tunnel create langbot
cloudflared tunnel route dns langbot bot.yourdomain.com
cloudflared tunnel run langbot
```

**方式 C：其他内网穿透（国内推荐）**
- natapp.cn
- cpolar.com
- frp (自建)

---

## 4. 三种企微 AI 客服能力与限制对比

### 4.1 总览对比表

| 维度 | 企微智能机器人 (wecombot) | 微信客服 (wecomcs) | 企微自建应用 (wecom) |
|------|:------------------------:|:------------------:|:-------------------:|
| **适配器名称** | `wecombot` | `wecomcs` | `wecom` |
| **连接方式** | WebSocket 长连接 | Webhook 回调 | Webhook 回调 |
| **公网 IP** | ❌ 不需要 | ✅ 需要 | ✅ 需要 |
| **HTTPS** | ❌ 不需要 | ✅ 需要 | ✅ 需要 |
| **IP 白名单** | ❌ 不需要 | ✅ 需要 | ⚠️ 建议配置 |

### 4.2 消息能力对比

| 消息能力 | 企微智能机器人 | 微信客服 | 企微自建应用 |
|---------|:------------:|:-------:|:-----------:|
| **单聊（内部员工）** | ✅ | ✅ | ✅ |
| **内部群聊** | ✅ @机器人触发 | ❌ | ❌ (pass) |
| **外部群聊** | ❌ | ✅ 客服场景 | ❌ |
| **外部客户（个人微信）** | ❌ | ✅ 唯一方式 | ❌ |
| **文本消息** | ✅ 收发 | ✅ 收发 | ✅ 收发 |
| **图片消息** | ✅ 收发 | ✅ 收发 | ✅ 收发 |
| **语音消息** | ⚠️ 接收 | ⚠️ 接收 | ⚠️ 接收 |
| **文件消息** | ✅ 收发 | ❌ | ✅ 收发 |
| **视频消息** | ⚠️ 接收 | ⚠️ 接收 | ⚠️ 接收 |
| **流式回复（打字机）** | ✅ | ❌ | ❌ |
| **Markdown 格式** | ✅ | ❌ 纯文本 | ❌ 纯文本 |
| **回复时限** | 3 分钟 | 48 小时（客户主动） | 无限制 |

### 4.3 用户触达场景

| 场景 | 企微智能机器人 | 微信客服 | 企微自建应用 |
|------|:------------:|:-------:|:-----------:|
| 企业内部员工日常问答 | ✅ 最佳 | ⚠️ 可用 | ✅ 可用 |
| 内部群 AI 助手 | ✅ 唯一选择 | ❌ | ❌ |
| 外部客户微信咨询 | ❌ | ✅ 唯一选择 | ❌ |
| 微信扫码进入客服 | ❌ | ✅ | ❌ |
| 公众号/小程序接入 | ❌ | ✅ | ❌ |
| 视频号主页客服 | ❌ | ✅ | ❌ |
| 员工 1对1 私聊 | ✅ | ❌ | ✅ |
| 外部客户资料收集 | ❌ | ✅ 含 unionid | ❌ |

### 4.4 管理与运维

| 运维维度 | 企微智能机器人 | 微信客服 | 企微自建应用 |
|---------|:------------:|:-------:|:-----------:|
| **创建方式** | 管理后台→智能机器人→API模式 | 管理后台→微信客服→开启API | 管理后台→应用管理→自建 |
| **凭据** | BotId + Secret | 关联自建应用的 Secret | corpid + Secret |
| **回调配置** | 无需（WebSocket） | 自建应用的接收消息配置 | 自建应用的接收消息配置 |
| **可见范围** | 需配置 | 通过客服链接/二维码 | 需配置 |
| **部署复杂度** | ⭐ 最简单 | ⭐⭐⭐ 较复杂 | ⭐⭐ 中等 |
| **稳定性** | ⭐⭐⭐ WebSocket自动重连 | ⭐⭐ 依赖回调可达性 | ⭐⭐ 依赖回调可达性 |
| **多实例** | 可创建多个机器人 | 可创建多个客服账号 | 可创建多个应用 |

### 4.5 限制与注意事项

#### 企微智能机器人 (wecombot)

```
✅ 优点：
  - 部署最简单，不需要公网 IP，WebSocket 主动外连
  - 支持流式回复（打字机效果），体验最好
  - 支持内部群聊 @机器人
  - 自动重连机制，稳定性高

❌ 限制：
  - 只能企业内部使用，不能触达外部客户/个人微信
  - 需要在管理后台创建「智能机器人」并选「API 模式」
  - 机器人回复超 3 分钟会被截断
  - Secret 只显示一次，需妥善保存
  - 不支持外部群

⚠️ 注意：
  - 创建时必须选「API 模式创建」，不是「使用官方模型」
  - 连接方式选「使用长连接」（WebSocket 模式）
  - 可见范围必须包含使用者，否则找不到机器人
```

#### 微信客服 (wecomcs)

```
✅ 优点：
  - 唯一能让外部个人微信用户直接对话的方式
  - 支持微信扫码、公众号、小程序、视频号多入口
  - 可获取客户 unionid，用于跨平台识别
  - 48 小时回复窗口（客户主动联系后）

❌ 限制：
  - 必须有公网可访问的 HTTPS 回调地址
  - 必须配置 IP 白名单（服务器出口 IP）
  - 未认证企业限 100 个客户
  - 不支持流式回复，只能发完整消息
  - 不支持 Markdown 格式
  - 回调地址与自建应用共用，同一应用只能配一个回调 URL
  - API 调用有频率限制

⚠️ 注意：
  - Secret 不在客服页面显示，需通过关联的自建应用获取
  - 关联的自建应用需在「可调用接口的应用」中配置
  - 自建应用的 IP 白名单要包含 LangBot 服务器出口 IP
  - 开启 API 后，客服消息只能通过 API 管理（不再通过管理后台）
  - 回调连续失败会导致企微暂停推送，需重新保存回调配置恢复
  - 不同客服账号需通过「前往配置」关联到 API
```

#### 企微自建应用 (wecom)

```
✅ 优点：
  - 配置相对简单，凭据在应用详情页直接可见
  - 支持文件收发
  - 回复无时间限制

❌ 限制：
  - 只能内部使用，不能触达外部客户
  - 不支持群聊（代码中 GroupMessage 是 pass）
  - 不支持流式回复
  - 需要公网回调地址
  - 功能被企微智能机器人完全覆盖（建议用 wecombot 替代）

⚠️ 注意：
  - 如果同时配了微信客服，回调 URL 会冲突（共用一个）
  - 建议优先使用 wecombot，wecom 适配器作为备选
```

### 4.6 推荐组合方案

| 需求场景 | 推荐配置 | 说明 |
|---------|---------|------|
| 仅内部使用 | wecombot | 最简部署，不需要公网 |
| 仅外部客服 | wecomcs | 需公网，配置客服账号 |
| 内部 + 外部 | wecombot + wecomcs | 推荐方案，两者独立运行 |
| 全部需要 | wecombot + wecomcs + Hook | 加 WeChat Hook 覆盖个人微信 |

---

## 5. 各通道详细配置指南

### 5.1 企微智能机器人 (wecombot) — 配置步骤

**第一步：在企微后台创建机器人**

1. 登录企业微信管理后台 → **安全与管理** → **管理工具** → **智能机器人**
2. 点击 **创建机器人** → 选择 **手动创建**
3. 填写名称、头像、简介
4. ⚠️ 关键：点击底部 **「API 模式创建」**
5. 连接方式选择 **「使用长连接」**
6. 获取 **BotId** 和 **Secret**（Secret 只显示一次！）
7. 设置 **可见范围**（必须包含使用者）

**第二步：在 LangBot 中配置**

| 配置项 | 值 | 说明 |
|-------|-----|------|
| 适配器 | `wecombot` | 企业微信智能机器人 |
| BotId | `aibXXXXXX...` | 从企微后台获取 |
| Secret | `MVpXXXXXX...` | 从企微后台获取，仅显示一次 |
| robot_name | 自定义 | 机器人显示名称 |
| enable-webhook | `false` | 使用 WebSocket 模式 |
| enable-stream-reply | `true` | 开启流式回复 |

**第三步：验证**

- 在企微客户端 → 工作台 → 智能机器人 → 找到机器人 → 发送消息
- 群聊中 @机器人名称 发送消息

---

### 5.2 微信客服 (wecomcs) — 配置步骤

**第一步：开启微信客服 API**

1. 登录企业微信管理后台 → **应用管理** → 找到 **微信客服** 应用
2. 开启 **API** 功能
3. 在「可调用接口的应用」中关联一个**自建应用**

**第二步：配置自建应用的回调**

1. 进入关联的 **自建应用** → **接收消息** → **设置 API 接收**
2. 配置：

| 配置项 | 值 |
|-------|-----|
| URL | `https://your-domain.com/bots/<wecomcs-bot-uuid>` |
| Token | 自定义或随机生成（32位以内英文数字） |
| EncodingAESKey | 自定义或随机生成（43位英文数字） |

3. 点击保存，等待验证通过

**第三步：配置 IP 白名单**

1. 在自建应用中找到 **企业可信 IP**
2. 添加 LangBot 服务器的**出口公网 IP**
3. 如果服务器 IP 不固定，需要添加所有可能的出口 IP

**第四步：配置客服账号**

1. 回到微信客服页面 → 点击需要 API 管理的客服账号
2. 点击 **「前往配置」** 关联到 API

**第五步：在 LangBot 中配置**

| 配置项 | 值 | 说明 |
|-------|-----|------|
| 适配器 | `wecomcs` | 微信客服 |
| corpid | `wwXXXXXX...` | 企业 ID，在「我的企业」页面查看 |
| secret | `9YGXXXXXX...` | **关联的自建应用的 Secret**，不是客服单独的 |
| token | 与回调配置一致 | 和自建应用 API 接收中配的一样 |
| EncodingAESKey | 与回调配置一致 | 和自建应用 API 接收中配的一样 |
| api_base_url | `https://qyapi.weixin.qq.com/cgi-bin` | 默认值，一般不改 |

**第六步：修改 config.yaml**

```yaml
api:
    webhook_prefix: 'https://your-domain.com'  # 改为你的公网域名
```

修改后需**重启 LangBot 后端**。

**第七步：获取客服入口**

在微信客服管理页面 → 点击客服账号 → 获取**客服链接**或**二维码**，分享给客户即可。

---

### 5.3 企微自建应用 (wecom) — 配置步骤

> ⚠️ 建议优先使用 wecombot，wecom 功能已被 wecombot 完全覆盖

**配置流程与 wecomcs 类似，但更简单：**

| 配置项 | 值 | 说明 |
|-------|-----|------|
| 适配器 | `wecom` | 企微自建应用 |
| corpid | `wwXXXXXX...` | 企业 ID |
| secret | 自建应用的 Secret | 应用详情页获取 |
| token | 与回调配置一致 | API 接收配置中的值 |
| EncodingAESKey | 与回调配置一致 | API 接收配置中的值 |

⚠️ **重要**：wecom 和 wecomcs 的回调 URL 都走自建应用的「接收消息」配置，但**只能填一个 URL**。如果同时使用，需要让消息路由到 wecomcs 的 bot UUID（客服优先级更高）。

---

## 6. AI 模型配置

### 6.1 已验证可用的模型

| 提供者 | requester 名称 | 默认 Base URL | 推荐模型 |
|-------|---------------|---------------|---------|
| 阿里云百炼 | `bailian-chat-completions` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus, qwen-max, qwen-turbo |
| OpenAI | `openai-chat-completions` | `https://api.openai.com/v1` | gpt-4o, gpt-4o-mini |
| DeepSeek | `deepseek-chat-completions` | `https://api.deepseek.com/v1` | deepseek-chat, deepseek-reasoner |
| Ollama (本地) | `ollama-chat` | `http://localhost:11434` | llama3, qwen2.5 |

### 6.2 配置联网搜索（推荐）

在 LangBot 管理后台：
1. 进入 **模型** → 找到 qwen-plus 模型 → 编辑
2. 在 **extra_args** 中设置：`{"enable_search": true}`
3. 保存后生效，无需重启

或直接修改数据库：
```sql
UPDATE llm_models SET extra_args = '{"enable_search": true}' WHERE name = 'qwen-plus';
```

### 6.3 配置步骤

1. 管理后台 → **模型** → **添加提供者**
2. 选择提供者类型，填入 API Key
3. 添加具体模型名称
4. 点击 **测试** 验证连通性

---

## 7. 管道（Pipeline）配置

### 7.1 管道概念

管道 = AI Runner + 模型 + System Prompt + 可选知识库

每个机器人绑定一个管道，管道决定了 AI 如何处理消息。

### 7.2 创建管道

1. 管理后台 → **管道** → **新建管道**
2. 选择 AI Runner：`local-agent`（默认）
3. 选择模型：如 `qwen-plus`
4. 配置 System Prompt，例如：

**通用客服 Prompt：**
```
你是一个专业的客服助手。请用简洁友好的语言回答客户问题。
如果无法回答，请建议客户联系人工客服。
回复使用中文，保持专业和礼貌。
```

**资料收集 Prompt：**
```
你是一个客户信息收集助手。在对话中自然地收集以下信息：
- 姓名
- 联系电话
- 公司名称
- 具体需求

不要一次性询问所有信息，根据对话自然引导。
收集到的信息以 JSON 格式在回复末尾标注。
```

### 7.3 绑定机器人

创建机器人时或编辑机器人时，在「路由与连接」中选择对应的管道。

---

## 8. 常见问题排查

### 8.1 回调验证失败

| 错误码 | 原因 | 解决方案 |
|-------|------|---------|
| -40001 | msg_signature 验证失败 | 检查 Token 是否与企微后台一致 |
| -40003 | corpid 不匹配 | 检查 corpid 配置是否正确 |
| -40004 | AES 解密失败 | 检查 EncodingAESKey 是否正确（必须 43 位） |
| HTTP 400 | 缺少验证参数 | 正常（无参数的直接访问会返回 400） |
| 连接超时 | 服务器不可达 | 检查公网地址/域名/端口是否可访问 |

### 8.2 微信客服消息不回复

排查清单：
1. ✅ LangBot 后端是否运行中？ → `curl http://localhost:5300/healthz`
2. ✅ 回调地址是否可达？ → 从外网测试 `curl https://your-domain/healthz`
3. ✅ 客服账号是否通过 API 管理？ → 确认「前往配置」已完成
4. ✅ IP 白名单是否包含服务器 IP？ → `curl https://checkip.amazonaws.com`
5. ✅ 回调配置是否保存成功？ → 重新保存一次触发验证
6. ✅ 插件系统是否已禁用？ → `config.yaml` 中 `plugin.enable: false`
7. ✅ 模型是否可用？ → 管理后台测试模型连通性

### 8.3 企微智能机器人无回复

排查清单：
1. ✅ 日志中是否显示 `Authenticated successfully`？
2. ✅ BotId 和 Secret 是否正确？
3. ✅ 可见范围是否包含使用者？
4. ✅ 管道是否已绑定？
5. ✅ 模型 API Key 是否有效？

### 8.4 回调连续失败后恢复

企微检测到回调连续失败会暂停推送。恢复方法：
1. 确保 LangBot 后端稳定运行
2. 确保回调地址可达
3. 到企微管理后台 → 自建应用 → API 接收 → **重新保存**（不改内容也要点保存）
4. 这会触发重新验证，验证通过后推送恢复

---

## 9. 运维手册

### 9.1 重要文件位置

| 文件/目录 | 说明 |
|----------|------|
| `data/config.yaml` | 主配置文件（webhook_prefix、数据库、插件开关等） |
| `data/langbot.db` | SQLite 数据库（用户、模型、机器人、管道配置） |
| `data/chroma/` | ChromaDB 向量数据库（知识库） |
| `data/logs/` | 运行日志 |
| `data/storage/` | 文件存储 |
| `web/.env` | 前端配置（API 地址） |

### 9.2 备份策略

```bash
# 定时备份脚本（加入 crontab）
#!/bin/bash
BACKUP_DIR="/backup/langbot/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR
cp data/config.yaml $BACKUP_DIR/
cp data/langbot.db $BACKUP_DIR/
cp -r data/chroma $BACKUP_DIR/
echo "Backup completed: $BACKUP_DIR"
```

### 9.3 服务管理

```bash
# 启动
uv run main.py &

# 查看日志
tail -f data/logs/langbot.log

# 重启（先找 PID）
kill $(netstat -tlnp | grep :5300 | awk '{print $NF}' | cut -d/ -f1)
sleep 3
uv run main.py &

# 健康检查
curl -s http://localhost:5300/healthz
curl -s http://localhost:5300/api/v1/system/info
```

### 9.4 关键配置项说明

```yaml
# data/config.yaml 关键配置

api:
    port: 5300                    # 后端端口
    webhook_prefix: 'https://...' # 公网回调前缀（Webhook 模式必填）
    extra_webhook_prefix: ''      # 备用回调前缀

plugin:
    enable: false                 # 插件系统（无 Plugin Runtime 时必须关闭）

database:
    use: sqlite                   # 数据库类型（sqlite / postgresql）
    sqlite:
        path: data/langbot.db

system:
    allow_modify_login_info: true # 允许修改登录信息
    jwt:
        expire: 604800            # JWT 过期时间（秒），默认 7 天
        secret: '...'             # JWT 密钥（自动生成）
    recovery_key: '...'           # 恢复密钥（重置密码用）
```

### 9.5 性能调优

```yaml
concurrency:
    pipeline: 20    # 同时处理的管道数（增大可提升并发）
    session: 1      # 每会话并发数
```

### 9.6 升级流程

```bash
cd LangBot
git pull origin wending

# 更新依赖
uv sync --dev
cd web && pnpm install && cd ..

# 重启服务
kill $(netstat -tlnp | grep :5300 | awk '{print $NF}' | cut -d/ -f1)
sleep 3
uv run main.py &
```
