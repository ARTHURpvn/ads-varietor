# 🏗️ Architecture — Video Variations System

## Visão Geral

```
┌─────────────────┐
│   Video Input   │
│   (seu_video.mp4)│
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│   VideoVariationGenerator                   │
│  - Gera 5/10/20/N configurações aleatórias  │
│  - Varia speed, filtros, cores, etc         │
│  - Cada config é independente               │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│   VariationProcessor                        │
│  - Orquestra processamento paralelo         │
│  - Usa ThreadPoolExecutor com N workers     │
│  - Aguarda todas as tasks concluírem       │
└────────┬────────────────────────────────────┘
         │
    ┌────┴───────────────────┬─────────────┐
    ▼                        ▼             ▼
┌──────────┐            ┌──────────┐  ┌──────────┐
│VideoProc │            │VideoProc │  │VideoProc │
│Worker 1  │            │Worker 2  │  │Worker N  │
└──────────┘            └──────────┘  └──────────┘
    │                        │             │
    └────────────┬───────────┴─────────────┘
                 │
        ┌────────▼────────┐
        │   FFmpeg CLI    │
        │  (processo ext) │
        └────────┬────────┘
                 │
    ┌────────────┼───────────┐
    ▼            ▼           ▼
┌──────────┐ ┌────────┐ ┌──────────┐
│var_001.  │ │var_002.│ │var_00N.  │
│   mp4    │ │  mp4   │ │  mp4     │
└──────────┘ └────────┘ └──────────┘
    │            │           │
    └────────────┼───────────┘
                 │
                 ▼
        ┌────────────────┐
        │ Output Folder  │
        ├────────────────┤
        │ report.json    │
        │ config.json    │
        └────────────────┘
```

## Fluxo Detalhado

### 1. **Entrada**
```
user$ python3 video_variations_system.py video.mp4 -n 5
```
- Valida arquivo de entrada
- Cria diretório `output/`

### 2. **Geração de Configurações**
```python
VideoVariationGenerator.generate_variations(count=5)
│
├─ var_001: speed=1.023451, filter=brightness, bg=#1a1a1a
├─ var_002: speed=1.048329, filter=contrast, bg=#2a2a2a
├─ var_003: speed=1.001234, filter=none, bg=#0f0f0f
├─ var_004: speed=1.032451, filter=saturate, bg=#3a3a3a
└─ var_005: speed=1.015678, filter=hue, bg=#1f1f1f
```

Cada config tem:
- ID único (timestamp + índice)
- Speed (1.0 a 1.05 com precisão)
- Filtro de cor aleatorizado
- Cor de fundo RGB aleatória
- Transparências variadas
- Ruído de áudio (50% chance)
- Overlay (30% chance)

### 3. **Processamento Paralelo**

```
VariationProcessor
├─ max_workers = 4 (padrão)
│
├─ ThreadPoolExecutor (4 threads)
│  ├─ Thread 1: Processa var_001 → worker → ffmpeg
│  ├─ Thread 2: Processa var_002 → worker → ffmpeg
│  ├─ Thread 3: Processa var_003 → worker → ffmpeg
│  ├─ Thread 4: Processa var_004 → worker → ffmpeg
│  └─ [Aguarda] → Processa var_005 quando thread libera
│
└─ Retorna quando TODAS completam ou falham
```

**Importante:** ThreadPoolExecutor permite N processamentos simultâneos, não sequenciais.

### 4. **Processamento Individual (VideoProcessor)**

Para cada variação:

```
var_001.mp4
    │
    ├─ Input: seu_video.mp4
    │
    ├─ Build FFmpeg Filter Chain:
    │  ├─ Apply filter (brightness, contrast, etc)
    │  ├─ Scale video (0.8 to 1.0)
    │  ├─ Pad with background color
    │  ├─ Apply opacity
    │  └─ Overlay (if enabled)
    │
    ├─ Speed adjustment:
    │  └─ -itsscale 1/speed (e.g., 1/1.023451)
    │
    ├─ Metadata:
    │  ├─ title="Video Variation 001"
    │  └─ author="Auto Generated"
    │
    ├─ Audio:
    │  ├─ Original audio
    │  └─ + Noise (if enabled)
    │
    ├─ Codec:
    │  ├─ Video: libx264, preset=ultrafast, crf=23
    │  └─ Audio: aac, bitrate=128k
    │
    └─ Output: output/var_001_TIMESTAMP.mp4
```

### 5. **Relatório Final**

```json
{
  "success": [
    {
      "variation_id": "var_001_1721234567",
      "output": "output/var_001_1721234567.mp4",
      "config": {
        "speed": 1.023451,
        "filter_type": "brightness",
        ...
      }
    },
    ...
  ],
  "failed": [],
  "summary": {
    "total": 5,
    "success": 5,
    "failed": 0,
    "total_time_seconds": 87.5,
    "avg_time_per_video": 17.5
  }
}
```

## 📊 Componentes

### VideoVariationConfig (Dataclass)
Representa UMA variação com todos os parâmetros:
```python
@dataclass
class VideoVariationConfig:
    variation_id: str
    metadata_title: str
    speed: float                # 1.0 a 1.05
    filter_type: str            # brightness, contrast, saturate, hue, none
    filter_value: float         # 0.8 a 1.2
    background_color: str       # RGB hex
    bg_opacity: float           # 0.6 a 1.0
    video_opacity: float        # 0.7 a 0.95
    video_scale: float          # 0.8 a 1.0
    noise_audio: bool           # True/False
    noise_level: float          # 0.02 a 0.08
    overlay_enabled: bool       # True/False
    overlay_opacity: float      # 0.05 a 0.15
    overlay_scale: float        # 0.2 a 0.4
```

### VideoVariationGenerator
Gera N configs com parâmetros aleatórios:
```python
class VideoVariationGenerator:
    def generate_variations(count: int) → List[VideoVariationConfig]
    # Retorna array de N configs prontos
```

### VideoProcessor
Processa UM vídeo com UMA config usando FFmpeg:
```python
class VideoProcessor:
    def process_variation(
        input_video: str,
        output_dir: str,
        config: VideoVariationConfig,
        overlay_video: str = None
    ) → (bool, str)
    # Retorna (sucesso, path_output_ou_erro)
```

### VariationProcessor
Orquestra processamento em paralelo:
```python
class VariationProcessor:
    def process_batch(
        input_video: str,
        output_dir: str,
        num_variations: int = 5,
        overlay_video: str = None
    ) → Dict
    # Usa ThreadPoolExecutor para rodar N workers em paralelo
    # Retorna relatório com sucesso/falhas
```

## ⏱️ Timeline de Execução

```
Tempo: 0s      Início
       ├─ Gerar configs (< 1s)
       ├─ Iniciar workers (< 1s)
       │
       1s ──┬─ Worker 1 inicia var_001
           ├─ Worker 2 inicia var_002
           ├─ Worker 3 inicia var_003
           ├─ Worker 4 inicia var_004
           │
    20-30s ──┼─ Worker 1 completa var_001 ✓
           ├─ Worker 1 inicia var_005
           │
    40-60s ──┼─ Todos completam ✓
           │
    65s ──┴─ Salvar relatório (< 5s)
           └─ Concluído! ✓
```

**Com 5 variações e 4 workers:**
- Sequential: 5 × 20s = 100s
- Parallel: ceil(5/4) × 20s = 40s + overhead = ~50-60s

## 🔄 Loop de Processamento

```
for cada variation_config:
    ┌─ FFmpeg Command Build
    │  ├─ Video Input
    │  ├─ Filter Chain (brightness, scale, pad, overlay)
    │  ├─ Speed Adjustment (-itsscale)
    │  ├─ Metadata (-metadata)
    │  ├─ Audio Processing (± noise)
    │  ├─ Codec Selection (libx264, aac)
    │  └─ Output Path
    │
    ├─ Execute subprocess.run()
    │
    ├─ Monitor (timeout=120s)
    │
    └─ Capture Result (success/error)
```

## 🚀 Escalabilidade

### Local (seu Mac/Linux)
- Max workers: CPU cores - 2
- Típico: 4-8 workers
- 5 variações: ~2 minutos
- 20 variações: ~5-6 minutos

### Cloud (AWS/Google Cloud)
- Serverless: Lambda/Cloud Functions (< 15min execution)
- VM: Instância com múltiplas cores
- Docker: Containerizar + orquestração com Kubernetes

Exemplo Docker:
```dockerfile
FROM python:3.11-slim
RUN apt install ffmpeg

COPY video_variations_system.py .
CMD ["python3", "video_variations_system.py"]
```

## 🔌 Pontos de Customização

### 1. Gerar diferentes ranges de valores
Edite `VideoVariationGenerator.generate_variations()`:
```python
speed = round(1.0 + random.uniform(0, 0.03), 6)  # Reduz range
video_opacity = round(random.uniform(0.85, 0.99), 2)  # Mais opaco
```

### 2. Adicionar novos filtros
Edite `VideoProcessor._build_filter_chain()`:
```python
elif config.filter_type == "blur":
    filters.append(f"boxblur={config.filter_value}")
```

### 3. Alterar codec/qualidade
Edite comando FFmpeg em `process_variation()`:
```python
cmd.extend(["-c:v", "libx265"])  # HEVC em vez de H.264
cmd.extend(["-crf", "20"])       # Melhor qualidade
```

### 4. Usar configuração fixa
Use `video_variations_from_config.py` com JSON:
```bash
python3 video_variations_from_config.py video.mp4 -c my_config.json
```

## 📝 FFmpeg Filter Chain Exemplo

Para `var_001: speed=1.023451, filter=brightness, bg=#1a1a1a`:

```bash
ffmpeg -i video.mp4 \
  -vf "eq=brightness=1.05:1,scale=iw*0.92:ih*0.92,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#1a1a1a" \
  -itsscale 0.977 \
  -metadata title="Video Variation 001" \
  -c:v libx264 -preset ultrafast -crf 23 \
  -c:a aac -b:a 128k \
  -y output/var_001.mp4
```

## 🎯 Resumo

1. **Gerar**: N configs aleatórias
2. **Paralelizar**: ThreadPoolExecutor com M workers
3. **Processar**: Each worker → FFmpeg subprocess
4. **Relatar**: Agregar resultados em JSON

**Resultado:** N vídeos em ceil(N/M) × (tempo_por_video)

---

Para mais detalhes, veja:
- `README.md` — Casos de uso e customização
- `QUICKSTART.md` — Como começar
- `video_variations_system.py` — Código fonte comentado
