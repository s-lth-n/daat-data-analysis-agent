# DAAT — Frontend Theme Layer

Tema kustom Open WebUI untuk **Data Analyst Agent (DAAT)**.
Penulis tema: **Hanan Ainayya Ramadina** (UI/UX). Integrasi backend: **Sulthan Miftahul Ulum**.

Lapisan ini **murni presentasi** (CSS + JS injeksi). Tidak menyentuh backend FastAPI,
Tool, Filter, Modelfile, maupun build Open WebUI. Aman dipasang di atas sistem DAAT
yang sudah berjalan.

Target Open WebUI: **v0.9.6** (verifikasi selector saat E2E — lihat `INTEGRATION_TEST.md`).

---

## Isi folder

| File | Fungsi | Tujuan pemasangan |
|---|---|---|
| `custom.css` | Tema utama (light Cocoa / dark Sage, glassmorphism, login + chat) | Ditimpa sebagai **static/custom.css** di container (lihat "Cara pasang") |
| `custom.js` | Toggle bahasa UI (INA/ENG), badge "Running locally", blank-slate kustom, terjemahan label | Dipasang sebagai **`loader.js`** di static container OWUI (lihat di bawah) |
| `login_mockup.html` | Pratinjau login di browser (untuk screenshot Buku TA) | Buka langsung di browser, tidak dipasang ke OWUI |
| `login_theory_mapping.md` | Pemetaan keputusan desain → sitasi (Grant/Krug/Marsh/Nunnally) | Sumber Bab UI/UX Buku TA |
| `JUST login page.css` | Varian login lama (arsip) | Tidak dipakai — simpan sebagai riwayat |

---

## Cara pasang

> ⚠️ **PENTING — Open WebUI TIDAK punya field "Custom CSS" di Admin panel.**
> Kustomisasi dilakukan dengan menimpa file static di dalam container.
> Di **v0.9.6**, OWUI sudah menyediakan dua file placeholder kosong (0 byte) yang
> direferensikan otomatis oleh HTML:
> - `static/custom.css` → CSS kustom
> - `static/loader.js` → **JS kustom** (BUKAN `custom.js` — meski file sumber Hanan
>   bernama `custom.js`, isinya harus dipasang sebagai `loader.js`)
>
> Path static aktif (terverifikasi v0.9.6): `/app/backend/open_webui/static/`

Verifikasi cepat bahwa slot file aktif (HTML mereferensikan keduanya, keduanya 200):

```bash
curl -s http://localhost:3000/ | grep -oE '(custom\.css|loader\.js)[^"]*' | sort -u
curl -s -o /dev/null -w "custom.css: %{http_code}\n" http://localhost:3000/static/custom.css
curl -s -o /dev/null -w "loader.js:  %{http_code}\n" http://localhost:3000/static/loader.js
```

### Cara A — Volume mount (PERMANEN, dipakai untuk kondisi final)

Tahan saat container di-recreate. Konsisten dengan mount-relatif repo DAAT.
Tambahkan ke service OWUI di `docker-compose.yml`:

```yaml
volumes:
  - ./frontend-theme/custom.css:/app/backend/open_webui/static/custom.css:ro
  - ./frontend-theme/custom.js:/app/backend/open_webui/static/loader.js:ro
```

Catat: file sumber `custom.js` di-mount KE `loader.js`. Lalu:

```bash
docker compose up -d   # recreate dengan mount baru
```

Hard refresh browser (Ctrl/Cmd+Shift+R).

### Cara B — docker cp (CEPAT, untuk tes — hilang saat recreate)

```bash
docker cp frontend-theme/custom.css open-webui:/app/backend/open_webui/static/custom.css
docker cp frontend-theme/custom.js  open-webui:/app/backend/open_webui/static/loader.js
```

> ⚠️ File yang di-`docker cp` **hilang saat container di-recreate** (`docker compose
> down/up`, update image). `docker restart` biasa aman. Untuk permanen pakai Cara A.

CSS punya **fallback mandiri**: tema aktif walau JS belum termuat. JS hanya menambah
toggle bahasa + blank-slate kaya.

### Verifikasi terpasang

```bash
curl -s http://localhost:3000/static/custom.css | wc -c   # ~41000
curl -s http://localhost:3000/static/loader.js  | wc -c   # ~23000
```

Visual: toggle **INA/ENG** muncul kanan-atas; blank slate kustom (judul "Data Analyst
Agent" + 3 pill) tampil dan hilang saat pesan pertama dikirim.

---

## Hubungan dengan komponen DAAT lain

| Lapisan | Pemilik | Slot OWUI | Konflik? |
|---|---|---|---|
| Backend FastAPI (`:8000`) | Sulthan | — | Tidak |
| Tool `analyze` / `analyze_followup` (v2.10.0) | Sulthan | Admin → Functions (Tools) | Tidak |
| Filter `inlet`/`outlet` (v1.4.0) | Sulthan | Admin → Functions (Filters) | Tidak |
| Modelfile `DAAT_Qwen3:8b` + params | Sulthan | Workspace → Models | Tidak |
| **Custom CSS** | Hanan | `static/custom.css` (file) | — |
| **Custom JS** | Hanan | `static/loader.js` (file) | — |

Tidak ada slot yang ditulis dua kali. Tema dan backend hidup di lapisan terpisah.

### Titik yang perlu diverifikasi (bukan konflik — asumsi)

1. `custom.js` memanipulasi DOM blank-slate (`hideOpenWebUISiblings`,
   `hideDefaultSuggestionsContainer`). Hanya jalan saat belum ada pesan — pastikan tidak
   menyembunyikan apa pun setelah pesan pertama.
2. Chart markdown DAAT di-emit via `__event_emitter__` ke rendered message. JS Hanan tidak
   menyentuh rendered message (selektornya `.daa-blank`/`.daa-suggestions`) — **tetap cek di layar**
   karena MutationObserver memantau seluruh body.
3. Selector DOM ditulis untuk struktur OWUI tertentu (TipTap, `#auth-page`,
   `aria-label="Controls"`). Konfirmasi cocok di v0.9.6.
4. Toggle bahasa UI (`localStorage: daa-lang`) = bahasa antarmuka, **berbeda** dari deteksi
   bahasa output laporan di backend. Putuskan apakah perlu dihubungkan atau dibiarkan independen.
5. **Scope toggle bahasa (diketahui, bukan bug):** toggle hanya menerjemahkan brand title,
   subtitle, auth labels, dan blank-slate (judul + 3 pill) — BUKAN i18n penuh OWUI (sidebar,
   menu settings tetap Inggris). Ini sesuai scope desain `custom.js` Hanan (objek `T`). I18n
   penuh butuh masuk sistem locale SvelteKit OWUI, di luar layer injeksi CSS/JS. Cukup untuk
   orientasi pengguna non-teknis di landing.

Checklist verifikasi lengkap: lihat `INTEGRATION_TEST.md`.

---

## Sumber

Repo asli tema: `raeinayya/ThemeTA2` (private). Disalin ke repo DAAT untuk menjadikan satu
repo = sistem lengkap bagi penguji SemHas/Sidang.
