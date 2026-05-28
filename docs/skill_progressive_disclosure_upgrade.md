# Skill 渐进式披露升级说明

## 1. 这次升级解决什么问题

在上一版项目里，`Skill` 已经承担了场景配置的作用，但它更像“静态配置”：

- 任务一开始就能看到该 skill 下的完整工具集合
- RAG 和外部 source 的可用性也是一次性全量暴露
- 不同阶段虽然有 `phase`，但能力披露还没有真正随阶段收敛

这样会带来几个问题：

- Agent 在早期阶段就能看到过多能力，容易扩大搜索空间
- review 和 writer 阶段缺少明确的能力边界
- follow-up 阶段虽然本来应该是“定向补证据”，但能力没有被显式收束
- 项目里虽然已经有 Goal Summary 主线层，但 Skill 还没有做到按阶段协同治理

所以这次升级的目标是：

**把 Skill 从“静态场景配置”升级成“按阶段渐进式披露能力的运行时治理层”。**

---

## 2. 什么是渐进式披露

这里说的渐进式披露，不是前端交互里的折叠展开，而是 runtime 层面的能力披露策略。

核心思想是：

- 先只暴露当前阶段最必要的工具和上下文
- 等任务推进到下一阶段，再逐步开放更多能力
- 不是一开始把所有工具、所有 source、所有上下文一次性塞给 Agent

放到这个项目里，它主要表现为：

1. `data_analysis`
- 主要暴露结构化数据工具
- 不优先暴露外部知识和外部 source

2. `economist_review`
- 主要暴露轻量知识增强和有限外部 source
- 重点是判断证据够不够，而不是重新打开全部分析面

3. `economist_follow_up`
- 只在 review 明确证据不足后，才暴露更聚焦的补充分析能力
- 这时可以披露更深的数据工具和更广的外部 source

4. `economist_writer`
- 主要暴露写作所需的来源引用能力
- 不再暴露一大堆原始分析工具

---

## 3. 这次具体改了什么

### 3.1 Skill schema 增加阶段披露配置

在 `app/schemas.py` 中给 `SkillDefinition` 增加：

- `stage_disclosures`

新增 `SkillStageDisclosure`：

- `stage`
- `stage_goal`
- `allowed_tools`
- `rag_enabled`
- `mcp_sources`
- `output_type`
- `disclosure_rationale`

这让一个 skill 不再只有“全局可用能力”，而是能描述：

- 某个阶段该暴露什么
- 某个阶段为什么只暴露这些

### 3.2 Skill 注册表改成“全局配置 + 阶段配置”

在 `app/skills.py` 里给每个 skill 增加了分阶段披露定义。

例如 `economic_report`：

- `data_analysis`
  - 暴露数据分析工具
  - 不开 RAG
  - 不开外部 source

- `economist_review`
  - 不暴露数据工具
  - 开启 RAG
  - 只开放有限外部 source

- `economist_follow_up`
  - 暴露定向补分析工具
  - 开启更广外部来源

- `economist_writer`
  - 主要使用来源和参考信息
  - 不再重新开放原始分析工具

### 3.3 Orchestrator 按阶段装配能力

在 `app/agents/orchestrator.py` 中：

- 新增了按当前 `phase` 获取阶段披露配置的逻辑
- 给 Agent 增加了 `Skill Disclosure` block
- 不同阶段构建不同工具集
- fallback 来源构建也改为读取当前阶段的披露配置

这意味着：

- `Data Analyst Agent` 只能拿到 data_analysis 阶段披露的能力
- `Economist Review Agent` 只能拿到 review 阶段披露的能力
- `Data Follow-up Agent` 只能拿到 follow-up 阶段披露的能力
- `Economist Writer Agent` 只能拿到 writer 阶段披露的能力

### 3.4 测试补充

在 `tests/test_app.py` 里补了两类验证：

- `Skill` 注册表里存在阶段披露配置
- `economic_report` 的不同阶段确实有不同的能力边界

---

## 4. 这次升级带来的效果

### 4.1 降低早期阶段能力噪声

过去一上来就暴露整套能力，模型更容易发散。

现在在 `data_analysis` 阶段，系统会优先引导 Agent：

- 先把数据看清楚
- 先把结构化证据做好
- 不急着拉外部上下文

### 4.2 让 review 阶段更像“审查”

过去 review 很容易和 data analysis 边界混在一起。

现在 review 阶段主要拿到的是：

- 任务主线
- 当前证据
- 轻量知识增强
- 有限外部来源

所以它的职责更聚焦：

- 判断证据够不够
- 决定要不要 follow-up

### 4.3 让 follow-up 更像“定向补证据”

follow-up 不是重新做一遍完整分析，而是只补缺口。

通过渐进式披露后，系统会在这个阶段只开放：

- 补证据需要的工具
- 更有针对性的外部来源

这让 follow-up 的角色更清楚。

### 4.4 让 Skill 更像 runtime 治理层

这次升级后，Skill 的定位更完整了：

- 以前：场景配置层
- 现在：场景配置 + 阶段能力披露层

也就是说，它不只是回答“当前是什么场景”，还开始回答：

- 当前阶段应该暴露什么能力
- 为什么只暴露这些能力

---

## 5. 这次升级和 Goal Summary 的关系

这次升级和第二次升级里的 Goal Summary 并不冲突，反而是互补关系。

- Goal Summary 负责“任务主线”
- 渐进式披露 Skill 负责“阶段能力治理”

可以这样理解：

- Goal Summary 回答：我们在做什么、做到哪了、下一步是什么
- Progressive Skill Disclosure 回答：当前阶段该让 Agent 看到哪些能力

所以：

- Goal Summary 是主线层
- 渐进式披露 Skill 是能力治理层

---

## 6. 面试时怎么讲这次升级

你可以这样说：

> 我之前已经把 Skill 做成了场景配置层，但它还是偏静态，任务一开始就会暴露该场景下的大部分能力。后面我继续往下看时，发现这会带来一个问题，就是不同阶段的能力边界不够清楚。比如 data analysis 阶段本来应该先聚焦数据本身，但如果一开始就把全部能力都暴露出来，模型更容易发散。所以我又把 Skill 升级成了渐进式披露模型，也就是按阶段逐步开放能力。  
> 比如 data analysis 阶段主要开放结构化数据工具，economist review 阶段开放轻量检索和有限外部 source，只有 follow-up 阶段才开放更深的数据补分析能力，writer 阶段则主要开放来源引用能力。这样做以后，Skill 就不只是场景配置层，而是开始承担 runtime 的阶段能力治理职责。

---

## 7. 一句话总结

这次升级的本质是：

**把 Skill 从“静态场景配置”升级成“按阶段渐进式披露能力的运行时治理层”。**

