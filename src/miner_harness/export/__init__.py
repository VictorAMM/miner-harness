"""Export — exportação de relatórios de prospecção para formatos GIS.

Módulo responsável por converter ProspectionReport em GeoPackage,
GeoJSON e outros formatos consumíveis por ferramentas profissionais
(QGIS, ArcGIS, geopandas).

Ref: PRD-002 F1
"""

from miner_harness.export.gis_exporter import GisExporter

__all__ = ["GisExporter"]
