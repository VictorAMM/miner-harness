# Sistema de Memória Persistente — miner-harness

**Status**: APPROVED
**Data**: 2026-05-11
**Fase ASO**: 0 — Fundação e Governança

---

## Princípio

> "Sem memória, o sistema é um amnésico brilhante." — ASO v3

O miner-harness opera em dois níveis de memória: a memória do **sistema de desenvolvimento** (como desenvolvemos) e a memória dos **agentes de prospecção** (o que aprendem ao analisar dados geológicos).

## 1. Memória do Sistema de Desenvolvimento

### Memória Semântica (padrões e convenções estáveis)
- **CLAUDE.md** — regras de desenvolvimento, stack, convenções
- **ADRs** — decisões arquiteturais com validade temporal
- **docs/architecture/** — padrões de engenharia e protocolos

### Memória Episódica (eventos e incidentes)
- **Git log** — histórico de mudanças
- **docs/rca/** — Root Cause Analysis de incidentes
- **GitHub Issues** — bugs, tarefas, discussões

### Memória Procedural (runbooks e SOPs)
- **docs/architecture/environment-protocols.md** — como operar ambientes
- **scripts/** — automações de setup e manutenção
- **README.md** — como instalar e contribuir

### Persistência no Cowork
- **memory/** — memória entre sessões Claude (projeto, referências, feedback, user context)
- Atualizada a cada sessão com aprendizados relevantes

## 2. Memória dos Agentes de Prospecção

### Memória Semântica (conhecimento geológico)
| Tipo | Armazenamento | Exemplo |
|---|---|---|
| Padrões geológicos | Índice vetorial (embeddings) | "Greenstone belts arqueanos são favoráveis a ouro orogênico" |
| Convenções de classificação | Config files | Escala estratigráfica, classificação de rochas |
| Templates de análise | Prompts | Framework de 5 passos Dr. Augusto Valen |

### Memória Episódica (análises realizadas)
| Tipo | Armazenamento | Exemplo |
|---|---|---|
| Análises por região | SQLite | "Análise de Carajás em 2026-05-15: 3 alvos identificados" |
| Resultados de agentes | JSON logs | "Geofísico encontrou anomalia magnética em lat/lon X" |
| Feedback do usuário | SQLite | "Usuário confirmou alvo A como relevante" |

### Memória Procedural (workflows aprendidos)
| Tipo | Armazenamento | Exemplo |
|---|---|---|
| Queries eficazes | Cache de prompts | "Para IOCG, consultar: ocorrências + magnetometria + geoquímica Cu-Au" |
| Combinações de dados | Config | "Região X requer escala 1:250k, não 1:1M" |
| Parâmetros otimizados | SQLite | "Threshold de anomalia magnética para Carajás: >200 nT" |

## 3. Tempo Semântico

Toda decisão registrada pelo sistema deve conter:

```python
@dataclass
class TemporalDecision:
    decision: str
    valid_from: date
    valid_until: date | None     # None = sem expiração definida
    review_trigger: str          # Evento que dispara revisão
    confidence: float            # 0.0 a 1.0
    source: str                  # ADR, agente, usuário
```

### Exemplos de Triggers de Revisão
- "API GeoSGB mudar de versão (atualmente 11.3)"
- "Novo modelo LLM superar benchmark do atual em >10%"
- "Cobertura de testes cair abaixo de 60%"
- "Feedback negativo do usuário em >30% das análises"

## 4. Grafo de Rastreabilidade

```
Feature ↔ PRD ↔ RFC ↔ ADR ↔ Commit ↔ Deploy ↔ Incidente ↔ RCA
```

### Implementação no miner-harness

| Nó | Ferramenta | ID |
|---|---|---|
| Feature | GitHub Issues | `#issue-N` |
| PRD | docs/prd/ | `PRD-NNN` |
| RFC | docs/rfc/ | `RFC-NNN` |
| ADR | docs/adr/ | `ADR-NNN` |
| Commit | Git | SHA |
| Deploy | GitHub Releases | `vX.Y.Z` |
| Incidente | GitHub Issues (label: incident) | `#issue-N` |
| RCA | docs/rca/ | `RCA-NNN` |

### Convenção de Links
Todo artefato referencia seus vizinhos no grafo:
- PRD cita Features e RFCs
- ADR cita PRD e alternativas descartadas
- Commit message cita Issue: `feat: add geosgb connector (#12)`
- RCA cita Commit e Deploy que causaram o incidente

## 5. Cristalização de Conhecimento (Fase 11 — já preparado)

Após cada análise de prospecção, o sistema deve:

1. **Extrair padrões** — o que funcionou, o que não funcionou
2. **Atualizar memória semântica** — novos padrões geológicos aprendidos
3. **Atualizar memória procedural** — workflows otimizados
4. **Registrar com tempo semântico** — válido até quando, trigger de revisão

Isso será implementado na Fase 11, mas a estrutura de dados está pronta desde agora.

## Correlação

- Baseline: [`fase-0-baseline-governanca.md`](fase-0-baseline-governanca.md)
- Memória ASO: `../../entrai-docs/docs/agentic-os/memory/knowledge-crystallization.md`
- Governança ASO: `../../entrai-docs/docs/agentic-os/governance/validation-and-policy.md`
