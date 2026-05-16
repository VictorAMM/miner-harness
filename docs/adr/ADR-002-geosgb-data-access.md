# ADR-002: Estratégia de Acesso aos Dados GeoSGB

**Status**: ACCEPTED (revisado após Fase 1 Discovery)
**Data**: 2026-05-11
**Revisado**: 2026-05-11 (Fase 1 — probing real da API)
**valid_from**: 2026-05-11
**valid_until**: 2026-11-11
**review_trigger**: Mudança na API do geoportal ou lançamento de API oficial pelo SGB

---

## Contexto

O miner-harness precisa acessar dados geológicos, geofísicos e geoquímicos do Serviço Geológico do Brasil (SGB/CPRM) para análise de prospecção mineral. A Fase 1 de Discovery realizou probing real em 8+ endpoints da API, revelando limitações críticas que alteraram a estratégia de acesso original.

## Achado Crítico da Fase 1

**A maioria dos FeatureServers bloqueia query de features** (retorna HTTP 200 com `{"error": {"code": 400}}`), embora `capabilities` declare "Query,Extract" e `returnCountOnly` funcione normalmente. Este comportamento foi confirmado em ocorrências, geoquímica, geocronologia e análise espectral.

**Exceção confirmada**: `geofisica/gravimetria` permite query completa via FeatureServer (7 campos, 20.407 registros).

**Solução descoberta**: `MapServer/identify` funciona como método de extração — testado com 375 resultados em Carajás (tolerance=100, latência ~1300ms).

## Decisão Revisada: MapServer/identify + FeatureServer seletivo + Shapefiles

### Forma de Acesso Primária: MapServer/identify (grid adaptativo)

Para a maioria dos endpoints, o método funcional de extração é:

```
GET {BASE}/{service}/MapServer/identify
  ?geometry={lon},{lat}           # Ponto central
  &geometryType=esriGeometryPoint
  &sr=4326
  &layers=all:{layerId}
  &tolerance={raio}               # Controla área de busca
  &mapExtent={bbox}               # Extensão do mapa
  &imageDisplay={w},{h},96        # Resolução virtual
  &returnGeometry=true
  &f=json
```

**Padrão de grid adaptativo**:
1. Dividir bbox do usuário em grid de pontos
2. Para cada ponto, chamar identify com tolerance calculado
3. Merge de resultados, deduplica por OBJECTID/coordenadas
4. Ajustar densidade do grid se muitos/poucos resultados

**Mapeamento de tolerance vs cobertura** (testado em Carajás):
- tolerance=10, extent=4°×4°, display=400×400 → ~6 resultados
- tolerance=100, extent=6°×6°, display=800×800 → ~375 resultados

### Forma de Acesso Secundária: FeatureServer/query (endpoints compatíveis)

Alguns endpoints permitem query direta. Usar quando disponível por ser mais eficiente:

| Endpoint | Query funciona? | maxRecordCount | Notas |
|---|---|---|---|
| `geofisica/gravimetria` | ✅ SIM | 1.000 | Único confirmado — paginação via offset |
| `geologia/ocorrencias` | ❌ NÃO (400) | 100.000 (declarado) | returnCountOnly funciona |
| `geoquimica/geoquimica_integrada` | ❌ NÃO (400) | 1.000 (declarado) | 9 layers, 51 campos |
| `geologia/geocronologia` | ❌ NÃO (400) | — | 3.158 registros |
| `geologia/aespectral` | ❌ NÃO (400) | — | — |
| `geofisica/aerogeofisica` | ❌ NÃO (timeout) | — | 4 séries |
| `geologia/litoestratigrafia_*` | ❌ NÃO (timeout) | — | Polígonos pesados |

### Forma de Acesso Terciária: Download de Shapefiles

Para dados com timeout persistente (litoestratigrafia, bacias):
- Download via opendata.sgb.gov.br (GeoNode, 8 datasets)
- Armazenamento local permanente em GeoPackage
- Atualização manual periódica (dados geológicos mudam raramente)

### Endpoints Mapeados por Domínio

#### Geologia (`/geologia/`)
| Serviço | Acesso Recomendado | Registros | Status Fase 1 |
|---|---|---|---|
| `ocorrencias` | MapServer/identify | 36.472 | ✅ Testado — 375 results em Carajás |
| `litoestratigrafia_1000000` | Download shapefile | polígonos | ⚠ Timeout em FS e MS |
| `litoestratigrafia_250000` | Download shapefile | polígonos | ⚠ Não testado (provavelmente timeout) |
| `geocronologia` | MapServer/identify | 3.158 | ⚠ FS erro 400, MS a testar |
| `afloramentos` | MapServer/identify | a mapear | ⚠ Parcialmente testado |
| `bacias_sedimentares` | Download shapefile | polígonos | ⚠ Timeout |
| `aespectral` | MapServer/identify | a mapear | ❌ FS erro 400 |
| `furos_sondagem` | MapServer/identify | a mapear | MapServer only |
| `Estruturas_GIS_Brasil_2004` | MapServer/identify | linhas | MapServer only |

#### Geofísica (`/geofisica/`)
| Serviço | Acesso Recomendado | Registros | Status Fase 1 |
|---|---|---|---|
| `gravimetria` | FeatureServer/query | 20.407 | ✅ Query funcional |
| `aerogeofisica` | MapServer/identify | 4 séries | ⚠ FS timeout, MS info ok |
| `aerogeofisica_query` | MapServer/identify | — | A testar |

#### Geoquímica (`/geoquimica/`)
| Serviço | Acesso Recomendado | Registros | Status Fase 1 |
|---|---|---|---|
| `geoquimica_integrada` | MapServer/identify | 1.440 | ⚠ FS erro 400, 9 layers (Água, Bateia, Sed. Corrente, etc.) |
| `geoquimica_integrada_all` | MapServer/identify | — | 1 layer agregada |

#### Serviços Raiz (relevantes)
| Serviço | Acesso Recomendado | Status Fase 1 |
|---|---|---|
| `Provincias_e_Distritos_Auriferos` | MapServer info/identify | ✅ Layers visíveis |
| `Mapa_de_Provincias_Estruturais` | MapServer info/identify | A testar |
| `Cartas_de_Anomalia` | MapServer | A testar |
| `Grav_Brasil_Public_MIL1` | MapServer | A testar |

### Schemas Validados (Fase 1)

#### Ocorrências Minerais — 36 campos
Campos críticos confirmados:
- `SUBSTANCIAS` (string) — ex: "Cobre, Ouro"
- `MUNICIPIO`, `UF` (string)
- `PROVINCIA` (string) — província mineral
- `STATUS_ECONOMICO`, `IMPORTANCIA` (string)
- `ROCHAS_HOSPEDEIRAS`, `ROCHAS_ENCAIXANTES` (string)
- `MORFOLOGIA`, `TEXTURAS`, `TIPOS_ALTERACAO` (string)
- `X`, `Y` (double) — coordenadas
- `DATUM` (string)

**Nota**: via MapServer/identify, os campos usam aliases legíveis ("Substâncias minerais" em vez de "SUBSTANCIAS"). O connector precisa de um mapper alias→campo.

#### Gravimetria — 7 campos (query funcional)
- `longitude`, `latitude` (double)
- `alt_ortome` (double) — altitude ortométrica
- `gravidade` (double)
- `anom_ar_li` (double) — anomalia ar livre
- `anom_bougu` (double) — anomalia Bouguer

#### Geoquímica Integrada — 51 campos, 9 layers
Layers: Água, Concentrado de Bateia, Sedimento de Corrente, Sedimento Marinho, Rocha, + 4 outros.
- `PROJETO`, `CLASSE`, `MATCOLETAD`, `ROCHMATRIZ`
- 51 campos incluindo dados analíticos

## Licenciamento

### Status Legal
O SGB **não está no escopo do Decreto nº 8.777/2016** (Política de Dados Abertos) e **não possui Plano de Dados Abertos (PDA)** formal. Entretanto:

1. **Lei de Acesso à Informação (Lei 12.527/2011)**: dados produzidos por órgãos públicos são, por regra, públicos.
2. **INDE (Decreto 6.666/2008)**: dados geoespaciais governamentais devem ser compartilhados.
3. **Prática atual**: o SGB disponibiliza ativamente todos os dados via GeoSGB e opendata.sgb.gov.br sem autenticação.
4. **OneGeology (UNESCO)**: o SGB participa do projeto internacional de compartilhamento de dados geológicos.

### Conclusão sobre Licenciamento
Os dados são **efetivamente de uso livre**. O miner-harness deve:
- Citar: "Dados: Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB"
- Não sugerir endosso oficial
- Respeitar termos de uso do opendata.sgb.gov.br

## Estratégia Técnica Revisada

```
1. MapServer/identify (primário — maioria dos endpoints)
   - Grid adaptativo de pontos sobre bbox do usuário
   - Tolerance calculado por densidade desejada
   - Merge + dedup de resultados
   - Mapper: alias → campo interno (Pydantic)
   
2. FeatureServer/query (secundário — endpoints compatíveis)
   - Apenas gravimetria confirmada
   - Paginação via resultOffset (sem supportsPagination)
   - Testar novos endpoints periodicamente
   
3. Download shapefile (terciário — dados com timeout)
   - Litoestratigrafia, bacias sedimentares
   - Armazenamento local permanente em GeoPackage
   - Atualização semestral manual
   
4. CACHE LOCAL (SQLite + GeoPackage)
   - TTL: 30 dias para dados pontuais, permanente para polígonos
   - Download incremental por região
   - Modo offline após download inicial
   
5. ÍNDICE VETORIAL (embeddings)
   - Indexar descrições litológicas, minerais, estruturas
   - Busca semântica para agentes RAG
```

## Métricas da API (medidas na Fase 1)

| Métrica | Valor |
|---|---|
| Latência média (requests simples) | ~130ms |
| Latência MapServer/identify (375 rec) | ~1300ms |
| Rate limiting detectado | NÃO (5 requests consecutivos sem throttle) |
| Throttling recomendado | 500ms entre requests (conservador) |
| Total ocorrências Brasil | 36.472 |
| Total gravimetria | 20.407 |
| Ocorrências em Carajás (bbox) | 611 |
| Uptime observado | 100% durante testes |

## Alternativas descartadas

- **FeatureServer/query como primário**: bloqueado na maioria dos endpoints (erro 400)
- **Scraping HTML**: frágil, desnecessário
- **Download total de uma vez**: datasets muito grandes
- **API proprietária ESRI (token)**: não necessário
- **WFS (OGC)**: testado, sem vantagem sobre MapServer/identify

## Riscos Atualizados

| Risco | Severidade | Status | Mitigação |
|---|---|---|---|
| FeatureServer bloqueia queries | Alta | ✅ Confirmado | MapServer/identify como primário |
| API pode mudar sem aviso | Média | Possível | Versionamento, testes de contrato, cache |
| Rate limiting não documentado | Baixa | ❌ Não detectado | Throttling 500ms mantido |
| Litoestratigrafia timeout | Média | ✅ Confirmado | Download shapefile + cache permanente |
| MapServer/identify tem limite de resultados | Média | Possível | Grid adaptativo com density control |
| Campos com aliases vs nomes técnicos | Baixa | ✅ Confirmado | Mapper no connector |

## Correlação

- PRD: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- ADR Stack: [`ADR-001-stack-decision.md`](ADR-001-stack-decision.md)
- ADR Engenharia: [`ADR-003-engineering-security-standards.md`](ADR-003-engineering-security-standards.md)
- Arquitetura: [`../architecture/system-overview.md`](../architecture/system-overview.md)
- Discovery: [`../architecture/fase-1-discovery-report.md`](../architecture/fase-1-discovery-report.md)
