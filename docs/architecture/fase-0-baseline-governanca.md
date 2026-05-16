# Fase 0 — Baseline de Fundação e Governança

**Status**: APPROVED
**Data**: 2026-05-11
**Fase ASO**: 0 — Fundação e Governança
**Aprovador**: Victor Augusto (Product Owner)

---

## 1. Stack Baseline

### Linguagem e Runtime
- **Python 3.11+** — linguagem principal para todo o sistema
- **Ollama** — runtime de LLM local (API REST compatível OpenAI)
- **Modelos LLM**: Qwen 3 4B (padrão), Mistral 7B (intermediário), Phi-4 14B (premium)
- **Quantização**: Q4_K_M como padrão (melhor equilíbrio qualidade/VRAM)

### Dependências Core
| Domínio | Bibliotecas | Justificativa |
|---|---|---|
| HTTP/API | httpx, pydantic | Acesso REST API GeoSGB, validação |
| Geoespacial | geopandas, shapely, fiona, pyproj, rasterio | Processamento de dados geológicos |
| ML/IA | scikit-learn, xgboost | Modelagem prospectiva mineral |
| LLM | ollama (Python SDK) | Interface com modelos locais |
| Visualização | folium, matplotlib, plotly | Mapas e gráficos |
| Storage | sqlite3, geopackage | Cache local de dados |
| CLI/UI | rich, textual | Interface de usuário |
| Testes | pytest, pytest-cov | Testing framework |
| Qualidade | ruff, mypy, bandit | Lint, types, security |

### Versionamento e Controle
- **Git** com Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- **Branches**: `main` (estável), `develop` (integração), `feature/*`, `fix/*`, `release/*`
- **Repositório**: https://github.com/VictorAMM/miner-harness
- **Code Review**: todo PR requer aprovação antes de merge em `develop`

## 2. Padrões de Engenharia

### Código
- **Type hints** obrigatórios em todas as funções públicas
- **Docstrings** em formato Google Style para módulos e classes
- **Modularidade**: cada agente é um módulo independente
- **Observabilidade nativa**: logging estruturado (JSON) desde o início
- **Imutabilidade**: preferir dataclasses/Pydantic models sobre dicts

### Arquitetura
- **Separation of Concerns**: connector → cache → índice → agentes → output
- **Dependency Injection**: agentes recebem dependências via construtor
- **Anti-corruption Layer**: isolamento entre dados GeoSGB e modelo interno
- **Fail-safe**: toda chamada à API GeoSGB tem timeout, retry e fallback para cache

### Testes
- **pytest** como framework
- **Cobertura mínima**: 80% em código crítico (connectors, agentes)
- **Testes de contrato**: validar schema da API GeoSGB
- **Fixtures**: dados de teste baseados em regiões geológicas reais

## 3. Segurança (Secure-by-Design)

### OWASP Checklist Inicial
| Item | Status | Aplicação no miner-harness |
|---|---|---|
| Injeção | Ativo | Sanitização de inputs para queries REST API |
| Autenticação | N/A | App local, sem auth de usuário na v1 |
| Dados Sensíveis | Ativo | Dados GeoSGB são públicos, mas logs não devem expor paths locais |
| XML/JSON Parsing | Ativo | Validação estrita de respostas da API (Pydantic) |
| Controle de Acesso | N/A | App local single-user |
| Dependências | Ativo | `pip audit` + `bandit` no CI |
| Logging | Ativo | Nunca logar dados pessoais ou tokens |

### Threat Model Inicial
| Ameaça | Risco | Mitigação |
|---|---|---|
| Prompt injection via dados GeoSGB | Médio | Sanitizar textos geológicos antes de enviar ao LLM |
| Modelo LLM alucinando coordenadas | Alto | Evaluator-Optimizer valida outputs geoespaciais |
| API GeoSGB indisponível | Médio | Cache local agressivo, modo offline |
| Dados corrompidos no cache | Baixo | Checksums em downloads, validação de schema |
| Supply chain (deps maliciosas) | Baixo | Lock de versões, `pip audit` no CI |

### Anti-Corruption Layers
1. **GeoSGB → Modelo Interno**: Converter dados ArcGIS REST para schemas Pydantic internos
2. **Dados → LLM**: Template de prompt controlado, dados injetados como contexto estruturado
3. **LLM Output → Usuário**: Validação de formato e plausibilidade geológica

## 4. CoE — Center of Excellence (Adaptado para Solo Dev)

Como o projeto é desenvolvido por um único desenvolvedor (Victor), o CoE é implementado como:

### Papéis (exercidos pelo mesmo desenvolvedor + agentes IA)
| Papel | Responsável | Ferramenta |
|---|---|---|
| Product Owner | Victor | PRD, decisões de escopo |
| Architect | Victor + Claude | RFCs, ADRs, trade-offs |
| Developer | Victor + Claude | Implementação, code review |
| QA/Security | Agente Evaluator-Optimizer | Validação automatizada |
| SRE/Ops | GitHub Actions | CI/CD, security scan |

### Processo de Decisão
1. Toda decisão técnica significativa → ADR com validade temporal
2. Toda feature → PRD mínimo (mesmo que 1 parágrafo)
3. Toda arquitetura nova → RFC com debate (Victor vs Claude como Architect Swarm)
4. Toda saída crítica → passa por Evaluator-Optimizer

## 5. Protocolos de Ambiente

### Ambientes Definidos
| Ambiente | Propósito | Implementação |
|---|---|---|
| **Dev** | Desenvolvimento local | Máquina do Victor (i5-9600KF, RTX 2070 Super 8GB) |
| **CI** | Integração contínua | GitHub Actions (Ubuntu, sem GPU) |
| **Release** | Build do wizard/instalador | GitHub Actions (matrix: Windows, macOS, Linux) |

### Paridade de Ambiente
- Mesmo Python 3.11+ em todos os ambientes
- Mesmas dependências (pinadas em `pyproject.toml`)
- CI roda lint + testes em modo CPU-only (sem Ollama)
- Release build testa instalação do wizard

### FinOps Day 1
| Recurso | Custo | Orçamento |
|---|---|---|
| GitHub Actions | Free tier (2000 min/mês) | $0/mês |
| Ollama + modelos | Local, sem custo | $0/mês |
| API GeoSGB | Gratuita | $0/mês |
| Domínio/site (futuro) | ~R$50/ano | Quando necessário |
| **Total** | | **$0/mês** |

### Orçamento de Tokens (para agentes LLM)
| Operação | Tokens estimados | Frequência |
|---|---|---|
| Análise regional completa | ~50k tokens | Por consulta |
| Relatório de prospecção | ~20k tokens | Por relatório |
| Query individual a agente | ~5k tokens | Por interação |
| Indexação RAG (embeddings) | ~100k tokens | Por região (uma vez) |

## 6. KPIs Baseline (Fase 0)

| KPI | Baseline | Meta Fase 1 |
|---|---|---|
| Lead Time (ideia → PR) | N/A (greenfield) | < 1 dia para features simples |
| Defect Density | N/A | < 5 bugs/KLOC |
| Test Coverage | 0% | > 60% |
| Change Failure Rate | N/A | < 15% |
| Token Efficiency | N/A | Definir após Fase 1 |
| Hallucination Rate | N/A | Definir após Fase 6 |

## 7. Anti-Patterns Evitados

| Anti-Pattern | Descrição | Como Evitamos |
|---|---|---|
| Discovery-First Fallacy | Iniciar pesquisa sem base técnica | Stack, segurança e governança definidos antes de discovery |
| Vibe-Driven Decisions | Decidir sem evidência | ADRs com trade-off matrix, alternativas descartadas |
| Speed Over Security | Priorizar velocidade | OWASP checklist, threat model, bandit no CI |
| Amnésico Brilhante | Sem memória persistente | Knowledge Crystallization ativo desde Fase 0 |

## Correlação

- ADR Stack: [`../adr/ADR-001-stack-decision.md`](../adr/ADR-001-stack-decision.md)
- ADR GeoSGB: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- Governança ASO: `../../entrai-docs/docs/agentic-os/governance/validation-and-policy.md`
- PRD: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
