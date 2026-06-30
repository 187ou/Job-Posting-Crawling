"""反反爬虫 — UA池 + 速率限制"""
import time
import random
import threading

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

SITE_DELAYS = {"zhaopin": 2.0}


class RateLimiter:
    """域名级限速 + 指数退避

    - base_delay < 1.0 时启用"微抖动"模式：实际延迟在 [base_delay, base_delay*1.8] 随机
    - base_delay >= 1.0 时沿用旧策略：固定延迟 + 10%~50% 抖动
    """
    def __init__(self):
        self._last_request: dict[str, float] = {}
        self._backoff_until: dict[str, float] = {}
        self._backoff_count: dict[str, int] = {}
        self._lock = threading.Lock()

    def wait(self, domain, base_delay=None):
        if base_delay is None:
            base_delay = SITE_DELAYS.get(domain, 2.0)
        sleep_needed = 0.0
        with self._lock:
            now = time.time()
            until = self._backoff_until.get(domain, 0)
            if now < until:
                sleep_needed = until - now + random.uniform(0, 1)
            else:
                last = self._last_request.get(domain, 0)
                elapsed = now - last
                if elapsed < base_delay:
                    if base_delay < 1.0:
                        # 微抖动模式：不累积固定延迟，只补随机余量
                        target = base_delay * random.uniform(1.0, 1.8)
                        sleep_needed = max(target - elapsed, 0)
                    else:
                        sleep_needed = base_delay - elapsed + base_delay * random.uniform(0.1, 0.5)
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        with self._lock:
            self._last_request[domain] = time.time()

    def backoff(self, domain, base_seconds=5.0):
        """指数退避: base * 2^n, max 120秒"""
        with self._lock:
            count = self._backoff_count.get(domain, 0) + 1
            self._backoff_count[domain] = count
            delay = min(base_seconds * (2 ** (count - 1)), 120)
            self._backoff_until[domain] = time.time() + delay

    def reset_backoff(self, domain):
        """成功请求后重置退避计数"""
        with self._lock:
            self._backoff_count.pop(domain, None)
            self._backoff_until.pop(domain, None)


def get_random_ua():
    return random.choice(USER_AGENTS)


def build_headers(source=None):
    headers = {
        "User-Agent": get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if source == "zhaopin":
        headers["Referer"] = "https://sou.zhaopin.com/"
        headers["Host"] = "sou.zhaopin.com"
    return headers
