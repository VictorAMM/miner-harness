"""GisExporter — exportação de ProspectionReport para GeoPackage e GeoJSON.

Converte alvos, ocorrências, gravimetria e furos de sondagem em camadas
GIS consumíveis diretamente em QGIS, ArcGIS ou geopandas.

Cada alvo é exportado como:
  - Ponto central (longitude/latitude do MineralTarget)
  - Polígono de buffer (radius_km convertido em graus aproximados)

Camadas produzidas:
  - targets       → pontos + atributos de MineralTarget
  - targets_buffer→ polígonos de buffer (radius_km)
  - ocorrencias   → pontos de OcorrenciaMineral (se disponível no relatório)
  - gravimetria   → pontos de DadoGravimetrico (se disponível)
  - furos         → pontos de FuroSondagem (se disponível)

Ref: PRD-002 F1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.core.types import ProspectionReport

logger = structlog.get_logger(__name__)

# 1 grau ≈ 111 km; conversão aproximada de km para graus (suficiente para buffer visual)
_KM_TO_DEG = 1.0 / 111.0


def _target_to_point_feature(target: Any) -> dict[str, Any]:
    """Serializa MineralTarget como GeoJSON Feature (ponto)."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [target.longitude, target.latitude],
        },
        "properties": {
            "name": target.name,
            "priority": target.priority,
            "confidence": target.confidence.value,
            "mineral_system": target.mineral_system,
            "commodities": ", ".join(target.commodities),
            "radius_km": target.radius_km,
            "rationale": target.rationale,
            "recommended_followup": "; ".join(target.recommended_followup),
        },
    }


def _target_to_buffer_feature(target: Any) -> dict[str, Any]:
    """Serializa MineralTarget como GeoJSON Feature (polígono de buffer aproximado).

    Usa buffer circular em coordenadas geográficas. Para exportações
    profissionais, reprojetar para UTM antes de calcular buffer em metros.
    """
    import math

    lon, lat = target.longitude, target.latitude
    r_deg = target.radius_km * _KM_TO_DEG
    # Polígono de 36 pontos (círculo aproximado)
    n = 36
    coords = [
        [
            lon + r_deg * math.cos(2 * math.pi * i / n),
            lat + r_deg * math.sin(2 * math.pi * i / n),
        ]
        for i in range(n)
    ]
    coords.append(coords[0])  # fechar polígono
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "name": target.name,
            "priority": target.priority,
            "confidence": target.confidence.value,
            "mineral_system": target.mineral_system,
            "commodities": ", ".join(target.commodities),
            "radius_km": target.radius_km,
        },
    }


def _ocorrencia_to_feature(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Serializa registro de ocorrência como GeoJSON Feature."""
    coord = rec.get("coordenada", {})
    lon = coord.get("longitude") if isinstance(coord, dict) else None
    lat = coord.get("latitude") if isinstance(coord, dict) else None
    if lon is None or lat is None:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "objectid": rec.get("objectid"),
            "substancias": rec.get("substancias", ""),
            "municipio": rec.get("municipio", ""),
            "uf": rec.get("uf", ""),
            "provincia": rec.get("provincia"),
            "status_economico": rec.get("status_economico"),
            "importancia": rec.get("importancia"),
            "rochas_hospedeiras": rec.get("rochas_hospedeiras"),
        },
    }


def _gravimetria_to_feature(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Serializa registro gravimétrico como GeoJSON Feature."""
    coord = rec.get("coordenada", {})
    lon = coord.get("longitude") if isinstance(coord, dict) else None
    lat = coord.get("latitude") if isinstance(coord, dict) else None
    if lon is None or lat is None:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "objectid": rec.get("objectid"),
            "anomalia_bouguer": rec.get("anomalia_bouguer"),
            "anomalia_ar_livre": rec.get("anomalia_ar_livre"),
            "gravidade": rec.get("gravidade"),
            "altitude_ortometrica": rec.get("altitude_ortometrica"),
        },
    }


def _furo_to_feature(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Serializa registro de furo de sondagem como GeoJSON Feature."""
    coord = rec.get("coordenada", {})
    lon = coord.get("longitude") if isinstance(coord, dict) else None
    lat = coord.get("latitude") if isinstance(coord, dict) else None
    if lon is None or lat is None:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "objectid": rec.get("objectid"),
            "projeto": rec.get("projeto"),
            "profundidade_m": rec.get("profundidade_m"),
            "azimute": rec.get("azimute"),
            "mergulho": rec.get("mergulho"),
            "ano": rec.get("ano"),
        },
    }


def _build_feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


class GisExporter:
    """Exporta ProspectionReport para GeoPackage e GeoJSON.

    O GeoPackage (.gpkg) é o formato preferencial para uso em QGIS/ArcGIS.
    O GeoJSON é o formato de fallback (sem dependência de geopandas/fiona).

    Usage:
        exporter = GisExporter()
        exporter.export(report, Path("targets.gpkg"))
        exporter.export_geojson(report, Path("targets.geojson"))
    """

    def export(self, report: ProspectionReport, output_path: Path) -> Path:
        """Exporta relatório para GeoPackage (requer geopandas + fiona).

        Camadas: targets, targets_buffer, ocorrencias, gravimetria, furos.

        Args:
            report: Relatório de prospecção.
            output_path: Caminho de saída (.gpkg).

        Returns:
            Caminho do arquivo gerado.

        Raises:
            ImportError: Se geopandas/fiona não estiverem disponíveis.
            ValueError: Se não houver alvos para exportar.
        """
        try:
            import geopandas as gpd  # noqa: PLC0415
            from shapely.geometry import Point, Polygon, mapping  # noqa: PLC0415, F401
        except ImportError as exc:
            raise ImportError(
                "geopandas e shapely são necessários para exportação GeoPackage. "
                "Execute: pip install geopandas shapely"
            ) from exc

        if not report.targets:
            raise ValueError("Relatório sem alvos de prospecção — nada para exportar.")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove arquivo existente (fiona não sobrescreve GeoPackage)
        if output_path.exists():
            output_path.unlink()

        layers_exported: list[str] = []

        # --- Camada: targets (pontos) ---
        target_features = [_target_to_point_feature(t) for t in report.targets]
        gdf_targets = gpd.GeoDataFrame.from_features(target_features, crs="EPSG:4326")
        gdf_targets.to_file(output_path, layer="targets", driver="GPKG")
        layers_exported.append("targets")

        # --- Camada: targets_buffer (polígonos) ---
        buffer_features = [_target_to_buffer_feature(t) for t in report.targets]
        gdf_buf = gpd.GeoDataFrame.from_features(buffer_features, crs="EPSG:4326")
        gdf_buf.to_file(output_path, layer="targets_buffer", driver="GPKG")
        layers_exported.append("targets_buffer")

        # --- Camadas de dados brutos (quando disponíveis no relatório) ---
        geo_data = report.geological_data or {}

        for key, converter, layer_name in [
            ("ocorrencias", _ocorrencia_to_feature, "ocorrencias"),
            ("gravimetria", _gravimetria_to_feature, "gravimetria"),
            ("furos", _furo_to_feature, "furos"),
        ]:
            records = geo_data.get(key, [])
            if not records:
                continue
            feats = [f for r in records if (f := converter(r)) is not None]
            if not feats:
                continue
            gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
            gdf.to_file(output_path, layer=layer_name, driver="GPKG")
            layers_exported.append(layer_name)

        logger.info(
            "gis_export_complete",
            path=str(output_path),
            layers=layers_exported,
            targets=len(report.targets),
        )
        print(f"GeoPackage exportado: {output_path}")
        print(f"  Camadas: {', '.join(layers_exported)}")
        return output_path

    def export_geojson(self, report: ProspectionReport, output_path: Path) -> Path:
        """Exporta apenas os alvos como GeoJSON (sem dependência de geopandas).

        Args:
            report: Relatório de prospecção.
            output_path: Caminho de saída (.geojson).

        Returns:
            Caminho do arquivo gerado.

        Raises:
            ValueError: Se não houver alvos para exportar.
        """
        if not report.targets:
            raise ValueError("Relatório sem alvos de prospecção — nada para exportar.")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        features = [_target_to_point_feature(t) for t in report.targets]
        fc = _build_feature_collection(features)
        output_path.write_text(
            json.dumps(fc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "geojson_export_complete",
            path=str(output_path),
            targets=len(report.targets),
        )
        print(f"GeoJSON exportado: {output_path} ({len(features)} alvos)")
        return output_path
