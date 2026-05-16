"""GeoSGBConnector — interface pública de acesso ao GeoSGB.

Orquestra ThrottledClient, GridExtractor e AliasMapper para
extrair dados geológicos da API do Serviço Geológico do Brasil.

Ref: RFC-001 §4.2 (Interface do Connector)
"""

from __future__ import annotations

from typing import Any

import structlog

from miner_harness.core.config import GeoSGBConfig
from miner_harness.core.exceptions import GeoSGBError, GeoSGBQueryError
from miner_harness.core.types import (
    AmostraGeoquimica,
    BoundingBox,
    Coordenada,
    DadoGravimetrico,
    DatacaoGeocronologica,
    OcorrenciaMineral,
    ProjetoAerogeofisico,
    UnidadeLitoestratigrafica,
)

from .alias_mapper import AliasMapper
from .grid_extractor import (
    GridDensity,
    build_identify_params,
    deduplicate_features,
    generate_grid,
)
from .services import GRAVIMETRIA, SERVICE_REGISTRY, ServiceEndpoint
from .throttled_client import ThrottledClient

logger = structlog.get_logger(__name__)


class GeoSGBConnector:
    """Interface pública do connector GeoSGB.

    Provê métodos tipados para cada serviço, abstraindo:
    - MapServer/identify (grid + dedup) para a maioria dos serviços
    - FeatureServer/query para gravimetria
    - Alias mapping para normalizar campos
    - Rate limiting via ThrottledClient

    Usage:
        async with GeoSGBConnector() as connector:
            ocorrencias = await connector.ocorrencias(bbox)
            gravimetria = await connector.gravimetria(bbox)
    """

    def __init__(self, config: GeoSGBConfig | None = None) -> None:
        self._config = config or GeoSGBConfig()
        self._client = ThrottledClient(self._config)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> GeoSGBConnector:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Fecha o cliente HTTP subjacente."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Métodos públicos tipados (RFC-001 §4.2)
    # ------------------------------------------------------------------

    async def ocorrencias(
        self,
        bbox: BoundingBox,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[OcorrenciaMineral]:
        """Extrai ocorrências minerais da região.

        Args:
            bbox: Bounding box da região.
            density: Densidade do grid de extração.

        Returns:
            Lista de ocorrências minerais tipadas.
        """
        raw = await self._extract_via_identify("ocorrencias", bbox, density=density)
        mapper = AliasMapper("ocorrencias")
        mapped = mapper.map_records(raw)
        return [self._parse_ocorrencia(r) for r in mapped]

    async def gravimetria(
        self,
        bbox: BoundingBox,
    ) -> list[DadoGravimetrico]:
        """Extrai dados gravimétricos da região via FeatureServer/query.

        Gravimetria é o único serviço com FeatureServer funcional.

        Args:
            bbox: Bounding box da região.

        Returns:
            Lista de dados gravimétricos tipados.
        """
        raw = await self._query_features(GRAVIMETRIA, bbox=bbox)
        mapper = AliasMapper("gravimetria")
        mapped = mapper.map_records(raw)
        return [self._parse_gravimetria(r) for r in mapped]

    async def geoquimica(
        self,
        bbox: BoundingBox,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[AmostraGeoquimica]:
        """Extrai amostras geoquímicas da região."""
        raw = await self._extract_via_identify("geoquimica", bbox, density=density)
        mapper = AliasMapper("geoquimica")
        mapped = mapper.map_records(raw)
        return [self._parse_geoquimica(r) for r in mapped]

    async def geocronologia(
        self,
        bbox: BoundingBox,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[DatacaoGeocronologica]:
        """Extrai datações geocronológicas da região."""
        raw = await self._extract_via_identify("geocronologia", bbox, density=density)
        mapper = AliasMapper("geocronologia")
        mapped = mapper.map_records(raw)
        return [self._parse_geocronologia(r) for r in mapped]

    async def litoestratigrafia(
        self,
        bbox: BoundingBox,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[UnidadeLitoestratigrafica]:
        """Extrai unidades litoestratigráficas da região."""
        raw = await self._extract_via_identify("litoestratigrafia", bbox, density=density)
        mapper = AliasMapper("litoestratigrafia")
        mapped = mapper.map_records(raw)
        return [self._parse_litoestratigrafia(r) for r in mapped]

    async def aerogeofisica(
        self,
        bbox: BoundingBox,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[ProjetoAerogeofisico]:
        """Extrai projetos aerogeofísicos da região."""
        raw = await self._extract_via_identify("aerogeofisica", bbox, density=density)
        mapper = AliasMapper("aerogeofisica")
        mapped = mapper.map_records(raw)
        return [self._parse_aerogeofisica(r) for r in mapped]

    async def count_ocorrencias(self, bbox: BoundingBox | None = None) -> int:
        """Conta ocorrências minerais (via FeatureServer/returnCountOnly).

        Args:
            bbox: Bounding box opcional para filtrar. None = total.

        Returns:
            Número de ocorrências.
        """
        endpoint = SERVICE_REGISTRY["ocorrencias"]
        params: dict[str, str] = {
            "f": "json",
            "where": "1=1",
            "returnCountOnly": "true",
        }
        if bbox is not None:
            params["geometry"] = f"{bbox.lon_min},{bbox.lat_min},{bbox.lon_max},{bbox.lat_max}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["inSR"] = "4326"

        url = endpoint.query_url(endpoint.default_layers[0])
        data = await self._client.get(url, params=params)
        return int(data.get("count", 0))

    # ------------------------------------------------------------------
    # Extração interna — MapServer/identify
    # ------------------------------------------------------------------

    async def _extract_via_identify(
        self,
        service_name: str,
        bbox: BoundingBox,
        *,
        layers: list[int] | None = None,
        density: GridDensity = GridDensity.MEDIUM,
    ) -> list[dict[str, Any]]:
        """Extrai features via grid de MapServer/identify.

        1. Gera grid de pontos sobre bbox
        2. Para cada ponto, chama identify
        3. Merge + deduplica por objectid
        """
        import time

        endpoint = SERVICE_REGISTRY[service_name]
        if layers is None:
            layers = endpoint.default_layers

        grid = generate_grid(bbox, density)
        all_features: list[dict[str, Any]] = []

        start = time.monotonic()

        for point in grid:
            params = build_identify_params(
                point=point,
                bbox=bbox,
                layers=layers,
                tolerance=density.tolerance,
            )
            try:
                data = await self._client.get(endpoint.identify_url, params=params)
                features = self._parse_identify_response(data)
                all_features.extend(features)
            except GeoSGBError:
                logger.warning(
                    "identify_point_failed",
                    service=service_name,
                    point=point,
                )
                # Continua com outros pontos

        unique = deduplicate_features(all_features, key="objectid")
        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "geosgb_extraction",
            service=service_name,
            bbox=bbox.as_tuple(),
            grid_points=len(grid),
            total_results=len(all_features),
            unique_after_dedup=len(unique),
            duration_ms=duration_ms,
        )
        return unique

    # ------------------------------------------------------------------
    # Extração interna — FeatureServer/query
    # ------------------------------------------------------------------

    async def _query_features(
        self,
        endpoint: ServiceEndpoint,
        *,
        layer: int | None = None,
        where: str = "1=1",
        bbox: BoundingBox | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query via FeatureServer com paginação.

        Args:
            endpoint: Endpoint do serviço.
            layer: Layer ID. None = primeiro da lista default.
            where: Cláusula WHERE SQL.
            bbox: Filtro espacial opcional.
            fields: Campos a retornar. None = todos.
            limit: Máximo de resultados. None = todos (paginado).

        Returns:
            Lista de registros como dicts.
        """
        if not endpoint.supports_query:
            msg = f"Service '{endpoint.name}' does not support FeatureServer/query"
            raise GeoSGBQueryError(endpoint.name, 0, msg)

        layer_id = layer if layer is not None else endpoint.default_layers[0]
        url = endpoint.query_url(layer_id)

        params: dict[str, str] = {
            "f": "json",
            "where": where,
            "outFields": ",".join(fields) if fields else "*",
            "returnGeometry": "true",
            "outSR": "4326",
        }
        if bbox is not None:
            params["geometry"] = f"{bbox.lon_min},{bbox.lat_min},{bbox.lon_max},{bbox.lat_max}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["inSR"] = "4326"
            params["spatialRel"] = "esriSpatialRelIntersects"

        all_features: list[dict[str, Any]] = []
        offset = 0
        page_size = 1000

        while True:
            params["resultOffset"] = str(offset)
            params["resultRecordCount"] = str(
                min(page_size, limit - len(all_features)) if limit else page_size
            )

            data = await self._client.get(url, params=params)

            if "error" in data:
                err = data["error"]
                raise GeoSGBQueryError(
                    endpoint.name,
                    err.get("code", 0),
                    err.get("message", "Unknown error"),
                )

            features = data.get("features", [])
            for feat in features:
                attrs = feat.get("attributes", {})
                geom = feat.get("geometry", {})
                if geom:
                    attrs["longitude"] = geom.get("x")
                    attrs["latitude"] = geom.get("y")
                all_features.append(attrs)

            # Verificar se há mais páginas
            if len(features) < page_size:
                break
            if limit and len(all_features) >= limit:
                break
            offset += len(features)

        return all_features

    # ------------------------------------------------------------------
    # Parsing de respostas
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_identify_response(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai atributos de uma resposta MapServer/identify.

        A resposta tem formato:
        {"results": [{"layerId": 0, "attributes": {...}, "geometry": {...}}, ...]}
        """
        results = data.get("results", [])
        features: list[dict[str, Any]] = []
        for result in results:
            attrs = dict(result.get("attributes", {}))
            geom = result.get("geometry", {})
            if geom:
                attrs["longitude"] = geom.get("x")
                attrs["latitude"] = geom.get("y")
            features.append(attrs)
        return features

    # ------------------------------------------------------------------
    # Construtores de modelos tipados
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ocorrencia(data: dict[str, Any]) -> OcorrenciaMineral:
        """Constrói OcorrenciaMineral a partir de dados mapeados."""
        return OcorrenciaMineral(
            objectid=int(data.get("objectid", 0)),
            substancias=str(data.get("substancias", "")),
            municipio=str(data.get("municipio", "")),
            uf=str(data.get("uf", "")),
            provincia=data.get("provincia"),
            status_economico=data.get("status_economico"),
            importancia=data.get("importancia"),
            rochas_hospedeiras=data.get("rochas_hospedeiras"),
            rochas_encaixantes=data.get("rochas_encaixantes"),
            tipos_alteracao=data.get("tipos_alteracao"),
            morfologia=data.get("morfologia"),
            texturas=data.get("texturas"),
            coordenada=Coordenada(
                longitude=float(data.get("longitude", -50.0)),
                latitude=float(data.get("latitude", -6.0)),
            ),
        )

    @staticmethod
    def _parse_gravimetria(data: dict[str, Any]) -> DadoGravimetrico:
        """Constrói DadoGravimetrico a partir de dados mapeados."""
        return DadoGravimetrico(
            objectid=int(data.get("objectid", 0)),
            coordenada=Coordenada(
                longitude=float(data.get("longitude", -50.0)),
                latitude=float(data.get("latitude", -6.0)),
            ),
            altitude_ortometrica=float(data.get("altitude_ortometrica", 0.0)),
            gravidade=float(data.get("gravidade", 0.0)),
            anomalia_ar_livre=float(data.get("anomalia_ar_livre", 0.0)),
            anomalia_bouguer=float(data.get("anomalia_bouguer", 0.0)),
        )

    @staticmethod
    def _parse_geoquimica(data: dict[str, Any]) -> AmostraGeoquimica:
        """Constrói AmostraGeoquimica a partir de dados mapeados."""
        # Campos conhecidos
        known_keys = {
            "objectid",
            "projeto",
            "classe",
            "material_coletado",
            "rocha_matriz",
            "longitude",
            "latitude",
        }
        # Campos extras → analises
        analises = {k: v for k, v in data.items() if k not in known_keys and v is not None}

        return AmostraGeoquimica(
            objectid=int(data.get("objectid", 0)),
            projeto=str(data.get("projeto", "")),
            classe=str(data.get("classe", "")),
            material_coletado=data.get("material_coletado"),
            rocha_matriz=data.get("rocha_matriz"),
            coordenada=Coordenada(
                longitude=float(data.get("longitude", -50.0)),
                latitude=float(data.get("latitude", -6.0)),
            ),
            analises=analises,
        )

    @staticmethod
    def _parse_geocronologia(data: dict[str, Any]) -> DatacaoGeocronologica:
        """Constrói DatacaoGeocronologica a partir de dados mapeados."""
        idade_raw = data.get("idade_ma")
        erro_raw = data.get("erro_ma")
        return DatacaoGeocronologica(
            objectid=int(data.get("objectid", 0)),
            metodo=data.get("metodo"),
            idade_ma=float(idade_raw) if idade_raw is not None else None,
            erro_ma=float(erro_raw) if erro_raw is not None else None,
            material=data.get("material"),
            unidade_geologica=data.get("unidade_geologica"),
            coordenada=Coordenada(
                longitude=float(data.get("longitude", -50.0)),
                latitude=float(data.get("latitude", -6.0)),
            ),
        )

    @staticmethod
    def _parse_litoestratigrafia(data: dict[str, Any]) -> UnidadeLitoestratigrafica:
        """Constrói UnidadeLitoestratigrafica a partir de dados mapeados."""
        return UnidadeLitoestratigrafica(
            objectid=int(data.get("objectid", 0)),
            sigla=data.get("sigla"),
            nome=data.get("nome"),
            hierarquia=data.get("hierarquia"),
            litologia_principal=data.get("litologia_principal"),
            idade=data.get("idade"),
        )

    @staticmethod
    def _parse_aerogeofisica(data: dict[str, Any]) -> ProjetoAerogeofisico:
        """Constrói ProjetoAerogeofisico a partir de dados mapeados."""
        ano_raw = data.get("ano")
        area_raw = data.get("area_km2")
        return ProjetoAerogeofisico(
            objectid=int(data.get("objectid", 0)),
            nome_projeto=data.get("nome_projeto"),
            ano=int(ano_raw) if ano_raw is not None else None,
            tipo_levantamento=data.get("tipo_levantamento"),
            area_km2=float(area_raw) if area_raw is not None else None,
            coordenada=Coordenada(
                longitude=float(data.get("longitude", -50.0)),
                latitude=float(data.get("latitude", -6.0)),
            ),
        )
