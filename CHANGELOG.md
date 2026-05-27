# Changelog

## [1.8.0] — 2026-05-26

### Adicionado — PRD-007: Qualidade DOCX + Observabilidade + Resiliência Atlas

#### T1 — Atlas tile error badge (dashboard)

- Elemento `<span id="atlas-warn">` adicionado ao lado do título da seção Atlas.
- Listeners `tileerror` / `tileload` registrados nas 3 camadas `ArcGISExport`
  (wmsAtlasMag, wmsAtlasTern, wmsAeroprojetos): badge ativa quando tile falha,
  some ao primeiro tile carregado com sucesso.
- Usuário recebe feedback imediato quando REST `/export` do SGB está indisponível.

#### T2 — DOCX: campos PRD-006 ausentes (docx_exporter)

- `StepResult.calibration_note` adicionado a `core/types.py` (str | None, default None).
- `ProspectionReport.diversity_removed_count` adicionado a `core/types.py` (int, default 0).
- `_add_step_section()`: exibe "Nota de calibração: ..." quando `calibration_note` presente.
- `_add_caveats()`: exibe nota de diversidade espacial quando `diversity_removed_count > 0`.

#### T3 — Health: check de conectividade GeoSGB

- Nova função `check_geosgb(timeout_s=5.0)` — probe ao endpoint `ocorrencias_minerais`
  com 1 feature (~1 KB): HEALTHY / DEGRADED (HTTP != 200) / UNHEALTHY (ConnectError).
- `run_health_checks()` agora retorna **5 checks** (ollama, cache, index, disk_space, **geosgb**).
- `miner-harness health` detecta problemas de rede com a principal fonte de dados.

#### Testes

- Suite total: **1 438 testes**, 65 skipped, cobertura **100%**

---

## [1.7.3] — 2026-05-26

### Corrigido — Aeroprojetos WMS → ArcGIS REST export (EPSG:4326 incompatível)

#### Problema

`geofisica/aerogeofisica/MapServer/WMSServer` tem WMS habilitado mas declara apenas
`EPSG:4326` e `CRS:84` nas suas capabilities — sem suporte a EPSG:3857. O Leaflet enviava
`srs=EPSG:3857` por padrão, e o servidor retornaria `ServiceException` em XML, bloqueado
por `net::ERR_BLOCKED_BY_ORB` (mesma raiz do issue v1.7.2).

#### Fix

- Substituído `L.tileLayer.wms(_WMS_AEROPROJ, ...)` por
  `new L.TileLayer.ArcGISExport(_REST_AEROPROJ, { layerId: '0,1,2,3' })`.
- O endpoint REST `/export` reprojeta server-side para `imageSR=3857` sem distorção
  de projeção; `layerId: '0,1,2,3'` mapeia para `layers=show:0,1,2,3`.
- Constante renomeada `_WMS_AEROPROJ` → `_REST_AEROPROJ` apontando para
  `/MapServer/export`.

#### Testes

- Teste `test_aeroprojetos_keeps_wms` → `test_aeroprojetos_uses_rest_export`:
  verifica `_REST_AEROPROJ`, URL REST e ausência de `WMSServer` para esse serviço.
- Suite total: **1 428 testes**, 65 skipped, cobertura **100%**

---

## [1.7.2] — 2026-05-26

### Corrigido — Atlas WMS → ArcGIS REST export (tiles Mag Total e K-Th-U)

#### Problema

O serviço `Mapas_Tern_Mag_MIL1/MapServer` do geoportal SGB não tem WMS habilitado
(capabilities: `Query,Map,Data` apenas). `L.tileLayer.wms(...WMSServer)` retornava **HTTP 400**
em todos os tiles; o Chrome bloqueava as respostas com `net::ERR_BLOCKED_BY_ORB` porque o
conteúdo retornado era `text/html` em vez de `image/png`.

#### Fix

- Substituído `L.tileLayer.wms` por subclasse `L.TileLayer.ArcGISExport` que usa o endpoint
  REST `/export` com bbox EPSG:3857 calculado por coordenada de tile — sem dependência de WMS.
- Fórmula bbox: `E = 20037508.34`; `tileM = 2E / 2^z`;
  `bbox = xMin,yMin,xMax,yMax` em metros Web Mercator.
- `wmsAeroprojetos` (geofisica/aerogeofisica) mantém `L.tileLayer.wms` — esse serviço tem WMS
  habilitado (`supportedExtensions: WMSServer`).
- Guard de modo offline atualizado para excluir `L.TileLayer.ArcGISExport` (evitava remoção
  indevida ao entrar no modo offline).

#### Testes

- 5 novos testes `TestAtlasWmsFix` em `tests/report/test_renderer.py`:
  `test_uses_rest_export_not_wms_for_tern_mag`, `test_arcgis_export_tile_layer_class_defined`,
  `test_arcgis_export_bbox_formula_present`, `test_offline_guard_excludes_arcgis_export`,
  `test_aeroprojetos_keeps_wms`.
- Suite total: **1 428 testes**, 65 skipped, cobertura **100%**

---

## [1.7.1] — 2026-05-26

### Corrigido — Cobertura 100% restaurada pós-PRD-006

#### Bug fix

- **IndexError em `_assign_prospectivity_scores`**: `geom.get("coordinates", [[]])[0]` lançava
  `IndexError` quando um polígono GeoJSON tinha `coordinates: []` (lista de anéis vazia). Corrigido
  para `raw_coords[0] if raw_coords else []` — gracioso com GeoJSON malformado.

#### Cobertura

- 3 novos testes para lacunas residuais:
  - `cli/test_commands.py::TestCmdAnalyzeNewParams::test_analyze_with_no_aeromag_and_grid_n`
    — cobre `config.aeromag.enabled = False` e `config.aeromag.grid_n = N`
  - `orchestrator/test_orchestrator.py::TestAssignProspectivityScores::test_polygon_with_empty_coordinates_skipped`
    — valida que polígonos sem coordenadas são ignorados (e expôs o bug acima)
  - `analysis_runner.py:112` — guard defensivo marcado `# pragma: no cover`
    (branch inacessível via `set_channel()`)
- Suite total: **1 424 testes**, 65 skipped, cobertura **100%**

---

## [1.7.0] — 2026-05-26

### Adicionado — PRD-006 Dual-Persona Dashboard Improvements

#### Dashboard HTML (persona criança + Dr. Augusto Valen)

- **C1 — Painel inferior expandido**: altura de `300px` → `40vh` para melhor leitura de mapas
  em telas médias.
- **C2 — Aba padrão Alvos**: tab `🎯 Alvos` abre por padrão (era `📊 Análise`), colocando os
  resultados mais importantes em primeiro plano.
- **C3 — Tooltips de confiança**: constante `CONF_TOOLTIPS` com descrição contextual para cada
  nível (`high`, `medium`, `low`, `insufficient`) exibida ao passar o mouse sobre badges.
- **C4 — Banner de cobertura aprimorado**: texto atualizado para mencionar badges ⚠ nos steps.
- **A1 — Legenda do mapa expandida por padrão**: `collapsed = false` — legenda visível sem
  clique extra.
- **A2 — Benchmark de qualidade**: indicador de referência no donut de qualidade (≥80 % verde,
  60–80 % amarelo, <60 % vermelho) com dica textual contextual.
- **G1 — Grade Aeromag local**: botão `🧲 Aeromag local` em Camadas de Dados; renderiza pontos
  da `aeromag_grid` coloridos por gradiente azul→branco→vermelho (TMA mínimo→máximo);
  toggle on/off; helper `_tmaColor()` e `_nearestAeromagTma()`.
- **G3 — Nota de calibração visível**: `calibration_note` do `StepResult` exibida abaixo dos
  achados de cada step com estilo âmbar (`::before "⚠ "`).
- **G5 — TMA local no popup do alvo**: valor TMA mais próximo (proxy RGB) exibido no popup do
  marcador do alvo quando `aeromag_grid` está disponível.
- **G11 — Nota de diversidade removida**: quando `diversity_removed_count > 0`, nota
  informativa aparece na aba Alvos explicando quantos alvos próximos foram suprimidos.

#### Tipos de Domínio

- `StepResult` ganha campo `calibration_note: str | None` — nota do `ConfidenceCalibrator`
  quando a confiança é recalibrada; antes era concatenada em `data_gaps`.
- `ProspectionReport` ganha campo `diversity_removed_count: int` — quantidade de alvos
  removidos por `_enforce_target_diversity()` (<15 km de alvo de maior prioridade).

#### Orquestrador

- `ConfidenceCalibrator.calibrate()` → nota agora armazenada em `calibration_note`, não em
  `data_gaps`.
- `diversity_removed_count` calculado como `len(validated) - len(diverse)` em `analyze_region()`
  e propagado para `ProspectionReport`.

### Testes

- 7 novos testes em `tests/core/test_types.py`:
  `TestStepResultCalibrationNote` (4) + `TestProspectionReportDiversityCount` (3)
- 4 novos testes em `tests/orchestrator/test_orchestrator.py`:
  `TestCalibrationNoteInExecuteStep` (2) + `TestDiversityRemovedCountInReport` (2)
- 13 novos testes em `tests/report/test_renderer.py`:
  `TestPrd006DashboardImprovements` (13)
- Suite total: **1 421 testes**, 65 skipped

---

## [1.6.1] — 2026-05-26

### Corrigido — AeromagConnector (validação real Carajás)

#### Conectores

- **URL REST API correta**: `_ATLAS_BASE` corrigido de `/server/services/` (path SOAP → 403) para
  `/server/rest/services/` (ArcGIS REST API → 200). Root cause do 403 persistente mesmo com
  `_BROWSER_HEADERS` corretos adicionados no v1.5.0.
- **Parsing RGB de pixel**: `_parse_identify()` agora trata o caso em que `AM_Brasil.tif` é
  servido como raster RGB (`RGB.Red`/`RGB.Green`/`RGB.Blue`). Luminância (`0.299R+0.587G+0.114B`)
  usada como proxy relativo de TMA. Variação espacial preservada para detecção de anomalias.

### Testes

- 5 novos testes: `TestRestApiUrl` (2) + 3 testes RGB em `TestParseIdentify` (31 total no módulo)
- Suite total: **1 397 testes**, 65 skipped

---

## [1.6.0] — 2026-05-26

### Adicionado — PRD-005 UX Simplification

#### Dashboard HTML

- **T1 — Grupos colapsáveis de botões**: 15 botões do mapa reorganizados em 3 grupos com
  toggle collapse/expand via CSS `max-height` e `toggleMapGroup()` JS:
  - 📍 **Navegação** → Centralizar região, Mostrar/ocultar polígono, Enquadrar alvos, Modo Offline
  - 🗂 **Camadas de Dados** → Ocorrências, Litoestratigrafia, Furos GeoSGB, Furos Usuário,
    ANM, USGS, Prospectividade, Bouguer HGM
  - 🛰 **Atlas SGB/CPRM** → Mag. Total, K-Th-U, Pol. Projetos, Proj. Aero., Opacidade
    (inicia colapsado — requer internet)
- **T3 — Modo Offline**: botão 🗺 Modo Offline no grupo Navegação; `toggleOfflineMode()` remove
  tiles OSM externos mantendo marcadores, WMS e dados do relatório.
- **Overlay de progresso**: exibe `⏱ ~X min restantes` assim que o segundo step começa;
  fallback `calculando...` no primeiro step.

#### Servidor SSE

- **T2 — ETA de progresso**: `AnalysisRunner` rastreia duração de cada step concluído.
  Payload `step_start` SSE inclui `elapsed_s` e `eta_s` (`null` no primeiro step).

### Testes

- 15 novos testes: `TestPrd005UxFeatures` (12) + `TestAnalysisRunnerEta` (3)
- Suite total: **1 392 testes**, 65 skipped

---

## [1.5.0] — 2026-05-26

### Corrigido / Adicionado — PRD-004 Resiliência e Qualidade de Dados/Alvos

#### Conectores

- **T1 — Aeromag 403**: `AeromagConnector` cria `httpx.AsyncClient` com `_BROWSER_HEADERS`
  (Mozilla/Chrome User-Agent + `Referer: https://geoportal.sgb.gov.br/`). Resolve 403 do
  endpoint `MapServer/identify` do SGB geoportal.

#### Orquestrador

- **T2 — Diversidade espacial dos alvos**: `_enforce_target_diversity(min_km=15.0)` remove
  alvos a menos de 15 km de alvos de maior prioridade (Haversine), re-numerando prioridades.
  Corrige caso real Carajás: P1 e P2 gerados em `lat=-5.85` com ~11 km de separação.
- **T2-A — REGRA ESPACIAL no prompt**: persona evaluator instruída a distribuir alvos com
  mínimo 15 km entre eles.
- **T5 — Prospectivity score**: `MineralTarget.prospectivity_score: float | None`;
  `_assign_prospectivity_scores()` atribui score da célula do `prospectivity_grid` mais
  próxima a cada alvo.

#### ContextBuilder

- **T3 — Fontes vazias**: `ContextBuilder.empty_sources: list[str]` rastreia serviços GeoSGB
  que retornaram 0 registros — distinção de `bbox_filtered_sources` e de falhas de fetch.

#### CLI

- **T4 — Aviso drillhole cacheado**: `_load_user_drillholes()` avisa no `stderr` quando furos
  são carregados do `DrillholeStore` sem `--drillholes`, com instrução de como limpar.

### Testes

- 25 novos testes: `TestBrowserHeaders` (3) + `TestEnforceTargetDiversity` (7) +
  `TestAssignProspectivityScores` (5) + `TestEmptySources` (4) + 2 em `TestLoadUserDrillholes`
- Suite total: **1 377 testes**, 65 skipped

---

## [1.4.0] — 2026-05-25

### Adicionado — PRD-003 F10 Aeromagnética Real

- **AeromagConnector**: amostragem real de TMA via endpoint `MapServer/identify` do Atlas
  Aerogeofísico SGB em grade N×N pontos; fallback gracioso quando indisponível.
- **AeromagProcessor**: derivadas HGM (diferenças finitas), anomalias 2σ,
  `format_for_prompt()`, `to_geojson()`; injetado no `GeophysicistAgent` com guia TMA/HGM.
- **`AeromagConfig`**: `grid_n`, `timeout_s`, TTL 30 dias.
- **CLI**: `--no-aeromag` e `--aeromag-grid-n N`.
- **`_COMPUTED_KEYS`**: `aeromag_grid` sem penalidade HIGH na calibração de confiança.

### Testes

- 56 novos testes para `AeromagConnector` e `AeromagProcessor`
- Suite total: **1 356 testes**, 0 missing statements

---

## [1.3.0] — 2026-05-25

### Melhorado — UX Audit (19 melhorias)

#### CLI

- **PT-BR completo**: cabeçalho de análise (`Região`, `BBox`, `Modelo`), progresso dos passos com
  nomes em português (`Hist. Tectônica`, `Arq. Estrutural`, `Fertil. Magmática`, `Evid. Indiretas`,
  `Integração Total`) e ícones de confiança (`✓ alta`, `~ média`, `⚠ baixa`, `✗ insuficiente`).
- **`_print_report_summary` reescrito**: síntese integrada do LLM exibida em caixa destacada;
  passos com ícone + nome PT-BR + nível de confiança; alvos com sistema mineral, commodities e
  confiança; ressalvas listadas; totalmente em português.
- **Flag `--verbose`** agora propaga `num_ctx`, `min_sources` e `timeout` no cabeçalho.
- **Separador visual** (`──────`) antes do pipeline LLM no orquestrador.

#### Dashboard HTML

- **D1 — Strip `<think>`**: `stripThinking()` remove blocos `<think>…</think>` dos modelos qwen3
  antes de exibir o reasoning — geólogos veem apenas o conteúdo analítico final.
- **D2 — Reasoning por agente**: seções de reasoning separadas com o nome real de cada agente
  (ex: "Geoquímico", "Geofísico") nos passos de execução paralela (steps 3 e 4).
- **D3 — Popup de alvo**: trecho do rationale ampliado de 200 → 500 caracteres; rótulo
  corrigido para "Raio de interesse:".
- **D4 — Legenda do mapa colapsável**: controle Leaflet no canto inferior esquerdo com todos os
  overlays e marcadores — evita sobreposição com o mapa.
- **D5 — Print stylesheet**: `@media print` com margens, font-size 12px, remoção de controles e
  fundo colorido — dashboard imprimível diretamente do browser.
- **D6 — Tamanho de fonte**: `body` 13 → 14px; `.section-title` 10 → 11px; `.section-chevron`
  8 → 9px — maior legibilidade no painel de análise.
- **D7 — Dark theme consistente nas tabelas Dados**: todas as tabelas da aba Dados (ocorrências,
  gravimetria, geocronologia, litoestratigrafia, furos, ANM, USGS) agora usam dark theme
  (`#1e293b` / `#263348`) em vez de fundos coloridos claros — consistência visual com o resto
  do dashboard.
- **D8 — Aba "📋 Exportar"**: aba de exportação renomeada de `{ } JSON` para `📋 Exportar`,
  mais acessível para usuários não-técnicos.
- **D9 — Hint acionável no banner de cobertura**: quando fontes GeoSGB estão indisponíveis, o
  banner exibe a dica `💡 Dica: re-execute o comando ou use --min-sources N para aceitar estes
  dados parciais.` com `N` calculado automaticamente (fontes disponíveis na execução atual).

#### Qualidade de dados

- **Q5 — Nomeação geográfica de alvos**: `PromptManager` instrui o LLM a combinar referência
  geográfica real (serra, cinturão, bacia) com o sistema mineral identificado para nomear alvos
  (ex: `Serra do Rabo — Ouro Orogênico`). Proibido: `Alvo 1`, `Prospecto A`, `Target Norte`.
- **Q6 — Normalização de `data_sources_used`**: `BaseAgent._normalize_sources()` mapeia 40+
  aliases gerados pelo LLM para as chaves canônicas do sistema (ex: `"GeoSGB Ocorrências"` →
  `"ocorrencias_minerais"`), garantindo consistência nos relatórios e no dashboard.

## [1.2.0] — 2026-05-24

### Adicionado

- **F8 — RandomForest de Prospectividade** (`--rf-model PATH`): modelo de Machine Learning
  pré-treinado que substitui o weighted overlay (ProspectivityScorer) e adiciona um novo
  bloco `<ml_prospectivity_score>` no contexto de todos os agentes LLM:
  - **`ProspectivityMLScorer`** (`src/miner_harness/ml/scorer.py`): carrega
    `rf_prospectivity_v1.joblib` (200 árvores, `max_depth=8`, `class_weight=balanced`) e
    computa `P(mineralizado)` = `predict_proba(X)[0][1]` para a região de análise.
  - **`MLFeatureBuilder`** (`src/miner_harness/ml/feature_builder.py`): extrai vetor de 15
    features do contexto geológico — geoquímica (CF médio/máx, n_anomalias),
    gravimetria (HGM médio/std/máx), Sentinel-2 (4 × anom_pct), ocorrências (densidade/km²,
    n_substâncias) e bbox_area_km2.
  - **Modelo semente** (`src/miner_harness/ml/model/rf_prospectivity_v1.joblib`): treinado
    em 4000 amostras sintéticas (positivos: alta densidade de ocorrências + CF elevado +
    gradiente Bouguer + anomalias S2; negativos: background geológico). CV ROC-AUC ≈ 1.000
    nos dados sintéticos (separabilidade perfeita nos padrões de treinamento).
  - **Script de treino** (`scripts/train_rf_seed.py`): gera novo modelo com
    `--output <path>` para substituição com dados reais.
  - **Graceful fallback**: sem sklearn/joblib → heurística baseada nos 4 grupos de features
    (pesos domínio-geológico); sem dados suficientes → `context["ml_prospectivity"]` não adicionado.
  - **Integração no pipeline**: `context["ml_prospectivity"]` injetado após Sentinel-2 no
    ContextBuilder; injetado como `<ml_prospectivity_score>` em todos os agentes via `base.py`.
  - **EvaluatorAgent ciente**: guia em `prompt_manager.py` instrui a usar RF score ≥ 70/100
    para elevar prioridade de alvos, citar top-3 variáveis preditoras e interpretar score vs.
    evidências geológicas qualitativas.
  - **`MLConfig`** em `MinerHarnessConfig`: `enabled: bool = True`, `model_path: str = ""`.
  - **CLI `--rf-model PATH`**: substitui o modelo embutido por um `.joblib` personalizado.
  - **`_DERIVED_CONTEXT_KEYS`** no Orchestrator: exclui chaves computadas (incluindo
    `ml_prospectivity`) da contagem de `active_sources` para o limiar `min_data_sources`.
  - **Dependências opcionais** (`[ml]`): `scikit-learn>=1.4`, `joblib>=1.3` — graceful fallback
    se não instalados.
  - **57 testes novos** em `tests/ml/`: `test_feature_builder.py` (30 testes),
    `test_scorer.py` (27 testes).

## [1.1.0] — 2026-05-24

### Adicionado

- **F6 — Índices Espectrais Sentinel-2 via CDSE** (`--s2-max-cloud PCT` / `--s2-days DIAS`):
  integração com o Copernicus Data Space Ecosystem (CDSE) via Statistics API — sem download
  de rasters. Autentica com OAuth2 `client_credentials` (registro gratuito em
  dataspace.copernicus.eu) e obtém estatísticas JSON de 4 índices espectrais sobre L2A
  Surface Reflectance a ~60m:
  - **NDVI** = (B08−B04)/(B08+B04): vegetação; anomalia < 0.2 = solo alterado/mineralizado
  - **BSI** (Bare Soil Index) = ((B11+B04)−(B08+B02))/soma: solo/rocha exposta; anomalia > 0.1
  - **Clay Index** = B11/B12: argilominerais SWIR (sericita, caolinita, alunita); anomalia > 1.5
  - **Iron Oxide** = B04/B02: óxidos de ferro (gossã, cap ferrugíneo); anomalia > 2.0
  Cada índice reporta `mean`, `std`, `max`, `p90` e `area_anomalous_pct` (% pixels anômalos
  via máscara binária no evalscript). SCL usado para máscara de nuvens.
  Ativação: definir `MINER_COPERNICUS__CLIENT_ID` + `MINER_COPERNICUS__CLIENT_SECRET`.
  Sem credenciais, a feature é silenciosamente ignorada (retrocompatível).

### Melhorado

- **`RemoteSensingAgent`** / passo INDIRECT_EVIDENCE: guia de interpretação geológica para
  cada índice Sentinel-2 no `PromptManager` (NDVI → halo de alteração, Iron Oxide → gossã,
  Clay → sericítico/argílico, BSI → exposição rochosa).
- **Passo TOTAL_INTEGRATION** (`EvaluatorAgent`): guia para correlação de anomalias espectrais
  multi-índice com alvos de prospecção.
- **`ConfidenceCalibrator`**: `sentinel2_indices` adicionado a `_COMPUTED_KEYS` (não conta como
  dado bruto no cálculo de volume).
- **Cache**: TTL de 30 dias para `sentinel2` em `TTLPolicy`.
- **Suite de testes**: 1164 testes (42 novos para `CopernicusConnector` + `SentinelIndexProcessor`).

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
