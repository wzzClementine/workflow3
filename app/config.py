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

    tencent_secret_id: str
    tencent_secret_key: str
    tencent_region: str = "ap-beijing"

    llm_provider: str = "volcengine"
    llm_mock_mode: bool = True

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
    def papers_dir(self) -> Path:
        return self.data_root_path / "papers"

    def validate_required_for_current_stage(self) -> None:
        missing = []

        if not self.app_name:
            missing.append("APP_NAME")
        if not self.data_root:
            missing.append("DATA_ROOT")
        if not self.sqlite_db_path:
            missing.append("SQLITE_DB_PATH")

        # Step 4 需要
        if not self.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not self.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.ngrok_public_url:
            missing.append("NGROK_PUBLIC_URL")

        if missing:
            raise ValueError(f"缺少必要配置: {', '.join(missing)}")


settings = Settings()
settings.validate_required_for_current_stage()