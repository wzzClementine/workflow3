import os
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件
load_dotenv()


class Config:
    """
    OpenClaw 全局配置中心
    所有敏感信息均从 .env 读取，不在此处硬编码。
    """

    # --- 1. 飞书 (Lark) 配置 ---
    LARK_APP_ID = os.getenv("LARK_APP_ID")
    LARK_APP_SECRET = os.getenv("LARK_APP_SECRET")
    LARK_FOLDER_TOKEN = os.getenv("LARK_FOLDER_TOKEN")

    # --- 2. 阿里云 Qwen 配置 (从 .env 读取) ---
    QWEN_API_KEY = os.getenv("QWEN_API_KEY")
    QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    QWEN_MODEL_NAME = os.getenv("QWEN_MODEL_NAME", "qwen-plus")

    # --- 3. 路径配置 (自动定位 E 盘项目目录) ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # 论文存储目录
    PAPERS_DIR = os.path.join(BASE_DIR, "papers")
    # 结果输出目录
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")

    # 自动创建必要的文件夹 (防止初次运行报错)
    @classmethod
    def init_folders(cls):
        for path in [cls.PAPERS_DIR, cls.OUTPUT_DIR]:
            if not os.path.exists(path):
                os.makedirs(path)
                print(f"📁 已自动创建文件夹: {path}")


# 初始化文件夹
Config.init_folders()