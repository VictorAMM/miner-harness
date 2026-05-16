"""GeoSGB Connector — acesso à API do Serviço Geológico do Brasil.

Implementa extração via MapServer/identify (primário) e
FeatureServer/query (secundário, apenas gravimetria).
Ref: RFC-001, ADR-002.
"""

from miner_harness.connectors.geosgb.connector import GeoSGBConnector
from miner_harness.connectors.geosgb.grid_extractor import GridDensity
from miner_harness.connectors.geosgb.sanitizer import sanitize_for_llm, sanitize_record

__all__ = [
    "GeoSGBConnector",
    "GridDensity",
    "sanitize_for_llm",
    "sanitize_record",
]
