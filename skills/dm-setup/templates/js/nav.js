// Floating top nav — sessions dropdown + People & Places link.
// Injects #site-nav into <body> on DOMContentLoaded.
// Reads sessions.json from the current campaign directory.

async function buildNav() {
  const current = location.pathname.split('/').pop();

  // ── Load session list ───────────────────────────────────────────────────────
  let SESSIONS = [];
  let AUDIO_ENABLED = false;
  try {
    const resp = await fetch('sessions.json', { cache: 'no-cache' });
    if (resp.ok) {
      const data = await resp.json();
      // Support both array format and {audioEnabled, sessions} object format
      if (Array.isArray(data)) {
        SESSIONS = data;
      } else {
        SESSIONS = data.sessions || [];
        AUDIO_ENABLED = data.audioEnabled === true;
      }
    }
  } catch {
    // sessions.json missing or malformed — nav renders without session list
  }
  // Expose audioEnabled for audio.js
  window.CAMPAIGN_AUDIO_ENABLED = AUDIO_ENABLED;

  // ── Dropdown items ──────────────────────────────────────────────────────────
  const items = SESSIONS.map(s => {
    const isActive = s.file === current;
    return `<a class="nav-dropdown-item${isActive ? ' active' : ''}" href="${s.file}">
      <span class="nav-session-number">Session ${s.number}</span>
      <span class="nav-session-title">${s.title}</span>
      <span class="nav-session-subtitle">${s.subtitle}</span>
    </a>`;
  }).join('');

  // ── Label shown on the dropdown button ─────────────────────────────────────
  const active = SESSIONS.find(s => s.file === current);
  const label  = active ? `Session ${active.number} — ${active.title}` : 'Sessions';

  // ── Nav HTML ────────────────────────────────────────────────────────────────
  const nav = document.createElement('nav');
  nav.id = 'site-nav';
  nav.innerHTML = `
    <div class="nav-left">
      <a class="nav-campaign" href="../index.html">Campaigns</a>
      <div class="nav-dropdown-wrap" id="nav-sessions-wrap">
        <button class="nav-dropdown-btn" id="nav-sessions-btn" aria-haspopup="true" aria-expanded="false">
          ${label} <span class="nav-arrow">▾</span>
        </button>
        <div class="nav-dropdown" id="nav-sessions-dropdown" role="menu">
          ${items}
        </div>
      </div>
    </div>
    <div class="nav-right">
      <a class="nav-link" href="world.html">People &amp; Places</a>
    </div>`;

  document.body.prepend(nav);

  // ── Dropdown toggle ─────────────────────────────────────────────────────────
  const btn      = document.getElementById('nav-sessions-btn');
  const dropdown = document.getElementById('nav-sessions-dropdown');

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    dropdown.classList.toggle('open', !open);
  });

  document.addEventListener('click', () => {
    btn.setAttribute('aria-expanded', 'false');
    dropdown.classList.remove('open');
  });

  dropdown.addEventListener('click', e => e.stopPropagation());

  // ── Prev/next footer (session pages only) ──────────────────────────────────
  if (!active) return;
  const idx  = SESSIONS.indexOf(active);
  const prev = SESSIONS[idx - 1];
  const next = SESSIONS[idx + 1];
  if (!prev && !next) return;

  const footer = document.createElement('div');
  footer.id = 'session-footer';
  footer.innerHTML = `
    <div class="session-footer-prev">
      ${prev ? `<a href="${prev.file}">← Session ${prev.number} — ${prev.title}</a>` : ''}
    </div>
    <div class="session-footer-next">
      ${next ? `<a href="${next.file}">Session ${next.number} — ${next.title} →</a>` : ''}
    </div>`;
  document.body.appendChild(footer);
}

document.addEventListener('DOMContentLoaded', buildNav);

// ── Chapter TOC toggle + scroll-spy ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toc = document.getElementById('chapter-toc');
  if (!toc) return;

  // Toggle open/close on narrow viewports
  const toggleBtn = document.getElementById('toc-toggle');
  const closeBtn  = document.getElementById('toc-close');

  if (toggleBtn) {
    toggleBtn.addEventListener('click', e => {
      e.stopPropagation();
      toc.classList.toggle('open');
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', () => toc.classList.remove('open'));
  }

  // Close when a chapter link is clicked (navigates away from the button)
  toc.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', () => toc.classList.remove('open'));
  });

  // Close when clicking outside the TOC
  document.addEventListener('click', e => {
    if (!toc.contains(e.target)) toc.classList.remove('open');
  });

  // Scroll-spy — highlights active chapter link
  const links    = Array.from(toc.querySelectorAll('a[href^="#"]'));
  const headings = links.map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
  if (!headings.length) return;

  function updateActive() {
    const scrollY = window.scrollY + 80;
    let active = headings[0];
    for (const h of headings) {
      if (h.offsetTop <= scrollY) active = h;
    }
    links.forEach(a => a.classList.toggle('toc-active', a.getAttribute('href') === '#' + active.id));
  }

  window.addEventListener('scroll', updateActive, { passive: true });
  updateActive();
});
