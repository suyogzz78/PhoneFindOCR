
import logging
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

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
    incomplete_phones: list[str] = field(default_factory=list)
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
#constructor fo the Jobstore class, it initializes the job store with a time-to-live (TTL) value in seconds. It also creates an empty dictionary to hold the jobs and a lock to ensure thread safety when accessing the job store.
    def __init__(self, ttl_seconds: int):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

#create method 
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

    def save(self, job: Job) -> None:
        """Compatibility hook for durable stores."""

    def enqueue(self, job: Job, content: bytes, info: Inspected) -> None:
        raise NotImplementedError

"""Adding a retry logic such that the job is retried twice if it fails , and if it fails for the third time it is marked as failed,befroe this  one job could go in an inifinite loop of failing  """
MAX_RETRIES = 2
class RedisJobStore:
    """Durable FIFO queue and job state shared by API/worker processes."""

    def __init__(self, url: str, ttl_seconds: int):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("REDIS_URL is configured but the redis package is missing") from exc
        self._redis = redis.Redis.from_url(url, decode_responses=False)
        self._ttl = ttl_seconds
        self._prefix = "phone-extractor:"
        self._queue = self._prefix + "queue"
        self._active = self._prefix + "active"
        #secondary
        self._processing = self._prefix + "processing"
        self._redis.ping()

    def _key(self, job_id: str) -> str:  
        return self._prefix + "job:" + job_id

    def _decode(self, raw: bytes | str) -> Job:
        data = json.loads(raw)
        return Job(**data)

    def create(self, filename: str, total_pages: int) -> Job:
        job = Job(id=uuid.uuid4().hex, filename=filename, total_pages=total_pages)
        self._redis.set(self._key(job.id), json.dumps(job.__dict__), ex=self._ttl)
        self._redis.sadd(self._active, job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        raw = self._redis.get(self._key(job_id))
        return self._decode(raw) if raw else None

    def save(self, job: Job) -> None:
        self._redis.set(self._key(job.id), json.dumps(job.__dict__), ex=self._ttl)
        if not job.active:
            self._redis.srem(self._active, job.id)

    def active_count(self) -> int:
        return self._redis.scard(self._active)

    def purge(self) -> None:
        # Expiration is handled by Redis; this is intentionally a no-op.
        pass

    def enqueue(self, job: Job, content: bytes, info: Inspected) -> None:
        payload = json.dumps({"pages": info.pages, "kind": info.kind})
        pipe = self._redis.pipeline()
        pipe.set(self._prefix + "content:" + job.id, content, ex=self._ttl)
        pipe.set(self._prefix + "info:" + job.id, payload, ex=self._ttl)
        pipe.rpush(self._queue, job.id)
        pipe.execute()

    def requeue_unfinished(self)->None:

        while self._redis.lmove(self._processing,self._queue,"RIGHT","LEFT"):
            pass

    def claim(self, timeout: int = 1) -> tuple[Job, bytes, Inspected] | None:
        item = self._redis.blmove(self._queue, self._processing, timeout, "LEFT","RIGHT")
        if not item:
            return None
        job_id = item.decode() if isinstance(item, bytes) else item
        job = self.get(job_id)
        content = self._redis.get(self._prefix + "content:" + job_id)
        raw_info = self._redis.get(self._prefix + "info:" + job_id)
        if job is None or not isinstance(content, bytes) or raw_info is None:
            log.error("Redis queue item %s is incomplete", job_id)
            self._abandon(job_id, job)
            return None
        info_data = json.loads(raw_info)
        return job, content, Inspected(info_data["kind"], info_data["pages"])



    def _abandon(self, job_id:str , job:Job |None) ->None :
        
        if job is not None:
            job.status ="failed"
            job.error ="Processing interrupted. Please upload again"
            job.finished_at= time.time()
            self.save(job)
        self._redis.srem(self._active,job_id)
        self._redis.lrem(self._processing,1,job_id)



    def close_job_data(self, job_id: str) -> None:
        self._redis.delete(
            self._prefix + "content:" + job_id,
            self._prefix + "info:" + job_id,
        )
        self._redis.lrem(self._processing,1 , job_id)


def run_job(
    job: Job,
    content: bytes,
    info: Inspected,
    engine: OcrEngine,
    settings: Settings,
    save: Callable[[Job], None] | None = None,
) -> None:
    save = save or (lambda _job: None)

    job.status = "processing"
    save(job)
    log.info("job %s started: %s (%d page(s))", job.id, job.filename, job.total_pages)

    def on_progress(done: int, total: int, found: int) -> None:
        job.pages_done = done
        job.phones_found = found
        save(job)

    try:
        result = extract(content, info, engine, settings, on_progress)
        job.phones = result.phones
        job.phones_found = len(result.phones)
        job.incomplete_phones = result.incomplete_phones
        job.failed_pages = result.failed_pages
        job.status = "done"
        save(job)
        log.info("job %s done: %d number(s)", job.id, len(result.phones))
    except Exception:
        log.exception("job %s failed", job.id)
        job.error = "Could not read this file. It may be damaged or unreadable."
        job.status = "failed"
        save(job)
    finally:
        job.finished_at = time.time()
        save(job)
