# 🎬 Video Variations System

**Sistema automático para criar múltiplas variações de vídeos rapidamente**

> Cria variações de vídeo (metadados, velocidade, filtros, fundo, ruído, overlay) em paralelo. Máximo 1 minuto por variação. Escalável para cloud.

## ⚡ TL;DR (30 segundos)

```bash
# 1. Instalar dependências
brew install ffmpeg python3  # Mac
# ou: sudo apt install ffmpeg python3  # Linux

# 2. Extrair arquivo
unzip video_variations_system.zip

# 3. Testar (opcional)
python3 test_system.py

# 4. Usar
python3 video_variations_system.py seu_video.mp4 -n 10
```

**Resultado:** 10 vídeos em `output/` com variações diferentes.

---

## 📦 O Que Você Recebeu

### Scripts Python
- **`video_variations_system.py`** — Script principal (gera variações aleatórias)
- **`video_variations_from_config.py`** — Processa usando arquivo JSON customizado
- **`test_system.py`** — Testa se sistema está instalado corretamente

### Utilitários
- **`Makefile`** — Comandos úteis (make run, make test, etc)
- **`setup.sh`** — Script de setup automático
- **`requirements.txt`** — Dependências Python (nenhuma obrigatória)

### Documentação
- **`QUICKSTART.md`** — 📍 **COMECE AQUI** — 5 minutos para começar
- **`INSTALLATION.md`** — Instalação detalhada por SO
- **`README.md`** — Documentação completa
- **`ARCHITECTURE.md`** — Como funciona internamente
- **`EXAMPLES.md`** — Casos de uso práticos

### Exemplos
- **`config_example.json`** — Exemplo de configuração customizada

---

## 🚀 Quick Start (5 minutos)

### 1. Instalar Dependências

**Mac:**
```bash
brew install ffmpeg python3
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg python3
```

**Windows (WSL):**
```bash
# No WSL Ubuntu:
sudo apt install ffmpeg python3
```

### 2. Verificar Instalação

```bash
python3 test_system.py
# Deve retornar: ✅ TODOS OS TESTES PASSARAM!
```

### 3. Seu Primeiro Processamento

```bash
# Processar 5 variações do seu vídeo
python3 video_variations_system.py seu_video.mp4 -n 5

# Resultado em output/
ls output/
# var_001_*.mp4
# var_002_*.mp4
# var_003_*.mp4
# var_004_*.mp4
# var_005_*.mp4
# report.json
```

**Tempo:** 2-3 minutos

---

## 🎯 O Que o Sistema Faz

Cria variações automáticas de cada vídeo:

✅ **1. Metadados** — Título, autor (evita duplicação)  
✅ **2. Velocidade + Filtro** — Speed 1.0-1.05x + cores (brightness, contrast, etc)  
✅ **3. Fundo + Transparência** — Cor aleatória, ajusta escala do vídeo  
✅ **4. Ruído de Áudio** — Adiciona ruído leve (opcional)  
✅ **5. Overlay** — Sobrepõe outro vídeo (ex: logo) com transparência  

**Resultado:** Todos visualmente diferentes, mas mantêm conteúdo original.

---

## 📊 Exemplos de Uso

### Básico (5 variações)
```bash
python3 video_variations_system.py video.mp4 -n 5
# ⏱️ 2-3 minutos
```

### Médio (20 variações)
```bash
python3 video_variations_system.py video.mp4 -n 20 -w 8
# ⏱️ 5-6 minutos (8 processadores paralelos)
```

### Grande (100 variações)
```bash
python3 video_variations_system.py video.mp4 -n 100 -w 8
# ⏱️ 12-15 minutos
```

### Com Logo/Watermark
```bash
python3 video_variations_system.py video.mp4 \
  --overlay-video logo.mp4 -n 15
# Adiciona logo em todas as 15 variações
```

### Usar Configuração Customizada
```bash
python3 video_variations_from_config.py video.mp4 -c config_example.json
# Processa usando parâmetros específicos
```

---

## 🛠️ Opções Disponíveis

```bash
python3 video_variations_system.py VIDEO [OPTIONS]

OPTIONS:
  -n, --num-variations    Número de variações (padrão: 5)
  -w, --workers          Processadores paralelos (padrão: 4)
  -o, --output           Diretório de saída (padrão: ./output)
  --overlay-video        Vídeo para overlay (opcional)
  --save-config          Salva configurações em JSON
  -h, --help            Mostra ajuda
```

---

## 📚 Documentação

Leia nesta ordem:

1. **QUICKSTART.md** — Como começar
2. **README.md** — Guia completo
3. **EXAMPLES.md** — Casos de uso práticos
4. **ARCHITECTURE.md** — Como funciona
5. **INSTALLATION.md** — Troubleshooting

```bash
cat QUICKSTART.md    # Começar agora
cat README.md        # Documentação completa
cat EXAMPLES.md      # Casos práticos
```

---

## ⚡ Performance

| Variações | Workers | Tempo |
|-----------|---------|-------|
| 5 | 4 | 2-3 min |
| 10 | 4 | 3-4 min |
| 20 | 8 | 5-6 min |
| 50 | 8 | 12-15 min |
| 100 | 8 | 20-25 min |

**Máximo 1 minuto por variação** ✓

---

## 🐛 Se Algo Não Funcionar

### Erro: "FFmpeg não encontrado"
```bash
brew install ffmpeg  # Mac
# ou: sudo apt install ffmpeg  # Linux
```

### Erro: "Python3 não encontrado"
```bash
brew install python3  # Mac
# ou: sudo apt install python3  # Linux
```

### Erro: "Timeout (> 2 minutos)"
```bash
# Tenta com menos workers:
python3 video_variations_system.py video.mp4 -n 1 -w 1

# Ou comprimir vídeo original:
ffmpeg -i video.mp4 -vf scale=960:540 video_small.mp4
python3 video_variations_system.py video_small.mp4 -n 5
```

### Erro: "Espaço em disco insuficiente"
```bash
# Processar em lotes:
python3 video_variations_system.py video.mp4 -n 5
python3 video_variations_system.py video.mp4 -n 5 -o ./batch2
```

**Mais ajuda:** Veja `INSTALLATION.md` seção Troubleshooting

---

## 💡 Usar com Makefile (Mais Fácil)

Se preferir comandos mais simples:

```bash
# Ver comandos disponíveis
make help

# Setup
make setup

# Testar
make test

# Criar 10 variações
make run VIDEO=video.mp4 N=10

# Usar config customizada
make run-config VIDEO=video.mp4 CONFIG=config.json
```

---

## ☁️ Usar na Cloud (AWS/Google Cloud)

O sistema está pronto para cloud! Veja `README.md` seção "Deploy em Cloud" para:
- AWS Lambda
- Google Cloud Functions
- Docker containerization

---

## 📖 Próximas Leituras

1. **Começar agora:** `cat QUICKSTART.md`
2. **Documentação:** `cat README.md`
3. **Exemplos:** `cat EXAMPLES.md`
4. **Técnico:** `cat ARCHITECTURE.md`
5. **Install:** `cat INSTALLATION.md`

---

## ✅ Checklist

- [ ] FFmpeg instalado (`ffmpeg -version`)
- [ ] Python 3.8+ instalado (`python3 --version`)
- [ ] Arquivo extraído em pasta
- [ ] Testes passam (`python3 test_system.py`)
- [ ] Primeiro vídeo processado (`make run VIDEO=... N=5`)

---

## 🎯 O que você pode fazer agora

✅ **Gerar variações de vídeos rapidamente** (< 1 min cada)  
✅ **Processar múltiplos em paralelo** (4-8 ao mesmo tempo)  
✅ **Contornar detecção de conteúdo duplicado** (Content ID)  
✅ **A/B testing de vídeos** (testar qual converte melhor)  
✅ **Escalar para cloud** (AWS, Google Cloud, etc)  
✅ **Customizar parâmetros** (via JSON)  

---

## 🚀 Começar Agora

```bash
# 1. Instale FFmpeg
brew install ffmpeg

# 2. Teste o sistema
python3 test_system.py

# 3. Processe seu primeiro vídeo
python3 video_variations_system.py seu_video.mp4 -n 5

# 4. Verifique resultado
ls -lh output/
```

**Tempo total:** ~10 minutos (5 min setup + 5 min primeiro vídeo)

---

## 📞 Suporte

Dúvidas ou problemas?

1. **Leia a documentação** — QUICKSTART.md, README.md, INSTALLATION.md
2. **Teste o sistema** — `python3 test_system.py`
3. **Veja exemplos** — EXAMPLES.md
4. **Entenda a arquitetura** — ARCHITECTURE.md

---

## 📝 Licença

MIT (Use livremente, comercial ou pessoal)

---

**Última atualização:** 2026-07-21  
**Versão:** 1.0  
**Status:** Pronto para usar ✅

---

**Clique em:** [`QUICKSTART.md`](QUICKSTART.md) para começar agora!
