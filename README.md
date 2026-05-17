# miner-harness

[![CI](https://github.com/VictorAMM/miner-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/VictorAMM/miner-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Sistema de prospecção mineral inteligente que utiliza agentes de IA especializados em geologia e geofísica para analisar dados públicos do GeoSGB (Serviço Geológico do Brasil).

## Sobre

O miner-harness combina LLMs rodando **100% localmente** (via Ollama) com agentes especialistas em geociências para fornecer análise integrada de prospecção mineral. O framework analítico é guiado pela persona do **Dr. Augusto Valen** — geólogo exploracionista e geofísico de elite com 25+ anos de experiência.

### Agentes especialistas

| Agente | Disciplina |
|---|---|
| Geólogo Estrutural | Controles estruturais, falhas, zonas de cisalhamento |
| Geofísico | Anomalias gravimétricas e aeromagnéticas |
| Geoquímico | Análise de amostras e halos geoquímicos |
| Sensoriamento Remoto | Imagens orbitais e alterações hidrotermais |
| Avaliador | Integração crítica e score de confiança |

### Fontes de dados (GeoSGB)

Todos os dados são públicos, acessados via API do Serviço Geológico do Brasil:

- **Ocorrências minerais** — banco nacional (100 000+ registros)
- **Gravimetria** — dados gravimétricos terrestres
- **Geoquímica** — amostras geoquímicas regionais
- **Geocronologia** — datações geocronológicas
- **Litoestratigrafia** — unidades estratigráficas
- **Aerogeofísica** — levantamentos aerogamaespectrométricos e aeromagnéticos

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

O wizard interativo verifica pré-requisitos (Python, disco, Ollama, MINER_HOME), guia a configuração e cria a estrutura de diretórios.

### Não-interativa (CI/automação)

```bash
miner-harness install \
  --non-interactive \
  --miner-home ~/.miner-harness \
  --model qwen3:8b-q4_K_M \
  --ollama-url http://localhost:11434
```

### Desenvolvimento

```bash
git clone https://github.com/VictorAMM/miner-harness
cd miner-harness
uv sync
```

## Uso

### Análise de região

```bash
# Analisar região de Carajás (PA) — maior província de ferro do mundo
miner-harness analyze carajas \
  --bbox -51.5,-7.0,-49.0,-5.0 \
  --model qwen3:8b-q4_K_M \
  --output relatorio_carajas.json

# Validar relatório existente
miner-harness validate relatorio_carajas.json

# Verificar saúde do sistema
miner-harness health
```

### Cache de dados GeoSGB

```bash
miner-harness cache stats   # estatísticas (entradas, tamanho, serviços)
miner-harness cache clear   # limpar cache
```

## Arquitetura

```
src/miner_harness/
├── agents/           # Agentes especialistas (geofísica, geoquímica, etc.)
├── cache/            # Cache SQLite com TTL configurável
├── cli/              # Interface de linha de comando (Typer)
├── connectors/
│   ├── geosgb/       # MapServer/identify + FeatureServer/query
│   └── ollama/       # Cliente async httpx para Ollama
├── index/            # Índice vetorial de documentos (sqlite-vec)
├── observability/    # Health checks, métricas structlog
├── orchestrator/     # Pipeline principal + validação de relatórios
├── rca/              # Root Cause Analysis automático
├── self_improvement/ # Profiler, tuner e feedback loop
└── wizard/           # Wizard de instalação (checks + installer + UI Rich)
```

## Testes

```bash
# Suite completa — 447 testes (~30s)
uv run pytest

# Testes e2e contra GeoSGB real + Ollama local
MINER_E2E=1 uv run pytest tests/e2e/ -v

# Apenas GeoSGB (sem Ollama)
MINER_E2E=1 MINER_E2E_NO_OLLAMA=1 uv run pytest tests/e2e/ -v -k "geosgb"

# Modelo alternativo nos e2e
MINER_E2E=1 MINER_OLLAMA_MODEL=llama3 uv run pytest tests/e2e/ -v
```

## Status do projeto

Todas as 11 fases do **Agentic SDLC Operating System v3** (ASO v3) foram concluídas.

| Fase | Entregável | Status |
|---|---|---|
| 0 | Fundação e Governança | ✅ |
| 1 | Discovery e Pesquisa Autônoma | ✅ |
| 2 | PRD Executável | ✅ |
| 3 | Technical Design e RFC Swarm | ✅ |
| 4 | Incepção de Infra | ✅ |
| 5 | Implementação (56 módulos) | ✅ |
| 6 | Validation Harness | ✅ |
| 7 | Testing Swarm (447 testes, 92% cobertura) | ✅ |
| 8 | Governed CI/CD | ✅ |
| 9 | Observabilidade | ✅ |
| 10 | RCA Autônomo | ✅ |
| 11 | Self-Improvement | ✅ |
| — | Wizard de Instalação | ✅ |
| — | Testes E2E (17 testes, opt-in) | ✅ |

## Desenvolvimento

Consulte [`CLAUDE.md`](CLAUDE.md) para diretrizes de desenvolvimento e [`docs/`](docs/) para artefatos de arquitetura (ADR, RFC, PRD, RCA).

## Licença

MIT
