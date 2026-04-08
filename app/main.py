from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.infrastructure.db import SQLiteManager, init_db_schema
from app.infrastructure.llm import MockLLMClient
from app.infrastructure.ocr import OCRForLLMClient, TencentOCRClient
from app.infrastructure.feishu import (
    FeishuAuthClient,
    FeishuDriveClient,
    FeishuMessageFileClient,
    FeishuMessageSender,
)
from app.infrastructure.llm.qwen_text_client import QwenTextClient
from app.infrastructure.llm.qwen_vision_client import QwenVisionClient

from app.repositories.task_repo import TaskRepository
from app.repositories.session_repo import ChatSessionRepository
from app.repositories.memory_repo import TaskMemoryRepository
from app.repositories.file_repo import TaskFileRepository
from app.repositories.delivery_repo import DeliveryRecordRepository

from app.services.task import TaskService
from app.services.session import ChatSessionService
from app.services.memory import TaskMemoryService
from app.services.file import TaskFileService
from app.services.delivery import DeliveryService

from app.agent.memory import MemoryFacade
from app.agent.planner import PlannerInputBuilder, LLMPlanner
from app.agent.policies import ConfirmationPolicy
from app.agent.tools import ToolRegistry, ToolExecutor
from app.agent.orchestrator import AgentOrchestrator

from app.skills.task import ManageTaskTool
from app.skills.ingestion import IngestMaterialsTool
from app.skills.rendering import PDFRenderer
from app.skills.segmentation import QuestionSegmenter, AnalysisSegmenter, AnalysisCleaner
from app.skills.processing import ProcessPaperTool
from app.skills.delivery import DeliverResultsTool
from app.skills.ingestion.file_fetch_service import FileFetchService
from app.skills.manifest import BuildManifestTool
from app.skills.excel import WriteExcelTool
from app.skills.packaging import PackagingTool

from app.interfaces.api import agent_router
from app.interfaces.feishu.feishu_webhook import router as feishu_router


def build_app_components() -> dict:
    # ========= DB =========
    sqlite_manager = SQLiteManager(settings.sqlite_db_path_obj)
    init_db_schema(sqlite_manager)

    # ========= repositories =========
    task_repository = TaskRepository(sqlite_manager)
    session_repository = ChatSessionRepository(sqlite_manager)
    memory_repository = TaskMemoryRepository(sqlite_manager)
    file_repository = TaskFileRepository(sqlite_manager)
    delivery_record_repository = DeliveryRecordRepository(sqlite_manager)

    # ========= services =========
    task_service = TaskService(
        task_repository=task_repository,
        task_memory_repository=memory_repository,
    )
    session_service = ChatSessionService(
        chat_session_repository=session_repository,
    )
    memory_service = TaskMemoryService(
        task_memory_repository=memory_repository,
    )
    file_service = TaskFileService(
        task_file_repository=file_repository,
    )

    # ========= infra =========
    llm_client = QwenTextClient()
    vision_llm_client = QwenVisionClient()
    ocr_client_for_cleaner = TencentOCRClient()
    ocr_client = OCRForLLMClient()

    feishu_auth_client = FeishuAuthClient()

    feishu_message_sender = FeishuMessageSender(auth_client=feishu_auth_client)

    feishu_message_file_client = FeishuMessageFileClient(
        auth_client=feishu_auth_client,
    )
    file_fetch_service = FileFetchService(
        feishu_message_file_client=feishu_message_file_client,
    )

    feishu_drive_client = FeishuDriveClient(auth_client=feishu_auth_client)

    delivery_service = DeliveryService(
        drive_client=feishu_drive_client,
        delivery_record_repository=delivery_record_repository,
    )

    # ========= agent helper =========
    memory_facade = MemoryFacade(
        task_service=task_service,
        chat_session_service=session_service,
        task_memory_service=memory_service,
        task_file_service=file_service,
    )

    planner_input_builder = PlannerInputBuilder()
    llm_planner = LLMPlanner(
        llm_client=llm_client,
        planner_input_builder=planner_input_builder,
    )

    confirmation_policy = ConfirmationPolicy()

    # ========= skill instances =========
    pdf_renderer = PDFRenderer()
    question_segmenter = QuestionSegmenter(ocr_client=ocr_client)
    analysis_segmenter = AnalysisSegmenter()
    analysis_cleaner = AnalysisCleaner(ocr_client=ocr_client_for_cleaner)

    # ========= tools =========
    tool_registry = ToolRegistry()

    tool_registry.register(
        ManageTaskTool(task_service=task_service)
    )

    tool_registry.register(
        IngestMaterialsTool(
            task_file_service=file_service,
            task_service=task_service,
            task_memory_service=memory_service,
            file_fetch_service=file_fetch_service,
        )
    )

    tool_registry.register(
        ProcessPaperTool(
            task_file_service=file_service,
            task_service=task_service,
            task_memory_service=memory_service,
            pdf_renderer=pdf_renderer,
            question_segmenter=question_segmenter,
            analysis_segmenter=analysis_segmenter,
            analysis_cleaner=analysis_cleaner,
        )
    )

    tool_registry.register(
        BuildManifestTool(
            task_service=task_service,
            task_memory_service=memory_service,
            vision_llm_client=vision_llm_client,
        )
    )

    tool_registry.register(
        WriteExcelTool(
            task_service=task_service,
            task_memory_service=memory_service,
        )
    )

    tool_registry.register(
        PackagingTool(
            task_service=task_service,
            task_memory_service=memory_service,
        )
    )

    tool_registry.register(
        DeliverResultsTool(
            delivery_service=delivery_service,
            task_service=task_service,
            task_memory_service=memory_service,
        )
    )

    tool_executor = ToolExecutor(tool_registry=tool_registry)

    orchestrator = AgentOrchestrator(
        task_service=task_service,
        chat_session_service=session_service,
        memory_facade=memory_facade,
        llm_planner=llm_planner,
        tool_executor=tool_executor,
        confirmation_policy=confirmation_policy,
        feishu_message_sender=feishu_message_sender,
    )

    return {
        "sqlite_manager": sqlite_manager,
        "task_service": task_service,
        "session_service": session_service,
        "memory_service": memory_service,
        "file_service": file_service,
        "delivery_service": delivery_service,
        "tool_registry": tool_registry,
        "tool_executor": tool_executor,
        "orchestrator": orchestrator,
        "vision_llm_client": vision_llm_client,
        "feishu_message_sender": feishu_message_sender,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    components = build_app_components()

    for key, value in components.items():
        setattr(app.state, key, value)

    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {
        "app_name": settings.app_name,
        "status": "ok",
        "env": settings.app_env,
    }


app.include_router(agent_router)
app.include_router(feishu_router)