# Changelog

## [0.1.8] — 2026-05-18

### Corrigido

- **`test_pipeline_live`**: testes `connector_to_cache` e `cache_hit_evita_requisicao` usavam API inventada (`set(key=...)` / `get(key=...)`); corrigidos para a API real `put(service, bbox, features)` / `get(service, bbox)`
- **`test_pipeline_connector_to_cache`**: trocado de gravimetria (sem cobertura em Carajás) para ocorrências minerais, que sempre retorna dados nessa BBox

## [0.1.7] — 2026-05-18

### Corrigido

- **Suite e2e robustez**: `GeoSGBConnectionError` agora converte em `pytest.skip` via `hookwrapper` no conftest — API GeoSGB tem disponibilidade intermitente, falha de conexão não deve marcar o sistema como quebrado
- **Gravimetria em Carajás**: `assert len > 0` substituído por `pytest.skip` quando sem cobertura (confirmado: serviço não tem dados nessa BBox)
- **Threshold de contagem total**: `>100 000` → `>20 000` (base real tem ~36 k ocorrências em 2026-05)
- **`pytest-timeout>=2.3`**: adicionado em `[dev]` e `[dependency-groups]` (era usado em `e2e.yml` mas não declarado como dependência)
- **`release.yml`**: publish simplificado — `uv publish` usa Trusted Publishing (OIDC) quando `PYPI_API_TOKEN` não está configurado

## [0.1.6] — 2026-05-17

### Corrigido

- **`context_builder`: cache de falhas de serviço**: quando um serviço GeoSGB lança exceção (ex: `litoestratigrafia` com 503), o resultado vazio agora é persistido no cache tal como uma resposta normal. Sem isso, cada execução desperdiçava ~60s esperando o timeout do serviço quebrado.

## [0.1.5] — 2026-05-17

### Corrigido

- **`_query_via_ids` — parâmetro `resultRecordCount` removido do passo 1**: incluir `resultRecordCount` na requisição `returnIdsOnly` causava HTTP 200 com `{"error":{"code":400}}` nos serviços `geologia/ocorrencias`, `geoquimica/geoquimica_integrada` e `geologia/geocronologia`. Removido do passo de IDs; o limite `max_ids` agora é aplicado como slice pós-fetch. O servidor retorna até 1000 IDs por padrão, suficiente para a maioria das regiões.
- **`gravimetria`**: confirmado que o serviço não tem dados no bbox Carajas (retorna `objectIds: null`) — comportamento correto, não é bug.
- **`litoestratigrafia` / `aerogeofisica`**: retornam `{"error":{"code":503}}` (timeout server-side de ~60s); tratados como degradação graciosa (retorna `[]`).

## [0.1.4] — 2026-05-17

### Corrigido

- **Fallback `_query_via_ids`**: `geologia/ocorrencias`, `geoquimica/geoquimica_integrada` e `geologia/geocronologia` retornam HTTP 200 com `{"error":{"code":400}}` para qualquer query com `outFields`, mas aceitam `returnIdsOnly=true`. Novo método `_query_via_ids` faz dois passos: (1) obtém OIDs via `returnIdsOnly` com filtro de BBOX, (2) busca atributos em lotes via `objectIds=...`. O fallback é ativado automaticamente em `_query_features` quando detecta error 400 na resposta.
- **Timeout aumentado de 30s para 90s**: serviços com polígonos complexos (`litoestratigrafia_1000000`, `aerogeofisica`) precisam de mais tempo de resposta do servidor.

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
