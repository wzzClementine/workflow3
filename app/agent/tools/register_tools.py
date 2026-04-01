from app.agent.tools.tool_registry import ToolRegistry
from app.skills.send_feishu_message import send_feishu_message
from app.skills.task_create import task_create
from app.skills.task_excel_upload import handle_excel_upload
from app.skills.task_update_status import task_update_status
from app.agent.tools.impl.get_task_state import get_task_state
from app.agent.tools.impl.check_missing_materials import check_missing_materials
from app.agent.tools.impl.attach_last_uploaded_file_to_task import attach_last_uploaded_file_to_task
from app.agent.tools.impl.render_pdf_pages_from_task import render_pdf_pages_from_task
from app.agent.tools.impl.summarize_task_materials import summarize_task_materials


tool_registry = ToolRegistry()

tool_registry.register_tool(
    name="task_create",
    description="创建一个新的任务",
    handler=task_create,
)

tool_registry.register_tool(
    name="task_update_status",
    description="更新任务状态",
    handler=task_update_status,
)

tool_registry.register_tool(
    name="task_excel_upload",
    description="上传 Excel 并触发 试卷切割任务",
    handler=handle_excel_upload,
)

tool_registry.register_tool(
    name="send_feishu_message",
    description="发送飞书消息",
    handler=send_feishu_message,
)

tool_registry.register_tool(
    name="get_task_state",
    description="获取任务当前状态，包括memory和artifact",
    handler=get_task_state,
)

tool_registry.register_tool(
    name="check_missing_materials",
    description="检查任务缺失的材料，比如solution_pdf等",
    handler=check_missing_materials,
)

tool_registry.register_tool(
    name="attach_last_uploaded_file_to_task",
    description="将 session 中最近上传的文件自动关联到当前任务；args: {chat_id: str, task_id: str}",
    handler=attach_last_uploaded_file_to_task,
)

tool_registry.register_tool(
    name="render_pdf_pages_from_task",
    description="根据 task_id 自动查找 blank_pdf 和 solution_pdf 并渲染页图；args: {task_id: str, dpi: int}",
    handler=render_pdf_pages_from_task,
)

tool_registry.register_tool(
    name="summarize_task_materials",
    description="汇总当前任务绑定的材料信息，包括 excel、blank_pdf、solution_pdf 的文件名和 PDF 页数；args: {task_id: str}",
    handler=summarize_task_materials,
)

