import os

from dotenv import load_dotenv

load_dotenv()


def get_supabase_config():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            sec = st.secrets
            if sec.get("SUPABASE_URL"):
                url = str(sec["SUPABASE_URL"]).strip()
            if sec.get("SUPABASE_KEY"):
                key = str(sec["SUPABASE_KEY"]).strip()
    except Exception:
        pass
    return url, key


def supabase_configured() -> bool:
    url, key = get_supabase_config()
    return bool(url and key)


def get_auth_redirect_url() -> str | None:
    """URL pública de la app para enlaces de correo (confirmar cuenta, recuperar contraseña).

    Orden: Secrets AUTH_REDIRECT_URL → PASSWORD_RESET_REDIRECT_URL → variables de entorno.
    Debe coincidir con una entrada en Supabase → Authentication → URL configuration → Redirect URLs.
    """
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            sec = st.secrets
            for key in ("AUTH_REDIRECT_URL", "PASSWORD_RESET_REDIRECT_URL"):
                if sec.get(key):
                    u = str(sec[key]).strip()
                    if u:
                        return u.rstrip("/")
    except Exception:
        pass
    for env_key in ("AUTH_REDIRECT_URL", "PASSWORD_RESET_REDIRECT_URL"):
        u = os.getenv(env_key, "").strip()
        if u:
            return u.rstrip("/")
    return None
