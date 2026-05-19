"""Testes de ServiceEndpoint em services.py."""

from __future__ import annotations

import pytest

from miner_harness.connectors.geosgb.services import OCORRENCIAS, ServiceEndpoint


class TestServiceEndpoint:
    """Testes das propriedades de ServiceEndpoint."""

    def test_url_property(self) -> None:
        ep = ServiceEndpoint(
            name="test",
            path="geologia/test",
            server_type="FeatureServer",
            supports_query=True,
        )
        assert ep.url.endswith("FeatureServer")
        assert "geologia/test" in ep.url

    def test_identify_url_on_mapserver(self) -> None:
        ep = ServiceEndpoint(
            name="test",
            path="geologia/test",
            server_type="MapServer",
        )
        assert ep.identify_url.endswith("/identify")

    def test_identify_url_on_featureserver_raises(self) -> None:
        with pytest.raises(ValueError, match="identify not available"):
            _ = OCORRENCIAS.identify_url

    def test_query_url(self) -> None:
        assert OCORRENCIAS.query_url(0).endswith("/0/query")
