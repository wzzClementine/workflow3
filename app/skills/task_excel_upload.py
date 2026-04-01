"""
skills/task_excel_upload.py

功能：
- 接收用户上传的 Excel 文件（通过飞书或其他接口）
- 保存到对应 task 的 raw 目录
- 自动触发 generate_questions skill（切题、解析提取、清洗、Excel 对齐）
- 返回执行结果，更新 task 状态
"""

import shutil
from pathlib import Path

from app.skills.generate_questions import generate_questions
from app.skills.file_store import file_store_init_task_dirs
from app.skills.task_update_status import task_update_status


def handle_excel_upload(
    task_id: str,
    excel_local_path: str,
    overwrite: bool = True
) -> dict:
    """
    处理飞书上传的 Excel 文件并触发 Step10.4
    Args:
        task_id: 当前 task_id
        excel_local_path: 上传的 Excel 文件本地路径
        overwrite: 是否覆盖 task/raw/ 下已有 Excel 文件
    Returns:
        dict: {
            "message": str,
            "task_id": str,
            "excel_file": str,
            "step10_4_status": str
        }
    """
    result = {
        "task_id": task_id,
        "excel_file": "",
        "step10_4_status": "pending",
        "message": "",
    }

    try:
        # 1. 获取 task 的 raw 目录
        dirs = file_store_init_task_dirs(task_id)
        task_raw_dir = Path(dirs["task_root"]) / "raw"
        task_raw_dir.mkdir(parents=True, exist_ok=True)

        # 2. 规范化路径
        source_excel_path = Path(excel_local_path).resolve()
        if not source_excel_path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {source_excel_path}")

        excel_filename = source_excel_path.name
        target_excel_path = (task_raw_dir / excel_filename).resolve()

        # 3. 只有“源路径 != 目标路径”时才复制
        if source_excel_path != target_excel_path:
            if target_excel_path.exists() and overwrite:
                target_excel_path.unlink()

            shutil.copy(source_excel_path, target_excel_path)

        # 如果源路径已经在 task/raw/ 下，就直接复用，不再复制
        result["excel_file"] = str(target_excel_path)

        # 4. 更新 task 状态为 running
        task_update_status(task_id=task_id, status="running")

        # 5. 调用 generate_questions skill
        generate_questions(task_id=task_id, excel_path=str(target_excel_path))

        # 6. Step10.4 成功，更新 task 状态
        task_update_status(task_id=task_id, status="success")
        result["step10_4_status"] = "success"
        result["message"] = "Step10.4 已成功执行，单题图片生成完成。"

    except Exception as e:
        task_update_status(task_id=task_id, status="failed")
        result["step10_4_status"] = "failed"
        result["message"] = f"Step10.4 执行失败: {e}"

    return result