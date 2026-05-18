#!/usr/bin/env bash
# Faz pull dos modelos Ollama necessários para o miner-harness.
# Uso: bash scripts/pull_models.sh [--model qwen3:8b]

set -euo pipefail

LLM_MODEL="${MINER_MODEL:-qwen3:8b}"
EMBED_MODEL="nomic-embed-text"
OLLAMA_URL="${MINER_OLLAMA_URL:-http://localhost:11434}"

echo "=== miner-harness :: pull models ==="
echo "  LLM:       ${LLM_MODEL}"
echo "  Embedding: ${EMBED_MODEL}"
echo "  Ollama:    ${OLLAMA_URL}"
echo ""

# Verificar Ollama disponível
if ! curl -sf "${OLLAMA_URL}/api/tags" >/dev/null; then
  echo "ERRO: Ollama não está disponível em ${OLLAMA_URL}"
  echo "Inicie com 'ollama serve' ou use 'docker compose -f infra/docker-compose.yml up -d'"
  exit 1
fi

echo "Baixando ${LLM_MODEL}..."
ollama pull "${LLM_MODEL}"
echo "✓ ${LLM_MODEL}"

echo "Baixando ${EMBED_MODEL}..."
ollama pull "${EMBED_MODEL}"
echo "✓ ${EMBED_MODEL}"

echo ""
echo "Modelos prontos. Execute: miner-harness health"
