.PHONY: help test install setup clean run

help:
	@echo "🎬 Video Variations System — Available Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          — Instalar dependências e preparar"
	@echo "  make test           — Testar sistema"
	@echo ""
	@echo "Uso:"
	@echo "  make run VIDEO=video.mp4 N=5         — Criar 5 variações"
	@echo "  make run VIDEO=video.mp4 N=20 W=8   — Criar 20 variações com 8 workers"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          — Limpar output/"
	@echo "  make docs           — Ver documentação"

setup:
	@echo "🔧 Instalando dependências..."
	@which ffmpeg > /dev/null || (echo "❌ FFmpeg não encontrado" && exit 1)
	@which python3 > /dev/null || (echo "❌ Python3 não encontrado" && exit 1)
	@chmod +x video_variations_system.py video_variations_from_config.py test_system.py
	@mkdir -p output
	@echo "✅ Setup concluído!"

test:
	@echo "🧪 Testando sistema..."
	@python3 test_system.py

run:
	@test -n "$(VIDEO)" || (echo "❌ Specify VIDEO: make run VIDEO=video.mp4" && exit 1)
	@test -f "$(VIDEO)" || (echo "❌ Arquivo não encontrado: $(VIDEO)" && exit 1)
	@echo "🎬 Processando $(VIDEO)..."
	@python3 video_variations_system.py $(VIDEO) -n $(N:-5) -w $(W:-4) $(EXTRA)

run-config:
	@test -n "$(VIDEO)" || (echo "❌ Specify VIDEO: make run-config VIDEO=video.mp4" && exit 1)
	@test -n "$(CONFIG)" || (echo "❌ Specify CONFIG: make run-config CONFIG=config.json" && exit 1)
	@test -f "$(VIDEO)" || (echo "❌ Arquivo não encontrado: $(VIDEO)" && exit 1)
	@test -f "$(CONFIG)" || (echo "❌ Arquivo não encontrado: $(CONFIG)" && exit 1)
	@echo "🎬 Processando com config customizada..."
	@python3 video_variations_from_config.py $(VIDEO) -c $(CONFIG) -w $(W:-4)

clean:
	@echo "🧹 Limpando output/..."
	@rm -rf output/*
	@mkdir -p output
	@echo "✅ Limpo!"

docs:
	@echo "📚 Documentação disponível:"
	@echo ""
	@ls -1 *.md 2>/dev/null | sed 's/^/  • /'
	@echo ""
	@echo "Abra com: cat README.md"

install-ffmpeg:
	@echo "📥 Instalando FFmpeg..."
	@if command -v brew >/dev/null 2>&1; then \
		brew install ffmpeg; \
	elif command -v apt-get >/dev/null 2>&1; then \
		sudo apt-get install ffmpeg; \
	else \
		echo "❌ Gerenciador de pacotes não identificado"; \
		echo "Manual: https://ffmpeg.org/download.html"; \
	fi
	@ffmpeg -version | head -1

install-python:
	@echo "📥 Instalando Python3..."
	@if command -v brew >/dev/null 2>&1; then \
		brew install python3; \
	elif command -v apt-get >/dev/null 2>&1; then \
		sudo apt-get install python3; \
	else \
		echo "❌ Gerenciador de pacotes não identificado"; \
		echo "Manual: https://www.python.org/downloads/"; \
	fi
	@python3 --version

quick-start:
	@echo "🚀 Quick Start — Video Variations System"
	@echo ""
	@echo "1. Verificar sistema:"
	@make test
	@echo ""
	@echo "2. Preparar vídeo de entrada:"
	@echo "   Coloque seu vídeo (video.mp4) nesta pasta"
	@echo ""
	@echo "3. Executar (criar 5 variações):"
	@echo "   make run VIDEO=video.mp4 N=5"
	@echo ""
	@echo "4. Verificar resultado:"
	@echo "   ls -lh output/"

benchmark:
	@echo "⚡ Benchmark — Testando performance"
	@test -f "test_video.mp4" || (echo "Criando vídeo de teste..." && ffmpeg -f lavfi -i color=c=blue:s=320x240:d=10 -f lavfi -i sine=f=1000:d=10 -c:v libx264 -preset ultrafast -c:a aac -y test_video.mp4 2>/dev/null)
	@echo ""
	@echo "Teste 1: 5 variações, 1 worker"
	@time python3 video_variations_system.py test_video.mp4 -n 5 -w 1
	@echo ""
	@echo "Teste 2: 5 variações, 4 workers"
	@rm -rf output/*
	@time python3 video_variations_system.py test_video.mp4 -n 5 -w 4
	@echo ""
	@echo "✅ Benchmark concluído!"

report:
	@test -f "output/report.json" || (echo "❌ Nenhum relatório encontrado. Execute: make run" && exit 1)
	@echo "📊 Relatório de Processamento:"
	@cat output/report.json | python3 -m json.tool
