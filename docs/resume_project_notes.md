# Resume Project Notes

## Recommended Project Title

`Economic Agent Platform | 多 Agent 经济数据分析平台`

## One-Line Positioning

一个面向经济数据分析场景的多 Agent 后端系统，支持工具调用、Agent 协作、任务追踪、报告生成和轻量 Web 展示。

## Resume Bullets

- 基于 `FastAPI + OpenAI Agents SDK + SQLite` 设计并实现多 Agent 经济分析平台，将 CSV 数据分析、Agent 协作、任务状态管理与报告生成封装为可复用后端服务。
- 为 `Data Analyst Agent` 设计结构化工具层，覆盖数据巡检、最新快照、城市排名、趋势分析、收入组对比、异常检测与图表载荷生成，形成 `EvidencePack` 中间协议。
- 为 `Economist Agent` 设计证据审查与补充分析机制，支持基于 schema 的 handoff 协作、一次回查补充分析和中文 Markdown 报告输出，降低自由文本链路不稳定性。
- 使用 SQLite 持久化 `analysis_jobs`、`artifacts`、`agent_runs`、`tool_call_logs`，实现任务状态流转、工具调用 trace 与报告结果可追踪，便于调试和演示。
- 基于 `Jinja2 + HTMX + Chart.js` 实现轻量前端，支持文件上传、任务状态查看、图表展示与 trace 可视化，形成可完整演示的 AI agent 全栈项目。

## Short Interview Pitch

这个项目我重点想解决的不是“让模型总结一份 CSV”，而是把 AI agent 做成一个真正的后端系统。我把数据分析 Agent 和经济解释 Agent 拆开，让前者只通过工具拿结构化证据，后者基于证据和本地知识库生成报告；同时我把任务、工具调用、Agent 交接和最终结果都落到 SQLite 里，再通过 FastAPI 和一个轻量页面把状态和 trace 展示出来。这样在面试里我能讲清楚 Agent 编排、工具设计、后端服务化、可观测性和全栈交付。

## Keywords

- Multi-agent orchestration
- Tool calling
- FastAPI
- Async job workflow
- SQLite persistence
- Traceability / observability
- Structured outputs with Pydantic
- AI agent backend
- HTMX
- Chart.js

## Suggested GitHub Repo Description

`A resume-ready multi-agent economic analysis platform built with FastAPI, OpenAI Agents SDK, SQLite, and HTMX.`
