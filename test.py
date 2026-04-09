from app.services.delivery import DeliveryService
from app.infrastructure.feishu import FeishuDriveClient
from app.repositories.delivery_repo import DeliveryRecordRepository

# 初始化依赖
drive_client = FeishuDriveClient()
delivery_repo = DeliveryRecordRepository()

delivery_service = DeliveryService(
    drive_client=drive_client,
    delivery_record_repository=delivery_repo,
)
# 你自己本地随便找一个已经打包好的目录
local_package_path = "runtime_data/BS-LJBS-2024-3星-10.zip"  # 改成你真实路径

result = delivery_service.deliver_package_to_feishu(
    local_package_path=local_package_path
)

print("==== DELIVERY RESULT ====")
print(result)