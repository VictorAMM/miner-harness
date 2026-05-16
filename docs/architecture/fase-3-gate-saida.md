# Gate de Saída — Fase 3: Technical Design e RFC Swarm

**Data de avaliação**: 2026-05-12
**Avaliador**: Evaluator-Optimizer (Claude como agente avaliador)
**Resultado**: ✅ APROVADO

---

## Checklist de Saída

### 1. RFCs Completos e Aprovados ✅

| Critério | Status | Evidência |
|---|---|---|
| RFC-001 GeoSGB Connector | ✅ APPROVED | Arquitetura, fluxos, contratos Pydantic (6 modelos), observabilidade, segurança, testes |
| RFC-002 Agent Orchestration | ✅ APPROVED | Pipeline 5 passos Dr. Valen, 5 agentes, LLM Engine, PromptManager, Evaluator-Optimizer |
| RFC-003 Storage & Index | ✅ APPROVED | CacheManager, GeoPackageStore, VectorIndex (sqlite-vec), TTL policies, modo offline |
| Todos seguem template ASO | ✅ | 7/7 campos obrigatórios cobertos em cada RFC |

### 2. Contratos de API Definidos ✅

| Contrato | RFC | Status | Modelos |
|---|---|---|---|
| GeoSGBConnector interface | RFC-001 | ✅ | 6 métodos async + export |
| Pydantic models GeoSGB | RFC-001 | ✅ | OcorrenciaMineral, DadoGravimetrico, AmostraGeoquimica, UnidadeLitoestratigrafica, ProjetoAerogeofisico, DatacaoGeocronologica |
| Orchestrator interface | RFC-002 | ✅ | analyze_region(), execute_step(), get_agent_for_step() |
| BaseAgent ABC | RFC-002 | ✅ | analyze(), build_prompt(), parse_response() |
| StepResult / ProspectionReport | RFC-002 | ✅ | Modelos completos com Confidence, MineralTarget |
| LLMEngine (OllamaClient) | RFC-002 | ✅ | chat(), generate(), embeddings(), health() |
| CacheManager interface | RFC-003 | ✅ | get(), put(), evict(), stats() |
| VectorIndex interface | RFC-003 | ✅ | search(), index_features(), get_context() |
| StorageConfig | RFC-003 | ✅ | Configuração completa com defaults |

### 3. Estrutura de Módulos Validada ✅

| Critério | Status | Evidência |
|---|---|---|
| Estrutura `src/miner_harness/` definida | ✅ | ADR-003 define: core/, connectors/, cache/, agents/, index/, wizard/, cli/ |
| Anti-corruption layers | ✅ | RFC-001 (API→Pydantic), RFC-002 (data→prompt), RFC-003 (raw→embedding) |
| Dependências entre RFCs claras | ✅ | RFC-001→RFC-003→RFC-002 (dados→cache→agentes) |
| Sem dependências circulares | ✅ | Grafo acíclico confirmado |

### 4. Segurança Coberta ✅

| Critério | Status | Evidência |
|---|---|---|
| Sanitização de dados para LLM | ✅ | RFC-001 §6, RFC-002 §9.3 |
| Rate limiting defensivo | ✅ | RFC-001 §6 (ThrottledClient) |
| SQL injection prevention | ✅ | RFC-003 §8.2 (queries parametrizadas) |
| Prompt injection defense | ✅ | RFC-002 §9.3 (delimitadores, instrução em system prompt) |
| File permissions | ✅ | RFC-003 §8.1 (700/600) |
| Isolamento de agentes | ✅ | RFC-002 §9.1 (sem acesso direto à rede) |
| Evaluator-Optimizer | ✅ | RFC-002 §9.2 (4 checks de plausibilidade) |

### 5. Observabilidade Planejada ✅

| Critério | Status | Evidência |
|---|---|---|
| Logging estruturado (structlog) | ✅ | RFC-001 §5, RFC-002 §8, RFC-003 §7 |
| Métricas de API | ✅ | latency_ms, cache_hit, error_code |
| Métricas de agentes | ✅ | prompt_tokens, completion_tokens, confidence |
| Métricas de storage | ✅ | cache_size_mb, index_size_mb, hit_rate |
| Métricas de LLM | ✅ | model_loaded, vram_used_gb, inference_ms |

### 6. Testes Definidos ✅

| Critério | Status | Evidência |
|---|---|---|
| Testes de contrato (API GeoSGB) | ✅ | RFC-001 §9 |
| Testes unitários (connector) | ✅ | RFC-001 §9 — alias mapper, grid, dedup |
| Testes de agente (output format) | ✅ | RFC-002 §11 — campos obrigatórios, fallback |
| Testes de cache (roundtrip, TTL) | ✅ | RFC-003 §9 — 12 testes unitários |
| Testes de integração | ✅ | RFC-003 §9 — pipeline cache→index, modo offline |
| Fixtures com dados reais | ✅ | 3 conjuntos de fixtures definidos |

### 7. Rastreabilidade ✅

| Critério | Status | Evidência |
|---|---|---|
| Todos os docs com seção Correlação | ✅ | 18/18 documentos (3 RFCs novos) |
| Links internos válidos | ✅ | Verificado — zero links quebrados |
| Grafo Feature↔PRD↔RFC↔ADR mantido | ✅ | PRD-001→RFC-001/002/003→ADR-001/002/003/004/005 |
| System overview atualizado | ✅ | Referências aos 3 RFCs adicionadas |
| README atualizado | ✅ | Fase 3 como fase atual, requisitos definidos |

---

## Avaliação do Evaluator-Optimizer

### Qualidade: 9/10
Três RFCs tecnicamente densos e implementáveis. O pipeline de 5 passos do Dr. Augusto Valen é traduzido em contratos Pydantic concretos com fluxo claro. A decisão de sqlite-vec para o índice vetorial é pragmática e alinhada com a filosofia local-first.

### Segurança: 9/10
Sete camadas de segurança mapeadas (sanitização, rate limiting, SQL parameterizado, prompt injection, file permissions, isolamento de agentes, Evaluator-Optimizer). Cobertura sólida para uma aplicação local.

### Completude: 9/10
Todos os componentes do system-overview agora têm RFCs: connector (001), agentes+LLM (002), cache+index (003). O wizard de instalação e a interface TUI não têm RFC dedicado, mas são componentes mais simples e podem ser definidos na Fase 5.

### Pontos de atenção para Fase 4+

1. **sqlite-vec**: biblioteca relativamente nova — validar compatibilidade com Python 3.11 e cross-platform (Windows/Linux/Mac) na Fase 4
2. **nomic-embed-text**: confirmar que Ollama suporta esse modelo e validar qualidade dos embeddings com dados geocientíficos em português
3. **geopandas + fiona**: dependências pesadas — validar tamanho do instalador na Fase 4
4. **Wizard de instalação**: não tem RFC — definir durante a implementação (Fase 5)
5. **Testes de contrato GeoSGB**: implementar como prioridade na Fase 5 (API pode mudar)

---

## Decisão

**✅ FASE 3 APROVADA** — Design técnico completo com 3 RFCs aprovados, contratos definidos, segurança mapeada e testes planejados. Pronto para Fase 4 (Incepção de Ambientes e Infra).

### Próximos Passos (Fase 4 — Incepção de Ambientes e Infra)

1. **Setup do ambiente de desenvolvimento**: pyproject.toml refinado, dependências instaladas e validadas
2. **Estrutura de diretórios `src/`**: criar módulos conforme ADR-003
3. **CI/CD refinado**: adicionar mypy, pip audit, coverage mínimo ao GitHub Actions
4. **Validar dependências cross-platform**: geopandas, sqlite-vec, Ollama em Windows/Linux/Mac
5. **Definir orçamento de tokens**: custo estimado por análise completa (5 passos × modelo)
6. **Dockerfile de dev** (opcional): ambiente reproduzível para contribuidores

### Gatilho de Retorno à Fase 3

- Descoberta de limitação técnica que invalide design dos RFCs
- Mudança na API GeoSGB que exija re-design do connector
- sqlite-vec incompatível com target platforms

## Correlação

- Gate anterior: [`fase-2-gate-saida.md`](fase-2-gate-saida.md)
- RFC-001: [`../rfc/RFC-001-geosgb-connector.md`](../rfc/RFC-001-geosgb-connector.md)
- RFC-002: [`../rfc/RFC-002-agent-orchestration.md`](../rfc/RFC-002-agent-orchestration.md)
- RFC-003: [`../rfc/RFC-003-storage-and-index.md`](../rfc/RFC-003-storage-and-index.md)
- ADR-003: [`../adr/ADR-003-engineering-security-standards.md`](../adr/ADR-003-engineering-security-standards.md)
- System Overview: [`system-overview.md`](system-overview.md)
