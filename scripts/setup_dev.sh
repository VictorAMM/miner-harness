#!/usr/bin/env bash
# Configura ambiente de desenvolvimento do miner-harness.
# Uso: bash scripts/setup_dev.sh

set -euo pipefail

echo "=== miner-harness :: setup dev ==="

# Verificar Python 3.11+
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required="3.11"
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
  echo "ERRO: Python ${required}+ necessário (encontrado: ${python_version})"
  exit 1
fi
echo "✓ Python ${python_version}"

# Instalar uv se ausente
if ! command -v uv &>/dev/null; then
  echo "Instalando uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "✓ uv $(uv --version)"

# Instalar dependências
uv sync --all-extras
echo "✓ Dependências instaladas"

# Verificar Ollama
if command -v ollama &>/dev/null; then
  echo "✓ Ollama $(ollama --version 2>/dev/null | head -1)"
else
  echo "⚠  Ollama não encontrado. Instale em https://ollama.com ou use infra/docker-compose.yml"
fi

echo ""
echo "Próximos passos:"
echo "  bash scripts/pull_models.sh   # baixar modelos LLM"
echo "  miner-harness install         # wizard de instalação"
echo "  miner-harness health          # verificar sistema"
