from __future__ import annotations


class ConfirmationPolicy:
    CONFIRM_KEYWORDS = {
        "确认",
        "确认无误",
        "没问题",
        "可以",
        "对的",
        "正确",
        "是的",
        "继续",
        "继续吧",
        "开始",
        "开始处理",
        "开始吧",
        "ok",
        "okay",
        "yes",
    }

    REJECT_KEYWORDS = {
        "不对",
        "不正确",
        "有问题",
        "不行",
        "重新上传",
        "重新来",
        "错了",
        "有误",
    }

    def is_confirm_message(self, text: str | None) -> bool:
        if not text:
            return False

        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CONFIRM_KEYWORDS)

    def is_reject_message(self, text: str | None) -> bool:
        if not text:
            return False

        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.REJECT_KEYWORDS)