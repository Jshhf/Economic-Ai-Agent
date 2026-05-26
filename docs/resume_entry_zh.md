# 简历项目描述（升级版）

## 推荐写法

Agent Runtime Platform for Economic Analysis 2026-05 ~ 2026-05  
AI Agent 后端 / 全栈项目  
FastAPI、OpenAI Agents SDK、SQLite、RAG、MCP、HTMX、Chart.js

项目介绍：本项目是一个面向经济分析场景的 AI Agent Runtime 平台，支持上传 CSV 数据后按 Skill 编排自动完成数据分析、异常定位、背景检索、图表生成与报告输出。系统在后端抽象出 `Agent + Skill + Tool` 三层结构，并通过 RAG 接入本地知识、通过 MCP 风格适配层接入外部经济与研究资料，同时记录任务状态、来源引用、运行 trace 与指标，重点体现 AI Agent 在工程系统中的可扩展性与可观测性。

- 基于 FastAPI 搭建任务式 Agent Runtime 服务，支持 Skill 选择、任务创建、状态查询、报告获取、来源查询和 trace 查看等接口。
- 设计 `economic_report`、`anomaly_investigation`、`policy_briefing` 三类 Skill，将原本固定流程升级为可注册、可切换的分析能力单元。
- 基于 OpenAI Agents SDK 设计 `Data Analyst Agent`、`Economist Review Agent`、`Economist Writer Agent` 协作链路，通过工具调用和结构化输出生成 `EvidencePack`、补充分析结果和最终报告。
- 构建本地知识 RAG 与 MCP 外部能力接入层，支持从方法论、指标定义、外部经济资料和研究背景中检索上下文，并在报告中展示引用来源。
- 使用 SQLite 持久化 `analysis_jobs`、`artifacts`、`agent_runs`、`tool_call_logs`、`source_references`、`metrics_log`，实现 Job、Skill、RAG、MCP 全链路可追踪和失败分类。
- 基于 Jinja2 + HTMX + Chart.js 构建轻量可视化页面，支持展示 Skill 选择、报告图表、引用来源、运行 trace 和观测指标。

## 更偏后端岗位的精简版

Agent Runtime Platform for Economic Analysis 2026-05 ~ 2026-05  
AI Agent 后端开发  
FastAPI、OpenAI Agents SDK、SQLite、RAG、MCP

- 设计并实现 AI Agent Runtime，将分析流程抽象为 `Agent + Skill + Tool` 分层架构，支持多种分析技能的服务化运行。
- 构建本地知识 RAG 和 MCP 外部接入层，增强 Agent 对经济分析背景、指标解释和政策上下文的检索能力。
- 使用 SQLite 持久化任务状态、运行 trace、来源引用和指标日志，提升系统可观测性与可调试性。
- 提供 Web/API 双入口，支持上传数据、触发分析、查看报告、检查来源与运行链路。

## 面试时可以强调的点

- 这不是单纯的 prompt chaining，而是具备 Skill 层、工具层、RAG 层、MCP 层和 trace 层的 Agent 工程系统。
- 重点不是“大模型会总结”，而是“我把 Agent 做成了能切换能力、能接外部来源、能做可观测性展示的运行时平台”。
- 这个项目能体现我对接口设计、任务编排、结构化输出、来源归因、可观测性和 AI-assisted engineering 的理解。
