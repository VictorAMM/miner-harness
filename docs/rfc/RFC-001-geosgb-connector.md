# RFC-001: Arquitetura do Connector GeoSGB

**Status**: APPROVED
**Autor**: Victor Augusto + Claude (Architect Swarm)
**Data**: 2026-05-11
**Fase ASO**: 3 — Technical Design e RFC Swarm

---

## 1. Objetivo

Definir a arquitetura técnica do connector que acessa dados do GeoSGB para o miner-harness, incorporando os achados da Fase 1 (MapServer/identify como método primário).

## 2. Arquitetura Alvo

```
┌─────────────────────────────────────────────────────┐
│                  GeoSGBConnector                     │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │              GeoSGBClient                     │    │
│  │  (httpx async + retry + throttle)             │    │
│  │                                               │    │
│  │  ┌─────────────────┐  ┌──────────────────┐   │    │
│  │  │ MapServerClient  │  │FeatureServerClient│  │    │
│  │  │                 │  │                  │   │    │
│  │  │ • identify()    │  │ • query()        │   │    │
│  │  │ • info()        │  │ • count()        │   │    │
│  │  │ • export()      │  │ • describe()     │   │    │
│  │  └─────────────────┘  └──────────────────┘   │    │
│  └──────────────────┬───────────────────────────┘    │
│                     │                                 │
│  ┌──────────────────▼───────────────────────────┐    │
│  │            GridExtractor                      │    │
│  │  (grid adaptativo sobre bbox)                 │    │
│  │                                               │    │
│  │  • generate_grid(bbox, density)               │    │
│  │  • extract_region(service, bbox) → features   │    │
│  │  • deduplicate(features) → unique             │    │
│  │  • adaptive_refine(sparse_areas)              │    │
│  └──────────────────┬───────────────────────────┘    │
│                     │                                 │
│  ┌──────────────────▼───────────────────────────┐    │
│  │            Pydantic Models                    │    │
│  │  (anti-corruption layer)                      │    │
│  │                                               │    │
│  │  • OcorrenciaMineral                          │    │
│  │  • DadoGravimetrico                           │    │
│  │  • AmostraGeoquimica                          │    │
│  │  • UnidadeLitoestratigrafica                  │    │
│  │  • ProjetoAerogeofisico                       │    │
│  │  • DatacaoGeocronologica                      │    │
│  └──────────────────┬───────────────────────────┘    │
│                     │                                 │
│  ┌──────────────────▼───────────────────────────┐    │
│  │            AliasMapper                        │    │
│  │  (MapServer aliases → campos internos)        │    │
│  │                                               │    │
│  │  "Substâncias minerais" → "substancias"       │    │
│  │  "Município" → "municipio"                    │    │
│  │  "Privíncia mineral" → "provincia"            │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │            CacheManager                       │    │
│  │  (SQLite + GeoPackage)                        │    │
│  │                                               │    │
│  │  • get(service, bbox) → cached?               │    │
│  │  • put(service, bbox, features)               │    │
│  │  • evict(ttl_expired)                         │    │
│  │  • export_geopackage(bbox) → .gpkg            │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

## 3. Fluxos de Dados

### 3.1 Extração via MapServer/identify (primário)

```python
async def extract_region(
    service: str,
    bbox: BoundingBox,
    layers: list[int] | None = None,
    density: GridDensity = GridDensity.MEDIUM,
) -> list[GeoFeature]:
    """
    Extrai features de uma região usando grid de identify.
    
    1. Verifica cache — se dados frescos, retorna
    2. Gera grid de pontos sobre bbox
    3. Para cada ponto, chama MapServer/identify
    4. Merge + deduplica resultados
    5. Mapeia aliases → campos internos (Pydantic)
    6. Salva no cache
    7. Retorna features tipadas
    """
```

**Grid adaptativo**:

```
Bbox do usuário: (-51.5, -7.0, -49.0, -5.0)  → 2.5° × 2.0°

MEDIUM density (default):
  Grid 5×4 = 20 pontos
  Tolerance = 50
  ~20 requests × 150ms = ~3s
  Cobertura esperada: ~80% dos dados

HIGH density (refinamento):
  Grid 10×8 = 80 pontos
  Tolerance = 25
  ~80 requests × 150ms = ~12s
  Cobertura esperada: ~95% dos dados

ADAPTIVE:
  1. Rodar MEDIUM
  2. Identificar áreas com poucos resultados
  3. Refinar com grid mais denso nessas áreas
  4. Merge final
```

### 3.2 Extração via FeatureServer/query (gravimetria)

```python
async def query_features(
    service: str,
    layer: int,
    where: str = "1=1",
    bbox: BoundingBox | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> list[GeoFeature]:
    """
    Query direta via FeatureServer (apenas endpoints compatíveis).
    Paginação via resultOffset quando necessário.
    """
```

### 3.3 Contagem (funciona em todos)

```python
async def count(service: str, layer: int, where: str = "1=1") -> int:
    """returnCountOnly — funciona em todos os FeatureServers."""
```

## 4. Contratos e APIs Internas

### 4.1 Modelos de Domínio

```python
from pydantic import BaseModel, Field
from datetime import date

class Coordenada(BaseModel):
    longitude: float = Field(ge=-74, le=-29)  # Limites do Brasil
    latitude: float = Field(ge=-34, le=6)
    datum: str = "WGS84"

class BoundingBox(BaseModel):
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    srid: int = 4326

class OcorrenciaMineral(BaseModel):
    objectid: int
    substancias: str              # "Cobre, Ouro"
    municipio: str
    uf: str                       # "PA"
    provincia: str | None         # "Carajás"
    status_economico: str | None
    importancia: str | None
    rochas_hospedeiras: str | None
    rochas_encaixantes: str | None
    tipos_alteracao: str | None
    morfologia: str | None
    texturas: str | None
    coordenada: Coordenada
    
class DadoGravimetrico(BaseModel):
    objectid: int
    coordenada: Coordenada
    altitude_ortometrica: float
    gravidade: float
    anomalia_ar_livre: float
    anomalia_bouguer: float

class AmostraGeoquimica(BaseModel):
    objectid: int
    projeto: str
    classe: str                   # "Sedimento de Corrente", "Rocha", etc.
    material_coletado: str | None
    rocha_matriz: str | None
    coordenada: Coordenada
    # Campos analíticos variam por layer — usar dict para extras
    analises: dict[str, float | str | None] = {}
```

### 4.2 Interface do Connector

```python
class GeoSGBConnector:
    """Interface pública do connector."""
    
    async def ocorrencias(self, bbox: BoundingBox) -> list[OcorrenciaMineral]
    async def gravimetria(self, bbox: BoundingBox) -> list[DadoGravimetrico]
    async def geoquimica(self, bbox: BoundingBox, layer: str = "all") -> list[AmostraGeoquimica]
    async def geocronologia(self, bbox: BoundingBox) -> list[DatacaoGeocronologica]
    async def litoestratigrafia(self, bbox: BoundingBox) -> list[UnidadeLitoestratigrafica]
    async def aerogeofisica(self, bbox: BoundingBox) -> list[ProjetoAerogeofisico]
    
    async def count_ocorrencias(self, bbox: BoundingBox | None = None) -> int
    
    def export_geopackage(self, bbox: BoundingBox, path: Path) -> Path
```

## 5. Observabilidade

```python
# Métricas a emitir via structlog
logger.info("geosgb_request", 
    service="ocorrencias",
    method="identify",          # ou "query"
    bbox=str(bbox),
    tolerance=50,
    results=42,
    latency_ms=150,
    cache_hit=False,
)

logger.info("geosgb_extraction",
    service="ocorrencias",
    bbox=str(bbox),
    grid_points=20,
    total_results=375,
    unique_after_dedup=340,
    duration_ms=3200,
)

logger.warning("geosgb_error",
    service="aespectral",
    method="query",
    error_code=400,
    message="Unable to complete operation",
    fallback="identify",
)
```

## 6. Segurança

### Sanitização de dados para LLM

Dados textuais do GeoSGB (descrições litológicas, nomes de formações) passam por:

```python
def sanitize_for_llm(text: str, max_length: int = 500) -> str:
    """
    1. Remover caracteres de controle
    2. Truncar a max_length
    3. Escapar delimitadores XML/HTML
    """
```

Dados injetados em prompts sempre dentro de delimitadores:

```xml
<geological_data source="GeoSGB/ocorrencias" objectid="12345">
  substancias: Cobre, Ouro
  municipio: Parauapebas
  provincia: Carajás
  rochas_hospedeiras: Gabro, Granito
  alteracao: Sódico-cálcica, potássica
</geological_data>
```

### Rate limiting defensivo

```python
class ThrottledClient:
    min_delay_ms: int = 500       # Config padrão
    max_concurrent: int = 3       # Max requests paralelos
    retry_on: set = {429, 503}    # Retry automático
    max_retries: int = 3
    backoff_factor: float = 2.0   # Exponential backoff
```

## 7. Deploy e Rollback

- Connector é um módulo Python puro (sem infraestrutura)
- Rollback = reverter versão do pacote
- Cache local sobrevive a atualizações (diretório `~/.miner-harness/cache/`)
- Schemas versionados: se API mudar, mapper trata diferenças

## 8. Impacto Sistêmico

- **Agentes dependem do connector**: toda análise começa com dados
- **Cache é crítico**: sem cache, cada análise requer ~20 requests × 5 serviços = 100 requests
- **Modo offline**: após download inicial, tudo funciona sem internet
- **Fallback chain**: FeatureServer → MapServer/identify → cache local → shapefile local

## 9. Testes

### Testes de contrato
```python
def test_ocorrencias_schema():
    """Valida que o schema da API não mudou."""
    # Faz 1 request real (ou usa fixture gravada)
    # Verifica que campos esperados existem
    # Verifica tipos de dados

def test_gravimetria_query():
    """Valida que FeatureServer/query funciona para gravimetria."""
    # Query com limit=1
    # Verifica campos: longitude, latitude, anom_bougu
```

### Testes unitários
```python
def test_alias_mapper():
    """Mapeia aliases do MapServer para campos internos."""
    
def test_grid_generation():
    """Gera grid correto para bbox."""
    
def test_deduplication():
    """Remove duplicatas por objectid e coordenadas."""
```

### Fixtures
Respostas gravadas da API GeoSGB em `tests/connectors/fixtures/`:
- `ocorrencias_identify_carajas.json`
- `gravimetria_query_sample.json`
- `geoquimica_layer_info.json`

## Correlação

- ADR-002: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- ADR-003: [`../adr/ADR-003-engineering-security-standards.md`](../adr/ADR-003-engineering-security-standards.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- System Overview: [`../architecture/system-overview.md`](../architecture/system-overview.md)
- Discovery: [`../architecture/fase-1-discovery-report.md`](../architecture/fase-1-discovery-report.md)
