# ADR-005: Estratégia de Sensoriamento Remoto

**Status**: ACCEPTED
**Data**: 2026-05-11
**valid_from**: 2026-05-11
**valid_until**: 2027-05-11
**review_trigger**: Início da Fase 5 (Implementação do agente de Sensoriamento Remoto) ou disponibilização de dados ASTER/Sentinel no GeoSGB

---

## Contexto

A Fase 1 de Discovery identificou que dados de sensoriamento remoto (ASTER, Sentinel-2, Landsat) **não estão disponíveis na API do GeoSGB**. Esses dados são essenciais para o Passo 4 do framework Dr. Augusto Valen (Evidências Indiretas), especialmente para mapeamento de alteração hidrotermal e lineamentos.

O endpoint `aespectral` do GeoSGB existe, mas retorna erro 400 em queries — e mesmo se funcionasse, contém análise espectral de amostras pontuais, não imagens orbitais.

## Decisão: Escopo Reduzido para v1 + Preparação para v2

### v1 — Sem integração direta com imagens orbitais

Na v1, o agente de Sensoriamento Remoto atuará com dados derivados já presentes no GeoSGB:
- Lineamentos de estruturas geológicas (`Estruturas_GIS_Brasil_2004`)
- Mapas de províncias e distritos (`Provincias_e_Distritos_Auriferos`)
- Análise espectral pontual (se `aespectral` funcionar via MapServer/identify)

O agente gerará recomendações de quais produtos de sensoriamento o prospector deveria adquirir/processar, sem processá-los internamente.

### v2 — Integração com ESA/NASA (planejado)

Fontes candidatas para v2:

| Fonte | Dados | API | Custo | Uso no miner-harness |
|---|---|---|---|---|
| ESA Copernicus | Sentinel-2 (10m RGB/NIR) | Copernicus Data Space | Gratuito | Mapeamento de lineamentos e vegetação |
| NASA EarthData | ASTER (15-90m, 14 bandas) | EarthData API | Gratuito | Alteração hidrotermal (VNIR/SWIR/TIR) |
| USGS EarthExplorer | Landsat 8/9 (30m) | USGS M2M API | Gratuito | Análise multitemporal, NDVI |
| Google Earth Engine | Composites | GEE Python API | Gratuito (pesquisa) | Processamento em nuvem (opt-in) |

### Requisitos para v2

1. Download e processamento de cenas ASTER para gerar mapas de alteração (Kaolinita, Alunita, Clorita)
2. Bandas Sentinel-2 para lineamentos e NDVI
3. Armazenamento: rasters em GeoTIFF local (~50-200MB/cena)
4. Processamento: rasterio + numpy (já no stack Python)

## Trade-offs

| Critério | v1 (sem imagens) | v2 (com imagens) |
|---|---|---|
| Completude do framework Dr. Valen | Parcial (Passo 4 limitado) | Completo |
| Storage necessário | ~1-5 GB (vetorial) | ~20-100 GB (raster) |
| Complexidade de instalação | Baixa | Média (download de cenas) |
| Dependência de internet | Apenas download inicial | Download de cenas por região |
| Tempo para implementar | 0 (já coberto por dados GeoSGB) | ~2-4 semanas |

## Impacto no Pipeline

Na v1, o Passo 4 (Evidências Indiretas) será alimentado por:
- Anomalias geofísicas (gravimetria, aerogeofísica) — disponíveis
- Dados estruturais do GeoSGB — disponíveis
- **Recomendações textuais** de quais produtos de sensoriamento analisar — gerados pelo agente

Isso é aceitável porque:
1. Prospectores experientes já processam imagens em software dedicado (ENVI, QGIS)
2. O valor do miner-harness é a integração multidisciplinar, não o processamento de imagens
3. Gerar recomendações específicas ("analise bandas ASTER 5/7 e 4/6 nesta área para alteração argilítica") já agrega valor

## Alternativas descartadas

- **Integrar imagens na v1**: adiciona complexidade desnecessária ao MVP. Storage alto, download demorado, processamento pesado.
- **Google Earth Engine como primário**: requer conta Google, execução em nuvem, contradiz filosofia local-first.
- **Comprar dados comerciais**: contradiz o objetivo de democratizar acesso.

## Correlação

- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- ADR-002: [`ADR-002-geosgb-data-access.md`](ADR-002-geosgb-data-access.md)
- Discovery: [`../architecture/fase-1-discovery-report.md`](../architecture/fase-1-discovery-report.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
