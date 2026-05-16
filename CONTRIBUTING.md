# Contribuindo para miner-harness

## Requisitos

- Python 3.11+
- Ferramentas de dev: `pip install -e ".[dev]"`

## Fluxo de Desenvolvimento

1. Criar branch a partir de `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/minha-feature
   ```

2. Implementar mudancas seguindo as convencoes abaixo.

3. Verificar localmente antes de abrir PR:
   ```bash
   ruff check src/ tests/
   ruff format --check src/ tests/
   mypy src/ --strict
   pytest tests/ -v --cov --cov-report=term-missing
   coverage report --fail-under=80
   bandit -r src/ -ll
   ```

4. Abrir PR para `develop` com titulo em Conventional Commits.

## Conventional Commits

Todos os commits devem seguir o formato:

```
<tipo>(<escopo>): <descricao>

[corpo opcional]

[footer opcional]
```

Tipos validos:
- `feat` — Nova funcionalidade
- `fix` — Correcao de bug
- `docs` — Documentacao
- `refactor` — Refatoracao sem mudanca funcional
- `test` — Adicao/correcao de testes
- `ci` — Mudancas de CI/CD
- `chore` — Manutencao geral

Exemplo:
```
feat(cache): adicionar TTL configuravel por servico

Permite configurar TTL diferente para cada tipo de dado do GeoSGB.
Dados gravimetricos mudam menos frequentemente que ocorrencias.

Refs: RFC-003 §3.2
```

## Gates de Qualidade

Nenhum PR sera mergeado se:
- Ruff reportar erros de lint ou formatacao
- Mypy (strict) reportar erros de tipo
- Testes falharem
- Coverage ficar abaixo de 80%
- Bandit encontrar vulnerabilidades de severidade media+
- pip-audit encontrar dependencias vulneraveis

## Estrutura de Testes

```
tests/
├── cache/          # Testes unitarios do CacheManager
├── cli/            # Testes dos comandos CLI
├── connectors/     # Testes dos connectors (GeoSGB, Ollama)
├── contract/       # Testes de contrato entre modulos
├── core/           # Testes dos tipos e config
├── index/          # Testes do VectorIndex
├── integration/    # Testes de integracao end-to-end
├── orchestrator/   # Testes do Orchestrator
└── property/       # Property-based tests (Hypothesis)
```

## Rastreabilidade

Toda mudanca significativa deve referenciar:
- RFC relevante (ex: `Refs: RFC-001 §4.1`)
- ADR se houver decisao arquitetural
- Issue/ticket se aplicavel
