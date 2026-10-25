export const phoneExtractConfig = {
  ocrServiceUrl: (process.env.OCR_SERVICE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, ''),
  maxUploadMb: Number(process.env.OCR_MAX_UPLOAD_MB ?? 50),
  requestTimeoutMs: Number(process.env.OCR_REQUEST_TIMEOUT_MS ?? 30_000),
  internalToken: process.env.OCR_INTERNAL_TOKEN ?? '',
};

if (!Number.isInteger(phoneExtractConfig.maxUploadMb) || phoneExtractConfig.maxUploadMb <= 0) {
  throw new Error('OCR_MAX_UPLOAD_MB must be a positive integer');
}
if (!Number.isInteger(phoneExtractConfig.requestTimeoutMs) || phoneExtractConfig.requestTimeoutMs <= 0) {
  throw new Error('OCR_REQUEST_TIMEOUT_MS must be a positive integer');
}

export const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'];
