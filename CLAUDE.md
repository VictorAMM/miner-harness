# miner-harness — CLAUDE.md

## Identidade do Projeto

**miner-harness** é um sistema de prospecção mineral inteligente que utiliza agentes especialistas em geologia e geofísica para analisar dados da base GeoSGB. O sistema roda localmente, com LLMs embarcados, e disponibiliza um wizard de instalação para download.

- **Repositório**: https://github.com/VictorAMM/miner-harness
- **Metodologia**: Agentic SDLC Operating System v3 (ASO v3)
- **Documentação ASO**: `../entrai-docs/`

## Persona Principal

**Dr. Augusto Valen** — Geólogo exploracionista e geofísico de elite (25+ anos). Define o tom técnico e o framework analítico dos agentes. Ver `docs/personas/dr-augusto-valen.md`.

## Princípios Inegociáveis (ASO v3)

1. **Contexto e segurança antes de velocidade** — nunca pular etapas de discovery
2. **Decision-by-evidence** — proibido decisões por "vibe"; toda decisão com rationale explícito
3. **Secure-by-Design** — segurança desde a Fase 0
4. **Policy-as-Code** — bloquear avanço em caso de violação
5. **Evaluator-Optimizer** — toda saída crítica passa por avaliação
6. **Memória persistente e temporal** — semântica, episódica e procedural

## Stack e Arquitetura

### Decisão de Stack (Discovery-First)
- **Python 3** — core do sistema: agentes, análise geoespacial, ML, integração com LLMs locais
- **LLMs embarcados** — modelos rodando localmente (Ollama + qwen3:8b por padrão)
- **Execução local** — aplicação instala e roda na máquina do usuário
- **Wizard de instalação** — installer para download com setup guiado
- **RAG** — features GeoSGB indexadas via `nomic-embed-text` + sqlite-vec; contexto recuperado por step
- **Dashboard HTML** — Jinja2 + Leaflet.js 1.9.4 + Chart.js 4.4, self-contained, auto-open no browser

### Dependências principais
- GeoSGB como fonte de dados principal (6 serviços: ocorrências, gravimetria, geoquímica, geocronologia, litoestratigrafia, aerogeofísica)
- Bibliotecas geocientíficas (geopandas, shapely, fiona, pyproj)
- Framework de agentes com LLM local (ollama)
- sqlite-vec para vector store do RAG
- jinja2 para geração de relatórios HTML

## Fases do Projeto (ASO v3)

O desenvolvimento segue as fases 0→11 do Agentic SDLC OS:

```
Fase 0  — Fundação e Governança ✅ CONCLUÍDA (2026-05-11)
Fase 1  — Discovery e Pesquisa Autônoma ✅ CONCLUÍDA (2026-05-11)
Fase 2  — PRD Executável ✅ CONCLUÍDA (2026-05-11)
Fase 3  — Technical Design e RFC Swarm ✅ CONCLUÍDA (2026-05-12)
Fase 4  — Incepção de Infra ✅ CONCLUÍDA (2026-05-12)
Fase 5  — Implementação ✅ CONCLUÍDA (2026-05-15)
Fase 6  — Validation Harness ✅ CONCLUÍDA (2026-05-16)
Fase 7  — Testing Swarm ✅ CONCLUÍDA (2026-05-16)
Fase 8  — Governed CI/CD ✅ CONCLUÍDA (2026-05-16)
Fase 9  — Observabilidade ✅ CONCLUÍDA (2026-05-16)
Fase 10 — RCA Autônomo ✅ CONCLUÍDA (2026-05-17)
Fase 11 — Self-Improvement ✅ CONCLUÍDA (2026-05-17)
Wizard  — Instalação Guiada ✅ CONCLUÍDA (2026-05-17)
RAG     — Retrieval-Augmented Generation ✅ CONCLUÍDA (2026-05-18) [v0.2.0]
Dashboard — Relatório HTML Interativo ✅ CONCLUÍDA (2026-05-18) [v0.2.1]
Nova Pesquisa — Servidor HTTP + SSE + Dashboard Interativo ✅ CONCLUÍDA (2026-05-19) [v0.3.0]
ANM/USGS — Integração com fontes de dados adicionais + agentes cientes ✅ CONCLUÍDA (2026-05-19) [v0.4.0]
Parallelização — Agentes dos passos 3 e 4 executados em asyncio.gather() + merge de resultados ✅ CONCLUÍDA (2026-05-19) [v0.5.0]
Benchmarks — Suite de latência (pipeline, cache, SSE) + ProfilingRunner + --profile CLI ✅ CONCLUÍDA (2026-05-20) [v0.5.1]
Report Quality — bbox no Evaluator (P0), progresso de fetch (P1), logs debug (P2) ✅ CONCLUÍDA (2026-05-19) [v0.5.2]
Resilient Fetch — --min-sources configurável + InsufficientDataError com hint acionável ✅ CONCLUÍDA (2026-05-20) [v0.5.3]
Concurrent Fetch — ContextBuilder.build() via asyncio.gather() (6 serviços em paralelo) ✅ CONCLUÍDA (2026-05-20) [v0.5.4]
Prompt Quality — guia de interpretação geológica por passo + rótulo RAG (evita pH/turbidez em achados tectônicos) ✅ CONCLUÍDA (2026-05-20) [v0.5.5]
Cache Fix — não cachear resultados de fetch com falha (erro transitório não bloqueia próximas execuções) ✅ CONCLUÍDA (2026-05-20) [v0.5.6]
TTL Explícito — TTL de 30d para ANM e 7d para USGS adicionados ao TTLPolicy ✅ CONCLUÍDA (2026-05-20) [v0.5.7]
Compat Py3.10 — timezone.utc nos testes, StrEnum shim no wizard, skip do bug Hypothesis 6.152.x ✅ CONCLUÍDA (2026-05-20) [v0.5.7]
Coverage 100% — exceptions, server body inválido, version_info gated branches ✅ CONCLUÍDA (2026-05-20) [v0.5.7]
Cache Evict — eviction automática no startup + comando `cache evict` no CLI ✅ CONCLUÍDA (2026-05-20) [v0.5.7]
Perf Evict — evict_expired() usa SELECT id,fetched_at,ttl_days (evita ler blobs JSON) ✅ CONCLUÍDA (2026-05-20) [v0.5.7]
Real Test Fixes — asyncio policy cross-platform, null coords GeoSGB, OllamaClient config propagation ✅ CONCLUÍDA (2026-05-20) [v0.5.8]
Commodities Extract — _findings_to_targets extrai commodities do texto com vocabulário PT-BR/EN ✅ CONCLUÍDA (2026-05-20) [v0.5.8]
LLM Timeout CLI — --llm-timeout SECONDS para configurar timeout do Ollama via CLI ✅ CONCLUÍDA (2026-05-20) [v0.5.8]
UX Data Fetch — resumo de fontes ativas/indisponíveis antes do pipeline LLM ✅ CONCLUÍDA (2026-05-20) [v0.5.9]
Dedup DataGaps — prompt do evaluator consolida data_gaps duplicados entre steps ✅ CONCLUÍDA (2026-05-20) [v0.5.9]
Security — remover dependência ollama SDK (não usada, 6 CVEs eliminadas) ✅ CONCLUÍDA (2026-05-20) [v0.5.9]
Mineral System — tabela de referência obrigatória no prompt total_integration ✅ CONCLUÍDA (2026-05-20) [v0.5.10]
Low Conf Badge — borda laranja + ícone ⚠ em steps com confidence=low/insufficient ✅ CONCLUÍDA (2026-05-20) [v0.5.10]
Occurrences Map — pontos GeoSGB coloridos por substância no Leaflet + legenda + toggle + tabela na aba Dados ✅ CONCLUÍDA (2026-05-20) [v0.5.11]
Occurrences Stats — widget sidebar com pills coloridas por substância (×N) + toggles ANM/USGS wired ✅ CONCLUÍDA (2026-05-20) [v0.5.12]
Target Alias Fix — model_validator normaliza mineralization_system→mineral_system evitando perda de alvos ✅ CONCLUÍDA (2026-05-20) [v0.5.13]
Summary Quality — integrated_summary usa evaluator; _dedup_gaps_semantic remove lacunas semânticas duplicadas ✅ CONCLUÍDA (2026-05-20) [v0.5.14]
Summary Display — integrated_summary exibido em caixa destacada nas abas Análise e Alvos do dashboard ✅ CONCLUÍDA (2026-05-20) [v0.5.15]
Target Dedup — _dedup_targets() mescla alvos sobrepostos (<10 km) via Haversine; re-numera prioridades ✅ CONCLUÍDA (2026-05-20) [v0.5.16]
Context Window — --ctx-size CLI + num_ctx em OrchestratorConfig + OllamaClient; Modelfile qwen3-64k (65k ctx, KV Q4 em VRAM via OLLAMA_KV_CACHE_TYPE=q4_0) ✅ CONCLUÍDA (2026-05-20) [v0.5.17]
Data Scale — limites de dados (records, chars, prev) escalados com √(num_ctx/4096): 65k ctx → 200 records, 32k chars, 8k prev ✅ CONCLUÍDA (2026-05-20) [v0.5.18]
Geo Sort — ContextBuilder ordena registros por distância ao centróide do bbox antes de truncar (mais próximos primeiro; sem coord → fim da lista) ✅ CONCLUÍDA (2026-05-20) [v0.5.19]
Code Review — 11 bugs corrigidos (2 HIGH, 6 MED, 3 LOW): _extract_json ValueError, coords fallback silenciosas, BoundingBox validação de ordem, _ctx_scale floor, path traversal CLI, objectid/_safe_int, imports no topo, __del__ CacheManager ✅ CONCLUÍDA (2026-05-21) [v0.5.20]
Atlas Aerogeofísico — WMS overlays SGB/CPRM no Leaflet (🧲 Mag. Total, 🌈 K-Th-U, ✈️ Pol. Projetos) + marcadores interativos de projetos por tipo de levantamento com popup (offline) ✅ CONCLUÍDA (2026-05-21) [v0.5.20]
Lito Centroid — UnidadeLitoestratigrafica ganha coordenada opcional via centróide aritmético do polígono (_geom_to_xy); dashboard: marcadores quadrados por hierarquia + tabela na aba Dados ✅ CONCLUÍDA (2026-05-21) [v0.5.20]
Bbox Filter + Source Triage — _filter_by_bbox() remove registros com coords fora da área (buffer 20%); bbox_filtered_sources separa "fora do escopo" de "falhou/vazio"; _validate_target_coords() reposiciona alvos do LLM fora do bbox; banner de cobertura corrigido ✅ CONCLUÍDA (2026-05-21) [v0.5.21]
Dashboard UX — 3 bugs corrigidos em teste visual: banner "X de 14"→"X de 8", popup CSS overflow, aba Dados distingue bbox-filtrado de indisponível via bbox_filtered_sources ✅ CONCLUÍDA (2026-05-21) [v0.5.22]
Popup Rationale — nota técnica "[Coordenadas originais...]" removida do rationale do alvo; reposicionamento continua logado como warning estruturado ✅ CONCLUÍDA (2026-05-21) [v0.5.23]
GeoPackage Export — GisExporter gera .gpkg (5 camadas: targets, ocorrencias, gravimetria, geocronologia, aerogeofisica) e .geojson; --output-gis CLI ✅ CONCLUÍDA (2026-05-22) [v0.6.0]
GeoSGB Furos — endpoint furos_sondagem integrado; modelo FuroSondagem; marcadores ciano no mapa; EvaluatorAgent ciente ✅ CONCLUÍDA (2026-05-22) [v0.6.0]
GeochemNorm — GeochemistryNormalizer calcula CF + flag anomalia; tabela injetada no GeochemistAgent ✅ CONCLUÍDA (2026-05-22) [v0.6.1]
ProspectivityScore — ProspectivityScorer weighted overlay 0–100; barras por alvo no dashboard ✅ CONCLUÍDA (2026-05-22) [v0.6.2]
BouguerProcessor — derivadas gravimétricas IDW+GHT; injetadas no GeophysicistAgent como dado quantitativo ✅ CONCLUÍDA (2026-05-22) [v0.7.0]
ConfidenceCalibrator — recalibração de confiança por cobertura de dados calculados (geoquimica_normalizada, bouguer_gradient, rag, user_drillholes) ✅ CONCLUÍDA (2026-05-22) [v0.7.2]
F7 Drillholes — DrillholeParser (50+ aliases en/pt-BR) + DrillholeStore SQLite + injeção no contexto LLM + marcadores laranja Leaflet + tabela Dados + CLI --drillholes / index drillholes ✅ CONCLUÍDA (2026-05-22) [v0.9.0]
F9 DOCX — DocxReportExporter gera relatório Word 7 seções (sumário, tabela alvos, justificativas, análise por etapa, lacunas, ressalvas JORC, referências); --output-docx CLI ✅ CONCLUÍDA (2026-05-23) [v1.0.0]
Documentação v1.0.0 — CHANGELOG completo v0.3.0→v1.0.0, README atualizado, pyproject.toml 1.0.0 ✅ CONCLUÍDA (2026-05-23) [v1.0.0]
F6 Sentinel-2 — CopernicusConnector OAuth2 + Statistics API (sem rasters); NDVI/BSI/Clay/Iron + área anômala%; injeção prompt + guia geológico; --s2-max-cloud/--s2-days CLI; TTL 30d; 42 testes ✅ CONCLUÍDA (2026-05-24) [v1.1.0]
F8 Random Forest ML — ProspectivityMLScorer RF pré-treinado (15 features: geoquímica CF, Bouguer HGM, Sentinel-2 anomalias, densidade ocorrências); MLFeatureBuilder; modelo semente rf_prospectivity_v1.joblib (4000 amostras sintéticas); fallback heurístico gracioso; MLConfig + --rf-model CLI; injeção ml_prospectivity no contexto LLM; _DERIVED_CONTEXT_KEYS no orquestrador; 57 testes ✅ CONCLUÍDA (2026-05-24) [v1.2.0]
```

**Status**: v1.2.0 em produção. PRD-002 F6 (Sentinel-2) + F8 (Random Forest ML) entregues.

## Grafo de Rastreabilidade

```
Feature ↔ PRD ↔ RFC ↔ ADR ↔ Commit ↔ Deploy ↔ Incidente ↔ RCA
```

## Estrutura do Projeto

```
miner-harness/
├── CLAUDE.md              # Este arquivo
├── docs/
│   ├── prd/               # Product Requirements Documents
│   ├── rfc/               # Request for Comments (design técnico)
│   ├── adr/               # Architecture Decision Records
│   ├── rca/               # Root Cause Analysis
│   ├── architecture/      # Diagramas e decisões de arquitetura
│   └── personas/          # Personas dos agentes
├── src/miner_harness/
│   ├── agents/            # Agentes especialistas (geologia, geofísica, etc.)
│   ├── cache/             # CacheManager + SQLite store
│   ├── cli/               # CLI (argparse): analyze, validate, cache, index, health
│   ├── connectors/        # GeoSGB connector + Ollama client
│   ├── core/              # Tipos, config, exceções
│   ├── index/             # Vector store (sqlite-vec) + SearchEngine + Embedder
│   ├── observability/     # Health checks, logging estruturado
│   ├── orchestrator/      # Orchestrator, ContextBuilder, ReportValidator
│   ├── report/            # HtmlReportRenderer (Jinja2 + Leaflet + Chart.js)
│   ├── server/            # DashboardServer (aiohttp) + SseChannel + AnalysisRunner
│   └── wizard/            # Wizard de instalação guiada
├── tests/                 # Testes (pytest)
├── scripts/               # setup_dev.sh, pull_models.sh, run_analysis.sh
├── infra/                 # docker-compose.yml (Ollama)
└── .github/workflows/     # CI/CD: lint, test, typecheck, security, gate, release
```

## Convenções de Código

- **Linguagem principal**: Python 3.11+
- **Formatação**: ruff (lint + format)
- **Tipos**: type hints obrigatórios em funções públicas
- **Testes**: pytest
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **Branches**: `main` (prod), `develop` (integração), `feature/*`, `fix/*`

## Templates de Artefatos

Usar os templates definidos em `../entrai-docs/docs/agentic-os/templates/README.md`:
- **PRD** → `docs/prd/`
- **RFC** → `docs/rfc/`
- **ADR** → `docs/adr/` (com `valid_from`, `valid_until`, `review_trigger`)
- **RCA** → `docs/rca/`

## Workflow de Desenvolvimento (Obrigatório)

Seguir sempre esta sequência — sem exceções:

```
Para cada task:
  1. Implementar a task
  2. pytest tests/ -q → deve passar 100%
  3. ruff check + ruff format --check → sem violações
  4. Commitar (Conventional Commits)
  5. Repetir para a próxima task

Após todas as tasks:
  6. pytest tests/ -q → confirmar suite completa verde
  7. Abrir PR

Após abrir a PR:
  8. Aguardar CI completar (gh run list --branch <branch>)
  9. Revisar relatório do CI (gh run view <id>)
 10. Se CI falhou: corrigir, commitar, push → voltar ao passo 8
 11. CI verde → merge
```

**Regras inegociáveis:**
- Nunca abrir PR com testes falhando localmente
- Nunca mergear sem CI verde
- Nunca pular a espera pelo CI — o relatório pode revelar erros que os testes locais não pegaram (ex: ruff format, cobertura, bandit)

## Gates de Qualidade

Antes de avançar qualquer fase:
- [ ] Checklist de segurança OWASP
- [ ] Validação por Evaluator-Optimizer
- [ ] Policy-as-Code sem violações
- [ ] Testes passando
- [ ] Documentação atualizada

## CI/CD (GitHub Actions)

- Lint e format check em todo PR
- Testes automatizados
- Security scan
- Build do wizard de instalação

## Notas

- Toda decisão arquitetural deve ter ADR com validade temporal
- Incertezas devem ser marcadas com `[NEEDS CLARIFICATION]`
- PRD define O QUÊ e PORQUÊ, nunca o COMO
