from enum import Enum


class TaskState(str, Enum):
    CREATED = "created"
    COLLECTING_MATERIALS = "collecting_materials"
    WAITING_CONFIRMATION = "waiting_confirmation"
    PROCESSING = "processing"
    PACKAGING = "packaging"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"