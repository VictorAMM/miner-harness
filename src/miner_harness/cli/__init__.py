"""CLI -- interface de linha de comando.

Comandos:
    miner-harness analyze --bbox "lon_min,lat_min,lon_max,lat_max" --region NAME
    miner-harness cache stats
    miner-harness cache clear
    miner-harness index rebuild

Ref: ADR-004, RFC-002, RFC-003.
"""

from miner_harness.cli.app import main

__all__ = ["main"]
