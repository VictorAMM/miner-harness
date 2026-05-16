# RFC-003: Cache Local, Índice Vetorial e Storage

**Status**: APPROVED
**Autor**: Victor Augusto + Claude (Architect Swarm)
**Data**: 2026-05-12
**Fase ASO**: 3 — Technical Design e RFC Swarm

---

## 1. Objetivo

Definir a arquitetura do subsistema de persistência local do miner-harness: cache de dados GeoSGB, índice vetorial para busca semântica (RAG), e organização do storage local em disco. Este componente é a ponte entre a coleta de dados (RFC-001) e a análise por agentes (RFC-002).

## 2. Arquitetura Alvo

```
~/.miner-harness/                      ← MINER_HOME
├── config.toml                        ← Configuração do usuário
├── cache/
│   ├── geosgb.db                      ← SQLite: metadados + features pontuais
│   └── regions/
│       ├── carajas.gpkg               ← GeoPackage por região
│       └── quadrilatero_ferrifero.gpkg
├── models/                            ← Modelos LLM (gerenciado por Ollama)
├── index/
│   ├── vectors.db                     ← SQLite-vec: embeddings
│   └── metadata.db                    ← Metadados dos documentos indexados
├── exports/                           ← Relatórios e mapas exportados
│   └── reports/
└── logs/
    └── miner-harness.log              ← structlog JSON
```

```
┌──────────────────────────────────────────────────────────┐
│                   StorageLayer                            │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              CacheManager                            │  │
│  │                                                      │  │
│  │  ┌──────────────────┐  ┌──────────────────────────┐  │  │
│  │  │ SQLiteStore       │  │ GeoPackageStore          │  │  │
│  │  │                  │  │                          │  │  │
│  │  │ • get()          │  │ • save_region()          │  │  │
│  │  │ • put()          │  │ • load_region()          │  │  │
│  │  │ • evict()        │  │ • list_regions()         │  │  │
│  │  │ • stats()        │  │ • export()               │  │  │
│  │  └──────────────────┘  └──────────────────────────┘  │  │
│  │                                                      │  │
│  │  ┌──────────────────────────────────────────────┐    │  │
│  │  │ TTLPolicy                                     │    │  │
│  │  │                                               │    │  │
│  │  │ • pontuais: 30 dias                           │    │  │
│  │  │ • polígonos (litoestratigrafia): permanente    │    │  │
│  │  │ • gravimetria: 90 dias                        │    │  │
│  │  │ • contagem: 7 dias                            │    │  │
│  │  └──────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              VectorIndex                             │  │
│  │                                                      │  │
│  │  ┌──────────────────┐  ┌──────────────────────────┐  │  │
│  │  │ Embedder         │  │ SearchEngine             │  │  │
│  │  │                  │  │                          │  │  │
│  │  │ • embed_text()   │  │ • search(query, k)      │  │  │
│  │  │ • embed_batch()  │  │ • search_by_bbox()      │  │  │
│  │  │ • model: local   │  │ • search_by_type()      │  │  │
│  │  └──────────────────┘  └──────────────────────────┘  │  │
│  │                                                      │  │
│  │  ┌──────────────────────────────────────────────┐    │  │
│  │  │ DocumentStore                                 │    │  │
│  │  │                                               │    │  │
│  │  │ • index_features(features[])                  │    │  │
│  │  │ • index_analysis(report)                      │    │  │
│  │  │ • get_context(query, max_tokens) → str        │    │  │
│  │  └──────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              StorageConfig                           │  │
│  │                                                      │  │
│  │  • miner_home: Path                                  │  │
│  │  • max_cache_size_gb: float = 5.0                    │  │
│  │  • auto_evict: bool = True                           │  │
│  │  • vector_model: str = "nomic-embed-text"            │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## 3. CacheManager — Detalhamento

### 3.1 SQLiteStore (metadados + features pontuais)

O banco SQLite armazena features pontuais do GeoSGB (ocorrências, gravimetria, geoquímica, geocronologia) como JSON serializado, junto com metadados de quando e como os dados foram coletados.

```python
class CacheEntry(BaseModel):
    """Registro no cache."""
    service: str                    # "ocorrencias", "gravimetria", etc.
    bbox_hash: str                  # Hash do BoundingBox normalizado
    bbox: "BoundingBox"
    fetched_at: datetime
    ttl_days: int
    record_count: int
    extraction_method: str          # "identify", "query", "shapefile"
    data: str                       # JSON serializado das features


class SQLiteStore:
    """Cache de features GeoSGB em SQLite."""

    def __init__(self, db_path: Path) -> None: ...

    def get(
        self,
        service: str,
        bbox: "BoundingBox",
    ) -> list[dict] | None:
        """
        Retorna features cacheadas se existirem e estiverem frescas.
        Retorna None se cache miss ou TTL expirado.
        """

    def put(
        self,
        service: str,
        bbox: "BoundingBox",
        features: list[dict],
        method: str,
    ) -> None:
        """Salva features no cache com timestamp."""

    def evict_expired(self) -> int:
        """Remove entradas com TTL expirado. Retorna contagem."""

    def stats(self) -> CacheStats:
        """Estatísticas: tamanho, entradas, hit rate."""

    def contains(self, service: str, bbox: "BoundingBox") -> bool:
        """Verifica se bbox está coberto no cache (sem carregar dados)."""
```

### 3.2 GeoPackageStore (dados geoespaciais por região)

GeoPackage (.gpkg) é o formato padrão OGC para dados geoespaciais em SQLite. Usado para dados pesados (litoestratigrafia, polígonos) e para exportação.

```python
class GeoPackageStore:
    """Armazena dados geoespaciais regionais em GeoPackage."""

    def __init__(self, regions_dir: Path) -> None: ...

    def save_region(
        self,
        region_name: str,
        layers: dict[str, "GeoDataFrame"],
    ) -> Path:
        """
        Salva múltiplas camadas em um GeoPackage regional.
        Ex: save_region("carajas", {"ocorrencias": gdf, "gravimetria": gdf})
        """

    def load_region(
        self,
        region_name: str,
        layers: list[str] | None = None,
    ) -> dict[str, "GeoDataFrame"]:
        """Carrega camadas de um GeoPackage regional."""

    def list_regions(self) -> list[RegionInfo]:
        """Lista regiões cacheadas com metadados."""

    def export(
        self,
        region_name: str,
        output_path: Path,
        format: str = "gpkg",
    ) -> Path:
        """Exporta região para uso externo (QGIS, ArcGIS)."""
```

### 3.3 TTL Policy

```python
class TTLPolicy:
    """Política de expiração do cache por tipo de dado."""

    POLICIES: dict[str, int] = {
        # Dados pontuais que podem ser atualizados
        "ocorrencias": 30,          # 30 dias
        "geoquimica": 30,
        "geocronologia": 60,        # Muda raramente
        "gravimetria": 90,          # Dados estáveis

        # Dados de polígonos (mudam muito raramente)
        "litoestratigrafia": 365,   # Anual
        "bacias_sedimentares": 365,
        "provincias": 365,

        # Metadados voláteis
        "count": 7,                 # Contagens expiram rápido
        "service_info": 30,         # Info do serviço
    }

    def get_ttl(self, service: str) -> int:
        """Retorna TTL em dias para o serviço."""

    def is_expired(self, entry: CacheEntry) -> bool:
        """Verifica se entrada expirou."""
```

### 3.4 Fluxo de Cache (integração com RFC-001)

```
Requisição do Orquestrador
    │
    ▼
CacheManager.get(service, bbox)
    │
    ├── Cache HIT (fresco) → retorna dados imediatamente
    │
    └── Cache MISS ou TTL expirado
        │
        ▼
    GeoSGBConnector.extract_region(service, bbox)  ← RFC-001
        │
        ▼
    CacheManager.put(service, bbox, features)
        │
        ▼
    VectorIndex.index_features(features)  ← indexa para RAG
        │
        ▼
    Retorna features
```

## 4. VectorIndex — Detalhamento

### 4.1 Propósito

Os agentes (RFC-002) precisam de busca semântica para encontrar informações relevantes no contexto de dados geológicos. O índice vetorial permite queries como "alteração hidrotermal perto de zonas de cisalhamento" em vez de filtros SQL rígidos.

### 4.2 Tecnologia: sqlite-vec

Embeddings armazenados em SQLite via extensão `sqlite-vec`. Escolhido por:
- Zero dependência de servidor (alinhado com filosofia 100% local)
- Persistência em arquivo único
- Compatível com o ecossistema SQLite já usado no cache
- Performance adequada para dezenas de milhares de vetores

### 4.3 Modelo de Embeddings

```python
class EmbeddingConfig(BaseModel):
    """Configuração do modelo de embeddings."""
    model: str = "nomic-embed-text"     # Via Ollama
    dimensions: int = 768
    max_batch_size: int = 100
    max_text_length: int = 512          # Truncar textos longos


class Embedder:
    """Gera embeddings via Ollama."""

    def __init__(
        self,
        client: "OllamaClient",    # RFC-002
        config: EmbeddingConfig,
    ) -> None: ...

    async def embed_text(self, text: str) -> list[float]:
        """Gera embedding para um texto."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings em batch (mais eficiente)."""
```

### 4.4 Documentos Indexados

Cada feature do GeoSGB é convertida em "documento" para indexação:

```python
class IndexDocument(BaseModel):
    """Documento indexado no vetor store."""
    id: str                         # service:objectid
    source: str                     # "geosgb/ocorrencias"
    text: str                       # Texto para embedding
    metadata: dict                  # Campos originais
    bbox: "BoundingBox"             # Para filtro espacial
    embedding: list[float] | None   # Preenchido pelo Embedder


class DocumentStore:
    """Gerencia indexação e busca de documentos."""

    async def index_features(
        self,
        features: list[BaseModel],
        source: str,
    ) -> int:
        """
        Indexa features GeoSGB para busca semântica.
        
        Para cada feature:
        1. Gera texto descritivo combinando campos relevantes
        2. Gera embedding via Ollama
        3. Armazena vetor + metadados no sqlite-vec
        
        Retorna número de documentos indexados.
        """

    async def index_analysis(
        self,
        report: "ProspectionReport",     # RFC-002
    ) -> int:
        """Indexa relatório de análise anterior para referência futura."""

    async def search(
        self,
        query: str,
        k: int = 10,
        bbox: "BoundingBox | None" = None,
        source_filter: str | None = None,
    ) -> list[SearchResult]:
        """
        Busca semântica nos documentos indexados.
        
        1. Gera embedding da query
        2. Busca k vizinhos mais próximos no sqlite-vec
        3. Aplica filtros opcionais (bbox, source)
        4. Retorna resultados ranqueados por similaridade
        """

    def get_context(
        self,
        query: str,
        max_tokens: int = 4000,
    ) -> str:
        """
        Monta contexto RAG formatado para injeção em prompt.
        Usado pelo PromptManager (RFC-002).
        """
```

### 4.5 Geração de Texto para Embedding

```python
def feature_to_text(feature: BaseModel, source: str) -> str:
    """
    Converte feature GeoSGB em texto descritivo para embedding.
    
    Exemplos:
    
    OcorrenciaMineral → 
      "Ocorrência mineral em Parauapebas, PA. Província: Carajás. 
       Substâncias: Cobre, Ouro. Rochas hospedeiras: Gabro, Granito. 
       Alteração: Sódico-cálcica, potássica. Status: Depósito."
    
    DadoGravimetrico →
      "Dado gravimétrico em -6.05, -50.12. Anomalia Bouguer: -35.2 mGal.
       Anomalia ar livre: 12.8 mGal. Altitude: 245m."
    
    AmostraGeoquimica →
      "Amostra geoquímica do projeto RENCA. Classe: Sedimento de Corrente.
       Material: Fração fina. Cu: 45 ppm, Au: 0.12 ppm, Fe: 8.5%."
    """
```

## 5. Storage Config

```python
class StorageConfig(BaseModel):
    """Configuração do subsistema de storage."""
    
    miner_home: Path = Path.home() / ".miner-harness"
    
    # Cache
    max_cache_size_gb: float = 5.0
    auto_evict: bool = True
    
    # Índice vetorial
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    max_index_size: int = 100_000       # Max documentos indexados
    
    # GeoPackage
    default_srid: int = 4326
    
    # Logs
    log_level: str = "INFO"
    log_max_size_mb: int = 50
    log_rotation: int = 5               # Manter 5 arquivos

    def ensure_dirs(self) -> None:
        """Cria diretórios necessários se não existirem."""
```

## 6. Modo Offline

O subsistema de storage é desenhado para modo offline completo:

```
Primeiro uso (online):
  1. Wizard baixa modelo LLM via Ollama
  2. Wizard baixa modelo de embeddings (nomic-embed-text)
  3. Usuário solicita análise de região → dados baixados e cacheados
  4. Features indexadas no vetor store

Usos subsequentes (offline):
  1. CacheManager serve dados locais
  2. VectorIndex busca em embeddings locais
  3. LLM roda localmente via Ollama
  4. Zero requests de rede necessários
```

### Indicador de cobertura

```python
class CoverageReport(BaseModel):
    """Relatório de cobertura de cache para uma região."""
    region: "BoundingBox"
    services_cached: dict[str, bool]
    services_fresh: dict[str, bool]     # Dentro do TTL
    total_features: int
    indexed_features: int
    can_run_offline: bool               # Todos os dados essenciais cacheados?
    missing_services: list[str]         # O que falta baixar
```

## 7. Observabilidade

```python
# Cache metrics
logger.info("cache_hit",
    service="ocorrencias",
    bbox=str(bbox),
    age_hours=12.5,
    records=340,
)

logger.info("cache_miss",
    service="geoquimica",
    bbox=str(bbox),
    reason="not_found",     # ou "ttl_expired"
)

logger.info("cache_eviction",
    evicted=15,
    freed_mb=42.3,
    remaining_entries=230,
)

# Index metrics
logger.info("index_search",
    query="alteração hidrotermal cisalhamento",
    results=10,
    top_similarity=0.87,
    latency_ms=45,
)

logger.info("index_batch_embed",
    documents=150,
    model="nomic-embed-text",
    latency_ms=3200,
)

# Storage metrics
logger.info("storage_stats",
    cache_size_mb=1230,
    index_size_mb=85,
    regions_cached=3,
    total_features=12500,
    indexed_documents=11800,
)
```

## 8. Segurança

### 8.1 File permissions

```python
def secure_miner_home(path: Path) -> None:
    """
    Configura permissões do diretório MINER_HOME.
    - Diretórios: 700 (owner only)
    - Arquivos: 600 (owner only)
    - config.toml: 600 (pode conter paths sensíveis)
    """
```

### 8.2 SQL Injection

Todos os acessos a SQLite usam queries parametrizadas. Nenhum dado do GeoSGB é interpolado em SQL.

```python
# ✅ Correto
cursor.execute(
    "SELECT data FROM cache WHERE service = ? AND bbox_hash = ?",
    (service, bbox_hash),
)

# ❌ Proibido
cursor.execute(f"SELECT data FROM cache WHERE service = '{service}'")
```

### 8.3 Sanitização de dados antes de indexação

Dados textuais do GeoSGB são sanitizados (RFC-001 §6) antes de gerar embeddings e antes de armazenar no índice vetorial.

### 8.4 Limite de tamanho

```python
MAX_SINGLE_FEATURE_KB = 100        # Rejeitar features anormalmente grandes
MAX_CACHE_ENTRIES_PER_SERVICE = 50  # Por bbox — evita cache bombing
MAX_INDEX_BATCH = 1000              # Limitar batch de indexação
```

## 9. Testes

### Testes unitários

```python
def test_cache_put_get_roundtrip():
    """Salva e recupera features sem perda de dados."""

def test_cache_ttl_expiration():
    """Entradas expiradas retornam None."""

def test_cache_evict_removes_expired():
    """evict_expired() remove apenas entradas TTL expirado."""

def test_bbox_hash_deterministic():
    """Mesmo bbox sempre gera mesmo hash."""

def test_bbox_hash_invariant_to_precision():
    """bbox(-51.500, -7.000) == bbox(-51.5, -7.0)"""

def test_geopackage_save_load():
    """GeoPackage roundtrip preserva geometrias e atributos."""

def test_feature_to_text_ocorrencia():
    """Texto gerado contém campos-chave da ocorrência."""

def test_feature_to_text_gravimetria():
    """Texto gerado contém valores numéricos relevantes."""

def test_vector_search_returns_ranked():
    """Resultados ordenados por similaridade descendente."""

def test_vector_search_bbox_filter():
    """Filtro espacial exclui features fora do bbox."""

def test_coverage_report():
    """CoverageReport detecta serviços faltantes."""

def test_storage_config_creates_dirs():
    """ensure_dirs() cria toda a árvore de diretórios."""
```

### Testes de integração

```python
def test_cache_then_index_pipeline():
    """Dados cacheados são automaticamente indexados."""

def test_offline_mode_with_cached_data():
    """Análise funciona sem rede quando cache está populado."""
```

### Fixtures

Em `tests/storage/fixtures/`:
- `ocorrencias_carajas_sample.json` — 50 features para cache
- `gravimetria_sample.json` — 20 features para cache
- `sample_embeddings.json` — embeddings pré-calculados para teste sem Ollama

## 10. Dependências

```toml
# Novas dependências (pyproject.toml)
[project]
dependencies = [
    # ... existentes do RFC-001 ...
    "geopandas>=1.0",          # GeoPackage I/O
    "fiona>=1.10",             # Backend para geopandas
    "sqlite-vec>=0.1",         # Índice vetorial em SQLite
]
```

## 11. Deploy e Rollback

- Storage é diretório local, sem infraestrutura
- Migração de schema SQLite via versão de schema no DB
- Cache pode ser deletado sem perda funcional (apenas performance)
- Índice vetorial pode ser reconstruído a partir do cache
- `miner-harness cache clear` — CLI para limpar cache
- `miner-harness index rebuild` — CLI para reconstruir índice

## 12. Impacto Sistêmico

- **RFC-001 depende de**: CacheManager para persistir dados extraídos
- **RFC-002 depende de**: VectorIndex para contexto RAG dos agentes
- **Wizard depende de**: StorageConfig para criar diretórios iniciais
- **Performance**: cache elimina ~95% dos requests de rede após primeiro uso
- **Disco**: estimativa de ~500MB por região com todos os datasets + embeddings
- **Modo offline**: 100% funcional após download inicial

## Correlação

- RFC-001: [`RFC-001-geosgb-connector.md`](RFC-001-geosgb-connector.md)
- RFC-002: [`RFC-002-agent-orchestration.md`](RFC-002-agent-orchestration.md)
- ADR-001: [`../adr/ADR-001-stack-decision.md`](../adr/ADR-001-stack-decision.md)
- ADR-003: [`../adr/ADR-003-engineering-security-standards.md`](../adr/ADR-003-engineering-security-standards.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- System Overview: [`../architecture/system-overview.md`](../architecture/system-overview.md)
