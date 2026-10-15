"""Process memory and timing helpers for the evaluation commands."""
import datetime
import json
import os
import platform
import threading
import time
from pathlib import Path

import psutil

_PROCESS = psutil.Process(os.getpid())
MB = 1024 * 1024


def rss_mb() -> float:
    """Resident memory of this process, in MB."""
    return _PROCESS.memory_info().rss / MB


class PeakMemorySampler:
    """Samples RSS on a background thread so short spikes inside a stage are caught.

    with PeakMemorySampler() as sampler:
        sampler.start_stage()
        ...work...
        peak = sampler.stage_peak()
    """

    def __init__(self, interval=0.01):
        self.interval = interval
        self._peak = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            current = rss_mb()
            with self._lock:
                self._peak = max(self._peak, current)
            self._stop.wait(self.interval)

    def start_stage(self):
        with self._lock:
            self._peak = rss_mb()

    def stage_peak(self) -> float:
        current = rss_mb()  # in case the stage was shorter than one sampling interval
        with self._lock:
            self._peak = max(self._peak, current)
            return self._peak

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


class Stage:
    """Times one stage and records RSS before/after and the peak in between."""

    def __init__(self, sampler: PeakMemorySampler):
        self.sampler = sampler

    def __enter__(self):
        self.rss_before = rss_mb()
        self.sampler.start_stage()
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self._started
        self.peak = self.sampler.stage_peak()
        self.rss_after = rss_mb()


def machine_info() -> dict:
    memory = psutil.virtual_memory()
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "ram_total_gb": round(memory.total / 1024 ** 3, 1),
        "python": platform.python_version(),
        "ocr_device": "CPU (EasyOCR gpu=False)",
    }


def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
