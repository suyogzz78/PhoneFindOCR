
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from pydantic import BaseModel

from .config import Settings
from .jobs import Job, JobStore, run_job
from .ocr import load_engine
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
        app.state.jobs = JobStore(settings.job_ttl_seconds)
        app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        log.info("Ready.")
        
        #use of yield here as it marks a boundary between the setup and teardown phases of the lifespan context manager. The code before yield is executed when the application starts up, and the code after yield is executed when the application is shutting down. This allows for proper resource management, such as cleaning up threads or closing connections when the application is stopped.
        yield
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="OCR Service", lifespan=lifespan)
# this creates fastapi initialized app and connects it to the start/shutdown function
    @app.get("/health")
    def health(request: Request):
        st = request.app.state
        return {
            "status": "ok",
            "model_loaded": hasattr(st, "engine"),
            "stub": settings.use_stub,
            "active_jobs": st.jobs.active_count(),
        }

   
    @app.post("/jobs", response_model=JobOut, status_code=202)
    def create_job(request: Request, file: UploadFile):
        st = request.app.state
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
        st.executor.submit(run_job, job, content, info, st.engine, settings)
        return to_out(job)

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str, request: Request):
        job = request.app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found ")
        return to_out(job)

    return app


app = create_app()
