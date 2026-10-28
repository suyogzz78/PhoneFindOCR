
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

from .config import Settings
from .jobs import Job, JobStore, RedisJobStore, run_job
from .ocr import OcrEngine, load_engine
from .processing import UploadError, inspect_upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ocr")

#Pydantic model
class JobOut(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "failed"] 
    filename: str
    pages_done: int
    total_pages: int
    percent: int
    phones_found: int
    phones: list[str] | None  # only show the extracted phone numbers if the job is done completely
    incomplete_phones: list[str] | None = None
    failed_pages: list[int]  # pages that could not be read (result may be partial)
    error: str | None


def to_out(job: Job) -> JobOut:
    return JobOut(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        filename=job.filename,
        pages_done=job.pages_done,
        total_pages=job.total_pages,
        percent=job.percent,
        phones_found=job.phones_found,
        phones=job.phones if job.status == "done" else None,
        incomplete_phones=getattr(job, "incomplete_phones", []) if job.status == "done" else None,
        failed_pages=job.failed_pages,
        error=job.error,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Runs once at startup, loads the model, set up the job store and the worker.
        log.info("Loading OCR engine (%s)", "STUB" if settings.use_stub else "IndicOCR")
        app.state.settings = settings
        app.state.engine = load_engine(settings)
        app.state.jobs = (
            RedisJobStore(settings.redis_url, settings.job_ttl_seconds)
            if settings.redis_url
            else JobStore(settings.job_ttl_seconds)
        )
        app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        app.state.stop_event = threading.Event()
        if settings.redis_url:
            app.state.executor.submit(redis_worker, app.state.jobs, app.state.engine, settings, app.state.stop_event)
        log.info("Ready.")
        
        #use of yield here as it marks a boundary between the setup and teardown phases of the lifespan context manager. The code before yield is executed when the application starts up, and the code after yield is executed when the application is shutting down. This allows for proper resource management, such as cleaning up threads or closing connections when the application is stopped.
        yield
        app.state.stop_event.set()
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="OCR Service", lifespan=lifespan)
# this creates fastapi initialized app and connects it to the start/shutdown function
    def require_internal_token(token: str | None) -> None:
        if settings.internal_token and token != settings.internal_token:
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    def health(request: Request, x_ocr_token: str | None = Header(default=None)):
        st = request.app.state
        require_internal_token(x_ocr_token)
        return {
            "status": "ok",
            "model_loaded": hasattr(st, "engine"),
            "stub": settings.use_stub,
            "active_jobs": st.jobs.active_count(),
        }

   
    @app.post("/jobs", response_model=JobOut, status_code=202)
    def create_job(
        request: Request,
        file: UploadFile,
        x_ocr_token: str | None = Header(default=None),
    ):
        st = request.app.state
        require_internal_token(x_ocr_token)
        st.jobs.purge() # we remove the expired jobs from the job store to free up the memory so it doesnt grow forever.


        if st.jobs.active_count() >= settings.max_queued_jobs:
            raise HTTPException(429, "The OCR queue is full. Please try again in a few minutes.")

        content = file.file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
        if not content:
            raise HTTPException(400, "The uploaded file is empty")

        try:
            info = inspect_upload(content, settings)
        except UploadError as e:
            raise HTTPException(400, str(e))

        job = st.jobs.create(file.filename or "upload", info.pages)
        if settings.redis_url:
            st.jobs.enqueue(job, content, info)
        else:
            st.executor.submit(run_job, job, content, info, st.engine, settings, st.jobs.save)
        return to_out(job)

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(
        job_id: str,
        request: Request,
        x_ocr_token: str | None = Header(default=None),
    ):
        require_internal_token(x_ocr_token)
        job = request.app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found ")
        return to_out(job)

    return app


app = create_app()


def redis_worker(
    store: RedisJobStore,
    engine: OcrEngine,
    settings: Settings,
    stop_event: threading.Event,
) -> None:
    # while not stop_event.is_set():
    #     claimed = store.claim(timeout=1)
    #     if claimed is None:
    #         continue
    #     job, content, info = claimed
    #     run_job(job, content, info, engine, settings, store.save)
    #     store.close_job_data(job.id)
    store.requeue_unfinished()
    while not stop_event.is_set():
        try:
            claimed = store.claim(timeout=1)
        
        except Exception :
            log.exception("Redis worker error")
            stop_event.wait(2)
            continue
        if claimed is None:
            continue
        job,content ,info = claimed
        
        try:
            run_job(job,content,info,engine,settings,store.save)
            store.close_job_data(job.id)
        
        except Exception:
            log.exception("job %s worker error", job.id)

            


