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
- **LLMs embarcados** — modelos rodando localmente (ollama/llama.cpp ou similar)
- **Execução local** — aplicação instala e roda na máquina do usuário
- **Wizard de instalação** — installer para download com setup guiado

### Dependências esperadas
- GeoSGB como fonte de dados principal
- Bibliotecas geocientíficas (geopandas, rasterio, shapely, etc.)
- Framework de agentes com LLM local
- Interface de usuário para o wizard

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
Fase 8  — Governed CI/CD ← PRÓXIMA
Fase 8  — Governed CI/CD
Fase 9  — Observabilidade
Fase 10 — RCA Autônomo
Fase 11 — Self-Improvement
```

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
├── src/                   # Código-fonte
├── tests/                 # Testes
├── scripts/               # Scripts de automação e instalação
├── infra/                 # Configuração de infraestrutura
└── .github/workflows/     # GitHub Actions CI/CD
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
