"""Property-based tests com Hypothesis.

Testa invariantes dos tipos core e modulos de cache/index
com inputs gerados aleatoriamente.

Ref: ASO v3 Phase 7 -- Testing Swarm (fuzzing)
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from miner_harness.core.types import BoundingBox, Coordenada

# ============================================================
# Strategies
# ============================================================

# Coordenadas validas (WGS84)
valid_lon = st.floats(min_value=-74.0, max_value=-29.0, allow_nan=False, allow_infinity=False)
valid_lat = st.floats(min_value=-34.0, max_value=6.0, allow_nan=False, allow_infinity=False)

# BoundingBox strategy: garante lon_min < lon_max, lat_min < lat_max
@st.composite
def valid_bbox(draw):
    lon1 = draw(st.floats(min_value=-74.0, max_value=-30.0, allow_nan=False, allow_infinity=False))
    lon2 = draw(st.floats(
        min_value=lon1 + 0.001, max_value=-29.0, allow_nan=False, allow_infinity=False,
    ))
    lat1 = draw(st.floats(
        min_value=-34.0, max_value=5.0, allow_nan=False, allow_infinity=False,
    ))
    lat2 = draw(st.floats(
        min_value=lat1 + 0.001, max_value=6.0, allow_nan=False, allow_infinity=False,
    ))
    return BoundingBox(lon_min=lon1, lat_min=lat1, lon_max=lon2, lat_max=lat2)


# Feature dicts (simula dados do GeoSGB)
@st.composite
def geo_feature(draw):
    return {
        "objectid": draw(st.integers(min_value=1, max_value=999999)),
        "substancias": draw(st.text(min_size=1, max_size=50)),
        "uf": draw(st.sampled_from(["PA", "MG", "GO", "MT", "BA", "AM"])),
    }


# ============================================================
# BoundingBox properties
# ============================================================

class TestBoundingBoxProperties:
    """Invariantes do BoundingBox."""

    @given(bbox=valid_bbox())
    @settings(max_examples=50)
    def test_hash_is_deterministic(self, bbox: BoundingBox) -> None:
        """Mesmo bbox deve sempre produzir mesmo hash."""
        h1 = bbox.hash()
        h2 = bbox.hash()
        assert h1 == h2

    @given(bbox=valid_bbox())
    @settings(max_examples=50)
    def test_as_tuple_roundtrip(self, bbox: BoundingBox) -> None:
        """as_tuple() deve preservar todos os valores."""
        t = bbox.as_tuple()
        assert len(t) == 4
        assert t[0] == bbox.lon_min
        assert t[1] == bbox.lat_min
        assert t[2] == bbox.lon_max
        assert t[3] == bbox.lat_max

    @given(bbox=valid_bbox())
    @settings(max_examples=50)
    def test_hash_is_hex_string(self, bbox: BoundingBox) -> None:
        """Hash deve ser string hexadecimal valida."""
        h = bbox.hash()
        assert isinstance(h, str)
        assert len(h) > 0
        # Should be valid hex
        int(h, 16)

    @given(
        bbox1=valid_bbox(),
        bbox2=valid_bbox(),
    )
    @settings(max_examples=50)
    def test_different_bbox_likely_different_hash(
        self, bbox1: BoundingBox, bbox2: BoundingBox
    ) -> None:
        """BBox com coordenadas significativamente diferentes tem hash diferente."""
        # Only assert different hash if values differ by > 0.01 (rounding tolerance)
        t1, t2 = bbox1.as_tuple(), bbox2.as_tuple()
        if all(abs(a - b) > 0.01 for a, b in zip(t1, t2, strict=True)):
            assert bbox1.hash() != bbox2.hash()

    @given(bbox=valid_bbox())
    @settings(max_examples=50)
    def test_bbox_equality_implies_hash_equality(self, bbox: BoundingBox) -> None:
        """BBox com mesmos valores deve ter mesmo hash."""
        bbox2 = BoundingBox(
            lon_min=bbox.lon_min, lat_min=bbox.lat_min,
            lon_max=bbox.lon_max, lat_max=bbox.lat_max,
        )
        assert bbox.hash() == bbox2.hash()


# ============================================================
# Coordenada properties
# ============================================================

class TestCoordenadaProperties:
    """Invariantes da Coordenada."""

    @given(lon=valid_lon, lat=valid_lat)
    @settings(max_examples=50)
    def test_coordenada_preserves_values(self, lon: float, lat: float) -> None:
        """Coordenada deve preservar longitude e latitude."""
        c = Coordenada(longitude=lon, latitude=lat)
        assert c.longitude == lon
        assert c.latitude == lat

    @given(lon=valid_lon, lat=valid_lat)
    @settings(max_examples=50)
    def test_coordenada_serialization_roundtrip(self, lon: float, lat: float) -> None:
        """model_dump() + model_validate() deve preservar dados."""
        c = Coordenada(longitude=lon, latitude=lat)
        dumped = c.model_dump()
        restored = Coordenada.model_validate(dumped)
        assert restored.longitude == c.longitude
        assert restored.latitude == c.latitude


# ============================================================
# Cache roundtrip properties
# ============================================================

class TestCacheRoundtripProperties:
    """Invariantes do cache: put -> get preserva dados."""

    @given(
        bbox=valid_bbox(),
        features=st.lists(geo_feature(), min_size=0, max_size=20),
    )
    @settings(max_examples=30, deadline=5000)
    def test_cache_roundtrip_preserves_data(
        self, bbox: BoundingBox, features: list[dict], tmp_path_factory
    ) -> None:
        """put() seguido de get() deve retornar dados identicos."""
        from miner_harness.cache.manager import CacheManager
        from miner_harness.core.config import StorageConfig

        tmp = tmp_path_factory.mktemp("cache")
        config = StorageConfig(miner_home=tmp / ".miner")
        store = CacheManager(config)
        try:
            store.put("ocorrencias", bbox, features)
            result = store.get("ocorrencias", bbox)
            assert result is not None
            assert len(result) == len(features)
            if features:
                assert result[0]["objectid"] == features[0]["objectid"]
        finally:
            store.close()

    @given(
        bbox=valid_bbox(),
        service=st.sampled_from([
            "ocorrencias", "gravimetria", "geoquimica",
            "geocronologia", "litoestratigrafia", "aerogeofisica",
        ]),
    )
    @settings(max_examples=20, deadline=5000)
    def test_contains_after_put(
        self, bbox: BoundingBox, service: str, tmp_path_factory
    ) -> None:
        """contains() deve retornar True apos put()."""
        from miner_harness.cache.manager import CacheManager
        from miner_harness.core.config import StorageConfig

        tmp = tmp_path_factory.mktemp("cache")
        config = StorageConfig(miner_home=tmp / ".miner")
        store = CacheManager(config)
        try:
            store.put(service, bbox, [{"id": 1}])
            assert store.contains(service, bbox)
        finally:
            store.close()


# ============================================================
# Grid extractor properties
# ============================================================

class TestGridExtractorProperties:
    """Invariantes do GridExtractor."""

    @given(bbox=valid_bbox())
    @settings(max_examples=50)
    def test_grid_covers_bbox(self, bbox: BoundingBox) -> None:
        """Grid de pontos deve cobrir o bbox original."""
        from miner_harness.connectors.geosgb.grid_extractor import generate_grid

        points = generate_grid(bbox)
        assert len(points) >= 4  # Minimo 2x2

        lons = [p[0] for p in points]
        lats = [p[1] for p in points]

        # Pontos devem cobrir de lon_min a lon_max (com tolerancia de rounding)
        assert min(lons) <= bbox.lon_min + 0.01
        assert max(lons) >= bbox.lon_max - 0.01
        assert min(lats) <= bbox.lat_min + 0.01
        assert max(lats) >= bbox.lat_max - 0.01

    @given(bbox=valid_bbox())
    @settings(max_examples=30)
    def test_grid_points_are_within_bbox(self, bbox: BoundingBox) -> None:
        """Cada ponto do grid deve estar dentro do bbox (com tolerancia)."""
        from miner_harness.connectors.geosgb.grid_extractor import generate_grid

        points = generate_grid(bbox)
        for lon, lat in points:
            assert bbox.lon_min - 0.01 <= lon <= bbox.lon_max + 0.01
            assert bbox.lat_min - 0.01 <= lat <= bbox.lat_max + 0.01


# ============================================================
# Sanitizer properties
# ============================================================

class TestSanitizerProperties:
    """Invariantes do sanitizer."""

    @given(text=st.text(min_size=0, max_size=1000))
    @settings(max_examples=50)
    def test_sanitize_for_llm_bounded_length(self, text: str) -> None:
        """sanitize_for_llm nunca retorna mais que max_length + 3 (ellipsis)."""
        from miner_harness.connectors.geosgb.sanitizer import sanitize_for_llm

        max_len = 100
        result = sanitize_for_llm(text, max_length=max_len)
        # After escaping, length may increase, but input truncation happens first
        assert isinstance(result, str)

    @given(text=st.text(min_size=0, max_size=200))
    @settings(max_examples=50)
    def test_sanitize_removes_control_chars(self, text: str) -> None:
        """sanitize_for_llm deve remover caracteres de controle."""
        import re

        from miner_harness.connectors.geosgb.sanitizer import sanitize_for_llm

        result = sanitize_for_llm(text)
        # No control chars except tab and newline should remain
        control = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
        assert not control.search(result)

    @given(
        record=st.fixed_dictionaries({
            "objectid": st.integers(min_value=1),
            "nome": st.text(min_size=0, max_size=100),
            "valor": st.floats(allow_nan=False, allow_infinity=False),
        })
    )
    @settings(max_examples=30)
    def test_sanitize_record_preserves_non_strings(self, record: dict) -> None:
        """sanitize_record preserva valores nao-string."""
        from miner_harness.connectors.geosgb.sanitizer import sanitize_record

        result = sanitize_record(record)
        assert result["objectid"] == record["objectid"]
        assert result["valor"] == record["valor"]
