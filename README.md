# miner-harness

[![CI](https://github.com/VictorAMM/miner-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/VictorAMM/miner-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.6.1-green.svg)](CHANGELOG.md)

Sistema de prospecção mineral inteligente que utiliza agentes de IA especializados em geologia e
geofísica para analisar dados públicos do GeoSGB (Serviço Geológico do Brasil), ANM e USGS.

## Sobre

O miner-harness combina LLMs rodando **100% localmente** (via Ollama) com agentes especialistas em
geociências para fornecer análise integrada de prospecção mineral. O framework analítico é guiado
pela persona do **Dr. Augusto Valen** — geólogo exploracionista e geofísico de elite com 25+ anos
de experiência.

### Agentes especialistas

| Agente | Disciplina | Passo |
|---|---|---|
| Geólogo Estrutural | Controles estruturais, falhas, zonas de cisalhamento | 1–2 |
| Geofísico | Anomalias gravimétricas e aeromagnéticas | 2–3 |
| Geoquímico | Análise de amostras, CF por elemento, halos geoquímicos | 3–4 |
| Sensoriamento Remoto | Imagens orbitais, alterações hidrotermais | 3–4 |
| Avaliador | Integração crítica, score de confiança, alvos priorizados | 5 |

### Fontes de dados

| Fonte | Dados | TTL Cache |
|---|---|---|
| GeoSGB/CPRM | Ocorrências minerais, Gravimetria, Geoquímica, Geocronologia, Litoestratigrafia, Aerogeofísica, Furos | 7 dias |
| ANM/SIGMINE | Concessões minerárias (fase, titular, substâncias) | 30 dias |
| USGS Earthquakes | Eventos sísmicos (magnitude, profundidade) | 7 dias |
| CSV do usuário | Furos de sondagem proprietários (litologia, teores) | — |

## Requisitos

| Componente | Mínimo | Recomendado |
|---|---|---|
| Python | 3.11 | 3.12 |
| RAM | 8 GB | 16 GB |
| VRAM | 4 GB | 8 GB (NVIDIA RTX 2060+) |
| Disco | 10 GB livres | 20 GB livres |
| Ollama | qualquer | latest |

## Instalação

### Via wizard (recomendado)

```bash
pip install miner-harness
miner-harness install
```

O wizard interativo verifica pré-requisitos (Python, disco, Ollama, MINER_HOME), guia a configuração
e cria a estrutura de diretórios.

### Não-interativa (CI/automação)

```bash
miner-harness install \
  --non-interactive \
  --miner-home ~/.miner-harness \
  --model qwen3:8b \
  --ollama-url http://localhost:11434
```

### Desenvolvimento

```bash
git clone https://github.com/VictorAMM/miner-harness
cd miner-harness
uv sync
```

## Uso

### Análise básica

```bash
# Analisar região de Carajás (PA) — maior província de ferro do mundo
miner-harness analyze carajas \
  --bbox -51.5 -7.0 -49.0 -5.0 \
  --model qwen3:8b
```

Gera dashboard HTML interativo com mapa Leaflet, gráficos Chart.js e aba de análise por etapa.

### Opções avançadas

```bash
# Servidor HTTP interativo (análises sem reiniciar)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 --serve --port 8765

# Exportar alvos para GIS (QGIS/ArcGIS)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --output-gis targets.gpkg

# Exportar relatório técnico DOCX (compatível com JORC-preliminar)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --output-docx relatorio_carajas.docx

# Injetar furos de sondagem proprietários (prioridade máxima no LLM)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --drillholes meus_furos.csv

# Janela de contexto expandida (requer KV-cache Q4 no Ollama)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --ctx-size 32768

# Perfil de latência por step
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --profile

# Menor limiar de dados (quando serviços GeoSGB têm timeout)
miner-harness analyze carajas --bbox -51.5 -7.0 -49.0 -5.0 \
  --min-sources 2 --llm-timeout 180
```

### Furos de sondagem

```bash
# Indexar furos para uso permanente em todas as análises
miner-harness index drillholes meus_furos.csv

# Formato do CSV (colunas aceitas: en/pt-BR/acrônimos)
# hole_id/bhid/sondagem, x/lon/longitude, y/lat/latitude,
# z/elev, from/de, to/ate, lithology/litologia, alteration/alteracao
# + qualquer coluna extra (Au, Cu_ppm, etc.)
```

### Cache e índice

```bash
miner-harness cache stats          # estatísticas
miner-harness cache evict          # remover entradas expiradas
miner-harness cache clear          # limpar tudo

miner-harness index stats          # documentos indexados por fonte
miner-harness health               # status do sistema (Ollama, disco, cache)
miner-harness validate report.json # validar relatório JSON existente
```

## Arquitetura

```
src/miner_harness/
├── agents/           # Agentes especialistas (5 disciplinas)
├── cache/            # Cache SQLite com TTL configurável por fonte
├── cli/              # CLI argparse + handlers por subcomando
├── connectors/
│   ├── anm/          # ANM/SIGMINE — concessões minerárias
│   ├── geosgb/       # GeoSGB — 7 serviços geológicos
│   ├── ollama/       # Cliente async httpx + PromptManager
│   └── usgs/         # USGS Earthquakes
├── export/           # GisExporter (GeoPackage + GeoJSON)
├── index/            # Índice vetorial sqlite-vec + RAG
├── ingestion/        # DrillholeParser + DrillholeStore (CSV → SQLite)
├── observability/    # Health checks, métricas, ProfilingRunner
├── orchestrator/     # Pipeline principal, ContextBuilder, ConfidenceCalibrator
├── rca/              # Root Cause Analysis automático
├── report/           # HtmlReportRenderer (Jinja2/Leaflet) + DocxReportExporter
├── self_improvement/ # Profiler, tuner, feedback loop
├── server/           # DashboardServer (aiohttp) + SSE + AnalysisRunner
└── wizard/           # Wizard de instalação (checks + installer + UI Rich)
```

## Testes

```bash
# Suite completa — 1120 testes (~70s)
pytest tests/ -q

# Testes e2e contra GeoSGB real + Ollama local
MINER_E2E=1 pytest tests/e2e/ -v

# Apenas GeoSGB (sem Ollama)
MINER_E2E=1 MINER_E2E_NO_OLLAMA=1 pytest tests/e2e/ -v -k "geosgb"
```

## Status do projeto

**v1.0.0** — PRD-002 "Salto de Qualidade Analítica" concluído (F1–F5, F7, F9).

| Milestone | Entregável | Status |
|---|---|---|
| v0.1.0 | 11 fases ASO v3 — core, agentes, cache, índice, wizard, CI | ✅ |
| v0.2.x | Dashboard HTML (Leaflet + Chart.js), RAG | ✅ |
| v0.3.0 | Servidor HTTP local + SSE + dashboard interativo | ✅ |
| v0.4.0 | ANM/SIGMINE + USGS Earthquakes | ✅ |
| v0.5.x | Paralelização, benchmarks, qualidade de prompts, UI fixes | ✅ |
| v0.6.x | GeoPackage/GeoJSON export, furos GeoSGB, geoquímica normalizada | ✅ |
| v0.7.x | BouguerProcessor (derivadas gravimétricas), ConfidenceCalibrator | ✅ |
| v0.9.0 | Furos de sondagem do usuário (CSV → contexto LLM → mapa) | ✅ |
| v1.0.0 | Relatório técnico DOCX (7 seções, compatível JORC-preliminar) | ✅ |

Funcionalidades bloqueadas por `[NEEDS CLARIFICATION]`: F6 (Sentinel-2), F8 (Random Forest ML).

## Desenvolvimento

Consulte [`CLAUDE.md`](CLAUDE.md) para diretrizes de desenvolvimento e [`docs/`](docs/) para
artefatos de arquitetura (ADR, RFC, PRD, RCA).

## Licença

MIT
