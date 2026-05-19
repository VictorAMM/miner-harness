#!/usr/bin/env bash
# Executa análise de prospecção mineral para uma região.
#
# Uso:
#   bash scripts/run_analysis.sh <região> <lon_min> <lat_min> <lon_max> <lat_max>
#
# Exemplo (Carajás):
#   bash scripts/run_analysis.sh carajas -51.5 -7.0 -49.0 -5.0

set -euo pipefail

REGION="${1:-}"
LON_MIN="${2:-}"
LAT_MIN="${3:-}"
LON_MAX="${4:-}"
LAT_MAX="${5:-}"

if [[ -z "${REGION}" || -z "${LON_MIN}" || -z "${LAT_MIN}" || -z "${LON_MAX}" || -z "${LAT_MAX}" ]]; then
  echo "Uso: $0 <região> <lon_min> <lat_min> <lon_max> <lat_max>"
  echo ""
  echo "Exemplo (Carajás):"
  echo "  $0 carajas -51.5 -7.0 -49.0 -5.0"
  exit 1
fi

export MINER_MODEL="${MINER_MODEL:-qwen3:8b}"
export MINER_OLLAMA_URL="${MINER_OLLAMA_URL:-http://localhost:11434}"

echo "=== miner-harness :: análise ==="
echo "  Região: ${REGION}"
echo "  BBox:   ${LON_MIN} ${LAT_MIN} ${LON_MAX} ${LAT_MAX}"
echo "  Modelo: ${MINER_MODEL}"
echo ""

miner-harness analyze "${REGION}" \
  --bbox "${LON_MIN}" "${LAT_MIN}" "${LON_MAX}" "${LAT_MAX}"
