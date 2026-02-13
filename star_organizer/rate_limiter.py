import threading
import time


class RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._lock = threading.Lock()
        self._next_time = 0.0

    def acquire(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_time:
                    self._next_time = now + self.min_interval_seconds
                    return
                sleep_for = self._next_time - now
            time.sleep(sleep_for)

    def slow_down(self, factor: float = 1.5) -> None:
        with self._lock:
            self.min_interval_seconds = min(self.min_interval_seconds * factor, 5.0)

    def speed_up(self, factor: float = 0.9) -> None:
        with self._lock:
            self.min_interval_seconds = max(self.min_interval_seconds * factor, 0.1)
