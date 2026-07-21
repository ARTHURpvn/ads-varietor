# 🚀 Quick Start — Video Variations System

Comece em 5 minutos!

## 1️⃣ Instalar Dependências

### Mac
```bash
brew install ffmpeg python3
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install ffmpeg python3 python3-pip
```

### Windows (WSL)
```bash
# No WSL Ubuntu terminal:
sudo apt update && sudo apt install ffmpeg python3
```

## 2️⃣ Baixar Sistema

```bash
# Baixe os arquivos:
# - video_variations_system.py
# - video_variations_from_config.py
# - README.md
# - config_example.json

# Ou clone do GitHub (quando disponível)
cd seu_diretorio
```

## 3️⃣ Seu Primeiro Processamento

**Preparar:**
1. Colocar um vídeo (ex: `video.mp4`) na pasta do projeto
2. Abrir terminal nessa pasta

**Executar:**
```bash
python3 video_variations_system.py video.mp4 -n 5
```

**O que acontece:**
- ✅ Gera 5 variações aleatórias
- ✅ Processa em paralelo (2-3 minutos)
- ✅ Salva em `output/var_*.mp4`

## 4️⃣ Ver Resultado

```bash
ls output/
# output/
# ├── var_001_TIMESTAMP.mp4   ✓ Pronto
# ├── var_002_TIMESTAMP.mp4   ✓ Pronto
# ├── report.json             ← Relatório
```

Abra os vídeos em um player para verificar as variações.

## 5️⃣ Próximos Passos

### Criar mais variações
```bash
python3 video_variations_system.py video.mp4 -n 20
```

### Com overlay (watermark/logo)
```bash
python3 video_variations_system.py video.mp4 -n 10 --overlay-video logo.mp4
```

### Usar configuração fixa
```bash
python3 video_variations_from_config.py video.mp4 -c config_example.json
```

### Salvar as configurações usadas
```bash
python3 video_variations_system.py video.mp4 -n 5 --save-config
```

## 🎯 Exemplos Práticos

### Exemplo 1: Rápido (5 variações)
```bash
python3 video_variations_system.py meu_video.mp4 -n 5
# ⏱️ ~2-3 minutos
```

### Exemplo 2: Médio (20 variações)
```bash
python3 video_variations_system.py meu_video.mp4 -n 20 -w 8
# ⏱️ ~4-5 minutos
# -w 8 = usar 8 processadores paralelos
```

### Exemplo 3: Grande (50 variações)
```bash
python3 video_variations_system.py meu_video.mp4 -n 50 -w 8 -o ./output_grande
# ⏱️ ~8-10 minutos
```

### Exemplo 4: Com Logo/Watermark
```bash
python3 video_variations_system.py meu_video.mp4 \
  --overlay-video meu_logo.mp4 \
  -n 15
# Adiciona logo em todas as variações
```

## 📊 O que cada variação faz

Cada vídeo gerado tem:
✓ **Metadados** diferentes (título, autor)  
✓ **Velocidade** levemente diferente (1.0x a 1.05x)  
✓ **Filtro** diferente (brightness, contrast, saturate, etc)  
✓ **Fundo** com cor aleatória  
✓ **Transparência** ajustada  
✓ **Escala** ligeiramente diferente  
✓ **Ruído de áudio** (opcional)  
✓ **Overlay** (opcional)  

**Resultado:** Todos os vídeos são visualmente diferentes mas mantêm o conteúdo original.

## 🐛 Se Algo Não Funcionar

**Erro: "FFmpeg não encontrado"**
```bash
# Mac: instale FFmpeg
brew install ffmpeg

# Linux: instale FFmpeg
sudo apt install ffmpeg

# Verifique se está instalado:
ffmpeg -version
```

**Erro: "ModuleNotFoundError"**
```bash
# Nenhum módulo adicional é necessário!
# Se ocorrer erro, tenta:
python3 -m video_variations_system video.mp4 -n 5
```

**Erro: "Timeout (> 2 minutos)"**
- Seu vídeo é muito grande ou resolução alta
- Solução 1: Reduz para `-n 1` para testar
- Solução 2: Reduz resolução do vídeo original
- Solução 3: Use `-w 2` em vez de `-w 4`

**Erro: "Espaço em disco insuficiente"**
- Processa em lotes menores: `-n 5` de cada vez
- Limpa pasta `output/` entre processamentos
- Use outro disco/pasta

## 📈 Performance Esperada

| # Variações | Workers | Tempo | Tamanho (cada) |
|-------------|---------|-------|----------------|
| 5 | 4 | 2-3 min | ~50-100 MB |
| 10 | 4 | 3-4 min | ~50-100 MB |
| 20 | 8 | 5-6 min | ~50-100 MB |
| 50 | 8 | 12-15 min | ~50-100 MB |

*Tempos variam com resolução do vídeo original e CPU do computador*

## 📖 Documentação Completa

Para mais informações, detalhes de customização, deploy em cloud, etc:
→ Veja `README.md`

## 💡 Dicas Pro

### 1. Usar processamento em batches
```bash
# Em vez de gerar 100 de uma vez:
for i in {1..10}; do
  python3 video_variations_system.py video.mp4 -n 10
done
# Menos processador, mais estável
```

### 2. Monitorar progresso
```bash
# Terminal 1: Ver arquivos sendo criados
watch "ls -lh output/ | tail"

# Terminal 2: Executar
python3 video_variations_system.py video.mp4 -n 20
```

### 3. Usar configuração customizada
1. Crie `minha_config.json` baseado em `config_example.json`
2. Edite os parâmetros que quer
3. Execute:
```bash
python3 video_variations_from_config.py video.mp4 -c minha_config.json
```

### 4. Verificar qualidade
```bash
# Abra a pasta output e verifique:
# - Tamanho dos arquivos (devem ser parecidos)
# - Alguns segundos de alguns vídeos
# - Relatório (report.json) para ver sucesso/falhas
```

## 🎉 Pronto!

Você tem um sistema que:
✅ Cria variações de vídeo em segundos  
✅ Processa múltiplos simultaneamente  
✅ Varia parâmetros automaticamente  
✅ Pode escalar para cloud  
✅ Salva relatórios detalhados  

**Próximo passo:** Leia `README.md` para customizações avançadas.

---

**Dúvidas?** Veja os exemplos no README ou o código comentado em `video_variations_system.py`.
