"""
Cliente ligero para PostgREST de Supabase (sin SDK supabase-py).
Evita dependencias pesadas (p. ej. pyiceberg) en Windows/Python recientes.
"""

from functools import lru_cache
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx


def _fmt_filter_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

from src.config import get_supabase_config


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


class _Query:
    def __init__(self, base: str, table: str, key: str, op: str):
        self._base = base
        self._table = table
        self._key = key
        self._op = op
        self._select = "*"
        self._filters: list[tuple[str, str, str]] = []
        self._order: tuple[str, bool] | None = None
        self._body: Any = None

    def select(self, cols: str = "*") -> "_Query":
        self._select = cols
        return self

    def insert(self, row_or_rows: Any) -> "_Query":
        self._op = "insert"
        self._body = row_or_rows
        return self

    def update(self, data: dict) -> "_Query":
        self._op = "update"
        self._body = data
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append((column, "eq", _fmt_filter_value(value)))
        return self

    def order(self, column: str, desc: bool = False) -> "_Query":
        self._order = (column, desc)
        return self

    def execute(self) -> SimpleNamespace:
        url = f"{self._base}/{quote(self._table)}"
        params: list[tuple[str, str]] = []
        for col, op, val in self._filters:
            params.append((col, f"{op}.{val}"))
        if self._op == "select":
            params.append(("select", self._select))
            if self._order:
                col, desc = self._order
                params.append(("order", f"{col}.{'desc' if desc else 'asc'}"))
            with httpx.Client(timeout=30.0) as client:
                r = client.get(url, headers=_headers(self._key), params=params)
            r.raise_for_status()
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        if self._op == "insert":
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, headers=_headers(self._key), json=self._body)
            r.raise_for_status()
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        if self._op == "update":
            with httpx.Client(timeout=30.0) as client:
                r = client.patch(url, headers=_headers(self._key), params=params, json=self._body)
            r.raise_for_status()
            txt = r.text
            if not txt or txt == "null":
                return SimpleNamespace(data=[])
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        raise RuntimeError(f"Operación no soportada: {self._op}")


class _Client:
    def __init__(self, base: str, key: str):
        self._base = base.rstrip("/")
        self._key = key

    def table(self, name: str) -> _Query:
        return _Query(self._base, name, self._key, "select")


@lru_cache(maxsize=1)
def get_client() -> _Client:
    url, key = get_supabase_config()
    if not url or not key:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY en el entorno.")
    base = url.rstrip("/") + "/rest/v1"
    return _Client(base, key)


def clear_client_cache():
    get_client.cache_clear()
