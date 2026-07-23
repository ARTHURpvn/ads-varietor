import { requestBlob, requestEmpty, requestJson } from './client.ts';
import type {
  CreatedJob,
  HealthStatus,
  Job,
  ProcessingMode,
} from './types.ts';

export interface SelecaoDeEfeitos {
  color: boolean;
  framing: boolean;
  speed: boolean;
  noise: boolean;
}

export interface CreateJobInput {
  file: File;
  numVariations: number;
  mode: ProcessingMode;
  efeitos: SelecaoDeEfeitos;
}

export async function createJob(input: CreateJobInput): Promise<CreatedJob> {
  const formData = new FormData();
  formData.append('file', input.file);
  formData.append('num_variations', String(input.numVariations));
  formData.append('mode', input.mode);
  formData.append('effect_color', String(input.efeitos.color));
  formData.append('effect_framing', String(input.efeitos.framing));
  formData.append('effect_speed', String(input.efeitos.speed));
  formData.append('effect_noise', String(input.efeitos.noise));

  return await requestJson<CreatedJob>('/jobs', {
    method: 'POST',
    body: formData,
    context: 'upload',
  });
}

export async function fetchJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<Job> {
  return await requestJson<Job>(`/jobs/${encodeURIComponent(jobId)}`, {
    context: 'status',
    signal,
  });
}

export async function cancelJob(jobId: string): Promise<void> {
  await requestEmpty(`/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
    context: 'cancel',
  });
}

export async function fetchVariationFile(
  jobId: string,
  variationId: string,
): Promise<Blob> {
  const path =
    `/jobs/${encodeURIComponent(jobId)}` +
    `/variations/${encodeURIComponent(variationId)}/download`;

  return await requestBlob(path, { context: 'download' });
}

export async function fetchJobArchive(jobId: string): Promise<Blob> {
  return await requestBlob(`/jobs/${encodeURIComponent(jobId)}/download`, {
    context: 'download',
  });
}

export async function fetchHealth(): Promise<HealthStatus> {
  return await requestJson<HealthStatus>('/health', { context: 'status' });
}
