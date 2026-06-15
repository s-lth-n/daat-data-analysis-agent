/* ==========================================================
   Data Analyst Agent — custom.js  (v20)
   Companion script for custom.css

   Purpose:
   1. Inject INA / ENG language toggle on EVERY page (top-right)
   2. On the auth page: inject the rich "Running locally" badge
      and translate brand title / subtitle / form labels / placeholders /
      submit button (Open WebUI ships English defaults — JS swaps).
   3. On the chat page (blank slate): inject custom title + subtitle
      ("Data Analyst Agent" / "Analyze your data efficiently"), three
      data-focused suggestion pills (Upload / Summarize / Find patterns),
      and translate the chat textarea placeholder.
   4. Persist language choice in localStorage; default = ENG.

   Loaded by Open WebUI when /static/custom.js exists AND the
   SvelteKit HTML includes <script src="/static/custom.js">.
   ========================================================== */

(function () {
  'use strict';

  // ---------- Translations ----------
  const T = {
    en: {
      // Brand stays in English everywhere.
      title:        'Data Analyst Agent',
      subtitle:     'Sign in to continue',
      badge:        'Running locally · your data is safe',

      // Auth form
      username_lbl: 'Username',
      username_ph:  'Enter your username',
      password_lbl: 'Password',
      password_ph:  'Enter your password',
      sign_in:      'Sign in',
      signing_in:   'Signing in…',

      // Chat blank slate
      chat_title:        'Data Analyst Agent',     // brand stays
      chat_subtitle:     'Upload your file and choose what you want to do',
      chat_ph:           'Upload your file or state your request…',
      sug_upload:        'Upload your file',
      sug_summarize:     'Summarize this data',
      sug_patterns:      'Find patterns in this file',
      chat_reassurance:  'Your data stays on this device'
    },
    id: {
      title:        'Data Analyst Agent',
      subtitle:     'Masuk untuk melanjutkan',
      badge:        'Berjalan secara lokal · data Anda aman',

      username_lbl: 'Nama pengguna',
      username_ph:  'Masukkan nama pengguna',
      password_lbl: 'Kata sandi',
      password_ph:  'Masukkan kata sandi',
      sign_in:      'Masuk',
      signing_in:   'Sedang masuk…',

      chat_title:        'Data Analyst Agent',
      chat_subtitle:     'Unggah file Anda dan pilih yang ingin dilakukan',
      chat_ph:           'Masukkan file atau tulis kebutuhan Anda…',
      sug_upload:        'Unggah file Anda',
      sug_summarize:     'Ringkas data ini',
      sug_patterns:      'Temukan pola dalam file ini',
      chat_reassurance:  'Data Anda tetap di perangkat ini'
    }
  };

  const STORAGE_KEY = 'daa-lang';

  // ---------- Page detection ----------
  function isAuthPage() { return !!document.querySelector('#auth-page'); }

  // Find the chat input. Open WebUI uses TipTap/ProseMirror — a
  // contenteditable <div id="chat-input">, NOT a <textarea>.
  function findChatInput() {
    return (
      document.getElementById('chat-input') ||
      document.querySelector('[contenteditable="true"].ProseMirror') ||
      document.querySelector('[contenteditable="true"][class*="tiptap" i]') ||
      [].find.call(
        document.querySelectorAll('[contenteditable="true"]'),
        function (c) { return !c.closest('#auth-page'); }
      ) ||
      null
    );
  }
  // Back-compat alias
  function findChatTextarea() { return findChatInput(); }

  // Blank slate = chat input present and no real chat-bubble messages.
  // IMPORTANT: keep selectors TIGHT — Open WebUI has many helper elements
  // (message-input, message-thread, error-message...) that exist on blank
  // state too. Only match actual rendered chat-message bubbles.
  function isChatBlankSlate() {
    if (isAuthPage()) return false;
    const editor = findChatInput();
    if (!editor) return false;
    const hasMessages = !!document.querySelector(
      '.user-message, .assistant-message, ' +
      '[data-message-id], [id^="message-"]'
    );
    return !hasMessages;
  }

  // Anchor element used for inserting the custom blank slate
  function findBlankSlateAnchor() {
    const ta = findChatTextarea();
    if (!ta) return null;
    return ta.closest('form') || ta.parentElement;
  }

  // ---------- Auth-form helpers ----------
  function findEmailLabel() {
    return document.querySelector(
      '#auth-page label[for*="email" i], #auth-page label[for*="username" i]'
    );
  }
  function findEmailInput() {
    return document.querySelector(
      '#auth-page input[type="email"], ' +
      '#auth-page input[autocomplete*="username" i], ' +
      '#auth-page input[autocomplete*="email" i]'
    );
  }
  function findPasswordLabel() {
    return document.querySelector('#auth-page label[for*="password" i]');
  }
  function findPasswordInput() {
    return document.querySelector('#auth-page input[type="password"]');
  }
  function findSignInButton() {
    return document.querySelector('#auth-page button[type="submit"]');
  }

  // ---------- Apply language ----------
  function applyLang(lang) {
    if (!T[lang]) lang = 'en';
    const dict = T[lang];
    const root = document.documentElement;

    // CSS custom properties (used by ::before/::after content swaps in custom.css)
    root.style.setProperty('--i18n-title',    '"' + dict.title    + '"');
    root.style.setProperty('--i18n-subtitle', '"' + dict.subtitle + '"');
    root.style.setProperty('--i18n-badge',    '"\\2022\\00a0  ' + dict.badge + '"');

    // Auth form — direct DOM (Open WebUI's own elements)
    const eL = findEmailLabel();    if (eL) eL.textContent = dict.username_lbl;
    const eI = findEmailInput();    if (eI) eI.setAttribute('placeholder', dict.username_ph);
    const pL = findPasswordLabel(); if (pL) pL.textContent = dict.password_lbl;
    const pI = findPasswordInput(); if (pI) pI.setAttribute('placeholder', dict.password_ph);
    const sB = findSignInButton();  if (sB && !sB.disabled) sB.textContent = dict.sign_in;

    // Chat input placeholder — TipTap renders via the empty <p>'s ::before.
    // We override that ::before content via the --i18n-chat-ph CSS variable.
    // The value MUST be a quoted string so CSS `content: var(...)` resolves.
    root.style.setProperty('--i18n-chat-ph', '"' + dict.chat_ph + '"');

    // Also try the data-placeholder attr (works in some TipTap configs)
    const editor = findChatInput();
    if (editor) {
      editor.setAttribute('data-placeholder', dict.chat_ph);
      const emptyP = editor.querySelector('p.is-editor-empty, p[data-placeholder]');
      if (emptyP) emptyP.setAttribute('data-placeholder', dict.chat_ph);
    }

    document.querySelectorAll('[data-i18n-chat]').forEach(function (el) {
      const key = el.getAttribute('data-i18n-chat');
      if (dict[key] !== undefined) el.textContent = dict[key];
    });

    // Toggle visual state
    document.querySelectorAll('.lang-toggle button').forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false');
    });

    // Rich badge (auth)
    const richBadgeText = document.querySelector('.daa-badge .daa-badge-text');
    if (richBadgeText) richBadgeText.textContent = dict.badge;

    root.lang = lang;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
  }

  // ---------- Find the top-right header action container ----------
  // Open WebUI puts the Temporary chat + Controls icon buttons inside
  // a flex container. The Controls button has aria-label="Controls",
  // which is a stable identifier across versions.
  function findHeaderContainer() {
    const btn =
      document.querySelector('button[aria-label="Controls"]') ||
      document.querySelector('button[aria-label*="control" i]') ||
      document.querySelector('button[aria-label*="setting" i]');
    if (btn && btn.parentElement) return btn.parentElement;
    return null;
  }

  // ---------- Toggle injection — inside header container as flex sibling ----------
  function injectToggle() {
    if (document.querySelector('.lang-toggle')) return;

    const toggle = document.createElement('div');
    toggle.className = 'lang-toggle';
    toggle.setAttribute('role', 'group');
    toggle.setAttribute('aria-label', 'Language');
    toggle.innerHTML =
      '<button type="button" data-lang="id" aria-pressed="false" aria-label="Bahasa Indonesia">INA</button>' +
      '<button type="button" data-lang="en" aria-pressed="true"  aria-label="English">ENG</button>';

    const header = findHeaderContainer();
    if (header) {
      // Insert as the FIRST child so it sits to the left of settings + avatar
      header.insertBefore(toggle, header.firstChild);
    } else {
      // No header found yet (e.g. on the auth page, or page still mounting).
      // Fall back to floating top-right so the user always sees the toggle.
      toggle.style.position = 'fixed';
      toggle.style.top      = '20px';
      toggle.style.right    = '20px';
      toggle.style.zIndex   = '9999';
      document.body.appendChild(toggle);
    }

    toggle.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () { applyLang(b.dataset.lang); });
    });
  }

  // ---------- Rich badge (auth page only) ----------
  function injectRichBadge() {
    const form = document.querySelector('#auth-page form.flex.flex-col.justify-center');
    if (!form || form.querySelector('.daa-badge')) return;

    form.classList.add('has-js-badge');

    const lang = document.documentElement.lang || 'en';
    const badgeText = (T[lang] || T.en).badge;

    const badge = document.createElement('div');
    badge.className = 'daa-badge';
    badge.innerHTML =
      '<span class="daa-badge-dot" aria-hidden="true"></span>' +
      '<span class="daa-badge-text">' + badgeText + '</span>';
    form.appendChild(badge);

    if (!document.getElementById('daa-badge-style')) {
      const css = document.createElement('style');
      css.id = 'daa-badge-style';
      css.textContent =
        '.daa-badge {' +
        '  margin: 22px auto 0; display: flex; align-items: center;' +
        '  justify-content: center; gap: 8px; padding: 9px 16px;' +
        '  background: var(--powder-pale);' +
        '  border: 1px solid var(--input-border);' +
        '  border-radius: 999px; font-size: 12.5px;' +
        '  color: var(--text2); line-height: 1.4; white-space: nowrap;' +
        '  width: fit-content;' +
        '}' +
        '.daa-badge-dot {' +
        '  width: 8px; height: 8px; border-radius: 50%;' +
        '  background: var(--powder);' +
        '  box-shadow: 0 0 0 3px rgba(221,230,237,0.30);' +
        '  flex-shrink: 0; animation: daa-badge-pulse 2.4s ease-in-out infinite;' +
        '}' +
        '.dark .daa-badge-dot, :root.dark .daa-badge-dot {' +
        '  box-shadow: 0 0 0 3px rgba(183,172,155,0.30);' +
        '}' +
        '@keyframes daa-badge-pulse {' +
        '  0%, 100% { opacity: 0.75; transform: scale(1); }' +
        '  50%      { opacity: 1.00; transform: scale(1.18); }' +
        '}' +
        '@media (prefers-reduced-motion: reduce) {' +
        '  .daa-badge-dot { animation: none; }' +
        '}';
      document.head.appendChild(css);
    }
  }

  // ---------- File upload trigger ----------
  // Open WebUI's chat input has a "+" attachment button that opens a
  // menu (Upload File / Capture / etc.). Try multiple strategies to
  // find and click it.
  function triggerFileUpload() {
    // 1. Direct hidden <input type="file">
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.click();
      return true;
    }

    // 2. Buttons explicitly labeled for upload / attach / add
    const labeled = document.querySelector(
      'button[aria-label*="upload" i], '  +
      'button[aria-label*="attach" i], '  +
      'button[aria-label*="file"   i], '  +
      'button[aria-label*="add"    i], '  +
      'button[title*="upload" i], '       +
      'button[title*="attach" i], '       +
      'button[title*="add"    i]'
    );
    if (labeled) {
      labeled.click();
      return true;
    }

    // 3. Structural fallback — click the FIRST icon button inside the
    // form that wraps the chat input. In Open WebUI's TipTap layout
    // that's the "+" attach button (sits to the left of the input).
    const editor = findChatInput();
    if (editor) {
      const form = editor.closest('form');
      if (form) {
        const firstIconBtn = form.querySelector('button:has(svg)');
        if (firstIconBtn) {
          firstIconBtn.click();
          return true;
        }
      }
    }

    return false;
  }

  // ---------- Hide Open WebUI's default "Suggested" container ----------
  // Finds any element whose direct text === "Suggested" (or Indonesian
  // equivalent) and hides its enclosing container. The default suggestions
  // are usually NOT a direct sibling of the form, so the sibling-walk
  // alone doesn't reach them.
  function hideDefaultSuggestionsContainer() {
    const candidates = document.querySelectorAll(
      'h2, h3, h4, h5, span, div'
    );
    for (let i = 0; i < candidates.length; i++) {
      const el = candidates[i];
      // Read direct text only — .textContent includes children and is too eager
      const text = (el.firstChild && el.firstChild.nodeType === 3
        ? el.firstChild.textContent.trim()
        : el.textContent.trim());
      if (text !== 'Suggested' && text !== 'Saran') continue;
      // Walk up to the section/card that wraps both the heading + items.
      // Stop at the first ancestor that has multiple element children
      // (heading + list).
      let wrap = el.parentElement;
      while (wrap && wrap.children.length === 1) wrap = wrap.parentElement;
      if (!wrap) continue;
      if (wrap.classList.contains('daa-suggestions')) continue;
      if (wrap.querySelector('.daa-sug')) continue;
      if (wrap.getAttribute('data-daa-hidden') === 'true') continue;
      wrap.style.display = 'none';
      wrap.setAttribute('data-daa-hidden', 'true');
    }
  }

  // ---------- Detect right-side panel (Controls / Settings / Profile) ----------
  function isPanelOpen() {
    // 1. Look for a visible "Controls" / "Settings" / "Profile" / "Account"
    //    heading anywhere on the page (the right-side panels render one).
    const headings = document.querySelectorAll('h1, h2, h3, h4');
    const targets = ['Controls', 'Settings', 'Profile', 'Account'];
    for (let i = 0; i < headings.length; i++) {
      const h = headings[i];
      if (targets.indexOf(h.textContent.trim()) === -1) continue;
      const rect = h.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return true;
    }
    // 2. Standard ARIA modals
    if (document.querySelector(
      '[role="dialog"][aria-modal="true"]:not([aria-hidden="true"])'
    )) return true;
    return false;
  }

  function updateTogglePanelState() {
    const toggle = document.querySelector('.lang-toggle');
    if (!toggle) return;
    toggle.style.display = isPanelOpen() ? 'none' : '';
  }


  // ---------- Hide Open WebUI's blank-slate siblings ----------
  // After our blank slate is mounted, walk the DOM around it and hide
  // anything Open WebUI rendered as part of the default empty state.
  // We only walk SIBLINGS of our injected elements so we never hide
  // the form / chat-input / sidebar / etc.
  function hideOpenWebUISiblings() {
    const blank = document.querySelector('.daa-blank');
    const sugs  = document.querySelector('.daa-suggestions');
    if (!blank || !sugs) return;

    function shouldKeep(el) {
      if (!el) return true;
      if (el.classList.contains('daa-blank')) return true;
      if (el.classList.contains('daa-suggestions')) return true;
      if (el.classList.contains('daa-reassurance')) return true;
      if (el.tagName === 'FORM') return true;
      if (el.querySelector && el.querySelector('form, textarea, [contenteditable="true"]')) return true;
      return false;
    }

    // Hide siblings BEFORE .daa-blank
    let node = blank.previousElementSibling;
    while (node) {
      const prev = node.previousElementSibling;
      if (!shouldKeep(node) && node.style.display !== 'none') {
        node.style.display = 'none';
        node.setAttribute('data-daa-hidden', 'true');
      }
      node = prev;
    }

    // Hide siblings AFTER .daa-suggestions
    node = sugs.nextElementSibling;
    while (node) {
      const next = node.nextElementSibling;
      if (!shouldKeep(node) && node.style.display !== 'none') {
        node.style.display = 'none';
        node.setAttribute('data-daa-hidden', 'true');
      }
      node = next;
    }
  }

  // ---------- Chat blank slate injection ----------
  // Always inject when chat-input is present (and we're not on auth page).
  // CSS uses :has() to hide it when real chat messages appear.
  function injectChatBlank() {
    if (isAuthPage()) return;
    if (!findChatInput()) return;
    if (document.querySelector('.daa-blank')) return;

    const anchor = findBlankSlateAnchor();
    if (!anchor || !anchor.parentNode) return;

    // Title + subtitle (inserted before the input wrapper)
    const blank = document.createElement('div');
    blank.className = 'daa-blank';
    blank.innerHTML =
      '<h1 class="daa-blank-title" data-i18n-chat="chat_title">Data Analyst Agent</h1>' +
      '<p  class="daa-blank-subtitle" data-i18n-chat="chat_subtitle">Analyze your data efficiently</p>';

    // Suggestions row (inserted after the input wrapper).
    // The first one carries data-action="upload" so the click handler
    // triggers the file picker instead of just inserting text.
    const sugs = document.createElement('div');
    sugs.className = 'daa-suggestions';
    sugs.innerHTML =
      '<button class="daa-sug" type="button" data-action="upload"'             +
      '        data-prompt-key="sug_upload">'                                   +
      '<span data-i18n-chat="sug_upload">Upload a dataset</span></button>'      +
      '<button class="daa-sug" type="button" data-prompt-key="sug_summarize">' +
      '<span data-i18n-chat="sug_summarize">Summarize this data</span></button>' +
      '<button class="daa-sug" type="button" data-prompt-key="sug_patterns">'  +
      '<span data-i18n-chat="sug_patterns">Find patterns in my file</span></button>';

    // Reassurance line — small, subtle, builds trust ("data stays on device")
    const reass = document.createElement('p');
    reass.className = 'daa-reassurance';
    reass.setAttribute('data-i18n-chat', 'chat_reassurance');
    reass.textContent = 'Your data stays on this device';

    // Insert: title above the anchor, then suggestions → reassurance after.
    // No secondary suggestion sections — strict hierarchy ends at the
    // reassurance line per spec.
    anchor.parentNode.insertBefore(blank, anchor);
    if (anchor.nextSibling) {
      anchor.parentNode.insertBefore(sugs,  anchor.nextSibling);
      anchor.parentNode.insertBefore(reass, sugs.nextSibling);
    } else {
      anchor.parentNode.appendChild(sugs);
      anchor.parentNode.appendChild(reass);
    }

    // Click handler. For data-action="upload" we trigger Open WebUI's
    // own file picker; for everything else we drop the prompt text
    // into TipTap (ProseMirror) via execCommand so the editor registers
    // it as a real input.
    sugs.querySelectorAll('.daa-sug').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const action = btn.dataset.action;

        if (action === 'upload') {
          if (triggerFileUpload()) return;
          // If we couldn't find Open WebUI's upload trigger, fall through
          // to inserting the prompt text as a fallback.
        }

        const lang = document.documentElement.lang || 'en';
        const key  = btn.dataset.promptKey;
        const text = (T[lang] && T[lang][key]) || T.en[key] || '';
        const editor = findChatInput();
        if (!editor) return;

        editor.focus();
        setTimeout(function () {
          try {
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(editor);
            sel.removeAllRanges();
            sel.addRange(range);
            document.execCommand('insertText', false, text);
          } catch (err) {
            editor.innerHTML = '<p>' + text.replace(/[&<>]/g, '') + '</p>';
            editor.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }, 10);
      });
    });

    // Activate CSS rules that hide Open WebUI's default greeting + suggestions.
    document.body.classList.add('daa-custom-blank');

    // Hide any Open WebUI sibling content (greeting, default suggestions, etc.)
    hideOpenWebUISiblings();
    hideDefaultSuggestionsContainer();

    // Apply current language to the new elements
    let saved = 'en';
    try { saved = localStorage.getItem(STORAGE_KEY) || 'en'; } catch (e) {}
    applyLang(saved);
  }

  function tearDownChatBlank() {
    const blank = document.querySelector('.daa-blank');
    const sugs  = document.querySelector('.daa-suggestions');
    if (blank) blank.remove();
    if (sugs)  sugs.remove();
    document.body.classList.remove('daa-custom-blank');
  }

  // ---------- Initialization ----------
  // If the toggle is currently in fallback-fixed mode but the header
  // container has since rendered, move it into the header.
  function rehomeToggleIfNeeded() {
    const toggle = document.querySelector('.lang-toggle');
    if (!toggle) return;
    if (toggle.parentElement !== document.body) return; // already in header
    const header = findHeaderContainer();
    if (!header) return;
    // Clear the fallback inline positioning before re-homing
    toggle.style.position = '';
    toggle.style.top      = '';
    toggle.style.right    = '';
    toggle.style.zIndex   = '';
    header.insertBefore(toggle, header.firstChild);
  }

  function init() {
    injectToggle();
    rehomeToggleIfNeeded();

    if (isAuthPage()) {
      injectRichBadge();
    } else if (findChatInput()) {
      injectChatBlank();
      hideOpenWebUISiblings();
      hideDefaultSuggestionsContainer();
    }

    let saved = 'en';
    try { saved = localStorage.getItem(STORAGE_KEY) || 'en'; } catch (e) {}
    applyLang(saved);
  }

  // ---------- Mount ----------
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // SvelteKit re-renders pages asynchronously — watch + re-apply.
  // Throttle so we don't spam on every DOM mutation.
  let pending = false;
  const observer = new MutationObserver(function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      init();
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
