
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from .config import Settings
from .ocr import OcrEngine
from .processing import Inspected, extract

log = logging.getLogger("ocr.jobs")


@dataclass
class Job:
    id: str
    filename: str
    total_pages: int
    status: str = "queued"  #default value is queued ,other values are processing, done, failed which are changed in run_job function based on the status of the job
    pages_done: int = 0
    phones: list[str] = field(default_factory=list)
    phones_found: int = 0
    failed_pages: list[int] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


#@property is used to define a method that can be accessed like a attribute
   
# percent is used to calculate the percentage of pages processed in a job   
    @property
    def percent(self) -> int:
        if self.status == "done":
            return 100
        if self.total_pages == 0:
            return 0
        return min(99, int(self.pages_done * 100 / self.total_pages))

#active method is used to check if the job is still active or not, it returns True if the job is in queued or processing state, otherwise it returns False
    @property
    def active(self) ->bool:
         return self.status in ("queued", "processing")


class JobStore:
    def __init__(self, ttl_seconds: int):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self, filename: str, total_pages: int) -> Job:
        job = Job(id=uuid.uuid4().hex, filename=filename, total_pages=total_pages)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.active)

    def purge(self) -> None:
        cutoff = time.time() - self._ttl
        with self._lock:
            for jid in [
                j.id for j in self._jobs.values() if j.finished_at and j.finished_at < cutoff
            ]:
                del self._jobs[jid]


def run_job(job: Job, content: bytes, info: Inspected, engine: OcrEngine, settings: Settings) -> None:

    job.status = "processing"
    log.info("job %s started: %s (%d page(s))", job.id, job.filename, job.total_pages)

    def on_progress(done: int, total: int, found: int) -> None:
        job.pages_done = done
        job.phones_found = found

    try:
        result = extract(content, info, engine, settings, on_progress)
        job.phones = result.phones
        job.phones_found = len(result.phones)
        job.failed_pages = result.failed_pages
        job.status = "done"
        log.info("job %s done: %d number(s)", job.id, len(result.phones))
    except Exception:
        log.exception("job %s failed", job.id)
        job.error = "Could not read this file. It may be damaged or unreadable."
        job.status = "failed"
    finally:
        job.finished_at = time.time()
