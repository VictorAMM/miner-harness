"""ModelRegistry — gerencia modelos LLM disponíveis e recomendações.

Mantém catálogo de modelos testados com o miner-harness,
recomenda baseado na VRAM disponível e verifica disponibilidade.

Ref: RFC-002 §5.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from miner_harness.connectors.ollama.client import OllamaClient

from miner_harness.core.exceptions import ModelNotAvailableError

logger = structlog.get_logger(__name__)


class ModelSpec(BaseModel):
    """Especificação de um modelo LLM."""

    name: str = Field(description='Ex: "qwen3:8b"')
    family: str = Field(description='Ex: "qwen3"')
    parameters_b: float = Field(description="Bilhões de parâmetros")
    quantization: str = Field(description='Ex: "Q4_K_M"')
    vram_required_gb: float = Field(description="VRAM necessária estimada")
    context_window: int = Field(description="Tamanho da janela de contexto")
    strengths: list[str] = Field(
        default_factory=list,
        description='Ex: ["reasoning", "multilingual"]',
    )


# Modelos testados e recomendados para o miner-harness
RECOMMENDED_MODELS: dict[str, ModelSpec] = {
    "compact": ModelSpec(
        name="qwen3:4b",
        family="qwen3",
        parameters_b=4.0,
        quantization="Q4_K_M",
        vram_required_gb=4.0,
        context_window=32768,
        strengths=["reasoning", "multilingual", "fast"],
    ),
    "default": ModelSpec(
        name="qwen3:8b",
        family="qwen3",
        parameters_b=8.0,
        quantization="Q4_K_M",
        vram_required_gb=6.5,
        context_window=32768,
        strengths=["reasoning", "multilingual", "geoscience"],
    ),
    "quality": ModelSpec(
        name="qwen3:14b-q4_K_M",
        family="qwen3",
        parameters_b=14.0,
        quantization="Q4_K_M",
        vram_required_gb=10.0,
        context_window=32768,
        strengths=["reasoning", "multilingual", "geoscience", "analysis"],
    ),
}

# Modelo de embeddings
EMBEDDING_MODEL = ModelSpec(
    name="nomic-embed-text",
    family="nomic",
    parameters_b=0.137,
    quantization="fp16",
    vram_required_gb=0.5,
    context_window=8192,
    strengths=["embedding", "retrieval"],
)


class ModelRegistry:
    """Gerencia modelos disponíveis e recomendações."""

    def recommend(self, vram_gb: float) -> ModelSpec:
        """Recomenda modelo baseado na VRAM disponível.

        Args:
            vram_gb: VRAM disponível em GB.

        Returns:
            ModelSpec do modelo recomendado.

        Raises:
            ModelNotAvailableError: Se não há modelo compatível com a VRAM.
        """
        # Ordena por parâmetros (melhor → pior) e pega o maior que cabe
        candidates = sorted(
            RECOMMENDED_MODELS.values(),
            key=lambda m: m.parameters_b,
            reverse=True,
        )
        for model in candidates:
            if model.vram_required_gb <= vram_gb:
                logger.info(
                    "model_recommended",
                    model=model.name,
                    vram_available=vram_gb,
                    vram_required=model.vram_required_gb,
                )
                return model

        raise ModelNotAvailableError(
            f"No model fits in {vram_gb}GB VRAM. Minimum required: "
            f"{min(m.vram_required_gb for m in candidates)}GB"
        )

    async def ensure_available(
        self,
        client: OllamaClient,
        spec: ModelSpec,
    ) -> bool:
        """Verifica se o modelo está disponível no Ollama.

        Args:
            client: OllamaClient conectado.
            spec: Especificação do modelo.

        Returns:
            True se o modelo está disponível.
        """
        models = await client.list_models()
        available_names = {m.name for m in models}

        if spec.name in available_names:
            return True

        # Tenta match parcial (sem tag de quantização)
        base_name = spec.name.split(":")[0]
        for name in available_names:
            if name.startswith(base_name):
                logger.info(
                    "model_partial_match",
                    requested=spec.name,
                    found=name,
                )
                return True

        return False

    def get_embedding_model(self) -> ModelSpec:
        """Retorna o modelo de embeddings recomendado."""
        return EMBEDDING_MODEL

    def list_recommended(self) -> dict[str, ModelSpec]:
        """Lista todos os modelos recomendados."""
        return dict(RECOMMENDED_MODELS)
