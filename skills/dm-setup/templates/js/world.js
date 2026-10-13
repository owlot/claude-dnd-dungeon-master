(() => {
  // ── Render world.json into #world-root ──────────────────────────────────────

  const TAG_LABELS = {
    "tag-ally":    "Ally",
    "tag-enemy":   "Enemy",
    "tag-neutral": "Neutral",
    "tag-unknown": "Unknown",
    "tag-visited": "Visited",
    "tag-location":"Location",
    "tag-dead":    "Dead",
  };

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    }
    for (const child of children) {
      if (typeof child === "string") node.appendChild(document.createTextNode(child));
      else if (child) node.appendChild(child);
    }
    return node;
  }

  // ── Party-view cards (places / objects) ────────────────────────────────────
  // world-public.json holds only what the party knows; see export_world_public.py.

  function factRows(pub) {
    const rows = pub.holder !== undefined
      ? [["Held by", pub.holder], ["Where", pub.location], ["Status", pub.status]]
      : [["State", pub.state], ["Detail", pub.detail]];
    if (pub.last_changed_session) rows.push(["Last changed", `Session ${pub.last_changed_session}`]);
    return rows.filter(([, v]) => v);
  }

  function renderFacts(pub) {
    const dl = el("dl", { class: "card-facts" });
    for (const [k, v] of factRows(pub)) {
      const dt = el("dt", {});
      dt.textContent = k;
      const dd = el("dd", {});
      dd.textContent = v;
      dl.appendChild(dt);
      dl.appendChild(dd);
    }
    return dl;
  }

  function historyLine(h) {
    const parts = h.holder !== undefined
      ? [h.holder, h.location, h.status]
      : [h.state, h.detail];
    return parts.filter(Boolean).join(" · ");
  }

  function renderHistory(pub) {
    const hist = (pub.history || []).slice().reverse();
    if (!hist.length) return null;
    const details = el("details", { class: "card-history" });
    const summary = el("summary", {});
    summary.textContent = `History (${hist.length})`;
    details.appendChild(summary);
    const ol = el("ol", { class: "card-history-list" });
    for (const h of hist) {
      const li = el("li", {});
      const head = el("div", { class: "hist-head" });
      head.textContent = h.when ? `Session ${h.session} · ${h.when}` : `Session ${h.session}`;
      const ev = el("div", { class: "hist-event" });
      ev.textContent = h.event;
      li.appendChild(head);
      li.appendChild(ev);
      const st = historyLine(h);
      if (st) {
        const stEl = el("div", { class: "hist-state" });
        stEl.textContent = st;
        li.appendChild(stEl);
      }
      ol.appendChild(li);
    }
    details.appendChild(ol);
    return details;
  }

  function renderCard(card, pub) {
    const div = el("div", { class: "card", id: card.id });
    if (pub) {
      card = Object.assign({}, card, {
        name: pub.name,
        meta: pub.holder !== undefined ? pub.holder : pub.state,
        tags: [pub.tag],
      });
    }

    // Header
    const header = el("div", { class: "card-header" });
    const nameSpan = el("span", { class: "card-name" });
    const nameAnchor = el("a", {});
    nameAnchor.textContent = card.name;
    nameSpan.appendChild(nameAnchor);
    header.appendChild(nameSpan);

    if (card.meta) {
      const metaSpan = el("span", { class: "card-meta" });
      metaSpan.textContent = card.meta;
      header.appendChild(metaSpan);
    }

    for (const tag of (card.tags || [])) {
      const tagSpan = el("span", { class: `tag ${tag}` });
      tagSpan.textContent = TAG_LABELS[tag] || tag.replace("tag-", "");
      header.appendChild(tagSpan);
    }

    div.appendChild(header);

    // Body
    const body = el("div", { class: "card-body" });

    if (card.portrait) {
      const img = el("img", {
        class: "card-portrait",
        src: card.portrait,
        alt: card.name,
      });
      body.appendChild(img);
    }

    if (card.place) {
      const img = el("img", {
        class: "card-place",
        src: card.place,
        alt: card.name,
      });
      body.appendChild(img);
    }

    const content = el("div", { class: "card-body-content" });
    if (pub) {
      const paras = (pub.description && pub.description.length) ? pub.description : (pub.what ? [pub.what] : []);
      for (const text of paras) {
        const p = document.createElement("p");
        p.textContent = text;
        content.appendChild(p);
      }
      content.appendChild(renderFacts(pub));
      const hist = renderHistory(pub);
      if (hist) content.appendChild(hist);
    } else {
      for (const para of (card.body || [])) {
        const p = document.createElement("p");
        p.innerHTML = para;
        content.appendChild(p);
      }
    }
    body.appendChild(content);
    div.appendChild(body);

    return div;
  }

  function renderSection(section, pubIndex) {
    const frag = document.createDocumentFragment();
    const h2 = el("h2", { id: section.id });
    h2.textContent = section.title;
    frag.appendChild(h2);
    const usesPublic = section.id === "section-places" || section.id === "section-objects";
    for (const card of section.cards) {
      const pub = usesPublic ? pubIndex[card.public || card.id] : null;
      frag.appendChild(renderCard(card, pub));
    }
    return frag;
  }

  // ── Search & interaction ────────────────────────────────────────────────────

  function initSearch(root) {
    const input = document.getElementById("world-search");
    if (!input) return;

    function escapeRe(s) {
      return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function clearHighlights(root) {
      root.querySelectorAll("mark").forEach(mark => {
        mark.replaceWith(document.createTextNode(mark.textContent));
      });
    }

    function highlightNode(card, q) {
      const re = new RegExp(`(${escapeRe(q)})`, "gi");
      const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, {
        acceptNode: n => {
          const p = n.parentElement;
          if (p.tagName === "SCRIPT") return NodeFilter.FILTER_REJECT;
          if (p.closest(".voice-play-btn")) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      const textNodes = [];
      let n;
      while ((n = walker.nextNode())) textNodes.push(n);
      textNodes.forEach(node => {
        if (!re.test(node.textContent)) return;
        re.lastIndex = 0;
        const span = document.createElement("span");
        span.innerHTML = node.textContent.replace(re, "<mark>$1</mark>");
        node.parentNode.replaceChild(span, node);
      });
    }

    function attachCardListeners() {
      root.querySelectorAll(".card-header").forEach(header => {
        header.addEventListener("click", () => {
          header.closest(".card").classList.toggle("open");
        });
      });
    }
    attachCardListeners();

    input.addEventListener("input", () => {
      const q = input.value.trim();
      const ql = q.toLowerCase();

      clearHighlights(root);

      root.querySelectorAll(".card").forEach(card => {
        const match = !q || card.textContent.toLowerCase().includes(ql);
        card.style.display = match ? "" : "none";
        if (q) {
          card.classList.toggle("open", match);
          if (match) highlightNode(card, q);
        } else {
          card.classList.remove("open");
        }
      });

      root.querySelectorAll("h2").forEach(h2 => {
        let el = h2.nextElementSibling;
        let anyVisible = false;
        while (el && el.tagName !== "H2") {
          if (el.classList.contains("card") && el.style.display !== "none")
            anyVisible = true;
          el = el.nextElementSibling;
        }
        h2.style.display = anyVisible || !q ? "" : "none";
      });
    });
  }

  function openFromHash(root) {
    const id = location.hash.slice(1);
    if (!id) return;
    const card = root.querySelector(`#${CSS.escape(id)}`);
    if (card && card.classList.contains("card")) {
      card.classList.add("open");
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // ── Boot ───────────────────────────────────────────────────────────────────

  async function init() {
    const root = document.getElementById("world-root");
    if (!root) return;

    // Derive world.json path relative to current page
    const jsonPath = "world.json";
    let world;
    try {
      const r = await fetch(jsonPath, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      world = await r.json();
    } catch (e) {
      root.innerHTML = `<p style="color:red">Failed to load world.json: ${e.message}</p>`;
      return;
    }

    // Party-view data for places and objects (optional; cards fall back to world.json)
    const pubIndex = {};
    try {
      const pr = await fetch("world-public.json", { cache: "no-store" });
      if (pr.ok) {
        const pub = await pr.json();
        for (const e of [...(pub.places || []), ...(pub.objects || [])]) pubIndex[e.id] = e;
      }
    } catch (e) { /* no world-public.json: render world.json as-is */ }

    for (const section of world.sections) {
      root.appendChild(renderSection(section, pubIndex));
    }

    initSearch(root);
    openFromHash(root);
    window.addEventListener("hashchange", () => openFromHash(root));

    // Re-init lightbox if available
    if (typeof window.initLightbox === "function") window.initLightbox();

    // Trigger audio voice buttons
    if (typeof window.addVoiceButtons === "function") window.addVoiceButtons();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
