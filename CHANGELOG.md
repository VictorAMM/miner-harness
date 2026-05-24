# Changelog

## [1.0.0] — 2026-05-23

### Adicionado

- **F9 — Relatório Técnico DOCX** (`--output-docx relatorio.docx`): exportação de documento Word
  estruturado compatível com due diligence e JORC-preliminar, com 7 seções — sumário executivo,
  tabela de alvos, justificativas por alvo com follow-up recomendado, análise por etapa
  (achados + fontes + lacunas), lacunas de dados consolidadas deduplicas, limitações e ressalvas
  com aviso JORC, referências de dados. Dependência: `python-docx>=1.0`.
- **F7 — Furos de Sondagem do Usuário** (`--drillholes furos.csv` / `index drillholes furos.csv`):
  ingestão de CSV de furos proprietários com suporte a 50+ aliases de colunas (en/pt-BR/acrônimos),
  separador decimal vírgula, UTF-8-BOM; persistência em SQLite via `DrillholeStore`; injeção
  automática no contexto dos agentes com prioridade máxima; marcadores laranja no mapa Leaflet;
  tabela na aba Dados do dashboard.
- **`ConfidenceCalibrator`**: recalibração de confiança dos steps baseada em cobertura de dados
  calculados (geoquímica normalizada, gradiente Bouguer, RAG, furos do usuário) — `high` somente
  quando ≥2 fontes calculadas disponíveis.
- **Derivadas Gravimétricas Bouguer** (F5 parcial): `BouguerProcessor` calcula Gradiente Horizontal
  Total (GHT) e campo residual via interpolação IDW; injetado no `GeophysicistAgent` como dado
  quantitativo.

### Melhorado

- **Contexto para agentes**: dados geoquímicos com Concentration Factor (CF) calculado e flag de
  anomalia; guia de interpretação geológica por passo no `PromptManager`; rótulo RAG específico
  por disciplina.
- **Suite de testes**: 1120 testes passando (vs. 447 na v0.1.0).

---

## [0.6.2] — 2026-05-22

### Adicionado

- **Score de prospectividade por weighted overlay** (PRD-002 F3): `ProspectivityScorer` calcula
  score 0–100 por alvo com pesos configuráveis por evidência; exibido no dashboard como barra
  de progresso por alvo.

---

## [0.6.1] — 2026-05-22

### Adicionado

- **Normalização geoquímica regional** (PRD-002 F2): `GeochemistryNormalizer` calcula CF (razão
  amostra/mediana regional) e flag `is_anomaly` para cada elemento; tabela injetada no
  `GeochemistAgent`.

---

## [0.6.0] — 2026-05-22

### Adicionado

- **Exportação GIS** (`--output-gis targets.gpkg`): `GisExporter` gera GeoPackage (`.gpkg`) com
  camadas `targets`, `ocorrencias`, `gravimetria`, `geocronologia`, `aerogeofisica`; ou GeoJSON
  (`.geojson`) com a camada de alvos apenas. Requer `geopandas`.
- **Furos de Sondagem GeoSGB** (F4): endpoint `furos_sondagem` integrado ao `GeoSGBConnector`;
  modelo `FuroSondagem` (6 campos: projeto, tipo, profundidade, azimute, mergulho, ano); marcadores
  ciano no mapa Leaflet; mencionados pelo `EvaluatorAgent` quando presentes no bbox.

---

## [0.5.23] — 2026-05-21

### Corrigido

- **Dashboard**: nota técnica `[Coordenadas originais...]` removida do campo `rationale` dos alvos;
  reposicionamento de alvos fora do bbox continua logado internamente como warning.

---

## [0.5.22] — 2026-05-21

### Corrigido

- **Dashboard**: banner de fontes ativas exibia "X de 14" em vez de "X de 8" (serviços reais);
  popup CSS com overflow; aba Dados distingue fontes bbox-filtradas de indisponíveis.

---

## [0.5.21] — 2026-05-21

### Adicionado

- **Filtro spatial por bbox** (`_filter_by_bbox`): registros com coordenadas fora do bbox (+ buffer
  de 20%) são removidos antes de enviar ao LLM.
- **Source Triage**: `bbox_filtered_sources` separa fontes com dados válidos mas fora da área de
  fontes que falharam ou retornaram vazio.
- **Validação de coords de alvos**: `_validate_target_coords()` reposiciona alvos cujo LLM gerou
  coordenadas fora do bbox para o centróide da área.

---

## [0.5.20] — 2026-05-21

### Adicionado

- **Atlas Aerogeofísico**: overlays WMS SGB/CPRM no Leaflet (🧲 Magnetometria Total, 🌈 K-Th-U,
  ✈️ Pol. Projetos) + marcadores interativos de projetos por tipo de levantamento com popup offline.
- **Litoestratigrafia no mapa**: marcadores quadrados por hierarquia (Formação/Grupo/etc.) +
  tabela na aba Dados.

### Corrigido

- **Code Review**: 11 bugs críticos corrigidos (2 HIGH, 6 MED, 3 LOW) incluindo `_extract_json`
  `ValueError`, coords de fallback silenciosas, `BoundingBox` validação de ordem, `_ctx_scale`
  floor, path traversal no CLI, `objectid/_safe_int`, `__del__` do `CacheManager`.

---

## [0.5.19] — 2026-05-20

### Melhorado

- **`ContextBuilder`**: registros ordenados por distância ao centróide do bbox antes de truncar
  (mais próximos primeiro; sem coord → fim da lista).

---

## [0.5.18] — 2026-05-20

### Melhorado

- **Data Scale**: limites de dados (`max_records`, `max_chars`, `prev_results`) escalam com
  √(num_ctx/4096) — contexto 65k → 200 registros, 32k chars, 8k chars de histórico.

---

## [0.5.17] — 2026-05-20

### Adicionado

- **`--ctx-size TOKENS`**: janela de contexto configurável via CLI; `num_ctx` propagado ao
  `OllamaClient`; Modelfile `qwen3-64k` para KV-cache Q4 com 65k tokens.

---

## [0.5.16] — 2026-05-20

### Adicionado

- **Deduplicação de Alvos** (`_dedup_targets`): alvos sobrepostos (distância Haversine < 10 km)
  são mesclados; prioridades renumeradas em sequência.

---

## [0.5.15] — 2026-05-20

### Melhorado

- **Dashboard**: `integrated_summary` exibido em caixa destacada nas abas Análise e Alvos.

---

## [0.5.14] — 2026-05-20

### Melhorado

- **`integrated_summary`**: gerado pelo `EvaluatorAgent` (em vez de concatenação de achados);
  `_dedup_gaps_semantic` remove lacunas semanticamente duplicadas entre steps.

---

## [0.5.13] — 2026-05-20

### Corrigido

- **`MineralTarget`**: `model_validator` normaliza `mineralization_system` → `mineral_system`
  evitando perda silenciosa de alvos quando o LLM usa o nome alternativo.

---

## [0.5.12] — 2026-05-20

### Adicionado

- **Widget de Ocorrências**: sidebar com pills coloridas por substância (×N), filtro por confiança
  e toggles ANM/USGS conectados ao mapa.

---

## [0.5.11] — 2026-05-20

### Adicionado

- **Mapa de Ocorrências**: pontos GeoSGB coloridos por substância no Leaflet com legenda,
  toggle e tabela na aba Dados.

---

## [0.5.10] — 2026-05-20

### Adicionado

- **Tabela de Sistema Mineral**: referência obrigatória no prompt `total_integration` com
  critérios de Fertilidade, Arquitetura, Fluido e Trap por sistema (IOCG, Ouro Orogênico, etc.).
- **Badge de Confiança Baixa**: borda laranja + ícone ⚠ em steps com `confidence=low/insufficient`
  no dashboard.

---

## [0.5.9] — 2026-05-20

### Adicionado

- **UX Data Fetch**: resumo de fontes ativas/indisponíveis impresso antes do pipeline LLM.
- **Dedup Data Gaps**: prompt do `EvaluatorAgent` consolida `data_gaps` duplicados entre steps.

### Segurança

- Dependência `ollama` (SDK oficial) removida: 6 CVEs eliminadas. O sistema usava apenas
  `OllamaClient` próprio via `httpx`.

---

## [0.5.8] — 2026-05-20

### Adicionado

- **`--llm-timeout SECONDS`**: timeout do Ollama configurável via CLI (padrão: 120s).
- **Extração de Commodities**: `_findings_to_targets` extrai commodities do texto com vocabulário
  PT-BR/EN (ouro, cobre, ferro, manganês, etc.).

### Corrigido

- Política de event loop async cross-platform (Windows SelectorEventLoop).
- Coordenadas nulas do GeoSGB tratadas sem crash.
- Propagação de config `OllamaClient` → agentes.

---

## [0.5.7] — 2026-05-20

### Adicionado

- **TTL Explícito**: 30 dias para ANM/SIGMINE, 7 dias para USGS Earthquakes no `TTLPolicy`.
- **Cache Evict** (`miner-harness cache evict`): remoção automática de entradas expiradas no
  startup + comando CLI. `evict_expired()` lê apenas metadados (sem desserializar blobs JSON).

### Corrigido

- Compatibilidade Python 3.10 em testes (`timezone.utc`), `StrEnum` shim no wizard.
- Skip automático do bug Hypothesis 6.152.x em property tests.
- Cobertura de testes elevada a 100% nos módulos críticos.

---

## [0.5.6] — 2026-05-20

### Corrigido

- **Cache**: resultados de fetch com falha (erro transitório / serviço indisponível) não são
  mais armazenados no cache — evita bloquear execuções futuras com dados inválidos.

---

## [0.5.5] — 2026-05-20

### Melhorado

- **Qualidade de Prompts**: guia de interpretação geológica por passo injetado no `PromptManager`;
  rótulo RAG específico por disciplina evita cruzamento de contexto irrelevante (ex: pH em
  achados tectônicos).

---

## [0.5.4] — 2026-05-20

### Melhorado

- **`ContextBuilder.build()`**: 6 serviços GeoSGB + ANM + USGS consultados em paralelo via
  `asyncio.gather()` — tempo de fetch reduzido de ~serial para ~max_individual.

---

## [0.5.3] — 2026-05-20

### Adicionado

- **`--min-sources N`**: mínimo de fontes de dados ativas configurável via CLI (padrão: 3).
  `InsufficientDataError` agora inclui hint acionável com sugestão de `--min-sources`.

---

## [0.5.2] — 2026-05-19

### Adicionado

- **bbox no EvaluatorAgent** (P0): coordenadas do bbox injetadas no prompt do avaliador para
  posicionamento correto dos alvos.
- **Progresso de Fetch** (P1): SSE `data_fetch_progress` emitido por fonte no modo `--serve`.
- **Logs debug** (P2): logging estruturado de contagem de registros por fonte.

---

## [0.5.1] — 2026-05-20

### Adicionado

- **`--profile`**: `ProfilingRunner` coleta tempos wall-clock e LLM por step; imprime tabela
  `Pipeline Profile` ao final da análise.
- **Suite de Benchmarks** (`tests/benchmarks/`): latência de pipeline, cache hit, SSE.

---

## [0.5.0] — 2026-05-19

### Melhorado

- **Paralelização dos Passos 3 e 4**: agentes `MagmaticFertilityAgent` e `IndirectEvidenceAgent`
  executados em `asyncio.gather()` — latência total reduzida ~30–40% em máquinas com GPU ociosa
  entre calls.
- **Merge de Resultados**: `_merge_parallel_results` consolida findings e targets dos dois agentes
  paralelos com deduplicação.

---

## [0.4.0] — 2026-05-19

### Adicionado

- **ANM/SIGMINE**: concessões minerárias via API REST; modelo `ConcessaoMineira` (fase, titular,
  substâncias, área); marcadores no mapa com toggle por fase; injetadas no `EvaluatorAgent`.
- **USGS Earthquake Hazards**: eventos sísmicos via API USGS; modelo `EventoSismico`; círculos
  no mapa dimensionados por magnitude; injetados no `GeophysicistAgent`.
- **TTL diferenciado**: ANM 30d, USGS 7d, GeoSGB 7d (padrão).
- **Dashboard Interativo v2**: layers ANM (vermelho) + USGS (roxo) com toggles independentes;
  mini-legenda de magnitude sísmica; aba Dados com tabelas por fonte.

---

## [0.3.0] — 2026-05-19

### Adicionado

- **Servidor HTTP local** (`--serve`): `DashboardServer` baseado em `aiohttp` com suporte a
  WebSocket/SSE para análise interativa — análise nova sem reiniciar o processo.
- **SSE (Server-Sent Events)**: `SseChannel` emite eventos `data_fetch_start`, `data_fetch_done`,
  `step_start`, `step_complete`, `complete`, `error` — progresso em tempo real no browser.
- **`AnalysisRunner`**: subclasse do `Orchestrator` que envia eventos SSE a cada step.
- **Dashboard Interativo** ("Nova Pesquisa"): painel lateral no HTML com form de nova análise,
  barra de progresso por step, log de eventos SSE.
- **`--port`**: porta configurável do servidor (padrão: 8765).

---

## [0.2.1] — 2026-05-18

### Adicionado

- **Dashboard HTML interativo** (`miner-harness analyze`): após cada análise, gera automaticamente um arquivo HTML self-contained com:
  - Mapa **Leaflet.js 1.9.4** com 3 camadas de tiles (OSM, ESRI Satellite, ESRI Topo), marcadores SVG por prioridade (P1–P5), círculos de `radius_km`, polígono BBox, popups com detalhes dos alvos, botão "Centralizar região" e toggle BBox
  - Gráficos **Chart.js 4.4**: donut de qualidade (sidebar), barras de confiança por passo, barras de duração, radar de cobertura GeoSGB
  - Tabs: Análise (accordion por step), Alvos (cards com rationale + follow-up), Qualidade (3 gráficos), JSON (formatado + botão copiar)
  - Assets JS/CSS embutidos inline — arquivo abre offline
  - Auto-open no browser padrão via `webbrowser.open()`
- **`HtmlReportRenderer`** em `miner_harness.report` — API: `render(report) -> str`, `render_to_file(report, path) -> Path`
- **Flag `--no-html`** no subcomando `analyze` para suprimir geração do dashboard
- **12 testes** em `tests/report/test_renderer.py` cobrindo estrutura HTML, injeção de dados, escrita em disco, targets múltiplos e vazios

## [0.2.0] — 2026-05-18

### Adicionado

- **RAG (Retrieval-Augmented Generation)** integrado ao pipeline de análise:
  - `SearchEngine.index_batch()` indexa features GeoSGB no vector store após cada `ContextBuilder.build()`
  - `Orchestrator._execute_step()` consulta o índice vetorial com query geológica específica por step (`_STEP_RAG_QUERIES`) e injeta o contexto recuperado no prompt do agente
  - `OrchestratorConfig.use_rag: bool = True` — toggle para habilitar/desabilitar
  - `BaseAgent.build_prompt()` agora lê `geological_data["rag_context"]` e acrescenta ao bloco de dados geológicos enviado ao LLM
- **Scripts de automação** em `scripts/`:
  - `setup_dev.sh` — verifica Python 3.11+, instala uv, sincroniza deps, verifica Ollama
  - `pull_models.sh` — faz pull de `qwen3:8b` + `nomic-embed-text` via Ollama
  - `run_analysis.sh` — wrapper para `miner-harness analyze <region> --bbox ...`
- **`infra/docker-compose.yml`** — serviço Ollama (`ollama/ollama:latest`, porta 11434, volume persistente)

### Corrigido

- **Resiliência a HTTP 503 do GeoSGB** (serviço `litoestratigrafia`): novo método `_backoff_503()` no `ThrottledClient` com delays 5× maiores (base ≥ 2.5s), evitando storm de retries em serviços sobrecarregados

## [0.1.12] — 2026-05-18

### Corrigido

- **Prompt Evaluator (Passo 5)**: formato de resposta dedicado — `targets` obrigatório, `priority=1` é o melhor alvo (LLM começava em 2), commodities concretas obrigatórias (nunca `["Indeterminado"]`), coordenadas reais do bbox
- **Prompts passos 1–4**: `"targets": []` sem ruído de exemplos de alvos no formato de resposta

## [0.1.11] — 2026-05-18

### Adicionado

- **Extração de targets estruturados pelo `EvaluatorAgent`**: o campo `targets` do JSON já solicitado ao LLM agora é parseado e validado como `MineralTarget` — alvos reais (nome, commodities, sistema mineral, coordenadas) substituem os placeholders "Alvo N / Indeterminado"
- **`StepResult.targets`**: novo campo opcional `list[MineralTarget]` (default `[]`) para carregar os targets extraídos pelo Evaluator

### Corrigido

- **`BaseAgent` default model**: `qwen3:8b-q4_K_M` → `qwen3:8b` (tag inexistente no Ollama sem pull específico)

## [0.1.10] — 2026-05-18

### Corrigido

- **Modelo padrão**: `qwen3:8b-q4_K_M` → `qwen3:8b` em todos os defaults (tag explícita de quantização não existe no Ollama sem pull específico)
- **`cmd_analyze` encoding**: `write_text()` sem `encoding='utf-8'` gravava JSON em cp1252 no Windows; adicionado `encoding="utf-8"`
- **`hypothesis`**: adicionado em `[dependency-groups].dev` (já estava em `[project.optional-dependencies].dev` mas ausente no grupo usado por `uv sync`)

## [0.1.9] — 2026-05-18

### Corrigido

- **`check_cache` / `check_index`**: estado "not found, will be created on first use" agora retorna `HEALTHY` em vez de `DEGRADED` — instalação nova é saudável por definição
- **`check_disk_space`**: threshold absoluto tem prioridade sobre percentual; `UNHEALTHY` somente quando `< 2 GB` livres; `DEGRADED` quando `< 5 GB` ou `< 5%`; corrige falso positivo em SSDs grandes (ex.: 19 GB livres = 4% → DEGRADED, não UNHEALTHY)
- **`miner-harness health`**: comando agora retorna `HEALTHY` em instalação limpa

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
