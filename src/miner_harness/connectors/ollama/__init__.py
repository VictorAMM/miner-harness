"""Ollama Connector — cliente async para LLMs locais via Ollama.

Ref: RFC-002 §5.1, §5.2
"""

from miner_harness.connectors.ollama.client import ChatMessage, ChatResponse, OllamaClient
from miner_harness.connectors.ollama.registry import ModelRegistry, ModelSpec

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "ModelRegistry",
    "ModelSpec",
    "OllamaClient",
]
