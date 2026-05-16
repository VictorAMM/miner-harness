# Gate de Saída — Fase 1: Discovery e Pesquisa Autônoma

**Data de avaliação**: 2026-05-11
**Avaliador**: Evaluator-Optimizer (Claude como agente avaliador)
**Resultado**: ✅ APROVADO — todos os critérios obrigatórios atendidos

---

## Checklist de Saída

### 1. Probing de Fontes de Dados ✅
| Critério | Status | Evidência |
|---|---|---|
| API GeoSGB testada com requests reais | ✅ | 8+ endpoints testados, schemas validados |
| Schemas de dados documentados | ✅ | Ocorrências (36 campos), Gravimetria (7), Geoquímica (51) |
| Limitações de acesso mapeadas | ✅ | FeatureServer bloqueio → MapServer/identify como solução |
| Rate limiting avaliado | ✅ | Não detectado em 5 requests rápidos |
| Região piloto validada | ✅ | Carajás: 611 ocorrências, dados ricos |

### 2. Decomposição do Problema ✅
| Critério | Status | Evidência |
|---|---|---|
| Pipeline de análise definido | ✅ | 5 fases (A→E) mapeadas ao framework Dr. Valen |
| Subtarefas técnicas listadas | ✅ | 6 componentes × 4-6 subtarefas cada |
| Lacunas de dados identificadas | ✅ | 4 lacunas com alternativas definidas |
| Mapeamento dados vs necessidades | ✅ | 9 fontes avaliadas com status e alternativa |

### 3. Avaliação de LLMs ✅
| Critério | Status | Evidência |
|---|---|---|
| Modelos candidatos avaliados | ✅ | 6 modelos × 6 critérios ponderados |
| Recomendação com rationale | ✅ | Qwen 3 4B (padrão), Qwen 3 8B (intermediário) |
| Suite de benchmark definida | ✅ | 5 prompts geocientíficos prontos para teste local |
| Mitigação de alucinação planejada | ✅ | 5 estratégias definidas |

### 4. Documentação e Rastreabilidade ✅
| Critério | Status | Evidência |
|---|---|---|
| Relatório de discovery completo | ✅ | `fase-1-discovery-report.md` |
| ADRs a atualizar identificados | ✅ | ADR-002 (acesso), ADR-001 (modelos), ADR-004 (proposto) |
| Riscos atualizados | ✅ | 6 riscos com severidade e mitigação |
| CLAUDE.md atualizado | ✅ | Fase 1 marcada como concluída |

---

## Avaliação do Evaluator-Optimizer

### Qualidade: 8/10
Discovery abrangente com probing real da API. Achado do MapServer/identify como solução para o bloqueio do FeatureServer é valioso e evita meses de debugging futuro. Decomposição do pipeline bem alinhada ao framework Dr. Valen.

### Completude: 8/10
Três frentes de discovery cobertas. Benchmark de LLMs é teórico (sem execução local) — aceitável dado que Ollama não está disponível no ambiente de desenvolvimento atual. Suite de benchmark definida para execução futura.

### Riscos: 9/10
Riscos bem identificados e com mitigações concretas. O bloqueio do FeatureServer foi descoberto proativamente, não em produção. Lacuna de sensoriamento remoto documentada com alternativa.

### Pontos de melhoria
1. Benchmark de LLMs precisa de execução real com Ollama (na máquina do Victor)
2. Testar MapServer/identify para geoquímica e geocronologia
3. Validar download de shapefiles via opendata para litoestratigrafia

---

## Decisão

**✅ FASE 1 APROVADA** — Discovery suficiente para avançar. Os achados da API alteram significativamente a estratégia de acesso (ADR-002 precisa atualização), mas o pipeline de prospecção é viável.

### Próximos Passos (Fase 2)
1. Atualizar ADR-002 com estratégia MapServer/identify
2. Resolver decisão de interface (Textual recomendado)
3. Refinar PRD-001 com pipeline validado
4. Iniciar benchmark real de LLMs na máquina local

### Gatilho de Retorno à Fase 1
- Descoberta de que MapServer/identify também não funciona em algum endpoint crítico
- Mudança na API GeoSGB que invalide os schemas documentados
- Resultados de benchmark de LLMs inaceitáveis para domínio geocientífico

## Correlação

- Relatório completo: [`fase-1-discovery-report.md`](fase-1-discovery-report.md)
- Gate anterior: [`fase-0-gate-saida.md`](fase-0-gate-saida.md)
- ADR-002: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
