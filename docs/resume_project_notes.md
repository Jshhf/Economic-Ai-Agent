# Resume Project Notes

## Recommended Project Title

`Agent Runtime Platform for Economic Analysis | 支持 Skill、RAG、MCP 的 AI Agent 平台`

## One-Line Positioning

一个面向经济分析场景的 AI Agent Runtime 平台，支持 Skill 编排、RAG 增强、MCP 外部能力接入、任务追踪与可观测性展示。

## Resume Bullets

- 基于 `FastAPI + OpenAI Agents SDK + SQLite` 设计并实现 AI Agent Runtime，将系统抽象为 `Agent + Skill + Tool` 分层架构，支持多种分析技能的服务化运行。
- 设计 `economic_report / anomaly_investigation / policy_briefing` 三类 Skill，并通过统一运行时编排工具调用、证据生成、补充分析与最终报告输出。
- 构建本地知识库 RAG 与 MCP 风格外部来源接入层，支持从本地方法论文档和外部经济/研究资料中检索上下文，提升分析解释性和引用能力。
- 使用 SQLite 持久化 `analysis_jobs`、`artifacts`、`agent_runs`、`tool_call_logs`、`source_references` 和 `metrics_log`，实现 Job、Skill、RAG、MCP 全链路 trace 与指标记录。
- 基于 `Jinja2 + HTMX + Chart.js` 搭建可视化界面，支持查看技能选择、分析报告、引用来源、运行链路和可观测性指标，形成完整可演示的 Agent 平台项目。

## Short Interview Pitch

这个项目我重点想体现的不是“让大模型总结一份 CSV”，而是我把 AI Agent 做成了一个可以扩展的运行时平台。我把运行链路拆成了 Agent、Skill、Tool 三层，再加上 RAG 和 MCP 两类增强能力，让系统既能跑结构化分析，又能接入本地知识和外部资料；同时我把任务状态、运行 trace、来源引用和指标都落到后端里，并通过 Web 页面展示出来。这样在面试里我能讲清楚 Agent 编排、能力抽象、可观测性和 AI-assisted engineering 的整套实现思路。

## Keywords

- Agent runtime
- Skill orchestration
- Tool calling
- RAG
- MCP adapters
- FastAPI
- SQLite
- Observability
- Traceability
- AI-assisted engineering

## Suggested GitHub Repo Description

`A resume-ready AI Agent runtime platform for economic analysis with skills, RAG, MCP adapters, and observability.`
