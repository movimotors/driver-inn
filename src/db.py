"""
Cliente ligero para PostgREST de Supabase (sin SDK supabase-py).
Con `access_token` del usuario, RLS aplica según auth.uid().
"""

from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx

from src.config import get_supabase_config


def _fmt_filter_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _headers(anon_key: str, bearer: str) -> dict[str, str]:
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


class _Query:
    def __init__(self, base: str, table: str, anon_key: str, bearer: str, op: str):
        self._base = base
        self._table = table
        self._anon = anon_key
        self._bearer = bearer
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

    def delete(self) -> "_Query":
        self._op = "delete"
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
        hdrs = _headers(self._anon, self._bearer)
        if self._op == "select":
            params.append(("select", self._select))
            if self._order:
                col, desc = self._order
                params.append(("order", f"{col}.{'desc' if desc else 'asc'}"))
            with httpx.Client(timeout=30.0) as client:
                r = client.get(url, headers=hdrs, params=params)
            r.raise_for_status()
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        if self._op == "insert":
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, headers=hdrs, json=self._body)
            r.raise_for_status()
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        if self._op == "update":
            with httpx.Client(timeout=30.0) as client:
                r = client.patch(url, headers=hdrs, params=params, json=self._body)
            r.raise_for_status()
            txt = r.text
            if not txt or txt == "null":
                return SimpleNamespace(data=[])
            data = r.json()
            return SimpleNamespace(data=data if isinstance(data, list) else [data])
        if self._op == "delete":
            with httpx.Client(timeout=30.0) as client:
                r = client.delete(url, headers=hdrs, params=params)
            r.raise_for_status()
            return SimpleNamespace(data=[])
        raise RuntimeError(f"Operación no soportada: {self._op}")


class _Client:
    def __init__(self, base: str, anon_key: str, bearer: str):
        self._base = base.rstrip("/")
        self._anon = anon_key
        self._bearer = bearer

    def table(self, name: str) -> _Query:
        return _Query(self._base, name, self._anon, self._bearer, "select")


def get_client(access_token: str | None = None) -> _Client:
    """
    Si `access_token` es el JWT del usuario, las políticas RLS usan auth.uid().
    Si es None, se usa la anon key como Bearer (solo sirve si las políticas lo permiten; en producción no debería).
    """
    url, anon = get_supabase_config()
    if not url or not anon:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY en el entorno.")
    base = url.rstrip("/") + "/rest/v1"
    bearer = access_token if access_token else anon
    return _Client(base, anon, bearer)


def clear_client_cache():
    pass


_ACCOUNTS_LIST_COLS_V2 = (
    "id, client_id, platform_id, technician_id, sale_type, status, service_modality, requirements_notes, "
    "assigned_at, delivered_at, rental_weekly_amount, rental_next_due_date, external_ref, created_at"
)
_ACCOUNTS_LIST_COLS_V1 = (
    "id, client_id, platform_id, technician_id, sale_type, status, requirements_notes, "
    "assigned_at, delivered_at, rental_weekly_amount, rental_next_due_date, external_ref, created_at"
)

_ACCOUNTS_DASH_COLS_V2 = (
    "id, status, sale_type, service_modality, delivered_at, rental_next_due_date, rental_weekly_amount, "
    "platform_id, client_id, technician_id"
)
_ACCOUNTS_DASH_COLS_V1 = (
    "id, status, sale_type, delivered_at, rental_next_due_date, rental_weekly_amount, "
    "platform_id, client_id, technician_id"
)


def fetch_accounts_list_with_modality_fallback(client: _Client) -> tuple[list[dict], bool]:
    """Devuelve (filas, True) si existe `service_modality`; si PostgREST 400, reintenta sin la columna."""
    try:
        r = (
            client.table("accounts")
            .select(_ACCOUNTS_LIST_COLS_V2)
            .order("created_at", desc=True)
            .execute()
        )
        return (r.data or [], True)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            r = (
                client.table("accounts")
                .select(_ACCOUNTS_LIST_COLS_V1)
                .order("created_at", desc=True)
                .execute()
            )
            rows = r.data or []
            for row in rows:
                row.setdefault("service_modality", "cuenta_nombre_tercero")
            return (rows, False)
        raise


def fetch_accounts_dashboard_with_modality_fallback(client: _Client) -> tuple[list[dict], bool]:
    try:
        r = client.table("accounts").select(_ACCOUNTS_DASH_COLS_V2).execute()
        return (r.data or [], True)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            r = client.table("accounts").select(_ACCOUNTS_DASH_COLS_V1).execute()
            rows = r.data or []
            for row in rows:
                row.setdefault("service_modality", "cuenta_nombre_tercero")
            return (rows, False)
        raise
