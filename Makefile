.PHONY: help setup api frontend test run clean \
        docker-build docker-up docker-down docker-logs \
        storage-backup storage-usage storage-purge

VENV := .venv
PYTHON := $(VENV)/bin/python

help:
	@echo "ADS Varietor"
	@echo ""
	@echo "  make setup      — cria o venv, instala o pacote e o frontend"
	@echo "  make api        — sobe a API em http://127.0.0.1:8037"
	@echo "  make frontend   — sobe o frontend em http://127.0.0.1:5173"
	@echo "  make test       — roda a suite de testes"
	@echo "  make run VIDEO=video.mp4 N=5 — gera variações pela CLI"
	@echo "  make clean      — remove artefatos de build e saídas locais"
	@echo ""
	@echo "Deploy (Docker):"
	@echo "  make docker-build   — constrói as imagens (api e web)"
	@echo "  make docker-up      — sobe a stack; interface na porta 8037"
	@echo "  make docker-down    — derruba os containers (volume preservado)"
	@echo "  make docker-logs    — acompanha os logs JSON da API"
	@echo ""
	@echo "Operação do storage:"
	@echo "  make storage-usage  — mostra o espaço ocupado pelo volume"
	@echo "  make storage-backup — gera backup.tar.gz do volume nomeado"
	@echo "  make storage-purge  — APAGA todo o conteúdo do volume (pede confirmação)"

setup:
	@command -v ffmpeg >/dev/null || (echo "FFmpeg não encontrado. Rode: brew install ffmpeg" && exit 1)
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(VENV)/bin/pip install -q -e ".[dev]"
	@test -f .env || (sed 's|^API_KEYS=.*|API_KEYS='"$$($(VENV)/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"'|' .env.example > .env && echo "Criado .env com uma API key gerada.")
	@cd frontend && npm install
	@echo "Pronto. Rode 'make api' e 'make frontend'."

api:
	@$(PYTHON) -m uvicorn ads_varietor.api.main:app --host 127.0.0.1 --port 8037

frontend:
	@cd frontend && npm run dev

test:
	@$(VENV)/bin/pytest -q

run:
	@test -n "$(VIDEO)" || (echo "Informe o vídeo: make run VIDEO=video.mp4" && exit 1)
	@$(VENV)/bin/ads-varietor "$(VIDEO)" -n $(or $(N),5) -w $(or $(W),4) -o $(or $(OUT),./output)

clean:
	@rm -rf output frontend/dist .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Limpo. O diretorio storage/ nao e tocado — apague manualmente se quiser."

# --- Deploy ---------------------------------------------------------------

DOCKER_VOLUME := $(shell basename $(CURDIR) | tr 'A-Z' 'a-z')_storage
BACKUP_FILE ?= storage-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz

docker-build:
	@docker compose build

# O frontend é buildado dentro da imagem web, então não há passo de build
# no host. Fora do Coolify a porta precisa ser publicada: o override abaixo
# faz isso só no uso local, sem sujar o compose que vai para a plataforma.
docker-up:
	@printf 'services:\n  app:\n    ports:\n      - "8037:8037"\n' > .compose.local.yml
	@docker compose -f docker-compose.yml -f .compose.local.yml up -d
	@echo "Subiu em http://127.0.0.1:8037 — acompanhe com 'make docker-logs'."

docker-down:
	@docker compose down
	@echo "Containers parados. O volume '$(DOCKER_VOLUME)' foi preservado."

docker-logs:
	@docker compose logs -f api

# --- Operação do storage --------------------------------------------------

storage-usage:
	@docker compose exec api du -sh /data /data/uploads /data/jobs 2>/dev/null || \
		echo "A API precisa estar rodando: make docker-up"

# Backup a frio: o tar roda num container efêmero montando o mesmo volume,
# então não depende de a API estar de pé.
storage-backup:
	@docker run --rm \
		-v $(DOCKER_VOLUME):/data:ro \
		-v "$(CURDIR)":/backup \
		alpine tar czf /backup/$(BACKUP_FILE) -C /data .
	@echo "Backup gravado em ./$(BACKUP_FILE)"

# Restaurar: docker run --rm -v $(DOCKER_VOLUME):/data -v "$(CURDIR)":/backup \
#              alpine tar xzf /backup/<arquivo>.tar.gz -C /data
storage-purge:
	@echo "AÇÃO CRÍTICA"
	@echo "Operação  : apaga TODO o conteúdo do volume $(DOCKER_VOLUME)"
	@echo "Impacto   : todos os vídeos e variações são perdidos (o banco também)"
	@echo "Reversível: Não"
	@printf "Confirma? (s/n) " && read resposta && test "$$resposta" = "s"
	@docker compose down
	@docker volume rm $(DOCKER_VOLUME)
	@echo "Volume removido. Ele é recriado vazio no próximo 'make docker-up'."
