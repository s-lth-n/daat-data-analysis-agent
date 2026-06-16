"""
title: DAAT Analyze Tool
version: 2.10.0
This is a copy of the tool on open web ui,
used for editing the code, and after that get copy pasted back
to the open web ui, workspace,tool. to get integrated
"""

import base64
import inspect
import requests
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".tsv"}


class Tools:
    class Valves(BaseModel):
        backend_url: str = Field(
            default="http://host.docker.internal:8000",
            description="DAAT Backend URL (dipakai Tool→Backend, di dalam Docker)",
        )
        public_url: str = Field(
            default="http://localhost:8000",
            description="URL backend yang BISA diakses BROWSER (untuk src gambar chart)",
        )
        request_timeout: int = Field(default=300)

    def __init__(self):
        self.valves = self.Valves()

    def _stash_report(self, report: str, metadata) -> None:
        """
        Simpan laporan final ke file temp supaya Filter.outlet bisa MENGGANTI isi
        pesan asisten dengan laporan ini. Perlu karena di native function-calling,
        LLM sering TIDAK menyalin output tool verbatim (kadang cuma session_id).
        Outlet jalan SESUDAH LLM → hasil dijamin tampil.

        ANTI RACE/STALE (fix follow-up tertimpa report lama): stash di-key PER PESAN
        (chat_id + message_id), BUKAN chat_id saja. Dengan key per-chat, follow-up
        bisa membaca stash pesan SEBELUMNYA (basi) → jawaban baru tertimpa report
        pertama. Kita tulis DUA file:
          - daat_report_<chat_id>_<message_id>.md  (utama, anti-stale)
          - daat_report_<chat_id>.md               (legacy/fallback bila outlet
                                                     tak dapat message_id)
        Keduanya berisi report pesan INI; outlet membersihkan keduanya tiap giliran.
        """
        try:
            import os
            import tempfile

            md = metadata or {}
            cid = md.get("chat_id")
            if not cid:
                print("[DAAT _stash_report] no chat_id in metadata → skip stash", flush=True)
                return
            mid = md.get("message_id") or md.get("id")
            tmpdir = tempfile.gettempdir()
            n_bytes = len(report.encode("utf-8"))

            paths = []
            if mid:
                paths.append(os.path.join(tmpdir, f"daat_report_{cid}_{mid}.md"))
            paths.append(os.path.join(tmpdir, f"daat_report_{cid}.md"))  # legacy/fallback

            for path in paths:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report)

            print(
                f"[DAAT _stash_report] chat_id={cid} message_id={mid} "
                f"bytes={n_bytes} wrote={paths}",
                flush=True,
            )
        except Exception as e:
            print(f"[DAAT _stash_report] error: {e}", flush=True)

    def _get_file_name(self, f: dict) -> str:
        """Normalize filename dari berbagai field name."""
        return (
            f.get("name")
            or f.get("filename")
            or f.get("file_name")
            or f.get("original_filename")
            or ""
        )

    def _extract_file(self, messages: list) -> Optional[dict]:
        for msg in reversed(messages or []):
            # Standard "files" key
            for f in msg.get("files", []):
                name = self._get_file_name(f)
                if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS and f.get("id"):
                    return {
                        "id": f["id"],
                        "name": name,
                        "url": f.get("url", ""),
                        "path": f.get("path", ""),
                    }
            # Multimodal content list
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    name = self._get_file_name(item)
                    fid = item.get("id") or item.get("file_id") or ""
                    if not name and isinstance(item.get("file"), dict):
                        inner = item["file"]
                        name = self._get_file_name(inner)
                        fid = fid or inner.get("id", "")
                    if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS and fid:
                        return {
                            "id": fid,
                            "name": name,
                            "url": item.get("url", ""),
                            "path": item.get("path", ""),
                        }
        return None

    def _read_file(self, file_info: dict) -> Optional[bytes]:
        try:
            from open_webui.models.files import Files as WF

            fm = WF.get_file_by_id(file_info["id"])
            # OWUI ≥0.9: get_file_by_id kini async. Kalau dapat coroutine,
            # tutup (hindari "coroutine was never awaited") & pakai fallback
            # directory-scan di bawah (terbukti jalan).
            if inspect.iscoroutine(fm):
                fm.close()
                fm = None
            if fm:
                p = getattr(fm, "path", None) or (
                    fm.meta.get("path") if hasattr(fm, "meta") and fm.meta else None
                )
                if p and Path(p).exists():
                    return Path(p).read_bytes()
                if hasattr(fm, "data") and isinstance(fm.data, dict):
                    c = fm.data.get("content", "")
                    if c:
                        try:
                            return base64.b64decode(c)
                        except Exception:
                            return c.encode()
        except Exception:
            pass

        for d in [
            Path("/app/backend/data/uploads"),
            Path("/app/backend/data/files"),
            Path("/app/backend/data/cache/files"),
        ]:
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file() and (
                    file_info["id"] in f.name or file_info["name"] in f.name
                ):
                    return f.read_bytes()
        return None

    def _format(self, data: dict) -> str:
        result = data.get("text", "")

        stats = (data.get("statistics") or {}).get("descriptive")
        if stats and isinstance(stats, dict) and "error" not in stats:
            result += "\n\n---\n📊 **Statistik Deskriptif:**\n"
            for col, s in stats.items():
                if isinstance(s, dict) and "mean" in s:
                    result += (
                        f"\n**{col}**: mean={s['mean']}, "
                        f"median={s['median']}, std={s['std']}, "
                        f"min={s['min']}, max={s['max']}"
                    )

        strong = (
            (data.get("statistics") or {})
            .get("correlation", {})
            .get("strong_correlations", [])
        )
        if strong:
            result += "\n\n🔗 **Korelasi Kuat:**"
            for c in strong:
                result += (
                    f"\n- {c['col1']} ↔ {c['col2']}: "
                    f"r={c['correlation']} ({c['strength']})"
                )

        sid = data.get("session_id", "")
        if sid:
            result += f"\n\n[SESSION_ID: {sid}]"

        return result

    # NOTE: inlet() DIHAPUS dari Tool ini.
    # Open WebUI TIDAK PERNAH memanggil inlet() pada Tool — hanya pada Filter
    # Function (class Filter). Injeksi marker [SESSION_ID]/[ACTIVE SESSION]/
    # [FILE TERLAMPIR] + /no_think sekarang ada di "DAAT Session Filter.py".
    # Aktifkan filter itu per-model agar follow-up berfungsi.

    async def analyze_data(
        self,
        prompt: str,
        language: str = "id",
        __messages__: list = None,
        __files__: list = None,
        __event_emitter__=None,
        __metadata__: dict = None,
    ) -> str:
        """
        Analyze a data file attached in chat.
        ALWAYS call this when user uploads CSV/Excel and asks for analysis.
        :param prompt: analysis request
        :param language: 'id' or 'en'
        """
        base = self.valves.backend_url.rstrip("/")

        async def emit(msg, done=False):
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": msg, "done": done}}
                )

        await emit("🔍 Mendeteksi file...")

        file_info = None
        if __files__:
            for f in __files__:
                name = self._get_file_name(f)
                if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS and f.get("id"):
                    file_info = {
                        "id": f["id"],
                        "name": name,
                        "url": f.get("url", ""),
                        "path": f.get("path", ""),
                    }
                    break

        if not file_info:
            file_info = self._extract_file(__messages__ or [])

        if not file_info:
            # Debug: bantu diagnose kenapa file tidak ketemu
            n_files = len(__files__ or [])
            n_msgs = len(__messages__ or [])
            last_msg_keys = (
                list((__messages__ or [{}])[-1].keys()) if __messages__ else []
            )
            return (
                f"⚠️ File tidak terdeteksi.\n"
                f"Debug: __files__={n_files} items | "
                f"__messages__={n_msgs} msgs | "
                f"last_msg keys={last_msg_keys}\n\n"
                f"Coba upload ulang file CSV/Excel."
            )

        await emit(f"📂 Membaca {file_info['name']}...")
        file_bytes = self._read_file(file_info)
        if not file_bytes:
            return (
                f"❌ Gagal membaca `{file_info['name']}` "
                f"(ID: {file_info['id']}). Coba upload ulang."
            )

        await emit("📤 Upload ke backend...")
        try:
            up = requests.post(
                f"{base}/upload",
                files={"file": (file_info["name"], file_bytes)},
                timeout=60,
            )
            up.raise_for_status()
            file_id = up.json()["file_id"]
            preview = up.json().get("preview", {})
        except requests.exceptions.ConnectionError:
            return f"❌ Backend tidak terhubung di `{base}`"
        except Exception as e:
            return f"❌ Upload gagal: {e}"

        await emit("🤖 Menganalisis data...")
        try:
            resp = requests.post(
                f"{base}/analyze",
                json={"file_id": file_id, "prompt": prompt, "language": language},
                timeout=self.valves.request_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            return "⏱️ Timeout. Coba prompt lebih spesifik."
        except Exception as e:
            return f"❌ Analisis error: {e}"

        await emit("✅ Selesai!", done=True)

        # CATATAN PENTING (Open WebUI native function-calling):
        # Konten yang di-emit via __event_emitter__ saat tool berjalan akan
        # DITIMPA oleh generasi LLM pasca-tool (sudah diverifikasi: hanya teks
        # LLM yang tersimpan). Jadi laporan TIDAK di-emit; dikembalikan sebagai
        # RETURN VALUE, lalu LLM diminta menyalinnya VERBATIM (lihat system prompt).
        #
        # Grafik dipasang sebagai URL markdown yang bisa diakses BROWSER
        # (public_url=localhost), BUKAN base64 (terlalu panjang untuk disalin LLM)
        # dan BUKAN host.docker.internal (tidak resolve di browser host).
        shape = preview.get("shape", {})
        header = (
            f"📁 **{file_info['name']}** — "
            f"{shape.get('rows','?')} baris × "
            f"{shape.get('columns','?')} kolom\n\n"
        )
        report = header + self._format(data)

        pub = self.valves.public_url.rstrip("/")
        # Revisi #2: caption ikut bahasa AKTUAL laporan (backend mendeteksi & meng-
        # override; nilainya ada di data["language"]). Fallback ke param tool.
        # Default EN bila bukan 'id'; tidak pernah bilingual.
        report_lang = data.get("language") or language
        word = "Grafik" if report_lang == "id" else "Chart"
        link_word = "Buka grafik interaktif" if report_lang == "id" else "Open interactive chart"
        # Backend memberi tahu key mana yang punya .html (tool ini di container lain →
        # tak bisa stat file). Link interaktif ADDITIF: PNG inline tetap; link cuma
        # ditempel bila k ∈ chart_html_keys (omission jujur bila HTML tak ada).
        # URL pakai public_url (browser host), BUKAN host.docker.internal.
        html_keys = set(data.get("chart_html_keys") or [])
        for i, k in enumerate(data.get("chart_keys") or []):
            lbl = f"{word} {i + 1}"
            report += f"\n\n**📊 {lbl}**\n\n![{lbl}]({pub}/chart/image/{k}.png)"
            if k in html_keys:
                report += f"\n\n🔍 [{link_word}]({pub}/chart/image/{k}.html)"

        # Outlet Filter akan mengganti isi pesan asisten dengan laporan ini.
        self._stash_report(report, __metadata__)
        return report

    async def analyze_followup(
        self,
        session_id: str,
        prompt: str,
        language: str = "id",
        __metadata__: dict = None,
    ) -> str:
        """
        Follow-up on previously analyzed data.
        Call when [SESSION_ID: xxx] is visible and user asks follow-up.
        :param session_id: from [SESSION_ID: xxx] in conversation
        :param prompt: follow-up question
        :param language: 'id' or 'en'
        """
        base = self.valves.backend_url.rstrip("/")
        try:
            resp = requests.post(
                f"{base}/analyze/followup",
                json={"session_id": session_id, "query": prompt, "language": language},
                timeout=self.valves.request_timeout,
            )
            # Session expired / tidak ditemukan → relay pesan ramah dari backend
            if resp.status_code == 404:
                try:
                    msg = resp.json().get("message", "")
                except Exception:
                    msg = ""
                return (
                    f"⚠️ {msg or 'Sesi tidak ditemukan / sudah expired. Upload ulang file untuk mulai analisis baru.'}"
                )
            resp.raise_for_status()
            data = resp.json()
            # Backend mengembalikan {"result": <markdown lengkap, grafik pakai
            # public_url=localhost>, "session_id": ...}. Dikembalikan apa adanya →
            # LLM menyalin VERBATIM (lihat system prompt).
            result = data.get("result") or data.get("text") or str(data)
            if data.get("session_id") and "[SESSION_ID:" not in result:
                result += f"\n\n[SESSION_ID: {data['session_id']}]"
            # Outlet Filter akan mengganti isi pesan asisten dengan hasil ini.
            self._stash_report(result, __metadata__)
            return result
        except Exception as e:
            return f"❌ Follow-up gagal: {e}"
