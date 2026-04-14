from __future__ import annotations


class ConfirmationPolicy:
    CONFIRM_KEYWORDS = {
        "确认",
        "确认无误",
        "没问题",
        "可以",
        "行",
        "好的",
        "好",
        "对的",
        "对",
        "正确",
        "是的",
        "是",
        "继续",
        "继续吧",
        "继续处理",
        "继续执行",
        "接着做",
        "往下做",
        "开始",
        "开始处理",
        "开始吧",
        "执行吧",
        "执行",
        "跑吧",
        "跑",
        "上传吧",
        "上传",
        "继续上传",
        "上传最新结果",
        "现在上传",
        "打包吧",
        "重新打包吧",
        "生成吧",
        "重新生成吧",
        "ok",
        "okay",
        "yes",
    }

    REJECT_KEYWORDS = {
        "不对",
        "不正确",
        "有问题",
        "不行",
        "错了",
        "有误",
        "不用了",
        "不用",
        "先这样",
        "先不用",
        "不继续",
        "先不继续",
        "到这里",
        "先到这里",
        "先停一下",
        "停在这里",
        "不用继续",
        "先不做了",
        "不需要",
        "算了",
        "先别做了",
        "别做了",
        "暂时不用",
        "先不用上传",
        "不上传",
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