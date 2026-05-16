# RFC-002: Orquestração de Agentes e LLM Engine

**Status**: APPROVED
**Autor**: Victor Augusto + Claude (Architect Swarm)
**Data**: 2026-05-12
**Fase ASO**: 3 — Technical Design e RFC Swarm

---

## 1. Objetivo

Definir a arquitetura técnica do orquestrador de agentes, dos agentes especialistas e da integração com LLM local (Ollama) para o miner-harness. Este RFC cobre os componentes centrais que transformam dados brutos do GeoSGB (extraídos via RFC-001) em análise de prospecção mineral integrada.

## 2. Arquitetura Alvo

```
┌──────────────────────────────────────────────────────────┐
│                  ProspectionEngine                        │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │             Orchestrator                             │  │
│  │  (Persona: Dr. Augusto Valen)                        │  │
│  │                                                      │  │
│  │  • run_analysis(region) → ProspectionReport           │  │
│  │  • execute_step(step, context) → StepResult           │  │
│  │  • integrate_results(steps[]) → IntegratedAnalysis    │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                            │
│  ┌────────────▼─────────────────────────────────────────┐  │
│  │             AgentPool                                 │  │
│  │                                                       │  │
│  │  ┌────────────────┐  ┌────────────────┐               │  │
│  │  │ StructuralGeo  │  │ Geophysicist   │               │  │
│  │  │   Agent        │  │   Agent        │               │  │
│  │  └────────────────┘  └────────────────┘               │  │
│  │  ┌────────────────┐  ┌────────────────┐               │  │
│  │  │ Geochemist     │  │ RemoteSensing  │               │  │
│  │  │   Agent        │  │   Agent        │               │  │
│  │  └────────────────┘  └────────────────┘               │  │
│  │  ┌────────────────┐                                   │  │
│  │  │ Evaluator      │                                   │  │
│  │  │   Agent        │                                   │  │
│  │  └────────────────┘                                   │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                            │
│  ┌────────────▼─────────────────────────────────────────┐  │
│  │             LLMEngine                                 │  │
│  │                                                       │  │
│  │  ┌────────────────┐  ┌────────────────────────────┐   │  │
│  │  │ OllamaClient   │  │ PromptManager              │   │  │
│  │  │                │  │                            │   │  │
│  │  │ • chat()       │  │ • build_prompt(agent,ctx)  │   │  │
│  │  │ • generate()   │  │ • system_prompt(persona)   │   │  │
│  │  │ • embeddings() │  │ • inject_data(geo_data)    │   │  │
│  │  │ • health()     │  │ • parse_response(raw)      │   │  │
│  │  └────────────────┘  └────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │ ModelRegistry                                   │   │  │
│  │  │                                                 │   │  │
│  │  │ • list_available() → Model[]                    │   │  │
│  │  │ • ensure_model(name) → bool                     │   │  │
│  │  │ • recommend(vram_gb) → Model                    │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │             ContextBuilder                            │  │
│  │                                                       │  │
│  │  • from_geosgb(connector, bbox) → AnalysisContext     │  │
│  │  • enrich_with_cache(ctx) → AnalysisContext           │  │
│  │  • build_rag_context(query, index) → str              │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## 3. Framework de Análise — Pipeline de 5 Passos

O orquestrador segue rigidamente o framework analítico do Dr. Augusto Valen. Cada passo é executado sequencialmente, com o resultado de cada um alimentando o próximo.

```
Passo 1: História Tectônica
  Agentes: StructuralGeoAgent
  Dados: litoestratigrafia, geocronologia, províncias estruturais
  Output: TectonicHistoryResult
    │
    ▼
Passo 2: Arquitetura Estrutural
  Agentes: StructuralGeoAgent
  Dados: estruturas, lineamentos, falhas, zonas de cisalhamento
  Output: StructuralArchitectureResult
    │
    ▼
Passo 3: Fertilidade Magmática
  Agentes: GeochemistAgent, GeophysicistAgent
  Dados: geoquímica, gravimetria, magnetometria, ocorrências
  Output: MagmaticFertilityResult
    │
    ▼
Passo 4: Evidências Indiretas
  Agentes: GeochemistAgent, RemoteSensingAgent, GeophysicistAgent
  Dados: alteração hidrotermal, minerais indicadores, anomalias geofísicas
  Output: IndirectEvidenceResult
    │
    ▼
Passo 5: Integração Total
  Agentes: EvaluatorAgent (com contexto de todos os passos)
  Dados: resultados dos passos 1-4
  Output: IntegratedAnalysis → ProspectionReport
```

## 4. Contratos e APIs Internas

### 4.1 Modelos do Orquestrador

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class AnalysisStep(str, Enum):
    TECTONIC_HISTORY = "tectonic_history"
    STRUCTURAL_ARCHITECTURE = "structural_architecture"
    MAGMATIC_FERTILITY = "magmatic_fertility"
    INDIRECT_EVIDENCE = "indirect_evidence"
    TOTAL_INTEGRATION = "total_integration"


class Confidence(str, Enum):
    HIGH = "high"         # Dados abundantes, interpretação sólida
    MEDIUM = "medium"     # Dados parciais, interpretação plausível
    LOW = "low"           # Dados escassos, interpretação especulativa
    INSUFFICIENT = "insufficient"  # Dados insuficientes para conclusão


class StepResult(BaseModel):
    """Resultado de um passo individual da análise."""
    step: AnalysisStep
    agent: str                          # Nome do agente executor
    summary: str                        # Resumo em linguagem natural
    findings: list[str]                 # Achados-chave (lista curta)
    confidence: Confidence
    data_sources_used: list[str]        # Quais datasets foram analisados
    data_gaps: list[str]                # Dados ausentes ou insuficientes
    raw_reasoning: str                  # Trace completo do raciocínio do LLM
    duration_ms: int


class MineralTarget(BaseModel):
    """Alvo de prospecção mineral identificado."""
    name: str                           # Nome descritivo do alvo
    longitude: float
    latitude: float
    radius_km: float                    # Raio estimado da área-alvo
    commodities: list[str]              # Minerais esperados
    mineral_system: str                 # Ex: "IOCG", "Ouro Orogênico"
    confidence: Confidence
    priority: int = Field(ge=1, le=5)   # 1=máxima, 5=mínima
    rationale: str                      # Justificativa integrada
    recommended_followup: list[str]     # Próximos passos recomendados


class ProspectionReport(BaseModel):
    """Relatório final de prospecção."""
    region_name: str
    bbox: "BoundingBox"                 # do RFC-001
    analysis_date: datetime
    steps: list[StepResult]             # 5 passos executados
    targets: list[MineralTarget]        # Alvos ranqueados
    integrated_summary: str             # Síntese final (Dr. Augusto Valen)
    caveats: list[str]                  # Limitações e advertências
    data_quality_score: float = Field(ge=0, le=1)  # Qualidade geral dos dados
    total_duration_ms: int
    model_used: str                     # Modelo LLM utilizado
```

### 4.2 Interface do Orquestrador

```python
class Orchestrator:
    """Coordena a análise de prospecção mineral."""

    def __init__(
        self,
        connector: "GeoSGBConnector",
        llm: "LLMEngine",
        config: "OrchestratorConfig",
    ) -> None: ...

    async def analyze_region(
        self,
        bbox: "BoundingBox",
        region_name: str | None = None,
        steps: list[AnalysisStep] | None = None,  # None = todos os 5
    ) -> ProspectionReport:
        """
        Executa análise completa de prospecção em uma região.
        
        1. Coleta dados via GeoSGBConnector (RFC-001)
        2. Constrói contexto de análise
        3. Executa cada passo sequencialmente
        4. Integra resultados via EvaluatorAgent
        5. Gera relatório final
        """

    async def execute_step(
        self,
        step: AnalysisStep,
        context: "AnalysisContext",
        previous_results: list[StepResult] | None = None,
    ) -> StepResult:
        """Executa um passo individual da análise."""

    def get_agent_for_step(self, step: AnalysisStep) -> "BaseAgent":
        """Retorna o agente responsável pelo passo."""
```

### 4.3 Classe Base dos Agentes

```python
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Classe base para todos os agentes especialistas."""

    name: str
    specialty: str
    system_prompt: str           # Prompt de sistema com persona

    def __init__(self, llm: "LLMEngine") -> None: ...

    @abstractmethod
    async def analyze(
        self,
        context: "AnalysisContext",
        previous_results: list[StepResult] | None = None,
    ) -> StepResult:
        """Executa análise especializada sobre os dados."""

    def build_prompt(
        self,
        context: "AnalysisContext",
        previous_results: list[StepResult] | None = None,
    ) -> list["ChatMessage"]:
        """Constrói mensagens para o LLM."""

    def parse_response(self, raw: str) -> StepResult:
        """Extrai resultado estruturado da resposta do LLM."""
```

### 4.4 Agentes Especialistas

```python
class StructuralGeoAgent(BaseAgent):
    """Geólogo Estrutural — Passos 1 e 2."""
    name = "structural_geologist"
    specialty = "Geologia estrutural, tectônica, reconstrução crustal"
    
    # Passo 1: analisa litoestratigrafia, geocronologia, províncias
    # Passo 2: analisa estruturas, lineamentos, zonas de cisalhamento


class GeophysicistAgent(BaseAgent):
    """Geofísico — Passos 3 e 4."""
    name = "geophysicist"
    specialty = "Magnetometria, gravimetria, IP/Resistividade, anomalias"
    
    # Passo 3: anomalias gravimétricas, padrões magnéticos
    # Passo 4: anomalias sutis, anomalias IP/Res


class GeochemistAgent(BaseAgent):
    """Geoquímico — Passos 3 e 4."""
    name = "geochemist"
    specialty = "Assinaturas geoquímicas, isotopia, alteração hidrotermal"
    
    # Passo 3: assinatura de fertilidade magmática
    # Passo 4: anomalias de pathfinder elements, alteração


class RemoteSensingAgent(BaseAgent):
    """Sensoriamento Remoto — Passo 4."""
    name = "remote_sensing"
    specialty = "Lineamentos, mapeamento espectral, anomalias de vegetação"
    
    # v1: trabalha com dados derivados do GeoSGB (ADR-005)
    # v2: integrará ESA/NASA


class EvaluatorAgent(BaseAgent):
    """Integrador/Avaliador — Passo 5."""
    name = "evaluator"
    specialty = "Integração multidisciplinar, validação de hipóteses"
    
    # Recebe resultados dos passos 1-4
    # Integra, identifica contradições, gera alvos ranqueados
    # Evaluator-Optimizer: valida plausibilidade geológica
```

### 4.5 Contexto de Análise

```python
class AnalysisContext(BaseModel):
    """Contexto completo para uma análise de prospecção."""
    
    bbox: "BoundingBox"
    region_name: str
    
    # Dados do GeoSGB (via RFC-001)
    ocorrencias: list["OcorrenciaMineral"]
    gravimetria: list["DadoGravimetrico"]
    geoquimica: list["AmostraGeoquimica"]
    geocronologia: list["DatacaoGeocronologica"]
    litoestratigrafia: list["UnidadeLitoestratigrafica"]
    aerogeofisica: list["ProjetoAerogeofisico"]
    
    # Metadados
    data_freshness: dict[str, datetime]   # Quando cada dataset foi baixado
    coverage_quality: dict[str, float]    # Cobertura estimada por dataset
    
    def summary_stats(self) -> dict[str, int]:
        """Conta registros por tipo de dado."""

    def has_sufficient_data(self, min_sources: int = 3) -> bool:
        """Verifica se há dados suficientes para análise."""
```

## 5. LLM Engine

### 5.1 OllamaClient

```python
class OllamaClient:
    """Client para Ollama REST API local."""
    
    base_url: str = "http://localhost:11434"
    timeout_s: int = 120            # LLMs locais podem ser lentos
    
    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.3,   # Baixo para análise técnica
        max_tokens: int = 4096,
    ) -> ChatResponse: ...
    
    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
    ) -> str: ...
    
    async def embeddings(
        self,
        model: str,
        text: str,
    ) -> list[float]: ...
    
    async def health(self) -> bool:
        """Verifica se Ollama está rodando."""

    async def list_models(self) -> list[ModelInfo]: ...
    async def pull_model(self, name: str) -> None: ...


class ChatMessage(BaseModel):
    role: str          # "system", "user", "assistant"
    content: str


class ChatResponse(BaseModel):
    content: str
    model: str
    total_duration_ns: int
    prompt_eval_count: int
    eval_count: int           # Tokens gerados
```

### 5.2 ModelRegistry

```python
class ModelSpec(BaseModel):
    """Especificação de um modelo LLM."""
    name: str                    # Ex: "qwen3:8b-q4_K_M"
    family: str                  # Ex: "qwen3"
    parameters_b: float          # Bilhões de parâmetros
    quantization: str            # Ex: "Q4_K_M"
    vram_required_gb: float      # VRAM necessária estimada
    context_window: int          # Tamanho da janela de contexto
    strengths: list[str]         # Ex: ["reasoning", "multilingual"]


class ModelRegistry:
    """Gerencia modelos disponíveis e recomendações."""
    
    # Modelos testados e recomendados
    RECOMMENDED: dict[str, ModelSpec] = {
        "default": ModelSpec(
            name="qwen3:4b",
            family="qwen3",
            parameters_b=4.0,
            quantization="Q4_K_M",
            vram_required_gb=4.0,
            context_window=32768,
            strengths=["reasoning", "multilingual", "fast"],
        ),
        "quality": ModelSpec(
            name="qwen3:8b-q4_K_M",
            family="qwen3",
            parameters_b=8.0,
            quantization="Q4_K_M",
            vram_required_gb=6.5,
            context_window=32768,
            strengths=["reasoning", "multilingual", "geocience"],
        ),
    }

    def recommend(self, vram_gb: float) -> ModelSpec:
        """Recomenda modelo baseado na VRAM disponível."""

    async def ensure_available(self, client: OllamaClient, spec: ModelSpec) -> bool:
        """Garante que o modelo está baixado e pronto."""
```

### 5.3 PromptManager

```python
class PromptManager:
    """Gerencia construção de prompts para os agentes."""
    
    def system_prompt(self, agent: BaseAgent) -> str:
        """Constrói system prompt com persona e especialidade."""

    def inject_geological_data(
        self,
        data: list[BaseModel],
        max_records: int = 50,
        max_chars: int = 8000,
    ) -> str:
        """
        Injeta dados geológicos no prompt de forma segura.
        
        1. Seleciona registros mais relevantes (por proximidade/importância)
        2. Sanitiza texto (RFC-001 §6)
        3. Encapsula em <geological_data> tags
        4. Respeita limites de tamanho
        """

    def build_step_prompt(
        self,
        step: AnalysisStep,
        context: AnalysisContext,
        previous_results: list[StepResult] | None = None,
    ) -> list[ChatMessage]:
        """Constrói prompt completo para um passo de análise."""
```

## 6. Fluxo de Execução Detalhado

```python
async def analyze_region(self, bbox, region_name):
    # 1. Coleta de dados
    logger.info("analysis_start", region=region_name, bbox=str(bbox))
    context = await self.context_builder.from_geosgb(self.connector, bbox)
    
    if not context.has_sufficient_data(min_sources=3):
        logger.warning("insufficient_data", 
            sources=context.summary_stats(),
            region=region_name)
        # Continua com advertência, não aborta
    
    # 2. Execução sequencial dos 5 passos
    results: list[StepResult] = []
    for step in AnalysisStep:
        agent = self.get_agent_for_step(step)
        result = await agent.analyze(
            context=context,
            previous_results=results,
        )
        results.append(result)
        logger.info("step_completed",
            step=step.value,
            agent=agent.name,
            confidence=result.confidence.value,
            duration_ms=result.duration_ms)
    
    # 3. Integração final (Evaluator)
    evaluator = self.agents["evaluator"]
    integration = await evaluator.integrate(results, context)
    
    # 4. Gerar relatório
    report = ProspectionReport(
        region_name=region_name or f"Region {bbox}",
        bbox=bbox,
        analysis_date=datetime.now(),
        steps=results,
        targets=integration.targets,
        integrated_summary=integration.summary,
        caveats=integration.caveats,
        data_quality_score=integration.data_quality,
        total_duration_ms=sum(r.duration_ms for r in results),
        model_used=self.llm.current_model,
    )
    
    logger.info("analysis_complete",
        region=region_name,
        targets=len(report.targets),
        quality=report.data_quality_score,
        total_ms=report.total_duration_ms)
    
    return report
```

## 7. Estratégia de Prompts

### 7.1 System Prompt Base (Dr. Augusto Valen)

Cada agente recebe um system prompt que combina:

```
1. Persona base Dr. Augusto Valen (tom técnico, desconfia de dados superficiais)
2. Especialidade do agente (geologia estrutural, geofísica, etc.)
3. Instruções de output (formato estruturado com findings + confidence)
4. Regras de integração ("nunca conclua com base em uma única técnica")
```

### 7.2 Formato de Output Esperado do LLM

```xml
<analysis>
  <step>tectonic_history</step>
  <confidence>medium</confidence>
  <summary>...</summary>
  <findings>
    <finding>...</finding>
    <finding>...</finding>
  </findings>
  <data_gaps>
    <gap>...</gap>
  </data_gaps>
  <reasoning>
    Trace completo do raciocínio...
  </reasoning>
</analysis>
```

Parser tolerante: se LLM não seguir formato exato, extrair informação por heurística e marcar `confidence` como `low`.

### 7.3 Gestão de Contexto (janela limitada)

Com janela de 32K tokens e dados potencialmente grandes:

```
Budget de tokens por passo:
  System prompt:        ~800 tokens
  Dados geológicos:     ~4000 tokens (selecionados por relevância)
  Resultados anteriores: ~2000 tokens (resumidos)
  Instrução do passo:   ~500 tokens
  Reserva para output:  ~4000 tokens
  ─────────────────────
  Total por chamada:    ~11300 tokens (confortável dentro de 32K)
```

Quando dados excedem o budget:
1. Priorizar por proximidade ao centróide do bbox
2. Priorizar por relevância ao passo atual
3. Sumarizar dados em excesso em tabela compacta
4. Registrar data_gaps para o que foi cortado

## 8. Observabilidade

```python
# Métricas do orquestrador
logger.info("orchestrator_analysis",
    region=region_name,
    bbox=str(bbox),
    data_sources=context.summary_stats(),
    model=self.llm.current_model,
    steps_completed=5,
    targets_found=len(targets),
    total_duration_ms=total_ms,
)

# Métricas por agente
logger.info("agent_inference",
    agent="structural_geologist",
    step="tectonic_history",
    prompt_tokens=prompt_eval_count,
    completion_tokens=eval_count,
    latency_ms=duration_ms,
    confidence="medium",
)

# Métricas do LLM Engine
logger.info("llm_health",
    ollama_status="running",
    model_loaded="qwen3:8b-q4_K_M",
    vram_used_gb=6.2,
    gpu="RTX 2070 Super",
)
```

## 9. Segurança

### 9.1 Isolamento de Agentes

- Agentes não têm acesso direto à rede — recebem dados já validados do AnalysisContext
- Output de cada agente é validado pelo Evaluator antes de compor o relatório final
- Nenhum agente pode executar código ou comandos — são puramente analíticos

### 9.2 Validação de Output (Evaluator-Optimizer)

O EvaluatorAgent aplica validações de plausibilidade:

```python
class EvaluatorChecks:
    """Verificações de plausibilidade geológica."""
    
    def coordinates_in_bbox(self, targets, bbox) -> bool:
        """Alvos estão dentro da região analisada."""
    
    def commodities_geologically_plausible(self, target, context) -> bool:
        """Minerais sugeridos são compatíveis com a geologia regional."""
    
    def no_hallucinated_data(self, result, context) -> bool:
        """Agente não referenciou dados que não existem no contexto."""
    
    def confidence_justified(self, result) -> bool:
        """Nível de confiança é coerente com dados disponíveis."""
```

### 9.3 Prompt Injection (dados → LLM)

Herda sanitização do RFC-001 §6. Adicionalmente:
- Resultados de passos anteriores também são sanitizados antes de reinjeção
- System prompt inclui instrução explícita para ignorar instruções incorporadas nos dados

## 10. Configuração

```python
class OrchestratorConfig(BaseModel):
    """Configuração do orquestrador."""
    
    model: str = "qwen3:8b-q4_K_M"
    temperature: float = 0.3
    max_tokens_per_step: int = 4096
    max_data_records_per_prompt: int = 50
    max_data_chars_per_prompt: int = 8000
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_s: int = 120
    
    # Passos a executar (permite pular passos em modo debug)
    enabled_steps: list[AnalysisStep] = list(AnalysisStep)
```

## 11. Testes

### Testes unitários

```python
def test_context_builder_summary():
    """AnalysisContext.summary_stats() conta corretamente."""

def test_context_sufficient_data():
    """has_sufficient_data() com threshold variável."""

def test_prompt_manager_data_injection():
    """Dados injetados respeitam limites de tamanho."""

def test_prompt_manager_sanitization():
    """Caracteres perigosos são sanitizados."""

def test_step_result_serialization():
    """StepResult serializa/desserializa sem perda."""

def test_evaluator_coordinates_check():
    """Alvos fora do bbox são rejeitados."""

def test_model_registry_recommendation():
    """Recomenda modelo correto para VRAM disponível."""
```

### Testes de agente (output format)

```python
def test_agent_output_has_required_fields():
    """Resposta parseada tem summary, findings, confidence."""

def test_agent_fallback_on_malformed_output():
    """Se LLM não seguir formato, parser extrai o possível."""

def test_evaluator_catches_hallucinated_data():
    """Evaluator detecta referência a dados inexistentes."""
```

### Fixtures

Respostas simuladas de LLM em `tests/agents/fixtures/`:
- `structural_geo_step1_response.txt`
- `geophysicist_step3_response.txt`
- `evaluator_integration_response.txt`
- `malformed_llm_response.txt` (para testar fallback)

## 12. Deploy e Rollback

- Orquestrador é módulo Python puro, sem infraestrutura própria
- Depende de Ollama estar rodando (verificado via `health()`)
- Config é arquivo local (`~/.miner-harness/config.toml`)
- Troca de modelo é hot-swap (Ollama gerencia loading/unloading)

## 13. Impacto Sistêmico

- **Depende de**: RFC-001 (GeoSGB Connector) para dados de entrada
- **Depende de**: Ollama rodando localmente
- **Produz**: ProspectionReport consumido pela Interface (TUI)
- **Performance**: análise completa (5 passos) estimada em 3-8 min dependendo do modelo e VRAM
- **Modo offline**: funciona 100% offline após dados cacheados e modelo baixado

## Correlação

- RFC-001: [`RFC-001-geosgb-connector.md`](RFC-001-geosgb-connector.md)
- ADR-001: [`../adr/ADR-001-stack-decision.md`](../adr/ADR-001-stack-decision.md)
- ADR-003: [`../adr/ADR-003-engineering-security-standards.md`](../adr/ADR-003-engineering-security-standards.md)
- ADR-004: [`../adr/ADR-004-user-interface.md`](../adr/ADR-004-user-interface.md)
- ADR-005: [`../adr/ADR-005-remote-sensing-strategy.md`](../adr/ADR-005-remote-sensing-strategy.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
- System Overview: [`../architecture/system-overview.md`](../architecture/system-overview.md)
- Discovery: [`../architecture/fase-1-discovery-report.md`](../architecture/fase-1-discovery-report.md)
