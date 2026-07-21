# Imagem única: serve a interface e a API na mesma origem, num processo só.
#
# Multi-stage: Node e as ferramentas de build do Python ficam nos estágios
# iniciais e não viajam para a imagem final.

# --- Estágio 1: build do frontend ----------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /frontend

# Copiar só os manifestos primeiro aproveita o cache de camada: o npm ci só
# refaz quando as dependências mudam, não a cada alteração de código.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Estágio 2: dependências Python --------------------------------------
FROM python:3.13-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# O venv é copiado inteiro para o estágio final; assim a imagem de runtime
# não precisa de pip nem de toolchain.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install .

# --- Estágio 3: runtime ---------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# ffmpeg e ffprobe são requisito duro: a API se recusa a subir sem eles.
# tini garante que os processos de FFmpeg mortos virem zumbis nunca.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Usuário sem privilégio. O UID é fixo para casar com a permissão do volume
# nomeado quando ele é criado do lado do host.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
# A interface sai do estágio de build do Node e é servida pela própria API.
COPY --from=frontend /frontend/dist /app/frontend

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_DIR=/data \
    FRONTEND_DIR=/app/frontend \
    LOG_JSON=true

WORKDIR /app
RUN mkdir -p /data && chown -R app:app /data

USER app
VOLUME ["/data"]
EXPOSE 8037

# O /health não depende de autenticação justamente para servir aqui.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8037/api/v1/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]

# Um worker só: o semáforo global de FFmpeg vive na memória do processo, e
# com dois workers cada um abriria o próprio limite.
CMD ["uvicorn", "ads_varietor.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8037", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
