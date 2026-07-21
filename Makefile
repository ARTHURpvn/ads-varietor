.PHONY: help setup api frontend test run clean

VENV := .venv
PYTHON := $(VENV)/bin/python

help:
	@echo "Video Variations System"
	@echo ""
	@echo "  make setup      — cria o venv, instala o pacote e o frontend"
	@echo "  make api        — sobe a API em http://127.0.0.1:8000"
	@echo "  make frontend   — sobe o frontend em http://127.0.0.1:5173"
	@echo "  make test       — roda a suite de testes"
	@echo "  make run VIDEO=video.mp4 N=5 — gera variações pela CLI"
	@echo "  make clean      — remove artefatos de build e saídas locais"

setup:
	@command -v ffmpeg >/dev/null || (echo "FFmpeg não encontrado. Rode: brew install ffmpeg" && exit 1)
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(VENV)/bin/pip install -q -e ".[dev]"
	@test -f .env || (sed 's|^API_KEYS=.*|API_KEYS='"$$($(VENV)/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"'|' .env.example > .env && echo "Criado .env com uma API key gerada.")
	@cd frontend && npm install
	@echo "Pronto. Rode 'make api' e 'make frontend'."

api:
	@$(PYTHON) -m uvicorn video_variations.api.main:app --host 127.0.0.1 --port 8000

frontend:
	@cd frontend && npm run dev

test:
	@$(VENV)/bin/pytest -q

run:
	@test -n "$(VIDEO)" || (echo "Informe o vídeo: make run VIDEO=video.mp4" && exit 1)
	@$(VENV)/bin/video-variations "$(VIDEO)" -n $(or $(N),5) -w $(or $(W),4) -o $(or $(OUT),./output)

clean:
	@rm -rf output frontend/dist .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Limpo. O diretorio storage/ nao e tocado — apague manualmente se quiser."
