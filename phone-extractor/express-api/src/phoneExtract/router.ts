import path from 'node:path';
import { NextFunction, Request, Response, Router } from 'express';
import multer from 'multer';
import { ALLOWED_EXTENSIONS, phoneExtractConfig } from './config';
import { buildPhonesWorkbook } from './excel';
import { getJob, OcrJob, OcrServiceError, submitJob } from './ocrClient';

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const JOB_ID = /^[a-f0-9]{32}$/;

const upload = multer({
  storage: multer.memoryStorage(), // we forward the bytes straight to FastAPI
  limits: { fileSize: phoneExtractConfig.maxUploadMb * 1024 * 1024, files: 1 },
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ALLOWED_EXTENSIONS.includes(ext)) return cb(null, true);
    cb(new OcrServiceError('Please upload a PDF or an image (PNG, JPG, WEBP, TIFF).', 400));
  },
});

/** What we send to *your* frontend (camelCase, no internal details). */
function toClient(job: OcrJob) {
  return {
    jobId: job.job_id,
    status: job.status,
    filename: job.filename,
    percent: job.percent,
    pagesDone: job.pages_done,
    totalPages: job.total_pages,
    phonesFound: job.phones_found,
    phones: job.phones, // null until status === 'done'
    failedPages: job.failed_pages, // non-empty => result is partial
    error: job.error,
  };
}

function safeDownloadName(original: string): string {
  const stem = path.parse(original).name.replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '');
  return `${stem || 'phones'}_numbers.xlsx`;
}

export function createPhoneExtractRouter(): Router {
  const router = Router();

  // 1) Upload a file -> returns immediately with a jobId (OCR runs in the background).
  router.post('/jobs', upload.single('file'), async (req, res, next) => {
    try {
      if (!req.file) throw new OcrServiceError('Please choose a file to upload.', 400);
      const job = await submitJob(req.file);
      res.status(202).json(toClient(job));
    } catch (err) {
      next(err);
    }
  });

  // 2) Poll for progress / result.
  router.get('/jobs/:id', async (req, res, next) => {
    try {
      res.json(toClient(await getJob(validJobId(req.params.id))));
    } catch (err) {
      next(err);
    }
  });

  // 3) Download the Excel file (only when the job is done).
  router.get('/jobs/:id/download', async (req, res, next) => {
    try {
      const job = await getJob(validJobId(req.params.id));
      if (job.status === 'failed') throw new OcrServiceError(job.error ?? 'Processing failed.', 422);
      if (job.status !== 'done' || !job.phones) {
        throw new OcrServiceError('The file is still being processed.', 409);
      }
      const xlsx = await buildPhonesWorkbook(job.phones);
      res.setHeader('Content-Type', XLSX_MIME);
      res.setHeader('Content-Disposition', `attachment; filename="${safeDownloadName(job.filename)}"`);
      res.send(xlsx);
    } catch (err) {
      next(err);
    }
  });

  // Turn our errors + multer's errors into clean JSON: { "error": "..." }
  router.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof OcrServiceError) {
      res.status(err.status).json({ error: err.message });
      return;
    }
    if (err instanceof multer.MulterError) {
      const tooBig = err.code === 'LIMIT_FILE_SIZE';
      res.status(tooBig ? 413 : 400).json({
        error: tooBig ? `File is larger than ${phoneExtractConfig.maxUploadMb} MB.` : err.message,
      });
      return;
    }
    console.error('[phoneExtract] unexpected error:', err);
    res.status(500).json({ error: 'Something went wrong.' });
  });

  return router;
}

function validJobId(id: string): string {
  if (!JOB_ID.test(id)) throw new OcrServiceError('Job not found.', 404);
  return id;
}
