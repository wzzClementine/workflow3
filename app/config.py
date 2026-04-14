import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "workflow3"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bot_name: str = "Workflow3 Agent Bot"
    ngrok_public_url: str = ""

    volcengine_api_key: str = ""
    volcengine_base_url: str = ""
    volcengine_model: str = "ark-code-latest"

    feishu_drive_folder_token: str = ""

    sqlite_db_path: str = "./runtime_data/workflow3.db"
    data_root: str = "./runtime_data"

    tencent_secret_id: str = ""
    tencent_secret_key: str = ""
    tencent_region: str = "ap-beijing"
    tencent_endpoint: str = ""
    tencent_service: str = ""
    tencent_version: str = ""

    llm_provider: str = "volcengine"
    llm_mock_mode: bool = True

    # 讯飞 OCR 配置
    iflytek_app_id: str = ""
    iflytek_api_key: str = ""
    iflytek_api_secret: str = ""

    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "")
    qwen_text_model: str = os.getenv("QWEN_TEXT_MODEL", "qwen-plus")
    qwen_vision_model: str = os.getenv("QWEN_VISION_MODEL", "qwen-vl-plus")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def data_root_path(self) -> Path:
        return Path(self.data_root).resolve()

    @property
    def sqlite_db_path_obj(self) -> Path:
        return Path(self.sqlite_db_path).resolve()

    @property
    def logs_dir(self) -> Path:
        return self.data_root_path / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.data_root_path / "temp"

    @property
    def uploads_dir(self) -> Path:
        return self.data_root_path / "uploads"

    @property
    def tasks_dir(self) -> Path:
        return self.data_root_path / "tasks"


settings = Settings()