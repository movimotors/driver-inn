"""Llamadas HTTP a Supabase Auth (sin SDK supabase-py)."""

from typing import Any

import httpx

from src.config import get_supabase_config


class AuthError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _auth_headers() -> dict[str, str]:
    url, key = get_supabase_config()
    if not url or not key:
        raise AuthError("Falta configuración de Supabase.")
    return {
        "apikey": key,
        "Content-Type": "application/json",
    }


def sign_in_with_password(email: str, password: str) -> dict[str, Any]:
    url, anon = get_supabase_config()
    endpoint = f"{url.rstrip('/')}/auth/v1/token?grant_type=password"
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            endpoint,
            headers=_auth_headers(),
            json={"email": email.strip(), "password": password},
        )
    if r.status_code != 200:
        try:
            detail = r.json().get("error_description") or r.json().get("msg") or r.text
        except Exception:
            detail = r.text
        raise AuthError(str(detail) or "Credenciales inválidas.", r.status_code)
    return r.json()


def sign_up(email: str, password: str, full_name: str | None = None) -> dict[str, Any]:
    """Registro vía Supabase Auth (el trigger crea la fila en public.profiles)."""
    url, _ = get_supabase_config()
    endpoint = f"{url.rstrip('/')}/auth/v1/signup"
    body: dict[str, Any] = {"email": email.strip(), "password": password}
    if full_name:
        body["data"] = {"full_name": full_name}
    with httpx.Client(timeout=30.0) as client:
        r = client.post(endpoint, headers=_auth_headers(), json=body)
    if r.status_code not in (200, 201):
        try:
            j = r.json()
            detail = j.get("error_description") or j.get("msg") or j.get("message") or r.text
        except Exception:
            detail = r.text
        raise AuthError(str(detail) or "No se pudo registrar.", r.status_code)
    return r.json()


def request_password_recovery(email: str, redirect_to: str | None = None) -> None:
    url, _ = get_supabase_config()
    endpoint = f"{url.rstrip('/')}/auth/v1/recover"
    body: dict[str, Any] = {"email": email.strip()}
    if redirect_to:
        body["redirect_to"] = redirect_to
    with httpx.Client(timeout=30.0) as client:
        r = client.post(endpoint, headers=_auth_headers(), json=body)
    if r.status_code not in (200, 204):
        try:
            detail = r.json().get("error_description") or r.json().get("msg") or r.text
        except Exception:
            detail = r.text
        raise AuthError(str(detail) or "No se pudo enviar el correo.", r.status_code)
