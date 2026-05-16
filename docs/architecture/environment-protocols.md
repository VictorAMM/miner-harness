# Protocolos de Ambiente — miner-harness

**Status**: APPROVED
**Data**: 2026-05-11
**Fase ASO**: 0 — Fundação e Governança

---

## 1. Ambientes

### Dev (Local)
- **Máquina de referência**: i5-9600KF, RTX 2070 Super 8GB, 16GB+ RAM
- **Python**: 3.11+ via pyenv ou sistema
- **Ollama**: instalado localmente, modelos baixados sob demanda
- **Dados GeoSGB**: cache local em `~/.miner-harness/cache/`
- **Config**: `.env` local (nunca commitado)

### CI (GitHub Actions)
- **Runner**: `ubuntu-latest`
- **Python**: 3.11 (matrix pode incluir 3.12+)
- **GPU**: nenhuma — testes rodam sem Ollama (mocks para testes de agente)
- **Jobs**:
  1. `lint` — ruff check + ruff format --check
  2. `typecheck` — mypy --strict
  3. `test` — pytest com coverage
  4. `security` — bandit + pip audit
- **Trigger**: push em `main`/`develop`, PRs contra `main`/`develop`

### Release (GitHub Actions)
- **Propósito**: build do wizard de instalação
- **Matrix**: Windows, macOS, Linux
- **Artefatos**: instalador por plataforma
- **Trigger**: tag `v*` em `main`

## 2. Paridade de Ambiente

| Aspecto | Dev | CI | Release |
|---|---|---|---|
| Python | 3.11+ | 3.11 | 3.11 |
| Dependências | pyproject.toml | pyproject.toml | pyproject.toml |
| Lint/Format | ruff | ruff (mesmo config) | N/A |
| Types | mypy | mypy (mesmo config) | N/A |
| Testes | pytest (com Ollama) | pytest (sem Ollama, mocks) | smoke test |
| Security | bandit local | bandit CI | bandit CI |

### Regra de Paridade
- **Mesma versão Python** em todos os ambientes
- **Mesmas dependências** pinadas no pyproject.toml
- **Mesma config** de ruff/mypy/pytest (um único arquivo de config)
- Diferença permitida: presença/ausência de GPU e Ollama (testes adaptam via fixtures)

## 3. FinOps Day 1

### Orçamento Operacional

| Item | Custo Mensal | Nota |
|---|---|---|
| GitHub (free tier) | $0 | 2000 min Actions/mês, repos ilimitados |
| Ollama + modelos | $0 | Roda local, modelos open source |
| API GeoSGB | $0 | API pública governamental |
| Eletricidade GPU | ~R$15-30/mês | Estimativa uso dev moderado |
| **Total** | **~R$15-30/mês** | |

### Orçamento de Tokens LLM

| Operação | Tokens/chamada | Calls/dia (est.) | Tokens/dia |
|---|---|---|---|
| Query de agente individual | ~5.000 | 20 | 100k |
| Análise regional completa | ~50.000 | 2 | 100k |
| Indexação RAG | ~100.000 | Raro | N/A |
| Evaluator-Optimizer | ~10.000 | 10 | 100k |
| **Total estimado** | | | **~300k/dia** |

A RTX 2070 Super processa ~30 tok/s com Mistral 7B (Q4). A 300k tokens/dia, isso equivale a ~2.8 horas de inferência contínua — confortável para uso diário.

### Alertas de Custo
- Se GitHub Actions ultrapassar 1500 min/mês → revisar frequência de CI
- Se cache GeoSGB ultrapassar 10GB → implementar LRU eviction
- Se tempo de inferência por consulta ultrapassar 5 min → otimizar prompts ou reduzir modelo

## 4. Gestão de Configuração

### Hierarquia de Config
```
1. Defaults em código (core/config.py)
2. Arquivo de config (~/.miner-harness/config.toml)
3. Variáveis de ambiente (MINER_*)
4. Argumentos CLI (maior prioridade)
```

### Config Padrão
```toml
# ~/.miner-harness/config.toml
[general]
data_dir = "~/.miner-harness"
log_level = "INFO"
log_format = "json"

[ollama]
base_url = "http://localhost:11434"
model = "qwen3:4b"
timeout_seconds = 120

[geosgb]
base_url = "https://geoportal.sgb.gov.br/server/rest/services"
cache_ttl_days = 30
max_concurrent_requests = 3
request_delay_ms = 500

[cache]
max_size_gb = 10
eviction_policy = "lru"
```

## 5. Workflow de Desenvolvimento

```
1. Criar branch: feature/NOME ou fix/NOME (a partir de develop)
2. Desenvolver com testes
3. Rodar localmente: ruff check && mypy && pytest
4. Push → CI roda automaticamente
5. PR contra develop → code review (Victor + Claude)
6. Merge em develop
7. Quando estável → merge develop → main → tag release
```

## Correlação

- Baseline: [`fase-0-baseline-governanca.md`](fase-0-baseline-governanca.md)
- ADR Engenharia: [`../adr/ADR-003-engineering-security-standards.md`](../adr/ADR-003-engineering-security-standards.md)
- CI Config: [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
