# Changelog

## [0.1.3] — 2026-05-17

### Corrigido

- **Caminhos de serviço GeoSGB**: todos os 6 serviços usavam o prefixo `GEOSGB/` inexistente; corrigidos para os caminhos reais (`geologia/`, `geofisica/`, `geoquimica/`)
- **Migração para FeatureServer/query**: todos os serviços migrados de MapServer/identify (que retornava `{"results":[]}` silenciosamente) para FeatureServer/query com filtro espacial por BBOX — mais confiável e não requer grid de pontos
- **Geoquímica multi-layer**: consulta as 3 camadas mais relevantes para prospecção mineral (Sedimento de Corrente, Rocha, Solo)
- **Aerogeofísica multi-layer**: consulta as 4 séries históricas de levantamentos (Séries 1000–4000)

### Mapeamento de serviços (antigo → novo)

| Serviço | Antes | Depois |
|---|---|---|
| ocorrencias | `GEOSGB/ocorrencias_minerais/MapServer` | `geologia/ocorrencias/FeatureServer` |
| gravimetria | `GEOSGB/dados_gravimetricos/FeatureServer` | `geofisica/gravimetria/FeatureServer` |
| geoquimica | `GEOSGB/geoquimica/MapServer` | `geoquimica/geoquimica_integrada/FeatureServer` |
| geocronologia | `GEOSGB/geocronologia/MapServer` | `geologia/geocronologia/FeatureServer` |
| litoestratigrafia | `GEOSGB/unidades_litoestratigraficas/MapServer` | `geologia/litoestratigrafia_1000000/FeatureServer` |
| aerogeofisica | `GEOSGB/projetos_aerogeofisicos/MapServer` | `geofisica/aerogeofisica/FeatureServer` |

## [0.1.2] — 2026-05-17

### Corrigido

- **GeoSGB connector**: `_extract_via_identify` agora captura `httpx.HTTPStatusError` (além de `GeoSGBError`) — HTTP 500s do MapServer pulam o ponto de grid falho e continuam sem travar o pipeline
- **GeoSGB connector**: `_query_features` converte `HTTPStatusError` em `GeoSGBQueryError`, permitindo que o `context_builder` faça degradação graciosa (retorna `[]` para o serviço) em vez de propagar a exceção
- O pipeline agora produz relatório parcial quando ≥3 de 6 serviços GeoSGB respondem com sucesso, em vez de lançar `InsufficientDataError` quando todos retornam 500

## [0.1.1] — 2026-05-17

### Corrigido

- **CLI `analyze`**: argumento `region` era flag nomeada (`--region`); corrigido para posicional
- **CLI `analyze`**: `--bbox` com floats negativos era interpretado pelo argparse como flags; corrigido via `nargs=4, type=float`

## [0.1.0] — 2026-05-17

Primeira release — todas as 11 fases do ASO v3 completas.

### Adicionado

**Core**
- `core/types.py` — modelos Pydantic para todos os domínios geológicos (OcorrenciaMineral, DadoGravimetrico, AmostraGeoquimica, DatacaoGeocronologica, UnidadeLitoestratigrafica, ProjetoAerogeofisico, ProspectionReport)
- `core/config.py` — configuração hierárquica (MinerHarnessConfig, StorageConfig, GeoSGBConfig, OrchestratorConfig)
- `core/exceptions.py` — hierarquia de exceções tipadas

**Conectores**
- `connectors/geosgb/` — connector completo para API GeoSGB: MapServer/identify (grid + dedup) + FeatureServer/query com paginação, rate limiting, alias mapping
- `connectors/ollama/` — cliente async httpx para Ollama: chat, embeddings, list_models, health

**Orquestrador**
- `orchestrator/orchestrator.py` — pipeline principal: connector → cache → context → agentes → report
- `orchestrator/report_validator.py` — validação e reparo automático de relatórios
- `orchestrator/context_builder.py` — construção de contexto para agentes

**Agentes**
- `agents/` — 5 agentes especialistas: geólogo estrutural, geofísico, geoquímico, sensoriamento remoto, avaliador
- `agents/base.py` — classe base com retry e logging estruturado

**Cache**
- `cache/manager.py` — CacheManager com TTL configurável
- `cache/sqlite_store.py` — persistência SQLite

**Índice**
- `index/document_store.py` — índice vetorial via sqlite-vec
- `index/search_engine.py` — busca semântica

**Observabilidade**
- `observability/health.py` — health checks async (disco, Ollama, cache, índice)
- `observability/metrics.py` — MetricsCollector com structlog
- `observability/logging_config.py` — configuração de logging estruturado

**RCA**
- `rca/classifier.py` — classificação automática de falhas
- `rca/diagnostics.py` — diagnóstico estruturado
- `rca/reporter.py` — geração de relatórios RCA em JSON
- `rca/retry.py` — retry com backoff exponencial

**Self-Improvement**
- `self_improvement/profiler.py` — profiling de pipeline e identificação de gargalos
- `self_improvement/tuner.py` — geração de recomendações de tuning
- `self_improvement/rca_learner.py` — aprendizado a partir de histórico de RCA
- `self_improvement/feedback_loop.py` — ciclo Profile → Tune → Apply → Learn

**Wizard**
- `wizard/checks.py` — verificações puras de pré-requisitos (Python, disco, Ollama, MINER_HOME)
- `wizard/installer.py` — criação de MINER_HOME, config.json, env_hint.sh
- `wizard/runner.py` — UI Rich com injeção de Console para testabilidade

**CLI**
- `miner-harness analyze` — pipeline completo de análise
- `miner-harness validate` — validação de relatório JSON
- `miner-harness install` — wizard de instalação (interativo e --non-interactive)
- `miner-harness health` — health checks do sistema
- `miner-harness cache stats/clear` — gestão do cache

**Testes**
- 447 testes unitários e de integração (92% cobertura)
- 17 testes e2e opt-in (`MINER_E2E=1`) contra GeoSGB real e Ollama local

**CI/CD**
- GitHub Actions: lint (ruff), typecheck (mypy), test (3.11 + 3.12), security (bandit + pip-audit), gate
- Workflow e2e separado (manual + schedule semanal)
