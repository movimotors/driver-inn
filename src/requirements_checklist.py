"""Checklist de requisitos por cuenta (jsonb en accounts.requirements_checklist)."""

from __future__ import annotations

from src.constants import (
    REQUIREMENTS_BASE,
    REQUIREMENTS_BY_MODALITY,
    REQUIREMENTS_BY_PLATFORM_CODE,
)


def checklist_template(platform_code: str | None, modality: str | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    out.extend(REQUIREMENTS_BASE)
    if modality and modality in REQUIREMENTS_BY_MODALITY:
        out.extend(REQUIREMENTS_BY_MODALITY[modality])
    if platform_code and platform_code in REQUIREMENTS_BY_PLATFORM_CODE:
        out.extend(REQUIREMENTS_BY_PLATFORM_CODE[platform_code])
    # dedupe keep order
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for k, lbl in out:
        if k in seen:
            continue
        seen.add(k)
        deduped.append((k, lbl))
    return deduped


def merge_checklist(existing: dict | None, template: list[tuple[str, str]]) -> dict[str, bool]:
    """Preserva checks existentes y añade faltantes."""
    ex = dict(existing or {})
    for key, _ in template:
        if key not in ex:
            ex[key] = False
    # normalizar a bool
    return {k: bool(v) for k, v in ex.items()}

