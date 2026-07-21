/** Contratos da API v1 do gerador de variações de vídeo. */

export type JobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired';

export type VariationStatus = 'pending' | 'running' | 'completed' | 'failed';

/**
 * Como cada saída é produzida.
 * - `full`: reprocessa o vídeo aplicando efeitos. A imagem muda; leva minutos.
 * - `metadata_only`: copia o conteúdo e só reescreve os metadados. A imagem e
 *   o som ficam idênticos; muda apenas o hash. Leva menos de um segundo.
 */
export type ProcessingMode = 'full' | 'metadata_only';

export interface VariationParams {
  speed: number;
  filter_type: string;
  filter_value: number;
  background_color: string;
  video_scale: number;
  noise_audio: boolean;
}

export interface Variation {
  variation_id: string;
  status: VariationStatus;
  error: string | null;
  size_bytes: number | null;
  /** MD5 do arquivo gerado. null enquanto a variação não terminou. */
  md5: string | null;
  params: VariationParams;
}

export interface JobProgress {
  total: number;
  completed: number;
  failed: number;
}

export interface CreatedJob {
  job_id: string;
  status: 'pending';
  num_variations: number;
  mode: ProcessingMode;
  created_at: string;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  num_variations: number;
  mode: ProcessingMode;
  /** MD5 do arquivo enviado, para comparar com o de cada saída. */
  source_md5: string | null;
  created_at: string;
  updated_at: string;
  /** Motivo da falha do trabalho inteiro. null quando não falhou. */
  error: string | null;
  progress: JobProgress;
  variations: Variation[];
}

export interface HealthStatus {
  /** 'degraded' quando o FFmpeg não está acessível no servidor. */
  status: 'ok' | 'degraded';
  /**
   * Apesar do nome, a API devolve aqui a disponibilidade do FFmpeg
   * ('disponível' / 'indisponível'), não o número da versão. O nome da
   * chave é contrato da API e por isso é mantido como está.
   */
  ffmpeg_version: string;
}

/** Corpo de erro conforme RFC 9457 (application/problem+json). */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
}

const TERMINAL_JOB_STATUSES: readonly JobStatus[] = [
  'completed',
  'failed',
  'cancelled',
  'expired',
];

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_JOB_STATUSES.includes(status);
}
