"""
database.py — Gestion de la connexion à la base de données
Supporte PostgreSQL local et Supabase (même driver psycopg2, URL différente).

Pour basculer entre les deux environnements, il suffit de changer
USE_SUPABASE dans le fichier .env :
  USE_SUPABASE=false  →  PostgreSQL local
  USE_SUPABASE=true   →  Supabase (PostgreSQL managé)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

# ==============================================================
# FLAG DE BASCULEMENT PRINCIPAL
# ==============================================================
USE_SUPABASE: bool = os.getenv("USE_SUPABASE", "false").lower() == "true"

# ==============================================================
# CONFIGURATION SELON L'ENVIRONNEMENT
# ==============================================================

if USE_SUPABASE:
    # Supabase : une seule URL de connexion (format libpq)
    # Récupérée dans : Dashboard Supabase > Settings > Database > Connection string
    _SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    if not _SUPABASE_DB_URL:
        raise RuntimeError(
            "USE_SUPABASE=true mais SUPABASE_DB_URL est absent du fichier .env\n"
            "Récupérez l'URL dans : Supabase Dashboard > Settings > Database"
        )
    DB_DSN = _SUPABASE_DB_URL          # ex: postgresql://postgres.[ref]:[pwd]@host:6543/postgres
    DB_KWARGS: dict = {}               # tout est dans l'URL
else:
    # PostgreSQL local : paramètres classiques
    DB_DSN = None
    DB_KWARGS = {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     os.getenv("DB_PORT", "5432"),
        "database": os.getenv("DB_NAME", "recettes_db"),
        "user":     os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

# ==============================================================
# URL DU SERVEUR VIDÉO (utilisée par les routes API pour renvoyer les URLs)
# ==============================================================

VIDEO_BASE_URL: str = (
    os.getenv("SUPABASE_STORAGE_URL", "")
    if USE_SUPABASE
    else os.getenv("LOCAL_VIDEO_URL", "http://localhost:8081/videos")
)

# ==============================================================
# FONCTIONS PUBLIQUES
# ==============================================================

def get_db_connection():
    """
    Retourne une connexion psycopg2 selon l'environnement actif.
    Toujours utiliser dans un bloc try/finally et appeler conn.close().

    Usage :
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            ...
        finally:
            conn.close()
    """
    try:
        if USE_SUPABASE:
            conn = psycopg2.connect(DB_DSN, cursor_factory=RealDictCursor)
        else:
            conn = psycopg2.connect(**DB_KWARGS, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        env_label = "Supabase" if USE_SUPABASE else "PostgreSQL local"
        print(f"[DB] Erreur de connexion ({env_label}): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur de connexion à la base de données ({env_label})"
        )


def get_current_env() -> dict:
    """Retourne un dict décrivant l'environnement actif (utile pour debug/healthcheck)."""
    return {
        "environment": "supabase" if USE_SUPABASE else "local",
        "video_base_url": VIDEO_BASE_URL,
    }