# Imagem da API. Multi-stage: as ferramentas de build (compilador, pip,
# cabeçalhos) ficam no primeiro estágio e não viajam para a imagem final.

# --- Estágio 1: dependências ---------------------------------------------
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

# --- Estágio 2: runtime ---------------------------------------------------
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

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_DIR=/data \
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
