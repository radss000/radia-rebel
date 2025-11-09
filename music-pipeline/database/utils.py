"""Shared database configuration/helpers."""

from __future__ import annotations

import os
from typing import Dict

import psycopg2

DB_CONFIG: Dict[str, object] = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "rebel_music"),
    "user": os.getenv("POSTGRES_USER", "rebel"),
    "password": os.getenv("POSTGRES_PASSWORD", "rebel_password"),
}


def get_db_connection():
    """Create a new psycopg2 connection using shared config."""
    return psycopg2.connect(**DB_CONFIG)
