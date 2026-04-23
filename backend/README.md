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

---

## 📁 项目结构

```
My-Project-Core/
├── app/
│   ├── api/v1/              # API 路由层
│   │   ├── auth.py          # 认证授权（JWT）
│   │   ├── chatbot.py       # 聊天机器人端点
│   │   └── travel.py        # 旅游规划端点
│   ├── core/
│   │   ├── langgraph/       # LangGraph Agent 核心
│   │   │   ├── agents/      # 子 Agent 定义
│   │   │   │   ├── sub_agents/  # 景点/酒店/天气子 Agent
│   │   │   │   └── travel_plan_agent/  # 主规划 Agent
│   │   │   ├── tools/       # 工具定义
│   │   │   │   ├── local/   # 本地工具（和风天气）
│   │   │   │   └── mcp/     # MCP 工具（高德地图）
│   │   │   └── graph.py     # Agent 主图
│   │   ├── config.py        # 配置管理
│   │   ├── logging.py       # 结构化日志
│   │   └── middleware.py    # 中间件
│   ├── models/              # 数据库模型（SQLModel）
│   ├── schemas/             # Pydantic 数据模型
│   ├── services/            # 服务层
│   │   ├── llm.py           # LLM 服务（多模型降级）
│   │   └── database.py      # 数据库服务
│   └── utils/               # 工具函数
├── tests/                   # 测试用例
├── pyproject.toml           # 项目依赖
└── .env.example             # 环境变量示例
```

---

## 🔧 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 14+
- uv（包管理器）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/your-username/TravelAgent-Graph-Pro.git
cd TravelAgent-Graph-Pro/My-Project-Core
```

2. **安装依赖**

```bash
uv sync
```

3. **配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件，填写必要的 API Key 和数据库配置
```

4. **初始化数据库**

```bash
# 创建 PostgreSQL 数据库
createdb travel_agent
```

5. **启动服务**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. **访问 API 文档**

```
http://localhost:8000/docs
```

---

## 📡 API 接口

### 认证相关

- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录

### 聊天机器人

- `POST /api/v1/chatbot/chat` - 常规聊天
- `POST /api/v1/chatbot/chat/stream` - 流式聊天（SSE）
- `GET /api/v1/chatbot/messages` - 获取历史消息
- `DELETE /api/v1/chatbot/messages` - 清空历史

### 旅游规划

- `POST /api/v1/trip/plan` - 生成旅行计划

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

---

## 📝 技术博客与文档

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [MCP 协议介绍](https://modelcontextprotocol.io/)
- [Langfuse 可观测性](https://langfuse.com/)
