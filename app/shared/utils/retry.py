import time
import requests
from functools import wraps


def retry(func=None, retries=3, delay=1, backoff=2):
    """
    支持两种用法：

    1️⃣ 作为函数调用：
        retry(func, retries=3)

    2️⃣ 作为装饰器：
        @retry(retries=3)
        def xxx():
            ...
    """

    # -------- 情况1：作为装饰器使用 --------
    if func is None:
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                current_delay = delay

                for i in range(retries):
                    try:
                        return f(*args, **kwargs)
                    except (
                        requests.exceptions.Timeout,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.SSLError,
                        requests.exceptions.HTTPError,
                    ):
                        if i == retries - 1:
                            raise
                        time.sleep(current_delay)
                        current_delay *= backoff

            return wrapper
        return decorator

    # -------- 情况2：作为函数直接调用 --------
    else:
        current_delay = delay

        for i in range(retries):
            try:
                return func()
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.SSLError,
                requests.exceptions.HTTPError,
            ):
                if i == retries - 1:
                    raise
                time.sleep(current_delay)
                current_delay *= backoff