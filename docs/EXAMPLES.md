# 💡 Exemplos Práticos — Video Variations System

Casos de uso reais e como executá-los.

## 📹 Caso 1: Criar 50 Variações para Content ID Bypass

**Cenário:** Você tem um vídeo de 30 segundos e quer criar 50 versões levemente diferentes para contornar a detecção de conteúdo duplicado (Content ID do YouTube, etc).

**Setup:**
```bash
# 1. Preparar vídeo (ex: video_original.mp4 em 1080p)
ls video_original.mp4

# 2. Criar 50 variações em batches de 10
for i in {1..5}; do
    echo "Batch $i..."
    python3 video_variations_system.py video_original.mp4 -n 10 -o ./output_batch_$i
    sleep 2
done

# 3. Combinar todos
mkdir output_final
mv output_batch_*/*.mp4 output_final/
```

**Resultado:** 50 arquivos `var_*.mp4` com variações entre si.

**Tempo:** ~40-50 minutos total (pode paralelizar em outro PC)

**Verificação:**
```bash
# Ver todas as variações
ls output_final/ | wc -l    # Deve retornar ~50

# Verificar tamanho (devem ser parecidos)
ls -lh output_final/ | head
```

---

## 📊 Caso 2: A/B Testing de Vídeos Publicitários

**Cenário:** Criar 15 versões de um anúncio para testar qual tem melhor conversão. Cada versão ligeiramente diferente.

**Comando:**
```bash
python3 video_variations_system.py anuncio.mp4 -n 15 --save-config
```

**Saída:**
```
output/
├── var_001_*.mp4       ← Versão A1
├── var_002_*.mp4       ← Versão A2
├── ...
├── var_015_*.mp4       ← Versão A15
├── report.json         ← Resumo
└── configurations.json ← Exatas configs usadas
```

**Próximo Passo:** Fazer upload dos 15 vídeos para plataforma de publicidade (Facebook, Google Ads, etc) com diferentes configs de target.

**Análise:** Usar `report.json` para rastrear qual variação teve melhor performance:
```json
{
  "success": [
    {
      "variation_id": "var_001_...",
      "config": {
        "speed": 1.001234,
        "filter_type": "brightness"
        ...
      }
    },
    ...
  ]
}
```

---

## 🎬 Caso 3: Adicionar Logo/Watermark em Todas as Variações

**Cenário:** Você tem um vídeo principal e quer adicionar seu logo (transparente) em todas as 20 variações.

**Preparar:**
1. Exportar logo como vídeo (ex: `logo.mp4`) com background transparente
   - Duração: Mesma do vídeo principal ou maior
   - Formato: MP4 ou MOV com codec suportado

**Executar:**
```bash
python3 video_variations_system.py video_principal.mp4 \
  --overlay-video logo.mp4 \
  -n 20
```

**O que acontece:**
- Vídeo principal é base
- Logo é sobreposto com transparência baixa (8-12%)
- Todas as 20 variações têm o logo

**Dica:** Se o logo piscasse, reduza `overlay_opacity` no código:
```python
overlay_opacity = round(random.uniform(0.05, 0.10), 2)  # Reduz de 0.15
```

---

## 🎵 Caso 4: Adicionar Ruído em Áudio (Para Evitar Duplicação)

**Cenário:** Vídeos com áudio importante. Adicionar ruído leve faz com que sistemas de detecção não reconheçam como duplicatas.

**Como Funciona:**
O sistema já gera variações com ruído (50% de chance). Para garantir ruído em TODAS:

**Opção 1: Editar configuração**
```python
# Em VideoVariationGenerator.generate_variations():
# Altere:
noise_enabled = random.choice([True, False])
# Para:
noise_enabled = True  # Sempre adiciona ruído
```

**Opção 2: Usar arquivo de config customizado**
```bash
# Criar config_com_ruido.json com todas as variações tendo noise_audio=true
python3 video_variations_from_config.py video.mp4 -c config_com_ruido.json
```

---

## 🖼️ Caso 5: Criar Variações com Diferentes Fundos

**Cenário:** Seus vídeos precisam de fundos específicos (não aleatórios). Ex: preto, branco, vermelho.

**Solução:** Customizar config JSON

```json
{
  "variations": [
    {
      "variation_id": "var_black_bg",
      "background_color": "000000",
      "bg_opacity": 1.0,
      "speed": 1.01,
      ...
    },
    {
      "variation_id": "var_white_bg",
      "background_color": "ffffff",
      "bg_opacity": 1.0,
      "speed": 1.02,
      ...
    },
    {
      "variation_id": "var_red_bg",
      "background_color": "ff0000",
      "bg_opacity": 0.8,
      "speed": 1.015,
      ...
    }
  ]
}
```

**Executar:**
```bash
python3 video_variations_from_config.py video.mp4 -c config_fundos.json
```

---

## ⚡ Caso 6: Processamento Rápido (Máxima Velocidade)

**Cenário:** Você precisa de 100 variações em menos de 30 minutos.

**Strategy:**
1. Usar máximo de workers (N = CPU cores)
2. Reduzir qualidade se necessário
3. Processar em paralelamente em múltiplos PCs

**Em um Mac com 8 cores:**
```bash
python3 video_variations_system.py video.mp4 -n 100 -w 8
```

**Tempo esperado:** 
- 100 variações ÷ 8 workers = ~13 batches
- 13 × 20s = 260s = ~4.3 minutos ✓

**Se ainda for lento:**
Alterar qualidade em `video_variations_system.py`:
```python
cmd.extend(["-preset", "ultrafast"])  # Já é o padrão
cmd.extend(["-crf", "28"])  # Reduz qualidade (padrão é 23)
```

---

## 📱 Caso 7: Processar Vídeos Verticais (9:16)

**Cenário:** Criar variações de um vídeo vertical (Stories, Reels, TikTok).

**Como:** O sistema detecta e mantém aspectratio automaticamente.

```bash
python3 video_variations_system.py reels_video.mp4 -n 30
```

**Dica:** Verticais ocupam menos espaço em disco, processam mais rápido.

---

## 🌐 Caso 8: Deploy em Cloud (AWS Lambda)

**Cenário:** Você quer processar vídeos via API na cloud.

**Estrutura:**
```
projeto/
├── lambda_function.py          ← Handler do Lambda
├── video_variations_system.py
└── requirements.txt
```

**lambda_function.py:**
```python
import json
import boto3
from video_variations_system import VariationProcessor

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = event['bucket']
    key = event['key']  # s3://bucket/video.mp4
    
    # Download from S3
    s3.download_file(bucket, key, '/tmp/video.mp4')
    
    # Process
    processor = VariationProcessor(max_workers=2)  # Lambda tem limite
    results = processor.process_batch(
        '/tmp/video.mp4',
        '/tmp/output',
        num_variations=5
    )
    
    # Upload results back to S3
    for result in results['success']:
        s3.upload_file(
            result['output'],
            bucket,
            f"output/{result['variation_id']}.mp4"
        )
    
    return {
        'statusCode': 200,
        'body': json.dumps(results['summary'])
    }
```

**Deploy:**
```bash
# 1. Criar zip com FFmpeg layer
# 2. Fazer upload para AWS Lambda
# 3. Configurar trigger (API Gateway, S3 event, etc)
```

---

## 🎯 Caso 9: Monitorar Processamento em Tempo Real

**Scenario:** Você quer ver o progresso enquanto processa 50 variações.

**Terminal Setup:**
```bash
# Terminal 1: Executar processamento
python3 video_variations_system.py video.mp4 -n 50 -w 8

# Terminal 2: Monitorar (em outra aba)
watch -n 2 "ls -lh output/*.mp4 | wc -l && du -sh output/"
```

**Output:**
```
Every 2.0s: ls -lh output/*.mp4 | wc -l && du -sh output/

12      # 12 vídeos processados
4.2G    # 4.2 GB total

# Depois de 1 min:
35      # 35 vídeos
11.8G   # 11.8 GB
```

---

## 🔍 Caso 10: Análise Comparativa de Variações

**Cenário:** Você criou 10 variações e quer entender exatamente o que mudou em cada uma.

**Script de análise:**
```python
import json

with open('output/configurations.json') as f:
    configs = json.load(f)

print("Resumo das Variações:")
print("-" * 80)

for i, cfg in enumerate(configs):
    print(f"\n[{i+1}] {cfg['variation_id']}")
    print(f"    Speed: {cfg['speed']} (original: 1.0)")
    print(f"    Filter: {cfg['filter_type']} (value: {cfg['filter_value']})")
    print(f"    Background: #{cfg['background_color']} (opacity: {cfg['bg_opacity']})")
    print(f"    Video: opacity={cfg['video_opacity']}, scale={cfg['video_scale']}")
    print(f"    Noise: {cfg['noise_audio']} (level: {cfg['noise_level']})")
    print(f"    Overlay: {cfg['overlay_enabled']}")
```

**Saída:**
```
Resumo das Variações:
--------------------------------------------------------------------------------

[1] var_001_1721234567
    Speed: 1.023451 (original: 1.0)
    Filter: brightness (value: 1.05)
    Background: #1a1a1a (opacity: 0.95)
    Video: opacity=0.85, scale=0.92
    Noise: True (level: 0.045)
    Overlay: False

[2] var_002_1721234568
    Speed: 1.048329 (original: 1.0)
    Filter: contrast (value: 1.12)
    ...
```

---

## 🛠️ Troubleshooting de Casos Reais

### Problema: Alguns vídeos falham, outros succedem

**Solução:**
```bash
# Verificar log
cat output/report.json | grep -A5 '"failed"'

# Reprocessar apenas os que falharam
# Editar config.json mantendo apenas os failed
python3 video_variations_from_config.py video.mp4 -c config_failed_only.json
```

### Problema: Tamanho de arquivo inconsistente

**Razão:** Codec varia baseado em conteúdo
**Solução:** Use `-crf` menor (melhor qualidade, maior arquivo)

```python
cmd.extend(["-crf", "20"])  # Melhor (arquivo maior)
```

### Problema: Processamento muito lento

**Diagnostic:**
```bash
# Ver quanto CPU/Memória está usando
top -o %CPU

# Se está usando < 100%, reduzir workers:
python3 video_variations_system.py video.mp4 -n 10 -w 2
```

---

## 📚 Referência Rápida

| Caso | Comando |
|------|---------|
| Rápido (5 variações) | `python3 video_variations_system.py video.mp4 -n 5` |
| Médio (20) | `python3 video_variations_system.py video.mp4 -n 20 -w 8` |
| Grande (100) | `python3 video_variations_system.py video.mp4 -n 100 -w 8` |
| Com overlay | `python3 video_variations_system.py video.mp4 --overlay-video logo.mp4 -n 10` |
| Config customizada | `python3 video_variations_from_config.py video.mp4 -c custom.json` |

---

Próximas leituras:
- `README.md` — Documentação completa
- `ARCHITECTURE.md` — Como funciona internamente
- `QUICKSTART.md` — Começar em 5 minutos
