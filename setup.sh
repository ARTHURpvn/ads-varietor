#!/bin/bash

# Setup do Video Variations System

echo "🔧 Instalando dependências..."

# Verifica se Python 3 está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale com:"
    echo "   Mac: brew install python3"
    echo "   Linux: sudo apt install python3"
    exit 1
fi

# Verifica se FFmpeg está instalado
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg não encontrado. Instale com:"
    echo "   Mac: brew install ffmpeg"
    echo "   Linux: sudo apt install ffmpeg"
    exit 1
fi

echo "✅ Python 3 encontrado: $(python3 --version)"
echo "✅ FFmpeg encontrado: $(ffmpeg -version | head -1)"

# Cria diretório de saída
mkdir -p ./output
chmod +x video_variations_system.py

echo ""
echo "✅ Setup concluído!"
echo ""
echo "📖 Como usar:"
echo "   python3 video_variations_system.py <video.mp4> -n 5 -w 4"
echo ""
echo "Opções:"
echo "   -n, --num-variations  Número de variações (padrão: 5)"
echo "   -w, --workers         Processadores paralelos (padrão: 4)"
echo "   -o, --output          Diretório de saída (padrão: ./output)"
echo "   --overlay-video       Vídeo para overlay"
echo "   --save-config         Salva configurações em JSON"
