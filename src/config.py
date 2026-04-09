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
