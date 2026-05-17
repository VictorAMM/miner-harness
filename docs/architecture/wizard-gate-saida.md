# Gate de Saída — Wizard de Instalação

**Data**: 2026-05-17
**Status**: APROVADO ✅
**PR**: [#2 feat: wizard de instalação](https://github.com/VictorAMM/miner-harness/pull/2)

## Entregáveis

| Artefato | Status |
|---|---|
| `wizard/checks.py` — verificações puras (Python, disco, Ollama, MINER_HOME) | ✅ |
| `wizard/installer.py` — cria dirs, config.json, env_hint.sh | ✅ |
| `wizard/runner.py` — UI Rich com injeção de Console | ✅ |
| `wizard/__init__.py` — exports públicos | ✅ |
| CLI `miner-harness install` (interativo + `--non-interactive`) | ✅ |
| `tests/wizard/` — 42 testes | ✅ |

## Métricas

| Indicador | Valor |
|---|---|
| Testes wizard | 42 |
| Testes totais (suite completa) | 447 |
| Cobertura estimada wizard | ~100% |
| ruff check | 0 violações |
| ruff format --check | 0 diferenças |
| mypy | 0 erros |
| bandit | 0 issues |
| pip-audit | 0 CVEs |

## CI Gates

- lint ✅
- typecheck ✅
- test (3.11) ✅
- test (3.12) ✅
- security ✅
- gate ✅

## Decisões de Design

- **Ollama = WARNING, não FAIL**: sistema funciona sem Ollama para etapas de setup; agentes precisam dele apenas durante análise.
- **Injeção de Console**: `WizardRunner(console=Console(quiet=True))` permite testes sem output.
- **Separação lógica/UI**: `checks.py` e `installer.py` são funções puras sem dependência de Rich; `runner.py` é o único arquivo com UI.
- **Abort on create_dirs failure**: se não conseguir criar o diretório, as etapas seguintes são puladas.
