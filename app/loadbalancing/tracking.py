import os
import threading
from dataclasses import dataclass


@dataclass
class ServerTier:
    name: str
    max_active_requests: int
    target_response_time_ms: int

    @classmethod
    def from_env(cls, raw: str | None) -> 'ServerTier':
        key = (raw or 'MEDIUM').strip().upper()
        tiers = {
            'SMALL': cls('SMALL', 64, 200),
            'MEDIUM': cls('MEDIUM', 128, 150),
            'MONSTER': cls('MONSTER', 256, 100),
        }
        return tiers.get(key, tiers['MEDIUM'])


class RequestConcurrencyTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_requests = 0
        self._in_flight_compute_units = 0

    def on_request_started(self, compute_units: int) -> None:
        units = max(1, int(compute_units))
        with self._lock:
            self._active_requests += 1
            self._in_flight_compute_units += units

    def on_request_finished(self, compute_units: int) -> None:
        units = max(1, int(compute_units))
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._in_flight_compute_units = max(0, self._in_flight_compute_units - units)

    @property
    def active_requests(self) -> int:
        with self._lock:
            return self._active_requests

    @property
    def in_flight_compute_units(self) -> int:
        with self._lock:
            return self._in_flight_compute_units


class ResponseTimeEwmaTracker:
    ALPHA = 0.2

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ewma_millis = 0

    def record(self, duration_ms: int) -> None:
        if duration_ms < 0:
            return
        with self._lock:
            if self._ewma_millis <= 0:
                self._ewma_millis = duration_ms
            else:
                updated = round(self.ALPHA * duration_ms + (1.0 - self.ALPHA) * self._ewma_millis)
                self._ewma_millis = max(0, updated)

    @property
    def ewma_millis(self) -> int:
        with self._lock:
            return self._ewma_millis


tracker = RequestConcurrencyTracker()
ewma_tracker = ResponseTimeEwmaTracker()
