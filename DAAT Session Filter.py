"""
title: DAAT Session Filter
author: Sulthan & Hanan (TA Teknik Telekomunikasi ITB)
version: 1.4.0
required_open_webui_version: 0.9.0
description: >
  Filter Function untuk DAAT. inlet() berjalan SEKALI per pesan user
  (sebelum LLM memutuskan tool call), jadi ini satu-satunya tempat yang
  benar untuk menyuntik marker sesi. Filter ini, SALING EKSKLUSIF:
    - session aktif terdeteksi di history → inject [ACTIVE SESSION=xxx] (follow-up)
    - else, file CSV/Excel terlampir      → inject [FILE TERLAMPIR: ...] (analisis baru)
  Sumber kebenaran session_id tetap backend (/analyze membuatnya,
  /analyze/followup mengkonsumsinya). Filter hanya memindahkan marker
  yang sudah ada di history ke pesan user terbaru agar terbawa ke argumen tool.

  Thinking dikontrol via model param `think=true` (BUKAN /no_think), karena
  Qwen3:8b butuh reasoning aktif agar andal memanggil tool.

  Enable: Admin → Functions → aktifkan (is_active=1). Sudah ter-assign ke
  model lewat meta.filterIds, jadi jalan otomatis di DAAT_Qwen3:8b.

NOTE: Ini copy untuk editing. Paste ke Admin → Functions
      (localhost:3000/admin/functions) setelah diedit.
"""

import re
import requests
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".tsv"}

# Format session_id backend DAAT: md5(...)[:12] → 12 karakter hex.
_SESSION_RE = re.compile(r"\[SESSION_ID:\s*([0-9a-f]{12})\]", re.IGNORECASE)
_SESSION_RE_ALT = re.compile(r"\(Session ID:\s*([0-9a-f]{12})\)", re.IGNORECASE)
_SESSION_RE_BARE = re.compile(r"Session[_ ]ID[:\s]+([0-9a-f]{12})", re.IGNORECASE)


class Filter:
    class Valves(BaseModel):
        backend_url: str = Field(
            default="http://host.docker.internal:8000",
            description="DAAT Backend URL (host.docker.internal karena Open WebUI di Docker)",
        )
        confirm_timeout: int = Field(
            default=3,
            description="Timeout (detik) untuk konfirmasi session ke backend",
        )

    def __init__(self):
        self.valves = self.Valves()
        # CATATAN: TIDAK pakai self.toggle.
        # Per source OWUI (utils/filter.py): kalau toggle=True, inlet() HANYA jalan
        # saat user menyalakan toggle per-chat (default OFF) → mudah lupa.
        # Enable per-model sudah lewat model.meta.filterIds, jadi cukup:
        #   Admin → Functions: aktifkan (is_active=1) + filter sudah ter-assign ke model.
        # Filter lalu jalan OTOMATIS setiap pesan. (Mau toggle manual? tambah self.toggle = True.)
        #
        # Ikon kecil di UI (opsional, aman dihapus).
        self.icon = (
            "data:image/svg+xml;base64,"
            "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAy"
            "NCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZS13aWR0aD0i"
            "MiI+PHBhdGggZD0iTTMgM3YxOGgxOCIvPjxwYXRoIGQ9Ik0xOCAxN1Y5Ii8+PHBhdGggZD0i"
            "TTEzIDE3VjUiLz48cGF0aCBkPSJNOCAxN3YtMyIvPjwvc3ZnPg=="
        )

    # ── Helpers ──────────────────────────────────────────────────────────
    def _get_file_name(self, f: dict) -> str:
        """Normalize filename dari berbagai field name."""
        if not isinstance(f, dict):
            return ""
        return (
            f.get("name")
            or f.get("filename")
            or f.get("file_name")
            or f.get("original_filename")
            or ""
        )

    def _is_supported(self, name: str) -> bool:
        return bool(name) and Path(name).suffix.lower() in SUPPORTED_EXTENSIONS

    def _collect_file_names(self, body: dict) -> list[str]:
        """5-path detection — diadaptasi dari Tool.inlet lama, sumber: body."""
        names: list[str] = []
        messages = body.get("messages") or []

        def _add(f: dict):
            name = self._get_file_name(f)
            if not name and isinstance(f.get("file"), dict):
                name = self._get_file_name(f["file"])
            if self._is_supported(name) and name not in names:
                names.append(name)

        # 1) body["files"] (lokasi umum upload Open WebUI)
        for f in body.get("files") or []:
            _add(f)

        # 2) body["metadata"]["files"]
        meta = body.get("metadata") or {}
        for f in meta.get("files") or []:
            _add(f)

        # 3) files pada pesan terakhir
        if messages:
            for f in messages[-1].get("files") or []:
                _add(f)

        # 4) content list (multimodal) pada pesan terakhir
        if messages:
            content = messages[-1].get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        _add(item)

        # 5) fallback: scan semua pesan dari belakang
        if not names:
            for msg in reversed(messages):
                for f in msg.get("files") or []:
                    _add(f)
                if names:
                    break

        return names

    def _find_session_id(self, body: dict) -> Optional[str]:
        """Cari [SESSION_ID: xxx] dari history (umumnya di pesan assistant sebelumnya)."""
        messages = body.get("messages") or []
        for msg in reversed(messages[-20:]):
            if msg.get("role") == "system":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if not isinstance(content, str):
                content = str(content)
            m = (
                _SESSION_RE.search(content)
                or _SESSION_RE_ALT.search(content)
                or _SESSION_RE_BARE.search(content)
            )
            if m:
                return m.group(1).lower()
        return None

    def _session_is_active(self, session_id: str) -> bool:
        """
        Konfirmasi ke backend bahwa session belum expired.
        Graceful: kalau backend tidak bisa dihubungi (exception) → anggap aktif
        (jangan blokir alur). Hanya skip kalau backend jelas bilang active=False.
        """
        base = self.valves.backend_url.rstrip("/")
        try:
            resp = requests.get(
                f"{base}/session/{session_id}/status",
                timeout=self.valves.confirm_timeout,
            )
            if resp.status_code == 200:
                return bool(resp.json().get("active", False))
            return True  # status aneh → jangan blokir
        except Exception:
            return True  # backend hiccup → jangan blokir

    @staticmethod
    def _flatten_content(content) -> str:
        if isinstance(content, list):
            return " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        return content if isinstance(content, str) else str(content)

    # ── inlet — dijalankan SEKALI per pesan user, sebelum LLM ────────────
    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
    ) -> dict:
        try:
            messages = body.get("messages") or []
            if not messages or messages[-1].get("role") != "user":
                return body

            prefixes: list[str] = []

            # PENTING: session vs file SALING EKSKLUSIF.
            # Open WebUI menempelkan ulang file ke SETIAP pesan di chat yang sama,
            # jadi pada follow-up file lama masih "terlampir". Kalau kita inject
            # [FILE TERLAMPIR] sekaligus [ACTIVE SESSION], model bingung antara
            # analyze_data vs analyze_followup (Rule 1 vs Rule 3) → sering salah.
            # Aturan: kalau sudah ada session aktif → itu follow-up, file diabaikan.
            #         (Mau analisa file BARU? mulai chat baru.)

            # ── LAYER 1: Session aktif (untuk follow-up) ──────────────────
            session_id = self._find_session_id(body)
            if session_id and self._session_is_active(session_id):
                prefixes.append(
                    f"[ACTIVE SESSION={session_id} — "
                    f"untuk pertanyaan tentang data WAJIB panggil analyze_followup. "
                    f"ABAIKAN file yang masih menempel; JANGAN panggil analyze_data]"
                )
            else:
                # ── LAYER 2: File terlampir (analisis baru, belum ada session) ─
                file_names = self._collect_file_names(body)
                if file_names:
                    prefixes.append(
                        f"[FILE TERLAMPIR: {', '.join(file_names)} — "
                        f"WAJIB panggil tool analyze_data sekarang]"
                    )

            # ── Susun ulang content pesan user terakhir ───────────────────
            orig = self._flatten_content(messages[-1].get("content", ""))

            # Tidak ada prefix → jangan sentuh pesan (hemat & aman).
            if not prefixes:
                return body

            new_content = orig
            for p in prefixes:  # FILE TERLAMPIR berakhir paling depan (sama spt logika lama)
                new_content = f"{p}\n\n{new_content}"

            # CATATAN: /no_think SENGAJA tidak diinject.
            # Template qwen3:8b di Ollama tidak punya hook enable_thinking, jadi
            # thinking dikontrol via param `think` (di-set true pada model).
            # Qwen3:8b butuh reasoning AKTIF agar andal memilih tool call;
            # menyuntik /no_think jadi noise inert sekarang & bisa mematikan
            # thinking (→ follow-up "malas") kalau template ke depan menghormatinya.

            messages[-1]["content"] = new_content
            body["messages"] = messages
            return body
        except Exception:
            # Apapun yang gagal → lewatkan pesan apa adanya, jangan blokir chat.
            return body

    # ── outlet — dijalankan SESUDAH LLM menghasilkan jawaban final ───────
    def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
    ) -> dict:
        """
        Ganti isi pesan asisten dengan laporan LENGKAP yang sudah disiapkan Tool
        (DAAT Analyze Tool) di file temp /tmp/daat_report_<chat_id>.md.

        Kenapa: di native function-calling, LLM sering TIDAK menyalin output tool
        verbatim (kadang hanya session_id) → laporan asli "ngumpet" di View Result.
        Tool menstash laporan, outlet ini menggantinya supaya TAMPIL di chat asli.
        Aman: kalau file tidak ada (pesan non-DAAT), pesan dilewatkan apa adanya.
        """
        try:
            import os
            import tempfile

            cid = (body or {}).get("chat_id") or (__metadata__ or {}).get("chat_id")
            if not cid:
                return body

            messages = body.get("messages") or []

            # ANTI RACE/STALE: utamakan stash PER PESAN (chat_id + message_id).
            # message_id pesan asisten yang akan kita ganti = metadata.message_id,
            # fallback ke id pesan terakhir di body. Kalau tak ada stash UNTUK pesan
            # ini → JANGAN tukar dengan stash lama (itu sumber follow-up ketimpa).
            mid = (__metadata__ or {}).get("message_id")
            if not mid and messages:
                mid = messages[-1].get("id")

            tmpdir = tempfile.gettempdir()
            candidates = []
            if mid:
                candidates.append(os.path.join(tmpdir, f"daat_report_{cid}_{mid}.md"))
            candidates.append(os.path.join(tmpdir, f"daat_report_{cid}.md"))  # legacy

            path = next((p for p in candidates if os.path.exists(p)), None)
            if not path:
                print(
                    f"[DAAT outlet] no fresh stash for chat_id={cid} message_id={mid} "
                    f"→ leave content as-is",
                    flush=True,
                )
                return body

            with open(path, "r", encoding="utf-8") as f:
                report = f.read()
            print(
                f"[DAAT outlet] chat_id={cid} message_id={mid} "
                f"read {len(report.encode('utf-8'))} bytes from {path}",
                flush=True,
            )

            # Bersihkan SEMUA key giliran ini (per-message + legacy) supaya tak basi.
            for p in candidates:
                try:
                    os.remove(p)
                except Exception:
                    pass

            if report.strip() and messages and messages[-1].get("role") == "assistant":
                messages[-1]["content"] = report
                body["messages"] = messages
            return body
        except Exception:
            return body
