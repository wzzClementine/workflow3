from app.infrastructure.ocr.xfyun_llm_ocr import OCRForLLMClient

client = OCRForLLMClient()

result = client.general_ocr("page_4.png")

texts = client.get_text_detections(result)

for item in texts:
    print(item["DetectedText"])