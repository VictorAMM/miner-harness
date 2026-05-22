"""DrillholeParser — importação de furos de sondagem do usuário a partir de CSV.

Lê arquivos CSV com dados de furos (collar + trecho + litologia + teores)
e normaliza os nomes de colunas usando aliases comuns (en/pt-BR/acrônimos).

Formato de saída: lista de dicts com chaves padronizadas:
  hole_id, x, y, z, from_m, to_m, lithology, alteration
  + quaisquer colunas adicionais (teores analíticos) como campos extras.

Ref: PRD-002 F7
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Aliases de colunas (lowercase) → nome canônico
# ---------------------------------------------------------------------------

_COL_ALIASES: dict[str, str] = {
    # identificador do furo
    "hole_id": "hole_id",
    "holeid": "hole_id",
    "bhid": "hole_id",
    "hole": "hole_id",
    "sondagem": "hole_id",
    "furo": "hole_id",
    "furoid": "hole_id",
    "dhid": "hole_id",
    # coordenada X (longitude ou easting)
    "x": "x",
    "lon": "x",
    "longitude": "x",
    "easting": "x",
    "este": "x",
    "long": "x",
    "xcoord": "x",
    # coordenada Y (latitude ou northing)
    "y": "y",
    "lat": "y",
    "latitude": "y",
    "northing": "y",
    "norte": "y",
    "ycoord": "y",
    # coordenada Z (elevação ou cota do collar)
    "z": "z",
    "elev": "z",
    "elevation": "z",
    "elevacao": "z",
    "elevação": "z",
    "rl": "z",
    "collar_z": "z",
    "zcoord": "z",
    # de (início do trecho)
    "from": "from_m",
    "from_m": "from_m",
    "de": "from_m",
    "de_m": "from_m",
    "inicio": "from_m",
    "início": "from_m",
    "top": "from_m",
    "topo": "from_m",
    "depth_from": "from_m",
    # a (fim do trecho)
    "to": "to_m",
    "to_m": "to_m",
    "ate": "to_m",
    "até": "to_m",
    "ate_m": "to_m",
    "fim": "to_m",
    "bottom": "to_m",
    "base": "to_m",
    "depth_to": "to_m",
    # litologia
    "lithology": "lithology",
    "lito": "lithology",
    "litologia": "lithology",
    "rock": "lithology",
    "litho": "lithology",
    "rock_type": "lithology",
    "rock_code": "lithology",
    "tipo_rocha": "lithology",
    "rockcode": "lithology",
    # alteração
    "alteration": "alteration",
    "alt": "alteration",
    "alteracao": "alteration",
    "alteração": "alteration",
    "alt_code": "alteration",
    "altcode": "alteration",
}

# Chaves canônicas numéricas (float)
_NUMERIC_KEYS: frozenset[str] = frozenset({"x", "y", "z", "from_m", "to_m"})

# Chaves canônicas de texto
_TEXT_KEYS: frozenset[str] = frozenset({"hole_id", "lithology", "alteration"})

# Limites para o prompt
_MAX_RECORDS_PROMPT: int = 200
_MAX_CHARS_PROMPT: int = 12_000


def _to_float(value: str) -> float | None:
    """Converte string para float; retorna None se inválido."""
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


class DrillholeParser:
    """Lê e normaliza furos de sondagem a partir de CSV.

    Suporta colunas em inglês, português e acrônimos de campo.
    Colunas não reconhecidas são tratadas como teores analíticos.

    Usage:
        records = DrillholeParser.parse("meus_furos.csv")
        text = DrillholeParser.format_for_prompt(records)
        geojson = DrillholeParser.to_geojson(records)
    """

    @staticmethod
    def parse(csv_path: Path | str) -> list[dict[str, Any]]:
        """Lê CSV de furos e retorna lista de dicts normalizados.

        Args:
            csv_path: Caminho para o arquivo CSV (UTF-8 ou UTF-8-BOM).

        Returns:
            Lista de dicts com chaves padronizadas.

        Raises:
            FileNotFoundError: Se o arquivo não existir.
            ValueError: Se o CSV não contiver coluna de identificação do furo.
        """
        path = Path(csv_path)
        if not path.exists():
            msg = f"Arquivo não encontrado: {path}"
            raise FileNotFoundError(msg)

        records: list[dict[str, Any]] = []

        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return records

            # Mapear colunas originais → canônicas
            col_map: dict[str, str] = {}
            for orig in reader.fieldnames:
                canonical = _COL_ALIASES.get(orig.strip().lower())
                if canonical:
                    col_map[orig] = canonical

            if not any(v == "hole_id" for v in col_map.values()):
                known = list(_COL_ALIASES)[:8]
                msg = f"CSV não contém coluna de identificação do furo. Esperado um de: {known}…"
                raise ValueError(msg)

            # Colunas extras (analíticas) = não mapeadas para canônico
            extra_cols = [c for c in reader.fieldnames if c not in col_map]

            for row in reader:
                rec: dict[str, Any] = {}

                # Colunas mapeadas (canônicas)
                for orig, canonical in col_map.items():
                    raw = (row.get(orig) or "").strip()
                    if canonical in _NUMERIC_KEYS:
                        rec[canonical] = _to_float(raw)
                    else:
                        rec[canonical] = raw

                # Defaults para chaves ausentes
                for key in _TEXT_KEYS:
                    if key not in rec:
                        rec[key] = ""
                for key in _NUMERIC_KEYS:
                    if key not in rec:
                        rec[key] = None

                # Colunas extras (teores analíticos) — chave em lowercase
                for col in extra_cols:
                    raw = (row.get(col) or "").strip()
                    rec[col.lower()] = _to_float(raw) if raw else None

                records.append(rec)

        return records

    @staticmethod
    def format_for_prompt(
        records: list[dict[str, Any]],
        max_records: int = _MAX_RECORDS_PROMPT,
        max_chars: int = _MAX_CHARS_PROMPT,
    ) -> str:
        """Formata furos para injeção no prompt do LLM.

        Args:
            records: Lista de furos normalizados.
            max_records: Máximo de registros a incluir.
            max_chars: Limite total de caracteres.

        Returns:
            Bloco de texto formatado.
        """
        if not records:
            return "Nenhum furo de sondagem disponível."

        lines: list[str] = [
            f"FUROS DE SONDAGEM DO USUÁRIO — {len(records)} trechos",
            "=" * 52,
        ]
        chars = sum(len(ln) + 1 for ln in lines)
        included = 0

        for i, r in enumerate(records[:max_records]):
            parts: list[str] = []

            if r.get("hole_id"):
                parts.append(f"Furo: {r['hole_id']}")

            coord_parts: list[str] = []
            if r.get("x") is not None:
                coord_parts.append(f"X={r['x']:.5f}")
            if r.get("y") is not None:
                coord_parts.append(f"Y={r['y']:.5f}")
            if r.get("z") is not None:
                coord_parts.append(f"Z={r['z']:.1f}m")
            if coord_parts:
                parts.append("Coord: (" + ", ".join(coord_parts) + ")")

            depth_parts: list[str] = []
            if r.get("from_m") is not None:
                depth_parts.append(f"{r['from_m']:.1f}")
            if r.get("to_m") is not None:
                depth_parts.append(f"{r['to_m']:.1f}m")
            if depth_parts:
                parts.append("Trecho: " + "–".join(depth_parts))

            if r.get("lithology"):
                parts.append(f"Lito: {r['lithology']}")
            if r.get("alteration"):
                parts.append(f"Alt: {r['alteration']}")

            # Teores analíticos extras
            extras = [
                f"{k.upper()}={v:.3g}"
                for k, v in r.items()
                if k
                not in {
                    "hole_id",
                    "x",
                    "y",
                    "z",
                    "from_m",
                    "to_m",
                    "lithology",
                    "alteration",
                }
                and isinstance(v, float)
                and not math.isnan(v)
            ]
            if extras:
                parts.append(" ".join(extras))

            line = " | ".join(parts)
            if chars + len(line) + 1 > max_chars:
                lines.append(f"... {len(records) - i} trechos omitidos por limite de tamanho")
                break
            lines.append(line)
            chars += len(line) + 1
            included += 1

        omitted = len(records) - included
        if omitted > 0 and not lines[-1].startswith("..."):
            lines.append(f"... {omitted} trechos omitidos (limite de {max_records} registros)")

        return "\n".join(lines)

    @staticmethod
    def to_geojson(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Converte furos (posições collar) para GeoJSON FeatureCollection.

        Inclui apenas furos com coordenadas x/y válidas.
        Para múltiplos trechos do mesmo furo, mantém apenas o collar
        (primeiro registro com coordenadas válidas por hole_id).

        Args:
            records: Lista de furos normalizados.

        Returns:
            GeoJSON FeatureCollection com pontos de collar.
        """
        features: list[dict[str, Any]] = []
        seen_holes: set[str] = set()

        for r in records:
            x, y = r.get("x"), r.get("y")
            if x is None or y is None:
                continue
            if isinstance(x, float) and math.isnan(x):
                continue
            if isinstance(y, float) and math.isnan(y):
                continue

            hole_id = r.get("hole_id") or ""
            if hole_id and hole_id in seen_holes:
                continue
            if hole_id:
                seen_holes.add(hole_id)

            props: dict[str, Any] = {
                "hole_id": hole_id,
                "from_m": r.get("from_m"),
                "to_m": r.get("to_m"),
                "lithology": r.get("lithology") or "",
                "alteration": r.get("alteration") or "",
            }
            # Teores analíticos como propriedades adicionais
            for k, v in r.items():
                if (
                    k
                    not in {
                        "hole_id",
                        "x",
                        "y",
                        "z",
                        "from_m",
                        "to_m",
                        "lithology",
                        "alteration",
                    }
                    and isinstance(v, float)
                    and not math.isnan(v)
                ):
                    props[k] = v

            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [x, y]},
                    "properties": props,
                }
            )

        return {"type": "FeatureCollection", "features": features}
