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

  function renderCard(card) {
    const div = el("div", { class: "card", id: card.id });

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
    for (const para of (card.body || [])) {
      const p = document.createElement("p");
      p.innerHTML = para;
      content.appendChild(p);
    }
    body.appendChild(content);
    div.appendChild(body);

    return div;
  }

  function renderSection(section) {
    const frag = document.createDocumentFragment();
    const h2 = el("h2", { id: section.id });
    h2.textContent = section.title;
    frag.appendChild(h2);
    for (const card of section.cards) {
      frag.appendChild(renderCard(card));
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
      const r = await fetch(jsonPath);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      world = await r.json();
    } catch (e) {
      root.innerHTML = `<p style="color:red">Failed to load world.json: ${e.message}</p>`;
      return;
    }

    for (const section of world.sections) {
      root.appendChild(renderSection(section));
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
