# Workflow3（完整工程说明文档）

用于实现：试卷解析制作 + 小程序上架 的自动化工作流

---

# 一、项目目标

实现从 PDF 到小程序数据的完整流水线：

PDF → 图片 → 切题 → OCR → Excel对齐 → JSON → 云端 → 小程序

---

# 二、整体流程（Step1-10）

## Step1-8（已完成）

基础设施：

- FastAPI 服务
- SQLite 数据库
- 文件系统
- Task任务流
- PDF渲染
- 飞书机器人

---

## Step9（人工）

- 上传 blank PDF
- OneNote 手写解析

---

## Step10（自动化）

### Step10.1
PDF → 图片

### Step10.2
生成：

- blank_pages
- solution_pages

---

### Step10.3
绑定任务 + 数据库

---

### Step10.4（已完成）

题目切割系统

输入：

- blank_pages
- solution_pages
- Excel

输出：

- blank_questions
- solution_questions

功能：

- OCR识别题号
- 投影补漏
- 裁剪边界
- 解析图清洗（覆盖原图）
- Excel对齐命名
- 写入questions表

---

### Step10.5（当前阶段）

JSON转换（核心）

目标：

将 Excel + 图片 转换为小程序 JSON

---

### Step10.6（待实现）

云端同步：

- 上传图片
- 上传JSON
- 返回URL

---

### Step10.7（待实现）

小程序读取 JSON

---

# 三、项目目录结构（最新）

```text
app/
 ├── db/
 │   ├── models.py
 │   └── sqlite_manager.py

 ├── routes/
 │   └── feishu_webhook.py

 ├── services/
 │   ├── feishu_service.py
 │   ├── llm_service.py
 │   ├── paper_service.py
 │   ├── pdf_render_service.py
 │   ├── question_service.py
 │   ├── storage_service.py
 │   ├── task_service.py
 │   └── webhook_event_service.py

 ├── skills/
 │   ├── file_store.py
 │   ├── generate_questions.py
 │   ├── import_pdf_to_workspace.py
 │   ├── render_pdf_pages.py
 │   ├── send_feishu_message.py
 │   ├── task_create.py
 │   ├── task_excel_upload.py
 │   └── task_update_status.py

 ├── utils/
 │   ├── clean_analysis_by_ocr.py
 │   ├── cut_questions_by_ocr.py
 │   ├── cut_solutions.py
 │   ├── download_file_from_feishu.py
 │   ├── file_utils.py
 │   ├── logger.py
 │   └── config.py

 └── main.py

runtime_data/
 ├── logs/
 ├── papers/
 │   └── task_xxx/
 │       ├── raw/
 │       ├── blank_pages/
 │       ├── solution_pages/
 │       ├── blank_questions/
 │       ├── solution_questions/
 │       ├── json/
 │       └── logs/
 └── temp/

workflow3.db


```
# 四、核心模块说明

## 1. routes 层

### feishu_webhook.py

**入口：**

```python
POST /feishu/event

**功能：**

- 接收飞书消息
- 解析 message_type（text/file）
- 调用 skill
- 触发任务流


---

## 2. services 层

### task_service.py

职责：任务管理

```python
create_task(created_by)
# 输入：用户ID
# 输出：task对象
```

```python
update_status(task_id, status)
```

```python
get_latest_task()
# 输出：最新任务
```


---

### paper_service.py

职责：试卷管理

```python
get_paper_by_task_id(task_id)
# 输出：paper
```

```python
update_json_path(paper_id, json_path)
```


---

### question_service.py

职责：题目管理

```python
upsert_question(...)
```

```python
get_questions_by_paper_id(paper_id)
# 输出：题目列表
```


---

### pdf_render_service.py

职责：

- PDF → 图片


---

### storage_service.py

职责：

- 路径生成 + 文件存储


---

### webhook_event_service.py（关键）

职责：飞书事件去重

```python
begin_event_once(event_key)
```

```python
update_event_status(event_key, status)
```


---

### feishu_service.py

职责：

- 飞书 API 调用
- token 获取


---

## 3. skills 层（核心执行层）

### task_create.py

创建任务


---

### task_update_status.py

更新任务状态


---

### file_store.py

创建任务目录：

- raw
- pages
- questions
- json


---

### import_pdf_to_workspace.py

导入 PDF 到 raw/


---

### render_pdf_pages.py

PDF → page 图片


---

### generate_questions.py（Step10.4核心）

输入：

- task_id
- Excel路径

输出：

- blank_questions
- solution_questions

流程：

1. OCR识别
2. 切题
3. 清洗解析
4. 命名
5. 写DB


---

### task_excel_upload.py

职责：

- 保存 Excel 到 raw/
- 触发 Step10.4


---

### send_feishu_message.py

发送消息


---

## 4. utils 层（算法核心）

### cut_questions_by_ocr.py

功能：

- OCR识别题号
- 定位题目区域


---

### cut_solutions.py

功能：

- 切解析图


---

### clean_analysis_by_ocr.py

功能：

- 删除题干文字
- 保留解析内容


---

### download_file_from_feishu.py

功能：

- 根据 file_key 下载文件


---

### config.py

功能：

- 读取 .env
- 提供配置（secret_id 等）


---

# 五、数据库设计

## tasks

- task_id
- status
- input_path
- output_path


---

## papers

- paper_id
- paper_name
- json_path
- publish_status


---

## questions

- question_no
- blank_image_path
- solution_image_path
- match_status


---

## webhook_events

- event_key
- status
- task_id