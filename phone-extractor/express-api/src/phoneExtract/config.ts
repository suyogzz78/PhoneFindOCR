export const phoneExtractConfig = {
  /** Where the FastAPI OCR service listens. Keep it on localhost / a private network. */
  ocrServiceUrl: (process.env.OCR_SERVICE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, ''),
  /** Max upload size accepted by Express (FastAPI enforces the same limit again). */
  maxUploadMb: Number(process.env.OCR_MAX_UPLOAD_MB ?? 50),
  /** How long to wait for FastAPI to answer a single quick call (submit / status). */
  requestTimeoutMs: Number(process.env.OCR_REQUEST_TIMEOUT_MS ?? 30_000),
};

export const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'];
