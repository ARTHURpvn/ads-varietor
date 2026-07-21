import { ApiError, type ErrorContext } from './errors.ts';
import type { ProblemDetails } from './types.ts';

/**
 * Base da API. Mesma origem de propósito: em dev o proxy do Vite
 * encaminha para o backend; em produção o reverse proxy injeta a
 * credencial. O frontend nunca lê nem envia API key.
 */
export const API_BASE_URL = '/api/v1';

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE';
  body?: BodyInit | undefined;
  context: ErrorContext;
  signal?: AbortSignal | undefined;
  accept?: string;
}

/** Executa a requisição e devolve a `Response` já validada. */
async function request(
  path: string,
  options: RequestOptions,
): Promise<Response> {
  const { method = 'GET', body, context, signal, accept } = options;

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      body: body ?? null,
      signal: signal ?? null,
      credentials: 'same-origin',
      headers: accept === undefined ? {} : { Accept: accept },
    });
  } catch (causa) {
    if (causa instanceof DOMException && causa.name === 'AbortError') {
      throw causa;
    }

    throw new ApiError({ status: null, context });
  }

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      context,
      problem: await lerProblemDetails(response),
      retryAfterSeconds: lerRetryAfter(response),
    });
  }

  return response;
}

export async function requestJson<T>(
  path: string,
  options: RequestOptions,
): Promise<T> {
  const response = await request(path, {
    ...options,
    accept: 'application/json',
  });

  return (await response.json()) as T;
}

export async function requestBlob(
  path: string,
  options: RequestOptions,
): Promise<Blob> {
  const response = await request(path, options);
  return await response.blob();
}

export async function requestEmpty(
  path: string,
  options: RequestOptions,
): Promise<void> {
  await request(path, options);
}

async function lerProblemDetails(
  response: Response,
): Promise<ProblemDetails | undefined> {
  const contentType = response.headers.get('Content-Type') ?? '';

  if (!contentType.includes('problem+json') && !contentType.includes('json')) {
    return undefined;
  }

  try {
    const corpo: unknown = await response.json();

    if (typeof corpo === 'object' && corpo !== null) {
      return corpo as ProblemDetails;
    }
  } catch {
    // Corpo inválido: seguimos com a mensagem genérica por status.
  }

  return undefined;
}

function lerRetryAfter(response: Response): number | undefined {
  const header = response.headers.get('Retry-After');

  if (header === null) {
    return undefined;
  }

  const segundos = Number.parseInt(header, 10);
  return Number.isFinite(segundos) ? segundos : undefined;
}
