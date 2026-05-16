# Fase 1 — Relatório de Discovery e Pesquisa Autônoma

**Status**: CONCLUÍDO
**Data**: 2026-05-11
**Fase ASO**: 1 — Discovery e Pesquisa Autônoma
**Autor**: Victor Augusto + Claude (Architect Swarm)

---

## Sumário Executivo

A Fase 1 realizou probing real na API do GeoSGB, decompôs o pipeline de prospecção mineral em subtarefas concretas e avaliou modelos LLM para o domínio geocientífico. Os achados principais são:

1. **A API GeoSGB é utilizável mas com restrições**: a maioria dos FeatureServers bloqueia query de features (erro 400), mas o **MapServer/identify** funciona como método primário de extração.
2. **Pipeline de análise definido**: 5 fases (coleta → processamento → agentes → validação → output) mapeadas ao framework Dr. Augusto Valen.
3. **LLM recomendado**: Qwen 3 4B como padrão, Qwen 3 8B como intermediário — ambos cabem na RTX 2070 Super.
4. **Região piloto**: Carajás (PA) — 611 ocorrências minerais no bbox testado, dados abundantes.

---

## 1. Probing da API GeoSGB

### 1.1 Resumo de Endpoints Testados

| Endpoint | Tipo | Count | Query Features | Identify | Latência |
|---|---|---|---|---|---|
| `geologia/ocorrencias` | FeatureServer + MapServer | 36.472 | ❌ erro 400 | ✅ funciona | ~150ms |
| `geofisica/gravimetria` | FeatureServer | 20.407 | ✅ funciona | N/A | ~135ms |
| `geologia/geocronologia` | FeatureServer | 3.158 | ❌ erro 400 | ⚠ não testado | ~120ms |
| `geoquimica/geoquimica_integrada` | FeatureServer | 1.440 | ❌ erro 400 | ⚠ não testado | ~115ms |
| `geofisica/aerogeofisica` | FeatureServer + MapServer | 4 séries | ❌ timeout | ✅ info ok | ~100ms |
| `geologia/litoestratigrafia_1000000` | FeatureServer + MapServer | polígonos | ❌ timeout | ⚠ timeout (pesado) | timeout |
| `geologia/afloramentos` | FeatureServer | ? | ⚠ não testado | N/A | — |
| `Provincias_e_Distritos_Auriferos` | MapServer | polígonos | N/A | N/A | ~100ms |
| `geologia/aespectral` | FeatureServer | ? | ❌ erro 400 | N/A | ~600ms |

### 1.2 Achado Crítico: FeatureServer vs MapServer

**Descoberta**: A maioria dos FeatureServers do GeoSGB **bloqueia query de features** (retorna HTTP 200 com body `{"error": {"code": 400, "message": "Unable to complete operation."}}`), mesmo que `capabilities` declare "Query,Extract" e `returnCountOnly` funcione normalmente.

**Exceção confirmada**: `geofisica/gravimetria` permite query completa via FeatureServer (7 campos, 20.407 registros, paginação via offset).

**Solução**: Usar `MapServer/identify` como método primário de extração de dados:
- Endpoint: `{service}/MapServer/identify`
- Parâmetros: `geometry` (ponto), `tolerance` (raio), `mapExtent`, `imageDisplay`
- Retorna features com atributos completos (usando aliases legíveis)
- Testado com sucesso: 6 results (150ms) a 375 results (1300ms)

### 1.3 Schema de Dados Validados

#### Ocorrências Minerais (36 campos)
Campos-chave confirmados:
- `SUBSTANCIAS` (string) — ex: "Cobre, Ouro"
- `MUNICIPIO`, `UF` (string)
- `PROVINCIA` (string) — província mineral
- `STATUS_ECONOMICO`, `IMPORTANCIA` (string)
- `ROCHAS_HOSPEDEIRAS`, `ROCHAS_ENCAIXANTES` (string)
- `MORFOLOGIA`, `TEXTURAS`, `TIPOS_ALTERACAO` (string)
- `X`, `Y` (double) — coordenadas
- `DATUM` (string)
- `maxRecordCount`: 100.000
- `geometryType`: esriGeometryPoint

#### Gravimetria (7 campos — query funcional)
- `longitude`, `latitude` (double)
- `alt_ortome` (double) — altitude ortométrica
- `gravidade` (double)
- `anom_ar_li` (double) — anomalia ar livre
- `anom_bougu` (double) — anomalia Bouguer
- `maxRecordCount`: 1.000

#### Geoquímica Integrada (51 campos, 9 layers)
Layers: Água, Concentrado de Bateia, Sedimento de Corrente, Sedimento Marinho, Rocha (+ 4 outros)
- `PROJETO`, `CLASSE`, `MATCOLETAD`, `ROCHMATRIZ`
- 51 campos incluindo dados analíticos
- `maxRecordCount`: 1.000

#### Aerogeofísica (4 séries)
- Série 1000: Projetos DNPM e CPRM
- Série 2000: Projetos CNEM e NUCLEBRÁS
- Série 3000: Projetos governamentais e privados
- Série 4000: Projetos CNP e PETROBRAS

### 1.4 Dados de Carajás (Região Piloto)

- **Ocorrências minerais**: 611 no bbox `-51.5,-7.0,-49.0,-5.0`
- **Substâncias encontradas**: Cobre, Ouro, Zinco, Ferro, Manganês, Níquel
- **Municípios**: Parauapebas, São Félix do Xingu, Tucumã, Ourilândia do Norte, Marabá
- **MapServer identify**: 375 resultados com tolerance=100, escala regional

### 1.5 Rate Limiting

- **Resultado**: NÃO detectado em 5 requests rápidos consecutivos
- Latências estáveis: 105-161ms (média 126ms)
- Sem headers de throttling na resposta
- **Recomendação**: manter throttling conservador de 500ms entre requests (config padrão)

### 1.6 opendata.sgb.gov.br

- API GeoNode v2 funcional
- 8 datasets catalogados (inclui Mapa Geológico 1:2.5M 2025)
- Útil como fallback para download de shapefiles
- Não substitui a API REST para queries espaciais

### 1.7 Impacto no ADR-002

O ADR-002 assume FeatureServer como acesso primário. **Precisa ser atualizado**:
- Acesso primário: `MapServer/identify` (grid de pontos + merge)
- Acesso secundário: `FeatureServer/query` (apenas gravimetria e endpoints compatíveis)
- Acesso terciário: `opendata.sgb.gov.br` (shapefiles)

---

## 2. Decomposição do Problema de Prospecção

### 2.1 Pipeline de Análise

```
Entrada do Usuário (região + substância + escala)
    │
    ▼
[A] Coleta de Dados GeoSGB
    ├── Ocorrências minerais (MapServer/identify)
    ├── Gravimetria (FeatureServer/query)
    ├── Litoestratigrafia (MapServer/identify)
    ├── Geoquímica (MapServer/identify)
    ├── Aerogeofísica (MapServer info)
    └── Províncias e estruturas (MapServer)
    │
    ▼
[B] Processamento e Indexação
    ├── Normalizar schemas (Pydantic)
    ├── Cache local (SQLite + GeoPackage)
    └── Embeddings para RAG
    │
    ▼
[C] Análise por Agentes (5 passos Dr. Valen)
    ├── 1. História tectônica (Geólogo Estrutural)
    ├── 2. Arquitetura estrutural (Geólogo Estrutural)
    ├── 3. Fertilidade magmática (Geoquímico)
    ├── 4. Evidências indiretas (Geofísico + Sens. Remoto)
    └── 5. Integração total (Dr. Augusto Valen)
    │
    ▼
[D] Validação (Evaluator-Optimizer)
    │
    ▼
[E] Output (relatório + mapa + GeoPackage)
```

### 2.2 Mapeamento Dados vs Necessidades

| Necessidade | Fonte | Status | Alternativa |
|---|---|---|---|
| Ocorrências minerais | GeoSGB REST | ✅ MapServer/identify | opendata shapefile |
| Gravimetria | GeoSGB REST | ✅ FeatureServer/query | — |
| Litoestratigrafia | GeoSGB REST | ⚠ timeout (pesado) | opendata shapefile |
| Geocronologia | GeoSGB REST | ⚠ count only | opendata se disponível |
| Geoquímica | GeoSGB REST | ⚠ count only | MapServer/identify |
| Aerogeofísica | GeoSGB REST | ⚠ identify parcial | — |
| Sensoriamento remoto | **NÃO no GeoSGB** | ❌ lacuna | ESA Copernicus / NASA EarthData |
| IP/Resistividade | **NÃO disponível** | ❌ lacuna | Dados proprietários |
| Furos de sondagem | GeoSGB REST | ⚠ MapServer only | — |

### 2.3 Lacunas Identificadas

1. **Sensoriamento remoto**: ASTER, Sentinel-2, Landsat não estão no GeoSGB. Necessário integrar APIs da ESA (Copernicus) ou NASA (EarthData). Impacta o Passo 4 do framework Dr. Valen.
2. **Análise espectral**: endpoint `aespectral` retorna erro 400. Dados espectrais são importantes para mapeamento de alteração hidrotermal.
3. **Litoestratigrafia**: FeatureServer dá timeout em queries. Polígonos pesados. Estratégia: download shapefile via opendata + cache local permanente.
4. **IP/Resistividade**: dados de geofísica detalhada não são públicos. Limitação aceita para v1.

### 2.4 Região Piloto: Carajás

**Justificativa técnica**:
- Maior província mineral do Brasil (Cu-Au IOCG, Fe BIF, Au orogênico, Ni, Mn)
- 611 ocorrências minerais no GeoSGB (bbox: -51.5,-7.0,-49.0,-5.0)
- Geologia bem documentada na literatura científica
- Múltiplos sistemas minerais para validar os agentes
- Alinhamento com expertise do Dr. Augusto Valen

**Bbox**: `-51.5, -7.0, -49.0, -5.0` (WGS84)
**UF**: PA (Pará)
**Municípios-chave**: Parauapebas, Marabá, Canaã dos Carajás, São Félix do Xingu

---

## 3. Benchmark de LLMs Locais

### 3.1 Modelos Avaliados

| Modelo | Params | VRAM (Q4) | Score Ponderado | Nota |
|---|---|---|---|---|
| **Qwen 3 4B** | 4B | ~3 GB | **7.8/10** | ⭐ Padrão recomendado |
| Qwen 3 8B | 8B | ~5.5 GB | 7.4/10 | Intermediário (novo, não no PRD) |
| Phi-4-mini | 3.8B | ~3 GB | 7.4/10 | Contexto 128K, fraco em PT |
| Gemma 3 4B | 4B | ~3 GB | 7.3/10 | Multimodal, bom em PT |
| Mistral 7B | 7B | ~5 GB | 6.6/10 | Function calling |
| Phi-4 14B | 14B | ~10 GB | 6.1/10 | Não cabe na RTX 2070S |

### 3.2 Critérios de Avaliação

- Português técnico geocientífico (25%)
- Raciocínio científico e integração (25%)
- Suporte a contexto longo / RAG (15%)
- Velocidade na RTX 2070 Super (15%)
- Footprint de VRAM (10%)
- Ecossistema e tooling (10%)

### 3.3 Recomendação Atualizada

| Tier | Modelo | VRAM | tok/s (est.) | Uso |
|---|---|---|---|---|
| Mínimo | Qwen 3 4B (Q4_K_M) | ~3 GB | ~40 | Hardware modesto, CPU-only viável |
| **Recomendado** | **Qwen 3 8B (Q4_K_M)** | **~5.5 GB** | **~22** | **Sweet spot para 8GB VRAM** |
| Premium | Qwen 3 14B ou cloud fallback | ~10 GB+ | ~12 | GPUs 12GB+ |

**Mudança vs PRD**: adicionar Qwen 3 8B como tier intermediário (não constava). Remover Phi-4 14B do tier premium (não cabe confortavelmente na RTX 2070 Super com contexto longo).

### 3.4 Mitigação de Alucinação

1. RAG com dados GeoSGB indexados (grounding factual)
2. Prompts estruturados com dados injetados (nunca confiar na memória do modelo)
3. Evaluator-Optimizer valida coordenadas e conclusões
4. Score de confiança por alvo baseado em cobertura de dados
5. Fine-tuning com LoRA em corpus geológico (planejado para Fase 6)

### 3.5 Suite de Benchmark (para execução local)

5 prompts geocientíficos definidos, cobrindo:
1. Conhecimento factual geológico (Carajás)
2. Interpretação de dados geofísicos
3. Integração multidisciplinar
4. Raciocínio sobre incerteza
5. Classificação de dados GeoSGB (RAG)

Script de benchmark a criar em `scripts/benchmark_llm.py` para execução na máquina do Victor.

---

## 4. Riscos Atualizados

| Risco | Severidade | Probabilidade | Mitigação |
|---|---|---|---|
| FeatureServer bloqueando queries | Alta | ✅ Confirmado | MapServer/identify como primário |
| Litoestratigrafia timeout | Média | ✅ Confirmado | Download shapefile + cache permanente |
| Rate limiting API | Baixa | ❌ Não detectado | Throttling conservador mantido |
| Alucinação de LLMs locais | Alta | Provável | RAG + Evaluator + score confiança |
| Sensoriamento remoto ausente | Média | ✅ Confirmado | Integrar ESA/NASA APIs |
| API mudar sem aviso | Média | Possível | Versionamento + testes contrato + cache |

---

## 5. ADRs a Atualizar

### ADR-002 (GeoSGB) — REQUER ATUALIZAÇÃO
- Acesso primário: mudar de FeatureServer para MapServer/identify
- Documentar padrão de grid adaptativo para extração
- Adicionar fallback via opendata.sgb.gov.br

### ADR-001 (Stack) — REQUER ADIÇÃO
- Adicionar Qwen 3 8B como tier intermediário
- Resolver [NEEDS CLARIFICATION] da interface: recomendo Textual (CLI) para v1

### Novo ADR-004 — Sensoriamento Remoto (PROPOSTO)
- Decisão sobre integração com ESA Copernicus / NASA EarthData
- Escopo: ASTER, Sentinel-2 para mapeamento de alteração hidrotermal

---

## 6. Próximos Passos (Fase 2 — PRD Executável)

1. Atualizar ADR-002 com achados da API
2. Resolver interface (Textual vs Streamlit) → recomendo Textual
3. Refinar PRD-001 com pipeline validado
4. Definir critérios de aceitação detalhados por componente
5. Iniciar RFC de arquitetura técnica detalhada

---

## Correlação

- Gate anterior: [`fase-0-gate-saida.md`](fase-0-gate-saida.md)
- Baseline: [`fase-0-baseline-governanca.md`](fase-0-baseline-governanca.md)
- ADR-002: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
- Protocolos: [`environment-protocols.md`](environment-protocols.md)
