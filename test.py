from app.services.task_stage_service import task_stage_service

result = task_stage_service.get_task_stage("task_20260401_172008_5414")
print(result)