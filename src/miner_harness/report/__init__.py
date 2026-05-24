"""Módulo de geração de relatórios HTML e DOCX do miner-harness."""

from miner_harness.report.docx_exporter import DocxReportExporter
from miner_harness.report.renderer import HtmlReportRenderer

__all__ = ["DocxReportExporter", "HtmlReportRenderer"]
