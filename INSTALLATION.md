# 📦 Installation & Setup Guide

Guia completo para instalar e configurar o Video Variations System.

## 📋 Pré-requisitos

- **Python 3.8+**
- **FFmpeg 4.0+**
- **Espaço em disco:** ~10GB mínimo (para processar vários vídeos)
- **Memória RAM:** 4GB (recomendado 8GB+)
- **CPU:** Multi-core recomendado (4+ cores)

## 🚀 Instalação Rápida (5 minutos)

### 1️⃣ Mac (Recomendado: Homebrew)

```bash
# Instalar dependências
brew install python3 ffmpeg

# Verificar instalação
python3 --version      # Deve retornar 3.8+
ffmpeg -version        # Deve retornar versão

# Navegar para pasta do projeto
cd ~/seu_projeto_videos
```

### 2️⃣ Linux (Ubuntu/Debian)

```bash
# Atualizar pacotes
sudo apt update && sudo apt upgrade -y

# Instalar dependências
sudo apt install python3 python3-pip ffmpeg

# Verificar
python3 --version
ffmpeg -version
```

### 3️⃣ Linux (Fedora/RHEL)

```bash
# Instalar dependências
sudo dnf install python3 ffmpeg

# Verificar
python3 --version
ffmpeg -version
```

### 4️⃣ Windows (WSL Recomendado)

```bash
# Abrir Windows Terminal com WSL Ubuntu

# Instalar dependências (Ubuntu)
sudo apt update && sudo apt install python3 ffmpeg

# Verificar
python3 --version
ffmpeg -version
```

Se preferir usar Windows nativamente:
1. Instale [Python 3](https://www.python.org/downloads/)
2. Instale [FFmpeg](https://ffmpeg.org/download.html)
3. Adicione ambos ao PATH

## 📁 Estrutura do Projeto

```
video-variations-system/
├── 📜 video_variations_system.py          ← Script principal
├── 📜 video_variations_from_config.py     ← Usar arquivo de config
├── 🧪 test_system.py                      ← Testar instalação
├── Makefile                               ← Comandos úteis
├── requirements.txt                       ← Dependências Python
├── 📋 README.md                           ← Documentação completa
├── 📋 QUICKSTART.md                       ← Começar em 5 min
├── 📋 ARCHITECTURE.md                     ← Como funciona
├── 📋 EXAMPLES.md                         ← Casos de uso
├── 📋 INSTALLATION.md                     ← Este arquivo
├── config_example.json                    ← Exemplo de config
└── output/                                ← Vídeos processados
```

## 🔧 Setup Detalhado

### Passo 1: Clonar/Baixar Projeto

```bash
# Opção 1: Clonar do GitHub (quando disponível)
git clone https://github.com/seu_usuario/video-variations-system.git
cd video-variations-system

# Opção 2: Baixar manual
# Baixe os arquivos e extraia em uma pasta
cd ~/Downloads/video-variations-system
```

### Passo 2: Verificar Dependências

```bash
# Verificar Python
python3 --version
# Deve retornar: Python 3.8.0+ (mínimo)

# Verificar FFmpeg
ffmpeg -version
# Deve retornar: ffmpeg version 4.0+ (mínimo)

# Se não tiver, instale:
# Mac: brew install python3 ffmpeg
# Linux: sudo apt install python3 ffmpeg
# Windows: Ver instruções acima
```

### Passo 3: Setup do Sistema

#### Opção A: Usar Makefile (Mac/Linux)

```bash
# Setup automático
make setup

# Testar
make test

# Resultado esperado: ✅ TODOS OS TESTES PASSARAM!
```

#### Opção B: Manual

```bash
# Criar diretório de saída
mkdir -p output

# Dar permissão de execução
chmod +x video_variations_system.py
chmod +x video_variations_from_config.py
chmod +x test_system.py

# Testar
python3 test_system.py

# Resultado esperado: ✅ TODOS OS TESTES PASSARAM!
```

### Passo 4: Verificar Instalação

```bash
# Executar suite de testes
python3 test_system.py

# Ou usando Makefile:
make test
```

**Output esperado:**
```
============================================================
  🔧 Video Variations System — Test Suite
============================================================

📋 Testando Dependências do Sistema...
[✓ PASS] Python Version
        └─ Python 3.11.2
[✓ PASS] FFmpeg Installed
        └─ ffmpeg version 6.0
[✓ PASS] Disk Space
        └─ 250.5GB disponível

📦 Testando Módulos Python...
[✓ PASS] Module: json
[✓ PASS] Module: subprocess
[✓ PASS] Module: concurrent.futures
[✓ PASS] Module: pathlib

🔍 Testando Funcionalidades...
[✓ PASS] File Permissions
[✓ PASS] Video Creation
[✓ PASS] Script: video_variations_system.py
[✓ PASS] Output Directory

📊 Resumo dos Testes
✓ Passou: 11/11
✗ Falhou: 0/11

✅ TODOS OS TESTES PASSARAM!

🚀 Sistema pronto para usar:
   python3 video_variations_system.py seu_video.mp4 -n 5
```

## 🐛 Troubleshooting de Instalação

### Erro: "FFmpeg não encontrado"

**Mac:**
```bash
brew install ffmpeg
# Ou
brew install ffmpeg --with-options
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Fedora/RHEL
sudo dnf install ffmpeg
```

**Windows (WSL):**
```bash
sudo apt install ffmpeg
```

**Verificar:**
```bash
ffmpeg -version
which ffmpeg  # Deve retornar o caminho
```

---

### Erro: "Python3 não encontrado"

**Mac:**
```bash
brew install python3
# Ou use python diretamente (geralmente Python 3 já vem)
python --version
```

**Linux:**
```bash
sudo apt install python3
```

**Windows:**
1. Baixe em https://www.python.org/downloads/
2. Ao instalar, marque "Add Python to PATH"
3. Reinicie o terminal

**Verificar:**
```bash
python3 --version
which python3  # Deve retornar o caminho
```

---

### Erro: "ModuleNotFoundError"

O sistema não usa dependências externas! Se ocorrer erro:

```bash
# Tente rodar com python (sem o 3)
python video_variations_system.py video.mp4 -n 5

# Ou reinstale Python:
# Mac: brew reinstall python3
# Linux: sudo apt install --reinstall python3
```

---

### Erro: "Permissão negada" (Mac/Linux)

```bash
# Dar permissão de execução
chmod +x video_variations_system.py
chmod +x video_variations_from_config.py

# Tentar rodar novamente
python3 video_variations_system.py video.mp4 -n 5
```

---

### Erro: "Espaço em disco insuficiente"

```bash
# Ver espaço disponível
df -h

# Limpar cache
python3 -m pip cache purge  # Se usou pip

# Processar em lotes menores
python3 video_variations_system.py video.mp4 -n 5 -o ./batch_1
python3 video_variations_system.py video.mp4 -n 5 -o ./batch_2
```

---

### Erro: "Timeout (> 2 minutos)"

```bash
# Opção 1: Reduzir workers
python3 video_variations_system.py video.mp4 -n 5 -w 1

# Opção 2: Reduzir variações
python3 video_variations_system.py video.mp4 -n 1

# Opção 3: Comprimir vídeo original
ffmpeg -i video_original.mp4 -vf "scale=960:540" -crf 23 video_compressed.mp4
python3 video_variations_system.py video_compressed.mp4 -n 5
```

## 📚 Documentação

Após instalação, leia nesta ordem:

1. **QUICKSTART.md** — Começar em 5 minutos
2. **README.md** — Documentação completa
3. **EXAMPLES.md** — Casos de uso práticos
4. **ARCHITECTURE.md** — Como funciona internamente

## 🎯 Próximos Passos

### 1. Testar com Vídeo de Exemplo

```bash
# Criar vídeo de teste (10 segundos)
ffmpeg -f lavfi -i color=c=blue:s=1920x1080:d=10 \
       -f lavfi -i sine=f=1000:d=10 \
       -c:v libx264 -preset ultrafast \
       -c:a aac -y test_video.mp4

# Processar (criar 3 variações)
python3 video_variations_system.py test_video.mp4 -n 3

# Ver resultado
ls -lh output/
```

### 2. Usar com Seu Vídeo

```bash
# Colocar seu vídeo na pasta
cp ~/Movies/meu_video.mp4 .

# Processar
python3 video_variations_system.py meu_video.mp4 -n 10

# Verificar
ls output/
```

### 3. Usar com Makefile (Mais Fácil)

```bash
# Ver comandos disponíveis
make help

# Quick start
make quick-start

# Criar 20 variações
make run VIDEO=meu_video.mp4 N=20 W=8
```

## ✅ Checklist de Setup

- [ ] Python 3.8+ instalado (`python3 --version`)
- [ ] FFmpeg 4.0+ instalado (`ffmpeg -version`)
- [ ] Projeto baixado/clonado
- [ ] Testes passam (`python3 test_system.py` ou `make test`)
- [ ] Pasta `output/` criada
- [ ] Documentação lida (QUICKSTART.md)
- [ ] Primeiro vídeo processado com sucesso

## 🚀 Você Está Pronto!

```bash
# Comando padrão para começar:
python3 video_variations_system.py seu_video.mp4 -n 5

# Ou com Makefile:
make run VIDEO=seu_video.mp4 N=5
```

Se tiver problemas, verifique:
1. `python3 test_system.py` — Testa sistema completo
2. `README.md` — Seção Troubleshooting
3. Documentação em ARCHITECTURE.md

---

**Pronto para começar?** → Veja [QUICKSTART.md](QUICKSTART.md)

**Precisa de ajuda?** → Veja [README.md](README.md)

**Quer entender como funciona?** → Veja [ARCHITECTURE.md](ARCHITECTURE.md)
