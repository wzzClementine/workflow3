from app.infrastructure.ocr.tencent_ocr_client import TencentOCRClient
from app.infrastructure.ocr.iflytek_ocr_client import IflytekOCRClient
from app.infrastructure.ocr.xfyun_llm_ocr import OCRForLLMClient

__all__ = ["TencentOCRClient", "IflytekOCRClient", "OCRForLLMClient"]