#!/usr/bin/env python
"""train_rf_seed.py — gera o modelo RF semente para prospectividade.

Treina um RandomForestClassifier em dados sintéticos projetados para
refletir padrões geológicos conhecidos, resultando num modelo base
que pode ser refinado com dados de campo reais.

Estratégia para dados sintéticos:
  - Positivos (mineralizado): alta densidade de ocorrências, CF elevado,
    gradientes Bouguer altos, anomalias espectrais de argila/Fe
  - Negativos: baixos indicadores com ruído realista

O modelo gerado é compatível com ProspectivityMLScorer e usa
FEATURE_NAMES para manter a ordem dos atributos.

Usage:
    python scripts/train_rf_seed.py [--output <path>]

Output padrão: src/miner_harness/ml/model/rf_prospectivity_v1.joblib
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Adicionar src/ ao path para importar FEATURE_NAMES
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split
import joblib

from miner_harness.ml.feature_builder import FEATURE_NAMES

# ---------------------------------------------------------------------------
# Configuração dos dados sintéticos
# ---------------------------------------------------------------------------
SEED = 42
N_POS = 1500   # amostras positivas (mineralizado)
N_NEG = 2500   # amostras negativas (não mineralizado)

# Índices das features (mesma ordem de FEATURE_NAMES)
IDX = {name: i for i, name in enumerate(FEATURE_NAMES)}


def _make_positive_samples(rng: np.random.Generator, n: int) -> np.ndarray:
    """Gera amostras de regiões mineralizadas.

    Padrões geológicos codificados:
    - Densidade de ocorrências acima de 0.005/km²
    - Pelo menos 2 elementos geoquímicos anômalos (CF > 2)
    - Gradiente horizontal moderado a alto (contato/falha)
    - Combinações de anomalias espectrais (argila OU ferro)
    """
    X = np.zeros((n, len(FEATURE_NAMES)))

    # Ocorrências: densidade alta
    X[:, IDX["occ_density_km2"]] = rng.lognormal(mean=-3.5, sigma=1.2, size=n).clip(0.002, 0.5)
    X[:, IDX["n_distinct_substances"]] = rng.integers(1, 8, size=n).astype(float)

    # Geoquímica: CF elevado com ruído
    X[:, IDX["geochem_mean_cf"]] = rng.lognormal(mean=0.8, sigma=0.6, size=n).clip(0.5, 15.0)
    X[:, IDX["geochem_max_cf"]] = (
        X[:, IDX["geochem_mean_cf"]] * rng.uniform(1.2, 4.0, size=n)
    )
    X[:, IDX["geochem_n_anomalies"]] = rng.integers(1, 8, size=n).astype(float)
    X[:, IDX["n_geochem_samples"]] = rng.integers(10, 200, size=n).astype(float)

    # Gravimetria: gradientes moderados a altos
    X[:, IDX["bouguer_mean_gradient"]] = rng.lognormal(
        mean=0.5, sigma=0.7, size=n
    ).clip(0.1, 10.0)
    X[:, IDX["bouguer_std_gradient"]] = (
        X[:, IDX["bouguer_mean_gradient"]] * rng.uniform(0.2, 0.8, size=n)
    )
    X[:, IDX["bouguer_max_gradient"]] = (
        X[:, IDX["bouguer_mean_gradient"]] * rng.uniform(1.5, 3.0, size=n)
    )
    X[:, IDX["n_gravity_stations"]] = rng.integers(20, 500, size=n).astype(float)

    # Sentinel-2: anomalias de argila e ferro (alteração hidrotermal)
    has_s2 = rng.random(size=n) > 0.35  # 65% têm dados S2
    X[:, IDX["s2_clay_anom_pct"]] = np.where(
        has_s2, rng.uniform(10.0, 60.0, size=n), rng.uniform(0.0, 5.0, size=n)
    )
    X[:, IDX["s2_iron_anom_pct"]] = np.where(
        has_s2, rng.uniform(5.0, 50.0, size=n), rng.uniform(0.0, 5.0, size=n)
    )
    X[:, IDX["s2_ndvi_anom_pct"]] = np.where(
        has_s2, rng.uniform(20.0, 70.0, size=n), rng.uniform(0.0, 10.0, size=n)
    )
    X[:, IDX["s2_bsi_anom_pct"]] = np.where(
        has_s2, rng.uniform(15.0, 55.0, size=n), rng.uniform(0.0, 8.0, size=n)
    )

    X[:, IDX["bbox_area_km2"]] = rng.lognormal(mean=9.5, sigma=1.0, size=n).clip(
        500, 100_000
    )
    return X


def _make_negative_samples(rng: np.random.Generator, n: int) -> np.ndarray:
    """Gera amostras de regiões não mineralizadas."""
    X = np.zeros((n, len(FEATURE_NAMES)))

    X[:, IDX["occ_density_km2"]] = rng.exponential(scale=0.0005, size=n).clip(0, 0.005)
    X[:, IDX["n_distinct_substances"]] = rng.integers(0, 3, size=n).astype(float)

    X[:, IDX["geochem_mean_cf"]] = rng.lognormal(mean=-0.2, sigma=0.4, size=n).clip(0.2, 3.0)
    X[:, IDX["geochem_max_cf"]] = (
        X[:, IDX["geochem_mean_cf"]] * rng.uniform(1.0, 2.0, size=n)
    )
    X[:, IDX["geochem_n_anomalies"]] = rng.integers(0, 2, size=n).astype(float)
    X[:, IDX["n_geochem_samples"]] = rng.integers(0, 50, size=n).astype(float)

    X[:, IDX["bouguer_mean_gradient"]] = rng.lognormal(
        mean=-1.0, sigma=0.8, size=n
    ).clip(0.0, 3.0)
    X[:, IDX["bouguer_std_gradient"]] = (
        X[:, IDX["bouguer_mean_gradient"]] * rng.uniform(0.1, 0.5, size=n)
    )
    X[:, IDX["bouguer_max_gradient"]] = (
        X[:, IDX["bouguer_mean_gradient"]] * rng.uniform(1.0, 2.0, size=n)
    )
    X[:, IDX["n_gravity_stations"]] = rng.integers(0, 200, size=n).astype(float)

    has_s2 = rng.random(size=n) > 0.60
    for idx_name in (
        "s2_ndvi_anom_pct",
        "s2_bsi_anom_pct",
        "s2_clay_anom_pct",
        "s2_iron_anom_pct",
    ):
        X[:, IDX[idx_name]] = np.where(
            has_s2, rng.uniform(0.0, 15.0, size=n), rng.uniform(0.0, 3.0, size=n)
        )

    X[:, IDX["bbox_area_km2"]] = rng.lognormal(mean=9.5, sigma=1.0, size=n).clip(
        500, 100_000
    )
    return X


def main(output: Path) -> None:
    rng = np.random.default_rng(SEED)

    print(f"Gerando dados sintéticos: {N_POS} positivos, {N_NEG} negativos...")
    X_pos = _make_positive_samples(rng, N_POS)
    X_neg = _make_negative_samples(rng, N_NEG)

    X = np.vstack([X_pos, X_neg])
    y = np.array([1] * N_POS + [0] * N_NEG)

    idx = rng.permutation(len(y))
    X, y = X[idx], y[idx]

    print("Treinando RandomForestClassifier...")
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=10,
        max_features="sqrt",
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
    )

    scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")
    print(f"CV ROC-AUC: {scores.mean():.3f} ± {scores.std():.3f}")

    model.fit(X, y)
    model.feature_names_in_ = np.array(FEATURE_NAMES)

    # Avaliação em test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    model_eval = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=10,
        max_features="sqrt",
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
    )
    model_eval.fit(X_train, y_train)
    y_prob = model_eval.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    print(f"Test ROC-AUC: {auc:.3f}")
    print(classification_report(y_test, model_eval.predict(X_test)))

    importances = sorted(
        zip(FEATURE_NAMES, model.feature_importances_),
        key=lambda x: -x[1],
    )
    print("\nTop-10 feature importances (modelo final):")
    for name, imp in importances[:10]:
        bar = "#" * int(imp * 100)
        print(f"  {name:<30} {imp:.4f} {bar}")

    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output, compress=3)
    size_kb = output.stat().st_size / 1024
    print(f"\nModelo salvo em: {output} ({size_kb:.0f} KB)")
    print("OK Modelo semente gerado com sucesso.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Treina modelo RF semente")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent
        / "src/miner_harness/ml/model/rf_prospectivity_v1.joblib",
        help="Caminho de saída do modelo",
    )
    args = parser.parse_args()
    main(args.output)
