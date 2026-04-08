# 🧠 自动试卷处理 Agent 系统

本项目是一个基于 Agent 架构的自动试卷处理系统，支持从飞书上传 PDF → 自动解析 → 结构化 → 生成 Excel → 打包 → 回传飞书。

---

# 🧩 一、系统整体架构

```text
用户（飞书）
    ↓
Webhook
    ↓
AgentOrchestrator（核心调度）
    ↓
Tool（标准执行单元）
    ↓
Service / Builder（业务逻辑）
    ↓
Infrastructure（外部系统：OCR / LLM / 飞书）
    ↓
本地文件系统 + SQLite
```


# 二、完整处理流程
```text
1. 用户上传 PDF（飞书）
2. webhook 接收 → 转 AgentEvent
3. ingest_materials
   → 下载 PDF 到本地
4. waiting_confirmation
5. 用户确认
6. process_paper
   → PDF → 图片 → 切题 → 切解析 → 清洗
7. build_manifest（LLM）
8. write_excel
9. package_results
10. deliver_results（上传飞书）
```

## 📦 三、模块详细说明

---

### 1️⃣ Agent 层（核心控制）

#### 📄 `app/agent/orchestrator/agent_orchestrator.py`

**功能：**

* 系统核心调度器（大脑）
* 控制完整处理流程（Pipeline）
* 管理状态机（任务阶段）
* 调度 Tool 执行
* 推送飞书进度消息

**输入：**

```python
AgentEvent
```

**输出：**

```python
AgentResult
```

**核心职责：**

* 判断当前任务阶段（collecting / confirmation / processing）
* 串联完整流程：

  ```
  process_paper → build_manifest → write_excel → package → deliver
  ```
* 控制执行顺序
* 统一用户反馈（飞书）

---

#### 📄 `app/agent/schema/agent_event.py`

**功能：**
定义系统输入事件结构

**数据结构：**

```python
AgentEvent:
    chat_id
    event_type
    user_message
    files

UploadedFile:
    file_name
    file_key
    message_id
```

---

#### 📄 `app/agent/schema/agent_result.py`

**功能：**
定义系统输出结构

```python
AgentResult:
    status
    message
    task_id
    snapshot
```

---

### 2️⃣ Tool 层（执行单元）

> 所有 orchestrator 调用的模块必须是 Tool

---

#### 📄 `IngestMaterialsTool`

路径：`app/skills/ingestion/ingest_materials_tool.py`

**功能：**

* 解析飞书上传文件
* 下载 PDF 到本地
* 写入任务文件记录

**输入：**

```python
task_id
files[]
```

**输出：**

```python
materials_summary
```

---

#### 📄 `ProcessPaperTool`

路径：`app/skills/processing/process_paper_tool.py`

**功能：**
执行核心图像处理流程：

```
PDF → 图片 → 切题 → 切解析 → 清洗
```

**输出：**

```python
{
    task_root,
    question_output_root,
    analysis_output_root,
    cleaned_output_root
}
```

---

#### 📄 `BuildManifestTool`

路径：`app/skills/manifest/build_manifest_tool.py`

**功能：**

* 调用视觉 LLM
* 解析题目内容
* 构建结构化数据

**输入：**

```python
question_root_dir
analysis_root_dir
```

**输出：**

```json
manifest.json
```

---

#### 📄 `WriteExcelTool`

路径：`app/skills/excel/write_excel_tool.py`

**功能：**

* 将 manifest 转换为 Excel
* 按模板生成试卷结构表

**输入：**

```python
manifest_path
```

**输出：**

```python
excel_path
```

---

#### 📄 `PackagingTool`

路径：`app/skills/packaging/packaging_tool.py`

**功能：**
构建最终交付目录：

```
delivery/
    excel/
    question_images/
    analysis_images/
```

**输出：**

```python
local_package_path
```

---

#### 📄 `DeliverResultsTool`

路径：`app/skills/delivery/deliver_results_tool.py`

**功能：**

* 上传交付文件到飞书云
* 记录 delivery 信息

**输出：**

```python
remote_url
```

---

### 3️⃣ Service / Builder 层（业务逻辑）

---

#### 📄 `LLMManifestBuilder`

路径：`app/skills/manifest/manifest_builder.py`

**功能：**

* 调用视觉 LLM
* 解析题目结构
* 生成标准化数据

**输出结构：**

```json
{
  "question_type": "...",
  "answer": "...",
  "score": ...,
  "knowledge_points": [...]
}
```

---

#### 📄 `ExcelWriter`

路径：`app/skills/excel/excel_writer.py`

**功能：**

* 读取 manifest.json
* 写入 Excel 模板
* 生成结构化表格

---

#### 📄 `PackagingService`

路径：`app/skills/packaging/packaging_service.py`

**功能：**

* 整理输出文件
* 构建交付目录结构
* 复制资源文件

---

### 4️⃣ Infrastructure 层（外部系统）

---

#### 📄 `feishu_message_file_client.py`

**功能：**

```text
file_key → 下载本地文件
```

---

#### 📄 `feishu_drive_client.py`

**功能：**

```text
本地文件 → 上传飞书云盘
```

---

#### 📄 `feishu_message_sender.py`

**功能：**
发送飞书消息（进度推送）

示例：

```
📥 接收文件
🛠️ 处理中
🧠 分析中
📊 生成Excel
📦 打包
☁️ 上传
🎉 完成
```

---

#### 📄 `tencent_ocr_client.py`

**功能：**
图像 OCR 识别

---

#### 📄 `vision_llm_client.py`

**功能：**
多模态推理（图像 → 结构化数据）

---

### 5️⃣ 数据层

---

#### 📄 `sqlite_manager.py`

**功能：**
管理 SQLite 数据库

**主要表：**

* tasks
* task_files
* delivery_records
* memory

---

### 6️⃣ 工具层

---

#### 📄 `retry.py`

路径：`app/shared/utils/retry.py`

**功能：**
统一重试机制：

* LLM 请求失败
* OCR 失败
* 网络异常

---

### 7️⃣ API 层

---

#### 📄 `app/main.py`

**功能：**

* 初始化所有组件
* 注册 Tool
* 启动 FastAPI
* 注入 orchestrator

---

#### 📄 `feishu_webhook.py`

**功能：**

```text
飞书事件 → AgentEvent → orchestrator
```

---

## 📌 模块关系总结

```text
AgentOrchestrator
    ↓
Tool（统一执行入口）
    ↓
Service / Builder（业务逻辑）
    ↓
Infrastructure（外部系统）
    ↓
文件系统 / 数据库
```

---

## 🎯 核心设计原则

```
1. orchestrator 只负责流程控制
2. Tool 是唯一执行入口
3. Service 负责逻辑
4. Infrastructure 负责外部交互
```

