# Context Mainline Upgrade

## 1. 这次升级的定位

这次是这个 AI Agent 项目的第二次升级，不是重做第一版。

项目演进分三段：

1. 初版
- 目标：先把数据上传、任务创建、分析执行、报告展示这条链路跑通
- 主要能力：FastAPI、双 Agent、SQLite、报告展示

2. 第一次升级
- 目标：从“能跑通”升级到“能扩展、能观测”
- 主要能力：Skill、Tool、RAG、MCP、Trace、Observability

3. 第二次升级
- 目标：从“能扩展、能观测”继续升级到“任务主线稳定、上下文可治理”
- 主要能力：Goal Summary / Context Mainline

这次的核心不是再加一个新工具，而是补一层稳定的任务主线对象。

## 2. 第一次升级之后，我观察到什么问题

第一次升级之后，系统已经能做：

- Skill 驱动的不同分析场景切换
- Tool / RAG / MCP 分层
- Trace、Metrics、SourceReference 持久化

但继续往下看，会发现下面这些问题：

### 问题 1：任务阶段越来越多，但缺少统一主线

现象：

- runtime 已经有 `EvidencePack`
- 有 `FollowUpRequest`
- 有 `SupplementalEvidence`
- 也有 trace 和 artifacts

但这些对象分别记录的是局部运行结果，不是整体任务主线。

风险：

- 系统知道自己做过什么，但不够清楚“当前整体目标是什么”
- 后续阶段如果变复杂，任务推进状态容易分散在多个对象里

### 问题 2：Trace 很全，但 Trace 不是主线

现象：

- trace 能记录 agent run、tool call、source reference、metrics
- 这很适合做可观测和排查

但 trace 更像运行日志，不像任务摘要。

风险：

- trace 可以解释“发生了什么”
- 但不能简洁回答“我们现在做到哪了、下一步是什么”

### 问题 3：RAG 能召回资料，但不能替代目标管理

现象：

- RAG 适合从知识库里找相关内容
- MCP 适合补外部上下文

但它们解决的是 retrieval，不是 task-goal management。

风险：

- 检索到的信息不等于任务主线
- 即使找回了相关片段，也不能保证系统知道当前阶段、已完成步骤和下一步动作

### 问题 4：如果后面任务变长，缺少稳定上下文层

现象：

- 当前项目虽然还不是完整聊天 Agent
- 但已经有多阶段执行、follow-up、writer 这些链路

这意味着它天然会往更长任务方向发展。

风险：

- 如果没有显式任务主线层，后续很容易出现上下文膨胀、主线漂移、阶段信息分散的问题

## 3. 为什么判断这是上下文治理问题，不是单纯模型问题

我的判断逻辑不是“模型回答不够好，所以再调 prompt”。

我是从系统结构去看的：

1. 项目已经有结果对象
- `EvidencePack`
- `FollowUpRequest`
- `FinalReport`

2. 项目已经有运行记录
- `agent_runs`
- `tool_call_logs`
- `source_references`
- `metrics_log`

3. 但缺少一个长期稳定的任务主线对象

也就是说：

- 运行结果是有的
- 运行过程是有的
- 外部证据是有的
- 但没有一个对象专门回答：
  - 现在整体目标是什么
  - 当前处于哪个阶段
  - 已经完成了哪些关键步骤
  - 下一步应该做什么

所以这不是简单的模型输出问题，而是 runtime 缺少上下文主线层的问题。

## 4. 为什么不能只靠 RAG

这次升级里一个重要判断是：

**RAG 解决 retrieval，Goal Summary 解决 task-goal management。**

RAG 适合：

- 从知识库里找相关文档
- 从外部来源补充背景资料
- 未来扩展时用于召回历史片段

但 RAG 不适合单独承担：

- 整体目标记录
- 当前阶段表达
- 已完成步骤归纳
- 下一步动作指引

原因很简单：

1. RAG 找回的是相关片段，不是稳定主线
2. 检索结果有相关性，不代表有阶段性
3. 召回到了内容，也不等于系统知道当前优先级

所以这次第二次升级不继续堆 RAG，而是补一层 Goal Summary。

## 5. 这次具体做了什么

这次升级主要加了四部分能力：

### 1. Goal Summary schema

新增 `GoalSummary`，固定记录：

- overall goal
- user constraints
- output requirements
- current stage
- completed steps
- resolved questions
- open questions
- key findings
- next action

### 2. Goal Summary 持久化

新增 `goal_summaries` 表。

采用 append-only 策略：

- 每个关键阶段写一个新版本
- 不覆盖旧版本
- 方便回溯任务主线如何演进

### 3. Job 生命周期主线更新

在这些阶段写 summary：

- queued
- data_analysis
- economist_review
- economist_follow_up
- economist_writer
- completed / failed

这样 summary 就不再是静态说明，而是 runtime 内部真正会更新的状态。

### 4. Agent 输入优先读主线摘要

给 Data Analyst / Economist Review / Follow-up / Writer 这些 agent 注入 Goal Summary block。

这一步很重要，因为它说明：

这次升级不是“多存一个 JSON 文件”，而是真正让主线摘要参与推理过程。

## 6. 这次升级解决了什么问题

升级后，系统多了一层稳定的任务主线能力：

1. 能清楚表达当前整体目标
2. 能明确展示当前处于哪个阶段
3. 能总结已经完成的关键步骤
4. 能把关键发现集中起来
5. 能给出下一步动作

所以它解决的不是“模型会不会写报告”，而是：

- runtime 能不能稳定地组织任务上下文
- 系统能不能解释自己现在做到哪了

## 7. 当前边界

这次升级是有意收敛范围的，没有把项目变成完整多轮聊天系统。

当前还没有做：

1. conversation memory
2. clarification policy
3. conversation RAG
4. resume / continue UI
5. 更细粒度的 task state machine

这是合理取舍。

因为第一次升级解决的是扩展和观测，第二次升级先解决主线稳定。

## 8. 后续扩展方向

如果继续往下做，我会优先考虑：

1. `conversation_turns`
- 记录最近若干轮对话

2. `clarification_logs`
- 记录哪些问题已经问过、哪些已经解决

3. conversation retrieval
- 用于长任务里按需召回历史片段

4. resume / continue
- 中断后按 summary 恢复执行

5. richer task state machine
- 比现在更细粒度地描述任务推进

## 9. 面试时可以怎么总结这次升级

推荐说法：

> 第一次升级之后，这个项目已经有 Skill、RAG、MCP 和 Trace 这些能力，能做到扩展和可观测。但我继续往下看时，发现系统虽然记录了很多运行结果和运行日志，却缺少一个稳定的任务主线对象。所以第二次升级我没有继续堆新工具，而是补了 Goal Summary 这层，用来记录整体目标、当前阶段、已完成步骤和下一步动作。本质上，这次升级解决的是上下文治理问题，而不是单纯模型问题。RAG 解决的是 retrieval，Goal Summary 解决的是 task-goal management，这两者职责不一样。
