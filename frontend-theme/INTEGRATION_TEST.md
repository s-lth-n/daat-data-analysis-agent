# DAAT — Integration E2E Checklist (Tema Hanan × Backend Sulthan)

Tujuan: pastikan tema frontend Hanan **tidak mengganggu** output Tool/Filter DAAT, dan
seluruh alur (login → blank slate → analisis → chart → followup) tampil benar di OWUI v0.9.6.

Lingkungan: OWUI v0.9.6 (Docker `:3000`), backend `:8000`, Ollama `:11434`,
`DAAT_Qwen3:8b`. Login `admin@admin.com`.

> Aturan demo yang sudah dipelajari: **satu pertanyaan per pesan** (bukan multi-pertanyaan
> dalam satu blok). Rekam/screenshot **setelah konten stabil** (refresh bila perlu) karena
> ada glitch render transien Svelte v0.9.6 yang sudah diterima sebagai known limitation.

---

## Fase 0 — Pra-kondisi (sebelum apply tema)

- [ ] Backend hidup: `cd ~/ta-data-analyst/backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- [ ] Container OWUI jalan, `WEBUI_SECRET_KEY="daat-ta-itb-2026-fixed-key"` ter-set
- [ ] Tool aktif (analyze + analyze_followup), Filter `is_active=1` + `model.meta.filterIds` ter-set
- [ ] Model `DAAT_Qwen3:8b`: File Upload ON, File Context OFF, Bypass Embedding ON
- [ ] **Baseline tanpa tema**: jalankan 1 analisis UCI, screenshot. Ini pembanding "before".

---

## Fase 1 — Pasang tema

- [ ] Tempel `custom.css` ke Admin → Settings → Interface → Custom CSS. Simpan.
- [ ] Copy/mount `custom.js` ke `/app/backend/open_webui/static/custom.js`
- [ ] Hard refresh (Ctrl/Cmd+Shift+R)

**Cek dasar tema:**
- [ ] Login page: glassmorphism + gradien tampil, badge "Running locally" muncul
- [ ] Toggle **INA/ENG** muncul (kanan-atas / header). Klik → label UI berganti bahasa
- [ ] Toggle bahasa persist setelah refresh (cek `localStorage.daa-lang`)
- [ ] Dark mode: aktifkan, pastikan palet Sage tampil & teks terbaca (kontras OK)
- [ ] Blank slate kustom: judul "Data Analyst Agent" + 3 pill (Upload/Summarize/Find patterns)
- [ ] Pill **Upload** → memicu file picker OWUI (bukan sekadar insert teks)

---

## Fase 2 — Use-case 1: UCI Online Retail 50K (paling matang)

**2a. Analisis awal (/analyze)**
- [ ] Upload `online_retail_50K`. Kirim 1 permintaan analisis.
- [ ] Blank-slate kustom **menghilang** begitu pesan pertama muncul (cek `:has()` CSS bekerja)
- [ ] Blok deterministik "📊 Angka kunci…" tampil format streaming (BUKAN laporan formal bilingual)
- [ ] **Chart inline muncul** dan ter-render (bukan markdown mentah). Ini titik kritis: pastikan
      tema tidak menyembunyikan / menggeser chart
- [ ] Angka kanonik benar: Revenue memimpin (bukan Σ Price menyesatkan); UK dominan #1
- [ ] Tidak ada `[?]` muncul-hilang (jalur /analyze deterministik, bukan sesi expired)

**2b. Followup (/analyze/followup) — satu pertanyaan per pesan**
- [ ] Tanya "produk terlaris" → angka nyata (Regency Cakestand / White Hanging Heart), bukan karangan
- [ ] Tanya "top negara" → UK ~89% by count, angka deterministik
- [ ] Chart followup: bila ada, grafik **baru relevan** (bukan 3 grafik identik berulang)
- [ ] `[ACTIVE SESSION]` ter-inject, tidak jatuh ke /analyze

**2c. Interferensi tema (verifikasi inti)**
- [ ] `hideOpenWebUISiblings` TIDAK menyembunyikan message bubble / chart setelah pesan muncul
- [ ] MutationObserver tidak menyebabkan flicker pada rendered message saat streaming
- [ ] Toggle bahasa UI tidak meng-clear / mengganggu chat input saat analisis berjalan

---

## Fase 3 — Use-case 2: CDC 50K

- [ ] Upload `chronic_disease_50K`. Analisis awal.
- [ ] Breakdown kategorikal benar (Topic/DataSource/DataValueType) — CVD ~9,99% (4.997/50K)
- [ ] Domain-aware: proporsi & count valid; sum lintas-satuan TIDAK ditampilkan sbg total
- [ ] Followup mean-aware konsisten dengan `Komparasi_CDC_DAAT.md`
- [ ] Tidak ada halusinasi angka lolos ke layar final (redactor bekerja)

---

## Fase 4 — Use-case 3: Akademik

- [ ] Upload dataset kinerja akademik. Analisis awal + 1 followup.
- [ ] Format streaming konsisten, chart relevan, tidak ada interferensi tema

---

## Fase 5 — Selector compatibility OWUI v0.9.6

Jika ada item Fase 1 yang gagal, kemungkinan selector tema meleset di versi ini. Cek:
- [ ] `#auth-page` masih ada di login v0.9.6
- [ ] Chat input: `#chat-input` / `.ProseMirror` contenteditable masih cocok
- [ ] `button[aria-label="Controls"]` masih ada (anchor header toggle)
- [ ] Default "Suggested" container ter-hide (atau perlu sesuaikan teks "Suggested"/"Saran")

Catat selector yang meleset → kirim ke Hanan untuk patch, atau patch lokal di repo.

---

## Fase 6 — Dokumentasi hasil

- [ ] Screenshot: login (light + dark), blank slate, analisis UCI + chart, followup
- [ ] Catat versi OWUI, tanggal uji, selector yang perlu patch (bila ada)
- [ ] Update README bila ada langkah pasang yang berubah untuk v0.9.6
- [ ] Untuk Buku TA: simpan screenshot before/after sebagai bukti integrasi frontend

---

## Hasil akhir yang diharapkan

✅ Tema tampil penuh (login + chat, light + dark, toggle bahasa)
✅ Seluruh output DAAT (deterministik + chart + followup) tampil benar, tanpa terhalang tema
✅ Tidak ada konflik fungsional — hanya lapisan presentasi yang berubah
✅ Bukti screenshot siap untuk SemHas / Buku TA
