from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routes.feishu_webhook import router as feishu_router
from app.utils.file_utils import init_runtime_dirs
from app.utils.logger import setup_logger

from app.db.sqlite_manager import sqlite_manager


logger = setup_logger(settings.log_level, settings.logs_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime_dirs = init_runtime_dirs(settings.data_root_path)

    logger.info("Runtime directories initialized: %s", runtime_dirs)
    logger.info("Application starting...")
    logger.info("APP_NAME: %s", settings.app_name)
    logger.info("APP_ENV: %s", settings.app_env)
    logger.info("APP_HOST: %s", settings.app_host)
    logger.info("APP_PORT: %s", settings.app_port)
    logger.info("DATA_ROOT: %s", settings.data_root_path)
    logger.info("SQLITE_DB_PATH: %s", settings.sqlite_db_path_obj)
    logger.info("VOLCENGINE_MODEL: %s", settings.volcengine_model)
    logger.info("NGROK_PUBLIC_URL: %s", settings.ngrok_public_url)

    sqlite_manager.init_db()
    logger.info("SQLite database initialized successfully.")

    yield

    logger.info("Application shutting down...")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "status": "ok",
    }


app.include_router(feishu_router)