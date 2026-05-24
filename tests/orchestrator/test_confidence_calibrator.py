"""Testes de ConfidenceCalibrator — recalibração de confiança por cobertura."""

from __future__ import annotations

from miner_harness.core.types import AnalysisStep, Confidence
from miner_harness.orchestrator.confidence_calibrator import (
    _COMPUTED_KEYS,
    _MIN_RECORDS_FOR_HIGH,
    _MIN_RECORDS_FOR_MEDIUM,
    _QUANTITATIVE_STEPS,
    ConfidenceCalibrator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STEPS_1_2 = [AnalysisStep.TECTONIC_HISTORY, AnalysisStep.STRUCTURAL_ARCHITECTURE]
_STEPS_3_5 = [
    AnalysisStep.MAGMATIC_FERTILITY,
    AnalysisStep.INDIRECT_EVIDENCE,
    AnalysisStep.TOTAL_INTEGRATION,
]


def _geo_with(
    *,
    bouguer: bool = False,
    geochem_norm: bool = False,
    n_raw_records: int = 20,
) -> dict:
    """Monta geological_data sintético para testes."""
    grav = [{"coordenada": {}, "anomalia_bouguer": -30.0}] * n_raw_records
    data: dict = {"gravimetria": grav}
    if bouguer:
        data["bouguer_gradient"] = [{"text": "HGM computed", "geojson": {}}]
    if geochem_norm:
        data["geoquimica_normalizada"] = [{"text": "CF computed"}]
    return data


# ---------------------------------------------------------------------------
# Constantes e invariantes
# ---------------------------------------------------------------------------


class TestConstants:
    def test_quantitative_steps_are_3_4_5(self) -> None:
        assert AnalysisStep.MAGMATIC_FERTILITY in _QUANTITATIVE_STEPS
        assert AnalysisStep.INDIRECT_EVIDENCE in _QUANTITATIVE_STEPS
        assert AnalysisStep.TOTAL_INTEGRATION in _QUANTITATIVE_STEPS
        assert AnalysisStep.TECTONIC_HISTORY not in _QUANTITATIVE_STEPS
        assert AnalysisStep.STRUCTURAL_ARCHITECTURE not in _QUANTITATIVE_STEPS

    def test_computed_keys_exclude_raw_sources(self) -> None:
        raw_keys = {"ocorrencias", "gravimetria", "geoquimica", "litoestratigrafia"}
        assert raw_keys.isdisjoint(_COMPUTED_KEYS)

    def test_thresholds_ordered(self) -> None:
        assert _MIN_RECORDS_FOR_MEDIUM < _MIN_RECORDS_FOR_HIGH


# ---------------------------------------------------------------------------
# TestComputedCap
# ---------------------------------------------------------------------------


class TestComputedCap:
    def test_steps_1_2_always_uncapped(self) -> None:
        cal = ConfidenceCalibrator()
        for step in _STEPS_1_2:
            # Mesmo sem bouguer/geochem_norm, passos 1 e 2 não são penalizados
            cap = cal._computed_cap(step, _geo_with(n_raw_records=20))
            assert cap == Confidence.HIGH, f"Step {step}: expected HIGH, got {cap}"

    def test_both_present_uncapped(self) -> None:
        cal = ConfidenceCalibrator()
        for step in _STEPS_3_5:
            cap = cal._computed_cap(step, _geo_with(bouguer=True, geochem_norm=True))
            assert cap == Confidence.HIGH

    def test_only_bouguer_caps_at_medium(self) -> None:
        cal = ConfidenceCalibrator()
        for step in _STEPS_3_5:
            cap = cal._computed_cap(step, _geo_with(bouguer=True, geochem_norm=False))
            assert cap == Confidence.MEDIUM

    def test_only_geochem_norm_caps_at_medium(self) -> None:
        cal = ConfidenceCalibrator()
        for step in _STEPS_3_5:
            cap = cal._computed_cap(step, _geo_with(bouguer=False, geochem_norm=True))
            assert cap == Confidence.MEDIUM

    def test_neither_present_caps_at_low(self) -> None:
        cal = ConfidenceCalibrator()
        for step in _STEPS_3_5:
            cap = cal._computed_cap(step, _geo_with(bouguer=False, geochem_norm=False))
            assert cap == Confidence.LOW


# ---------------------------------------------------------------------------
# TestVolumeCap
# ---------------------------------------------------------------------------


class TestVolumeCap:
    def test_high_records_uncapped(self) -> None:
        data = {"gravimetria": [{}] * _MIN_RECORDS_FOR_HIGH}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.HIGH

    def test_above_medium_threshold_caps_at_medium(self) -> None:
        # _MIN_RECORDS_FOR_MEDIUM ≤ n < _MIN_RECORDS_FOR_HIGH
        n = (_MIN_RECORDS_FOR_MEDIUM + _MIN_RECORDS_FOR_HIGH) // 2
        data = {"gravimetria": [{}] * n}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.MEDIUM

    def test_below_medium_threshold_caps_at_low(self) -> None:
        data = {"gravimetria": [{}] * (_MIN_RECORDS_FOR_MEDIUM - 1)}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.LOW

    def test_computed_keys_excluded_from_count(self) -> None:
        # 100 computed records + 2 raw → raw count = 2 < MIN_RECORDS_FOR_MEDIUM=3
        data = {
            "bouguer_gradient": [{}] * 100,
            "geoquimica_normalizada": [{}] * 100,
            "gravimetria": [{}] * 2,
        }
        cap = ConfidenceCalibrator._volume_cap(data)
        # Computed keys not counted; 2 raw < _MIN_RECORDS_FOR_MEDIUM → LOW
        assert cap == Confidence.LOW

    def test_zero_records_caps_at_low(self) -> None:
        data: dict = {}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.LOW

    def test_exactly_min_records_for_high(self) -> None:
        data = {"gravimetria": [{}] * _MIN_RECORDS_FOR_HIGH}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.HIGH

    def test_one_below_min_high_caps_at_medium(self) -> None:
        data = {"gravimetria": [{}] * (_MIN_RECORDS_FOR_HIGH - 1)}
        assert ConfidenceCalibrator._volume_cap(data) == Confidence.MEDIUM


# ---------------------------------------------------------------------------
# TestCalibrateNoChange
# ---------------------------------------------------------------------------


class TestCalibrateNoChange:
    """Casos em que a confiança NÃO deve ser alterada."""

    def test_insufficient_never_changed(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(n_raw_records=0)
        conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.INSUFFICIENT, data)
        assert conf == Confidence.INSUFFICIENT
        assert note is None

    def test_high_kept_when_all_computed_present_and_enough_data(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=True, geochem_norm=True, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        assert conf == Confidence.HIGH
        assert note is None

    def test_medium_kept_when_sufficient_data_steps_1_2(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(n_raw_records=_MIN_RECORDS_FOR_HIGH)
        for step in _STEPS_1_2:
            conf, note = cal.calibrate(step, Confidence.MEDIUM, data)
            assert conf == Confidence.MEDIUM
            assert note is None

    def test_low_never_downgraded(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(n_raw_records=0)
        conf, note = cal.calibrate(AnalysisStep.TOTAL_INTEGRATION, Confidence.LOW, data)
        assert conf == Confidence.LOW
        # LOW is the worst calibratable level; no downgrade below LOW
        assert note is None


# ---------------------------------------------------------------------------
# TestCalibrateDowngrade
# ---------------------------------------------------------------------------


class TestCalibrateDowngrade:
    """Casos em que a confiança DEVE ser rebaixada."""

    def test_high_downgraded_when_no_computed_data_step3(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        assert conf == Confidence.LOW
        assert note is not None
        assert "recalibrada" in note.lower()

    def test_high_downgraded_to_medium_with_only_bouguer(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=True, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.INDIRECT_EVIDENCE, Confidence.HIGH, data)
        assert conf == Confidence.MEDIUM
        assert note is not None

    def test_high_downgraded_to_medium_with_only_geochem_norm(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=True, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.TOTAL_INTEGRATION, Confidence.HIGH, data)
        assert conf == Confidence.MEDIUM
        assert note is not None

    def test_high_downgraded_by_volume_only(self) -> None:
        # bouguer + geochem_norm present (no computed cap) but few records
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=True, geochem_norm=True, n_raw_records=1)
        conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        # 1 record < MIN_RECORDS_FOR_MEDIUM → volume cap = LOW
        assert conf == Confidence.LOW
        assert note is not None
        assert "volume" in note.lower()

    def test_medium_downgraded_by_volume(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(n_raw_records=0)
        conf, note = cal.calibrate(AnalysisStep.TECTONIC_HISTORY, Confidence.MEDIUM, data)
        assert conf == Confidence.LOW
        assert note is not None

    def test_note_mentions_step_name(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        _conf, note = cal.calibrate(AnalysisStep.INDIRECT_EVIDENCE, Confidence.HIGH, data)
        assert note is not None
        assert "indirect_evidence" in note

    def test_note_mentions_missing_bouguer(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=True, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        _conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        assert note is not None
        assert "bouguer" in note.lower()

    def test_note_mentions_missing_geochem_norm(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=True, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        _conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        assert note is not None
        assert "geoquímica" in note.lower() or "normali" in note.lower()


# ---------------------------------------------------------------------------
# TestCalibrateSteps12NoComputedPenalty
# ---------------------------------------------------------------------------


class TestCalibrateSteps12:
    """Passos 1 e 2 não são penalizados pela ausência de dados computados."""

    def test_high_kept_without_computed_data_step1(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.TECTONIC_HISTORY, Confidence.HIGH, data)
        assert conf == Confidence.HIGH
        assert note is None

    def test_high_kept_without_computed_data_step2(self) -> None:
        cal = ConfidenceCalibrator()
        data = _geo_with(bouguer=False, geochem_norm=False, n_raw_records=_MIN_RECORDS_FOR_HIGH)
        conf, note = cal.calibrate(AnalysisStep.STRUCTURAL_ARCHITECTURE, Confidence.HIGH, data)
        assert conf == Confidence.HIGH
        assert note is None

    def test_high_still_penalized_by_volume_step1(self) -> None:
        cal = ConfidenceCalibrator()
        # No records → volume cap = LOW
        data: dict = {}
        conf, note = cal.calibrate(AnalysisStep.TECTONIC_HISTORY, Confidence.HIGH, data)
        assert conf == Confidence.LOW
        assert note is not None


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_geological_data(self) -> None:
        cal = ConfidenceCalibrator()
        conf, note = cal.calibrate(AnalysisStep.TOTAL_INTEGRATION, Confidence.HIGH, {})
        # No computed keys, no raw records → both caps = LOW
        assert conf == Confidence.LOW

    def test_only_computed_keys_present(self) -> None:
        cal = ConfidenceCalibrator()
        data = {
            "bouguer_gradient": [{"text": "x"}],
            "geoquimica_normalizada": [{"text": "y"}],
        }
        # No raw records → volume cap = LOW; computed cap = HIGH
        # → final cap = LOW
        conf, note = cal.calibrate(AnalysisStep.TOTAL_INTEGRATION, Confidence.HIGH, data)
        assert conf == Confidence.LOW
        assert note is not None

    def test_multiple_raw_sources_counted(self) -> None:
        cal = ConfidenceCalibrator()
        # Split records across multiple sources
        half = _MIN_RECORDS_FOR_HIGH // 2
        data = {
            "ocorrencias": [{}] * half,
            "gravimetria": [{}] * half,
            "bouguer_gradient": [{"text": "x"}],
            "geoquimica_normalizada": [{"text": "y"}],
        }
        conf, note = cal.calibrate(AnalysisStep.MAGMATIC_FERTILITY, Confidence.HIGH, data)
        assert conf == Confidence.HIGH
        assert note is None
