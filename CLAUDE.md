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
```

**Status**: v0.3.0 em produção. Próximo entregável: testes e2e com GeoSGB real + Ollama local.

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
