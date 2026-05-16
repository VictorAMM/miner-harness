# Branch Protection Rules

**Ref**: ASO v3 Phase 8 — Governed CI/CD
**Data**: 2026-05-16

---

## main (producao)

Configurar em GitHub > Settings > Branches > Branch protection rules:

### Regras Obrigatorias

| Regra | Valor |
|---|---|
| Require a pull request before merging | Sim |
| Require approvals | 1 (minimo) |
| Dismiss stale PR approvals on new pushes | Sim |
| Require status checks to pass before merging | Sim |
| Required status checks | `gate` |
| Require branches to be up to date before merging | Sim |
| Require conversation resolution before merging | Sim |
| Do not allow bypassing the above settings | Sim |

### Status Checks Obrigatorios

O job `gate` do CI consolida todos os checks:
- `lint` — ruff check + format
- `typecheck` — mypy strict
- `test` — pytest + coverage >= 80%
- `security` — bandit + pip-audit

### Restricoes

| Regra | Valor |
|---|---|
| Restrict pushes that create matching branches | Sim |
| Allow force pushes | Nao |
| Allow deletions | Nao |

---

## develop (integracao)

| Regra | Valor |
|---|---|
| Require a pull request before merging | Sim |
| Require status checks to pass before merging | Sim |
| Required status checks | `gate` |
| Allow force pushes | Nao |

---

## Fluxo de Trabalho

```
feature/* --PR--> develop --PR--> main --tag--> release
   fix/*  --PR--> develop --PR--> main --tag--> release
```

1. Criar branch `feature/*` ou `fix/*` a partir de `develop`
2. Abrir PR para `develop` — CI roda automaticamente
3. Apos aprovacao + gate pass, merge (squash)
4. Quando develop esta estavel, PR para `main`
5. Apos merge em main, criar tag `vX.Y.Z` para release

---

## Versionamento Semantico

- `MAJOR` (vX.0.0): Breaking changes em interfaces publicas
- `MINOR` (v0.X.0): Novas funcionalidades sem quebra
- `PATCH` (v0.0.X): Bug fixes e melhorias menores

Prefix de commits (Conventional Commits):
- `feat:` → MINOR bump
- `fix:` → PATCH bump
- `feat!:` ou `BREAKING CHANGE:` → MAJOR bump

---

## Configuracao via GitHub CLI

```bash
# Instalar gh cli (se necessario)
# Configurar branch protection para main
gh api repos/VictorAMM/miner-harness/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["gate"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```
