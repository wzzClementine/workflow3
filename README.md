# 🧠 Workflow3 - Agent-Based Exam Processing System

## 📌 项目简介

Workflow3 是一个基于 **Agent 架构** 的自动试卷处理系统，集成飞书机器人作为交互入口，实现从 PDF 上传到结构化结果交付的全流程自动化处理。

系统支持用户通过飞书上传试卷与解析 PDF，并自动完成：

- PDF 转图片
- 试题切分 / 解析切分
- OCR 识别
- 多模态模型（Qwen-VL）提取答案与知识点
- manifest.json 构建
- Excel（tags.xlsx）生成
- 文件打包
- 上传飞书云盘
- 返回下载链接

---

## 🚀 核心能力

### ✅ 自动化试卷处理

完整流程：

```text
PDF → 图片 → 切题 → OCR → LLM解析 → 结构化 → Excel → 打包 → 上传
```


---

### ✅ Agent 对话能力

系统不仅是工具链，更是一个具备状态感知的 Agent：

支持：

- 当前任务理解
- 历史任务理解
- 材料状态感知
- 多轮对话驱动流程

---

### ✅ 任务控制能力

用户可以通过自然语言控制任务：

| 功能       | 示例            |
|----------|---------------|
| 取消任务     | `取消这个任务`      |
| 重新开始     | `重新开始`        |
| 查询当前任务   | `我当前任务是什么`    |
| 查询缺失材料   | `我目前有哪些任务缺材料` |
| 重新处理指定材料 | `重新生成任务指定材料`  |
| 重新打包上传材料 | `重新打包/上传任务材料` |

---

### ✅ 结果查询能力

| 查询类型 | 示例 |
|--------|------|
| 最近结果 | `把结果给我` |
| 当前任务结果 | `当前任务的下载链接` |
| 已完成任务链接 | `给我完成任务的访问链接` |

---

### ✅ 上传智能接管

系统自动判断用户上传行为：

| 当前状态 | 行为 |
|--------|------|
| collecting_materials | 补充材料 |
| waiting_confirmation | 覆盖/补充 |
| processing | 创建新任务 |
| completed / failed | 创建新任务 |

---

## 🏗️ 系统架构

### 总体架构
```text
Feishu Bot
↓
AgentOrchestrator（唯一入口）
↓
Planner（决策）
↓
MemoryFacade（上下文）
↓
Services（业务逻辑）
↓
Tools（执行）
↓
Repositories（数据持久化）
```

---

## 🧩 核心模块说明

### 1️⃣ AgentOrchestrator（核心控制器）

> 📍 唯一入口（Single Entry Point）

职责：

- 解析用户输入
- 判断用户意图
- 调度任务执行
- 控制任务生命周期
- 调用 Planner / Memory / Tools

---

### 2️⃣ MemoryFacade（记忆系统）

统一管理：

- 当前任务状态
- 历史任务
- 材料状态
- Agent Snapshot

核心能力：

- build_agent_snapshot()
- get_current_task_id()
- 多任务状态聚合

---

### 3️⃣ TaskService / SessionService

#### TaskService

- 创建任务
- 更新状态
- 查询任务

#### SessionService

- chat ↔ task 绑定
- 当前任务管理
- 会话状态管理

---

### 4️⃣ DeliveryService（交付层）

负责：

- 上传飞书云盘
- 生成交付记录（delivery_records）
- 提供下载链接

关键能力：

- get_latest_result_by_chat_id
- get_result_by_task_id
- get_completed_task_results_by_chat_id

---

### 5️⃣ Tools（执行层）

系统核心流水线：

| Tool | 功能 |
|------|------|
| process_paper | PDF处理 + 切题 |
| build_manifest | 构建结构数据 |
| write_excel | 生成 tags.xlsx |
| package_results | 打包结果 |
| deliver_results | 上传飞书 |

---

## 📦 数据结构设计

### tasks 表

| 字段 | 含义 |
|------|------|
| task_id | 任务ID |
| chat_id | 会话ID |
| status | 状态 |
| current_stage | 当前阶段 |

---

### task_memory 表

| 字段 | 含义 |
|------|------|
| current_stage | 当前阶段 |
| files_summary_json | 材料状态 |
| processing_summary | 文本摘要 |

---

### chat_sessions 表

| 字段 | 含义 |
|------|------|
| current_task_id | 当前任务 |
| current_mode | 状态 |
| waiting_for | 等待内容 |

---

### delivery_records 表

| 字段 | 含义 |
|------|------|
| task_id | 任务ID |
| remote_url | 下载链接 |
| delivery_status | 是否成功 |

---

## 🔁 任务生命周期
```text
collecting_materials
↓
waiting_confirmation
↓
processing
↓
completed / failed / cancelled
```


---

## 🧠 Agent能力分层

### ✅ B1：任务理解

- 当前任务
- 当前阶段
- 材料完整性

---

### ✅ B2：历史理解

- 历史任务
- 上次失败原因
- 重跑能力

---

### ✅ B3：交互能力

- 任务控制（取消/重启）
- 结果查询
- 上传接管
- 材料缺失分析

---
### ✅ B4：控制能力

- 重新生成任务指定材料
- 重新打包任务材料
- 重新上传任务材料

---

## ⚙️ 开发原则（非常重要）

### ❗ 架构约束

- 单入口：AgentOrchestrator
- Memory 驱动
- Tool 不做决策
- Service 不做对话

---

### ❗ 修改原则

- 不重构已有流程
- 最小侵入修改
- 不影响成功路径
- 所有新增逻辑必须可回退

---

## 🧪 测试建议

### 必测场景

- 单任务完整流程
- 多任务并发上传
- 中途取消任务
- 上传覆盖 / 新建任务
- 查询结果（当前 / 历史）

---

## 📈 后续优化方向

### 🔶 多任务可视化

- 每个任务独立进度
- 明确 task_id 映射

---

### 🔶 任务选择能力

- “操作第2个任务”
- “继续刚才那个任务”

---

## 🧑‍💻 技术栈

- Python
- FastAPI
- SQLite
- Feishu OpenAPI
- Qwen-VL（多模态模型）

---

## 📌 项目特点总结

✅ Agent 驱动 
✅ 多任务状态管理  
✅ 对话式任务控制  
✅ 结构清晰、可扩展  
✅ 工程级可维护  

---
