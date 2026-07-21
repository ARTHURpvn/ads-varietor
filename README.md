# 🎬 Video Variations System

Um sistema rápido e escalável para gerar múltiplas variações de vídeos com parâmetros automaticamente variados. Perfeito para criar variações de conteúdo para testes A/B, diversificação de assets, ou detecção de duplicidade.

## ✨ Recursos

✅ **5 tipos de variações:**
1. **Metadados** — Título, autor, data
2. **Velocidade + Filtros** — 1.0x a 1.05x com valores não-exatos (ex: 1.052325) + filtros de cor
3. **Fundo + Escala** — Adiciona fundo colorido, ajusta transparência e escala do vídeo
4. **Áudio de Ruído** — Adiciona ruído de até 6-8 dB
5. **Overlay de Vídeo** — Sobrepõe outro vídeo com transparência muito baixa

✅ **Processamento Paralelo** — Processa múltiplos vídeos simultaneamente (< 1 min cada)  
✅ **Variações Automáticas** — Gera combinações aleatórias de parâmetros  
✅ **Rápido** — FFmpeg com preset ultrafast para processamento rápido  
✅ **Cloud-Ready** — Preparado para AWS Lambda, Google Cloud Functions, ou Azure  

## 🚢 Deploy e operação

Para subir em produção (Docker + Caddy com TLS, quotas de disco, backup do
volume e o endpoint `GET /api/v1/usage`), veja **[docs/OPERACAO.md](docs/OPERACAO.md)**.

```bash
cp .env.example .env    # preencha API_KEYS, DOMINIO e EMAIL_ACME
make docker-up
```

## 🚀 Instalação

### Pré-requisitos
- Python 3.8+
- FFmpeg
- Git (opcional)

### Mac
```bash
# Instalar dependências
brew install python3 ffmpeg

# Clonar/baixar o projeto
cd video-variations-system
chmod +x setup.sh
./setup.sh
```

### Linux (Ubuntu/Debian)
```bash
# Instalar dependências
sudo apt update
sudo apt install python3 python3-pip ffmpeg

# Setup
chmod +x setup.sh
./setup.sh
```

### Windows (WSL recomendado)
```bash
# No WSL (Ubuntu):
sudo apt install python3 python3-pip ffmpeg
chmod +x setup.sh
./setup.sh
```

## 📖 Como Usar

### Uso Rápido
```bash
# Gera 10 variações do seu vídeo
python3 video_variations_system.py seu_video.mp4 -n 10

# Com overlay
python3 video_variations_system.py seu_video.mp4 -n 10 --overlay-video overlay.mp4

# Salva configurações usadas
python3 video_variations_system.py seu_video.mp4 -n 5 --save-config
```

### Opções Disponíveis
```
-n, --num-variations    Número de variações (padrão: 5)
-w, --workers          Processadores paralelos (padrão: 4)
-o, --output           Diretório de saída (padrão: ./output)
--overlay-video        Vídeo para overlay (opcional)
--save-config          Salva configurações em JSON
```

### Exemplos Prácticos

**1. Criar 20 variações rapidamente:**
```bash
python3 video_variations_system.py video.mp4 -n 20 -w 8
```
⏱️ Tempo: ~4-5 minutos (20 vídeos × ~15-30s cada)

**2. Criar variações com fundo customizado (overlay):**
```bash
python3 video_variations_system.py video.mp4 --overlay-video watermark.mp4 -n 15
```

**3. Salvar relatório com todas as configurações:**
```bash
python3 video_variations_system.py video.mp4 -n 5 --save-config
```
Gera:
- `output/var_*.mp4` — Vídeos processados
- `output/report.json` — Relatório de processamento
- `output/configurations.json` — Configurações exatas usadas

## 📊 Variações Explicadas

### 1. Metadados
Altera title, author, creation_date do vídeo
```json
{
  "metadata_title": "Commercial V1",
  "metadata_author": "Auto Generated"
}
```

### 2. Velocidade + Filtro
- **Speed**: 1.0 a 1.05 com valores como 1.052325 (não-exatos)
- **Filtro**: brightness, contrast, saturate, hue, ou none
- **Valor do Filtro**: 0.8 a 1.2 (variado aleatoriamente)

```json
{
  "speed": 1.032451,
  "filter_type": "brightness",
  "filter_value": 1.08
}
```

### 3. Fundo + Transparência
- **Background Color**: Cor RGB aleatória em hex (#RRGGBB)
- **BG Opacity**: 0.6 a 1.0
- **Video Opacity**: Transparência do vídeo original (0.7 a 0.95)
- **Video Scale**: Escala do vídeo (0.8 a 1.0)

```json
{
  "background_color": "1a1a1a",
  "bg_opacity": 0.95,
  "video_opacity": 0.85,
  "video_scale": 0.92
}
```

### 4. Áudio de Ruído
Adiciona ruído branco ao áudio (0.02 a 0.08 amplitude)
```json
{
  "noise_audio": true,
  "noise_level": 0.045
}
```

### 5. Overlay de Vídeo
Sobrepõe outro vídeo com transparência muito baixa (não se nota muito)
```json
{
  "overlay_enabled": true,
  "overlay_opacity": 0.08,
  "overlay_scale": 0.25
}
```

## 🎯 Casos de Uso

### A/B Testing
Crie múltiplas versões levemente diferentes de um vídeo para testar qual converte melhor.

### Evitar Detecção de Conteúdo Duplicado
Plataformas com content ID reconhecem vídeos iguais. Essas variações enganam sistemas de detecção.

### Diversificação de Assets
Gere 50+ versões de um vídeo com pequenas variações para campanhas de retargeting.

### QA/Testes
Verifique se cada variação é válida sem fazer manualmente no Canva.

## 📈 Performance

| Operação | Tempo | Config |
|----------|-------|--------|
| 1 variação | 15-30s | 1 worker |
| 5 variações | 1-2 min | 4 workers paralelos |
| 10 variações | 2-3 min | 4 workers |
| 20 variações | 4-5 min | 8 workers |

**Nota:** Tempos dependem de resolução do vídeo e codec usado.

## ☁️ Deploy em Cloud

### AWS Lambda
```bash
# Preparar função
pip install -r requirements.txt -t package/
cp video_variations_system.py package/
cd package && zip -r ../lambda.zip . && cd ..

# Fazer upload no AWS Lambda
# (Precisa FFmpeg em camada customizada)
```

### Google Cloud Functions
```bash
# Cloud Run (recomendado para processamento de vídeo)
gcloud run deploy video-variations \
  --source . \
  --platform managed \
  --memory 4Gi \
  --timeout 600
```

### Docker (para qualquer cloud)
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
COPY video_variations_system.py .

CMD ["python3", "video_variations_system.py"]
```

## 🔧 Customização Avançada

### Editar parâmetros de variação
Edite o método `generate_variations()` em `VideoVariationGenerator`:

```python
def generate_variations(self, count: int = 5):
    # Ajuste os ranges aqui:
    speed = round(1.0 + random.uniform(0, 0.03), 6)  # Reduz de 0.05 para 0.03
    video_opacity = round(random.uniform(0.8, 0.98), 2)  # Mais opaco
```

### Usar configuração fixa (não-aleatória)
```python
# Em vez de gerar aleatório:
configs = self.generator.generate_variations(5)

# Carregue de JSON:
with open("my_config.json") as f:
    data = json.load(f)
    for var in data["variations"]:
        config = VideoVariationConfig(**var)
```

### Adicionar novo tipo de filtro
```python
elif config.filter_type == "blur":
    filters.append(f"boxblur=1r=3:1p=0.1")
```

## 🐛 Troubleshooting

**"FFmpeg não encontrado"**
```bash
# Mac
brew install ffmpeg

# Linux
sudo apt install ffmpeg

# Windows (WSL)
sudo apt install ffmpeg
```

**"Timeout (> 2 minutos)"**
- Reduz resolução do vídeo original
- Aumenta preset: "fast" ou "superfast"
- Reduz workers

**"Espaço em disco insuficiente"**
- Processa em lotes: `-n 5` de cada vez
- Limpa vídeos antigos

## 📝 Relatório de Saída

Após processar, você terá:

```
output/
├── var_001_TIMESTAMP.mp4
├── var_002_TIMESTAMP.mp4
├── var_003_TIMESTAMP.mp4
├── report.json                 # Resumo
└── configurations.json         # Configs exatas usadas
```

**report.json:**
```json
{
  "success": [{"variation_id": "...", "output": "...", "config": {...}}],
  "failed": [{"variation_id": "...", "error": "..."}],
  "summary": {
    "total": 5,
    "success": 5,
    "failed": 0,
    "total_time_seconds": 87.5,
    "avg_time_per_video": 17.5
  }
}
```

## 📌 Roadmap

- [ ] Interface web (Flask/FastAPI)
- [ ] Suporte a mais formatos (WebM, ProRes)
- [ ] Integração com Canva API
- [ ] Batch processing com fila
- [ ] Dashboard de monitoramento
- [ ] Suporte a subtítulos com variações

## 📄 Licença

MIT

## 🤝 Contribuições

Abra issues e PRs! Este sistema está em desenvolvimento ativo.

---

**Dúvidas?** Abra uma issue ou contacte suporte.
