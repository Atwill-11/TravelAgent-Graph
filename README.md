# 🤖 TravelAgent-Graph

> **一个基于 LangChain + LangGraph 的多智能体旅游规划助手**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.2.15-orange.svg)](https://python.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.1.6-red.svg)](https://langchain-ai.github.io/langgraph/)

---

## 📖 项目简介

TravelAgent-Graph 是一个**多智能体旅游规划系统**。项目基于 LangChain + LangGraph 构建，通过多智能体协作架构，自动完成旅游规划任务的任务拆分、子任务执行和结果整合。

**核心亮点**：

- 🧠 **多智能体协作**：主规划 Agent + 子 Agent（景点/酒店/天气）的任务编排模式
- 🔌 **MCP 协议集成**：通过 langchain-mcp-adapters 连接高德地图 MCP Server，动态调用 10+ 个地图工具
- 💾 **长期记忆系统**：基于 AsyncPostgresStore + 向量搜索实现个性化推荐
- 🔄 **LLM 多模型降级**：支持 OpenAI/Qwen 等多厂商模型，自动重试 + 环形降级
- 📊 **全链路可观测**：集成 Langfuse 实现 Trace 级别的调用追踪与调试
- 🌊 **SSE 流式响应**：实时展示 Agent 思考过程，支持断线重连与打字效果
- ⚡ **生产级特性**：状态持久化、流式响应、速率限制、结构化日志、JWT 认证

---

## 🏗️ 系统架构

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  Auth    │  │ Chatbot  │  │  Trip    │                  │
│  │  Router  │  │  Router  │  │  Router  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph Agent 核心层                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              主规划 Agent (Travel Planner)            │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │   │
│  │  │  Plan   │→ │ Execute │→ │Summarize│→ │  END    │ │   │
│  │  │  Node   │  │  Node   │  │  Node   │  │         │ │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│           │              │              │                    │
│           ▼              ▼              ▼                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ 景点子 Agent │ │ 酒店子 Agent │ │ 天气子 Agent │           │
│  │ Attraction  │ │   Hotel     │ │  Weather    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      工具层 (Tools)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  MCP Tools   │  │ Local Tools  │  │ Custom Tools │      │
│  │  (高德地图)  │  │ (和风天气)   │  │  (组合工具)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      数据持久化层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  PostgreSQL  │  │  PostgreSQL  │  │   Langfuse   │      │
│  │ (状态检查点) │  │ (长期记忆)   │  │  (可观测性)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈

| 类别         | 技术                                              |
| ------------ | ------------------------------------------------- |
| **核心框架** | FastAPI, LangChain, LangGraph                     |
| **LLM 模型** | Qwen (通义千问), OpenAI GPT                       |
| **向量嵌入** | DashScope Embeddings (text-embedding-v4, 1024 维) |
| **数据库**   | PostgreSQL (状态持久化 + 长期记忆)                |
| **ORM**      | SQLModel                                          |
| **MCP 集成** | langchain-mcp-adapters (高德地图 MCP Server)      |
| **API 集成** | 高德地图 API, 和风天气 API                        |
| **可观测性** | Langfuse (Trace 追踪 + 属性传播)                  |
| **认证授权** | JWT (python-jose)                                 |
| **速率限制** | SlowAPI                                           |
| **日志系统** | structlog (结构化日志 + JSONL 持久化)             |
| **测试框架** | pytest + pytest-asyncio                           |
| **包管理**   | uv (uv.lock)                                      |

---

## 🚀 核心功能

### 1. 智能旅游规划

- **输入**：用户指定城市、日期、旅行偏好（如"历史文化"、"亲子游"）
- **处理**：主规划 Agent 自动拆分为 3-5 个子任务（天气查询、景点搜索、酒店推荐）
- **输出**：完整的旅游规划方案（包含天气、景点、酒店、预算等）

### 2. 多智能体协作

- **主规划 Agent**：负责任务分析与编排，使用 `StateGraph` 构建条件路由
- **子 Agent**：
  - 🏛️ **景点 Agent**：基于 MCP 工具搜索景点，支持关键词智能转换（抽象→具体 POI 类型）
  - 🏨 **酒店 Agent**：根据景点位置推荐附近酒店
  - 🌤️ **天气 Agent**：查询天气预报 + 空气质量，生成旅游建议

### 3. 长期记忆与个性化

- 基于 `AsyncPostgresStore` + 向量搜索实现语义记忆检索
- 自动提取用户偏好（如"喜欢博物馆"、"不吃辣"）并存储为长期记忆
- 后续对话自动检索相关记忆，实现个性化推荐

### 4. 会话状态持久化

- 基于 `AsyncPostgresSaver` 实现检查点持久化
- 用户可随时恢复历史对话
- 支持跨设备、跨会话的连续性

### 5. 全链路可观测性

- 集成 Langfuse 实现 LLM 调用追踪
- 自动记录 user_id、session_id、environment 等上下文
- 支持 Trace 级别的分析与调试

### 6. SSE 流式响应

- **实时思考过程展示**：基于 Server-Sent Events 技术，实时推送 Agent 各节点的执行状态
- **断线重连机制**：前端支持指数退避重连策略，确保网络波动时的用户体验
- **打字效果动画**：前端组件支持状态动画、时间线展示，提升交互体验
- **事件类型丰富**：支持 `start`、`plan`、`execute`、`summarize`、`done`、`error` 等多种事件类型
- **兼容非流式接口**：保留原有非流式 API，前端可切换使用

---

## 📁 项目结构

```
TravelAgent-Graph/
├── backend/                   # 后端项目（Python + FastAPI）
│   ├── app/
│   │   ├── api/v1/            # API 路由层
│   │   │   ├── api.py         # API 路由聚合
│   │   │   ├── auth.py        # 认证授权（JWT）
│   │   │   └── travel.py      # 旅游规划端点（含 SSE 流式响应）
│   │   ├── core/              # 核心模块
│   │   │   ├── langgraph/     # LangGraph Agent 核心
│   │   │   │   ├── agents/    # Agent 定义
│   │   │   │   │   ├── sub_agents/         # 景点/酒店/天气子 Agent
│   │   │   │   │   └── travel_plan_agent/  # 主规划 Agent（含流式运行函数）
│   │   │   │   ├── tools/     # 工具定义
│   │   │   │   │   ├── local/  # 本地工具（和风天气）
│   │   │   │   │   └── mcp/    # MCP 工具（高德地图）
│   │   │   │   └── __init__.py
│   │   │   ├── prompts/       # Prompt 模板
│   │   │   ├── config.py      # 配置管理
│   │   │   ├── limiter.py     # 速率限制
│   │   │   ├── logging.py     # 结构化日志
│   │   │   └── middleware.py  # 中间件
│   │   ├── models/            # 数据库模型（SQLModel）
│   │   ├── schemas/           # Pydantic 数据模型
│   │   │   ├── agent/         # Agent 相关模型
│   │   │   ├── common/        # 通用模型
│   │   │   ├── travel/        # 旅游规划模型
│   │   │   ├── weather/       # 天气模型
│   │   │   └── auth.py        # 认证模型
│   │   ├── services/          # 服务层
│   │   │   └── database.py    # 数据库服务
│   │   ├── utils/             # 工具函数
│   │   │   ├── auth.py        # 认证工具
│   │   │   └── sanitization.py # 数据清洗
│   │   └── main.py            # 应用入口
│   ├── Dockerfile             # 后端 Docker 镜像
│   ├── pyproject.toml         # 项目依赖
│   └── uv.lock                # 锁定依赖版本
│
├── frontend/                  # 前端项目（Vue 3 + TypeScript + Vite）
│   ├── src/
│   │   ├── components/        # 可复用组件
│   │   │   ├── SessionSidebar.vue    # 会话侧边栏
│   │   │   └── ThinkingProcess.vue   # SSE 思考过程展示组件
│   │   ├── views/             # 页面视图
│   │   │   ├── Home.vue       # 主页（含 SSE 流式响应集成）
│   │   │   ├── Login.vue      # 登录页
│   │   │   └── Result.vue     # 结果页
│   │   ├── router/            # 路由配置
│   │   ├── services/          # API 服务（含 SSE 流式 API）
│   │   ├── types/             # TypeScript 类型定义（含 SSE 事件类型）
│   │   ├── App.vue            # 根组件
│   │   └── main.ts            # 入口文件
│   ├── public/                # 静态资源
│   ├── Dockerfile             # 前端 Docker 镜像
│   ├── nginx.conf             # Nginx 配置
│   ├── package.json           # 前端依赖
│   ├── tsconfig.json          # TypeScript 配置
│   └── vite.config.ts         # Vite 配置
│
├── docker-compose.yml         # Docker Compose 编排配置
├── .env.example               # 环境变量示例
└── README.md                  # 项目文档
```

---

## 🔧 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 14+
- uv（包管理器）
- Docker & Docker Compose（用于容器化部署）

---

## 🐳 Docker 部署

### 前置要求

- Docker Desktop 20.10+
- Docker Compose v2.0+

### 服务端口映射

| 服务           | 容器端口 | 主机端口 | 访问地址                   |
| -------------- | -------- | -------- | -------------------------- |
| 前端 (Nginx)   | 80       | 3001     | http://localhost:3001      |
| 后端 (FastAPI) | 8000     | 7999     | http://localhost:7999/docs |
| PostgreSQL     | 5432     | 5433     | localhost:5433             |

### 配置环境变量

1. 在项目根目录创建 `.env` 文件：

```bash
# Docker Compose 基础配置
APP_ENV=development

# 数据库配置
POSTGRES_DB=projectdb
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_POOL_SIZE=5
POSTGRES_MAX_OVERFLOW=10

# JWT 配置
JWT_SECRET_KEY=your-jwt-secret-key

# 前端构建配置
VITE_API_BASE_URL=
VITE_AMAP_WEB_JS_KEY=your_amap_web_js_key

# 后端 API Keys
DASHSCOPE_API_KEY=your_dashscope_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_HOST=http://host.docker.internal:3000
QWEATHER_API_KEY=your_qweather_key
AMAP_API_KEY=your_amap_key

# CORS 配置
ALLOWED_ORIGINS=http://localhost:3001,http://localhost:7999

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=console
LOG_DIR=../projectlogs
```

2. **Langfuse 配置说明**（可选）：

如果 Langfuse 运行在独立的 Docker 容器中，使用 `host.docker.internal` 访问宿主机网络：

```bash
LANGFUSE_HOST=http://host.docker.internal:3000
```

### 构建和启动

```bash
# 进入项目根目录
cd 实际项目位置

# 构建并启动所有服务
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f           # 所有服务
docker compose logs -f backend   # 仅后端

# 停止服务
docker compose down
```

### 验证部署

```bash
# 1. 检查容器状态
docker compose ps

# 2. 测试后端健康检查
curl http://localhost:7999/health

# 3. 测试前端页面
curl http://localhost:3001

# 4. 测试前端代理到后端
curl http://localhost:3001/health
```

### 访问应用

- **前端**：http://localhost:3001
- **后端 API 文档**：http://localhost:7999/docs
- **后端 ReDoc**：http://localhost:7999/redoc

---

### 认证相关

- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录
- `POST /api/v1/auth/session` - 创建新会话
- `PATCH /api/v1/auth/session/{session_id}/name` - 设置会话名称
- `DELETE /api/v1/auth/session/{session_id}` - 删除会话
- `GET /api/v1/auth/sessions` - 获取所有会话

### 旅游规划

- `POST /api/v1/trip/plan` - 生成旅行计划（非流式）
- `POST /api/v1/trip/plan/stream` - 流式生成旅行计划（SSE），实时展示 Agent 思考过程

### 健康检查

- `GET /api/v1/health` - 健康检查
- `GET /api/v1/check_env` - 检查环境变量

---

## 🎯 项目亮点总结

| 技术点           | 实现方式                        | 效果                            |
| ---------------- | ------------------------------- | ------------------------------- |
| **多智能体协作** | StateGraph + 条件路由           | 复杂任务自动拆分为 3-5 个子任务 |
| **MCP 协议**     | langchain-mcp-adapters          | 动态集成 10+ 个高德地图工具     |
| **长期记忆**     | AsyncPostgresStore + 向量搜索   | 实现个性化推荐                  |
| **可观测性**     | Langfuse + propagate_attributes | 全链路 Trace 追踪               |
| **状态持久化**   | AsyncPostgresSaver              | 支持跨会话恢复                  |
| **结构化日志**   | structlog + ContextVar          | 请求级日志上下文                |
| **SSE 流式响应** | StreamingResponse + fetch API   | 实时展示 Agent 思考过程         |

---

## 📝 技术博客与文档

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [MCP 协议介绍](https://modelcontextprotocol.io/)
- [Langfuse 可观测性](https://langfuse.com/)
