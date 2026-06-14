"""
backend/session_store.py
In-memory session store untuk DAAT.
Menyimpan hasil analisis per session sehingga follow-up chat bisa re-use.

Batas: 10 session aktif, TTL 2 jam.
"""

import hashlib
import time
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Session store (in-memory) ─────────────────────────────────────────────────

MAX_SESSIONS = 10
SESSION_TTL  = 7200   # 2 jam dalam detik

_store: dict[str, "SessionData"] = {}   # session_id → SessionData


class SessionData:
    def __init__(
        self,
        session_id: str,
        dataframe: pd.DataFrame,
        column_profile: dict,
        stats_result: dict,
        cleaning_report: dict,
        chart_keys: list[str],
        file_name: str,
        domain: str = "unknown",
    ):
        self.session_id      = session_id
        self.dataframe       = dataframe
        self.column_profile  = column_profile
        self.stats_result    = stats_result
        self.cleaning_report = cleaning_report
        self.chart_keys      = chart_keys
        self.file_name       = file_name
        self.domain          = domain
        self.created_at      = time.time()
        self.last_accessed   = time.time()

    def touch(self):
        self.last_accessed = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > SESSION_TTL


def _evict_if_needed():
    """Hapus session expired atau tertua jika sudah penuh."""
    global _store
    # Hapus expired
    expired = [sid for sid, s in _store.items() if s.is_expired()]
    for sid in expired:
        del _store[sid]
        logger.info(f"[session] Evicted expired session: {sid}")
    # Hapus tertua kalau masih penuh
    while len(_store) >= MAX_SESSIONS:
        oldest = min(_store.items(), key=lambda x: x[1].last_accessed)
        del _store[oldest[0]]
        logger.info(f"[session] Evicted oldest session: {oldest[0]}")


def make_session_id(file_name: str, file_size: int) -> str:
    """Buat session ID dari nama + ukuran file."""
    raw = f"{file_name}:{file_size}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def save_session(data: "SessionData"):
    _evict_if_needed()
    _store[data.session_id] = data
    logger.info(f"[session] Saved: {data.session_id} ({data.file_name})")


def get_session(session_id: str) -> "SessionData | None":
    s = _store.get(session_id)
    if s is None:
        return None
    if s.is_expired():
        del _store[session_id]
        logger.info(f"[session] Expired on access: {session_id}")
        return None
    s.touch()
    logger.debug(f"[session] TTL refreshed to +{SESSION_TTL}s: {session_id}")
    return s


def list_sessions() -> list[dict]:
    return [
        {
            "session_id":  s.session_id,
            "file_name":   s.file_name,
            "rows":        len(s.dataframe),
            "domain":      s.domain,
            "chart_keys":  s.chart_keys,
            "age_minutes": round((time.time() - s.created_at) / 60, 1),
        }
        for s in _store.values()
        if not s.is_expired()
    ]
