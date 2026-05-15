# 简历项目条目（适配你当前简历风格）

## 推荐写法

多 Agent 经济数据分析平台 2026-05 ~ 2026-05  
AI Agent 后端 / 全栈开发  
FastAPI、OpenAI Agents SDK、OpenAI Responses API、SQLite、Jinja2、HTMX、Chart.js

项目介绍：本项目是一个面向经济数据分析场景的多 Agent 智能分析平台，支持上传 CSV 数据文件，自动完成数据巡检、指标分析、异常检测、经济解读、图表生成与中文报告输出。系统以服务化方式提供分析任务 API，并通过 Web 页面展示任务状态、Agent 协作轨迹和工具调用日志，重点体现 AI Agent 在后端工程中的可落地能力。

- 基于 FastAPI 搭建异步分析任务服务，设计 `queued -> running -> reviewing -> completed/failed` 状态流转，并提供任务创建、状态查询、报告获取、trace 查询等接口。
- 基于 OpenAI Agents SDK 设计 `Data Analyst Agent` 与 `Economist Agent` 协作链路，前者通过工具调用形成结构化 `EvidencePack`，后者负责证据审查、补充分析请求与中文报告生成。
- 设计 `inspect_dataset`、`latest_snapshot`、`city_rankings`、`city_trend`、`income_group_comparison`、`detect_anomalies` 等数据工具，约束 Agent 以结构化 JSON 方式观察数据，避免直接吞整表带来的高 token 开销与不稳定输出。
- 使用 SQLite 持久化 `analysis_jobs`、`artifacts`、`agent_runs`、`tool_call_logs` 四类核心数据，实现任务结果、Agent handoff、工具调用参数与执行耗时的全链路可追踪。
- 基于 Jinja2 + HTMX + Chart.js 实现轻量前端，支持上传文件、查看任务执行状态、展示经济分析报告与图表，并直观呈现 Agent 协作和工具调用轨迹。

## 更偏后端岗位的精简版

多 Agent 经济数据分析平台 2026-05 ~ 2026-05  
AI Agent 后端开发  
FastAPI、OpenAI Agents SDK、SQLite、HTMX

- 设计并实现基于 FastAPI 的 AI agent 分析服务，支持 CSV 上传、异步任务调度、报告生成和 trace 查询。
- 基于 OpenAI Agents SDK 拆分数据分析 Agent 与经济解释 Agent，通过工具调用和 handoff 机制完成结构化证据生成与报告输出。
- 使用 SQLite 持久化任务状态、分析产物、Agent 运行记录和工具调用日志，提升系统可观测性与可调试性。
- 通过 HTMX + Chart.js 搭建轻量展示页，支持任务状态、图表和 Agent trace 的可视化查看。

## 面试时可以强调的点

- 这不是 prompt chaining，而是有工具层、状态机、持久化和 trace 的 agent 后端系统。
- 重点不是“大模型会总结”，而是“我把 Agent 做成了能接 API、能跑任务、能查轨迹的工程化服务”。
- 这个项目能体现我对后端接口设计、任务编排、数据建模、可观测性和 AI agent 集成的理解。
