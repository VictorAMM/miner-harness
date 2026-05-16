"""Agentes especialistas — pipeline de análise Dr. Augusto Valen.

Cada agente implementa uma disciplina geocientífica e produz
StepResult tipado a partir de dados do GeoSGB + LLM local.

Ref: RFC-002 §4.3, §4.4
"""

from miner_harness.agents.base import BaseAgent
from miner_harness.agents.evaluator import EvaluatorAgent
from miner_harness.agents.geochemist import GeochemistAgent
from miner_harness.agents.geophysicist import GeophysicistAgent
from miner_harness.agents.remote_sensing import RemoteSensingAgent
from miner_harness.agents.structural_geo import StructuralGeoAgent

__all__ = [
    "BaseAgent",
    "EvaluatorAgent",
    "GeochemistAgent",
    "GeophysicistAgent",
    "RemoteSensingAgent",
    "StructuralGeoAgent",
]
