import os

from dotenv import load_dotenv

load_dotenv()


def get_supabase_config():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    return url, key


def supabase_configured() -> bool:
    url, key = get_supabase_config()
    return bool(url and key)
