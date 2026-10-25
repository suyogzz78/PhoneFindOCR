/**
 * Tiny typed client for the FastAPI OCR service.
 * Uses Node's built-in fetch / FormData / Blob (Node 18+), so no extra HTTP library.
 */
import { phoneExtractConfig } from './config';

/** Exactly what FastAPI returns (snake_case). */
export interface OcrJob {
  job_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  filename: string;
  pages_done: number;
  total_pages: number;
  percent: number;
  phones_found: number;
  phones: string[] | null;
  failed_pages: number[];
  error: string | null;
}

/** An error we can show to the user, with the HTTP status Express should answer with. */
export class OcrServiceError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'OcrServiceError';
  }
}

async function call(path: string, init: RequestInit = {}): Promise<OcrJob> {
  let res: Response;
  try {
    const headers = new Headers(init.headers);
    if (phoneExtractConfig.internalToken) {
      headers.set('X-OCR-Token', phoneExtractConfig.internalToken);
    }
    res = await fetch(`${phoneExtractConfig.ocrServiceUrl}${path}`, {
      ...init,
      headers,
      signal: AbortSignal.timeout(phoneExtractConfig.requestTimeoutMs),
    });
  } catch (err) {
    console.error('[phoneExtract] OCR service unreachable:', err);
    throw new OcrServiceError('The text-recognition service is unavailable right now.', 503);
  }

  if (!res.ok) {
    // FastAPI errors look like {"detail": "..."}
    let detail = 'Text recognition failed.';
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* keep default */
    }
    // 4xx = the user's problem (bad file, queue full): pass the message through.
    // 5xx = ours: log details, show a generic message.
    if (res.status >= 500) {
      console.error('[phoneExtract] OCR service error', res.status, detail);
      throw new OcrServiceError('Text recognition failed. Please try again.', 502);
    }
    throw new OcrServiceError(detail, res.status);
  }
  return (await res.json()) as OcrJob;
}

export function submitJob(file: { buffer: Buffer; originalname: string; mimetype: string }) {
  const form = new FormData();
  form.append('file', new Blob([new Uint8Array(file.buffer)], { type: file.mimetype }), file.originalname);
  return call('/jobs', { method: 'POST', body: form });
}

export function getJob(jobId: string) {
  return call(`/jobs/${encodeURIComponent(jobId)}`);
}
