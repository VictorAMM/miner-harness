# ADR-003: Padrões de Engenharia e Segurança

**Status**: ACCEPTED
**Data**: 2026-05-11
**valid_from**: 2026-05-11
**valid_until**: 2026-11-11
**review_trigger**: Início da Fase 5 (Implementação) ou adição de nova integração externa

---

## Contexto

O miner-harness é uma aplicação local que consome dados públicos de API governamental (GeoSGB) e processa via LLMs locais. Precisa de padrões claros de engenharia e segurança desde o início para evitar débito técnico e garantir Secure-by-Design conforme ASO v3.

## Decisão

### Padrões de Código

```
# Formatação e Lint
ruff check --select E,F,I,N,W,UP,B,SIM,TCH
ruff format --line-length 100

# Type checking
mypy --strict src/

# Security
bandit -r src/ -ll
pip audit
```

**Regras inegociáveis:**
1. Type hints em toda função pública — sem exceção
2. Pydantic models para todos os schemas de dados (internos e externos)
3. Docstrings Google Style em módulos, classes e funções públicas
4. Nenhum `# type: ignore` sem comentário justificando
5. Nenhum `Any` em interfaces públicas

### Padrão de Módulos

```python
# Cada módulo segue esta estrutura:
src/miner_harness/
├── __init__.py
├── core/                    # Tipos, config, exceções
│   ├── config.py           # Pydantic Settings
│   ├── types.py            # Tipos compartilhados
│   └── exceptions.py       # Exceções do domínio
├── connectors/             # Anti-corruption layer
│   ├── geosgb/            # Connector GeoSGB REST API
│   │   ├── client.py      # HTTP client com retry/throttle
│   │   ├── models.py      # Pydantic models da API
│   │   └── mapper.py      # Mapeia API → domínio interno
│   └── ollama/            # Connector Ollama
├── cache/                  # SQLite + GeoPackage
├── agents/                 # Agentes especialistas
│   ├── base.py            # Classe base do agente
│   ├── geologist.py       # Geólogo Estrutural
│   ├── geophysicist.py    # Geofísico
│   ├── geochemist.py      # Geoquímico
│   ├── remote_sensing.py  # Sensoriamento Remoto
│   ├── integrator.py      # Integrador (Dr. Augusto Valen)
│   └── evaluator.py       # Evaluator-Optimizer
├── index/                  # Índice vetorial para RAG
├── wizard/                 # Wizard de instalação
└── cli/                    # Interface de linha de comando
```

### Padrão de Logging

```python
import structlog

logger = structlog.get_logger(__name__)

# Sempre estruturado, nunca print()
logger.info("query_geosgb", service="ocorrencias", bbox=[...], records=42)
logger.error("api_timeout", service="litoestratigrafia", timeout_ms=30000)
```

**Proibido em logs:** paths absolutos do usuário, conteúdo de prompts com dados pessoais, tokens/senhas.

### Padrão de Testes

```python
# tests/ espelha src/
tests/
├── conftest.py             # Fixtures compartilhadas
├── connectors/
│   ├── test_geosgb_client.py
│   └── fixtures/           # Respostas mock da API
│       └── ocorrencias_sample.json
├── agents/
│   ├── test_geologist.py
│   └── test_evaluator.py
└── integration/
    └── test_pipeline.py
```

**Regras:**
- Fixtures com dados reais de GeoSGB (anonimizados se necessário)
- Testes de contrato: validar que schema da API não mudou
- Testes de agente: validar que output tem formato esperado (não conteúdo)
- Sem mocks da base de dados em testes de integração — usar SQLite em memória

### Segurança: Anti-Corruption Layers

```
[GeoSGB REST API]
    │
    ▼ (raw JSON)
[geosgb/client.py] ── timeout, retry, rate limit
    │
    ▼ (validated)
[geosgb/models.py] ── Pydantic strict validation
    │
    ▼ (mapped)
[geosgb/mapper.py] ── Transforma para domínio interno
    │
    ▼ (domain types)
[core/types.py] ── Tipos internos puros
    │
    ▼ (structured context)
[agents/*.py] ── Dados injetados em prompts controlados
    │
    ▼ (validated output)
[evaluator.py] ── Evaluator-Optimizer valida plausibilidade
    │
    ▼ (safe output)
[Usuário]
```

### Segurança: Prompt Injection Defense

Dados GeoSGB contêm textos descritivos livres (descrições litológicas, nomes de formações). Antes de injetar no prompt do LLM:
1. Sanitizar caracteres de controle
2. Truncar a tamanho máximo definido
3. Encapsular em delimitadores explícitos (`<geological_data>...</geological_data>`)
4. Agente Evaluator valida que output é geologicamente plausível

### Segurança: Dependências

```yaml
# No CI (GitHub Actions):
- pip audit                    # Vulnerabilidades conhecidas
- bandit -r src/ -ll           # Análise estática de segurança
- ruff check                   # Lint
# Lock de versões via pyproject.toml com ranges conservadores
```

## Alternativas descartadas

- **Black + isort separados**: ruff faz tudo num único passo, mais rápido
- **unittest**: pytest é mais expressivo e tem melhor ecossistema de plugins
- **Logging com `logging` stdlib puro**: structlog oferece logging estruturado nativo

## Riscos residuais

- Ruff pode não cobrir todos os padrões em futuras versões (mitigação: pinning de versão)
- Strict mypy pode ser restritivo demais com libs geocientíficas (mitigação: allowlist por módulo)

## Correlação

- Baseline: [`../architecture/fase-0-baseline-governanca.md`](../architecture/fase-0-baseline-governanca.md)
- ADR Stack: [`ADR-001-stack-decision.md`](ADR-001-stack-decision.md)
- Governança ASO: `../../entrai-docs/docs/agentic-os/governance/validation-and-policy.md`
