"""Sanitização de dados do GeoSGB para uso seguro em prompts LLM.

Remove caracteres de controle, trunca textos longos e escapa
delimitadores XML/HTML para prevenir prompt injection.

Ref: RFC-001 §6 (Sanitização de dados para LLM)
"""

from __future__ import annotations

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_XML_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&apos;",
}


def sanitize_for_llm(text: str | None, max_length: int = 500) -> str:
    """Sanitiza texto do GeoSGB para inclusão segura em prompts.

    1. Remove caracteres de controle
    2. Trunca a max_length
    3. Escapa delimitadores XML/HTML

    Args:
        text: Texto bruto da API. None retorna string vazia.
        max_length: Comprimento máximo após sanitização.

    Returns:
        Texto sanitizado e seguro para inclusão em prompts.
    """
    if text is None:
        return ""

    # 1. Remove control chars (mantém newline \n e tab \t)
    cleaned = _CONTROL_CHARS.sub("", text)

    # 2. Trunca
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "..."

    # 3. Escapa XML/HTML delimiters
    for char, escape in _XML_ESCAPES.items():
        cleaned = cleaned.replace(char, escape)

    return cleaned


def sanitize_record(record: dict[str, object], max_length: int = 500) -> dict[str, object]:
    """Sanitiza todos os campos string de um registro.

    Campos não-string são preservados sem alteração.

    Args:
        record: Dicionário com valores do GeoSGB.
        max_length: Comprimento máximo por campo.

    Returns:
        Registro com strings sanitizadas.
    """
    result: dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, str):
            result[key] = sanitize_for_llm(value, max_length)
        else:
            result[key] = value
    return result
