// ── Audio player for session pages and world.html ─────────────────────────────
//
// Session pages: adds a 🔊 button to each <h2> and a sticky bottom player bar.
// World.html: adds a voice intro button to each character card.
//
// Playback queue: all play buttons on the page in document order.
// Auto-advances to the next button when a track ends (chapters + memoirs).
//
// Controlled by window.CAMPAIGN_AUDIO_ENABLED (set by nav.js from sessions.json).

(function () {

  // ── State ──────────────────────────────────────────────────────────────────

  const player = new Audio();
  let activeBtn = null;
  let playerBar = null;
  let progressTimer = null;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function allPlayButtons() {
    return Array.from(document.querySelectorAll(".audio-play-btn[data-src]"));
  }

  function nextButton(btn) {
    const all = allPlayButtons();
    const idx = all.indexOf(btn);
    return idx >= 0 && idx < all.length - 1 ? all[idx + 1] : null;
  }

  function formatTime(secs) {
    if (!isFinite(secs)) return "0:00";
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  // ── Player bar ─────────────────────────────────────────────────────────────

  function createPlayerBar() {
    const bar = document.createElement("div");
    bar.id = "audio-player-bar";
    bar.innerHTML = `
      <div class="apb-left">
        <button class="apb-btn" id="apb-prev" title="Previous">&#9664;&#9664;</button>
        <button class="apb-btn" id="apb-playpause" title="Play/Pause">&#9646;&#9646;</button>
        <button class="apb-btn" id="apb-next" title="Next">&#9654;&#9654;</button>
      </div>
      <div class="apb-center">
        <div class="apb-title" id="apb-title">—</div>
        <div class="apb-scrubber-wrap">
          <span class="apb-time" id="apb-current">0:00</span>
          <input type="range" id="apb-scrubber" min="0" max="100" value="0" step="0.1">
          <span class="apb-time" id="apb-duration">0:00</span>
        </div>
      </div>
      <div class="apb-right">
        <button class="apb-btn" id="apb-stop" title="Stop">&#9632;</button>
      </div>`;
    document.body.appendChild(bar);

    document.getElementById("apb-playpause").addEventListener("click", togglePause);
    document.getElementById("apb-stop").addEventListener("click", stop);
    document.getElementById("apb-prev").addEventListener("click", playPrev);
    document.getElementById("apb-next").addEventListener("click", playNext);

    const scrubber = document.getElementById("apb-scrubber");
    scrubber.addEventListener("input", () => {
      if (isFinite(player.duration)) {
        player.currentTime = (scrubber.value / 100) * player.duration;
      }
    });

    return bar;
  }

  function updateBar() {
    if (!playerBar) return;
    const title = document.getElementById("apb-title");
    const current = document.getElementById("apb-current");
    const duration = document.getElementById("apb-duration");
    const scrubber = document.getElementById("apb-scrubber");
    const playpause = document.getElementById("apb-playpause");

    if (activeBtn) {
      title.textContent = activeBtn.dataset.label || "—";
      playpause.innerHTML = player.paused ? "&#9654;" : "&#9646;&#9646;";
    }
    if (isFinite(player.duration) && player.duration > 0) {
      scrubber.value = (player.currentTime / player.duration) * 100;
      current.textContent = formatTime(player.currentTime);
      duration.textContent = formatTime(player.duration);
    }
  }

  function showBar() {
    if (!playerBar) playerBar = createPlayerBar();
    playerBar.classList.add("visible");
  }

  function hideBar() {
    if (playerBar) playerBar.classList.remove("visible");
  }

  // ── Playback ───────────────────────────────────────────────────────────────

  function play(btn) {
    // Deactivate previous button
    if (activeBtn && activeBtn !== btn) {
      activeBtn.classList.remove("playing");
    }

    activeBtn = btn;
    player.src = btn.dataset.src;
    player.play().then(() => {
      btn.classList.add("playing");
      showBar();
      updateBar();
      clearInterval(progressTimer);
      progressTimer = setInterval(updateBar, 500);
    }).catch(() => {
      // File not found — try advancing
      advance();
    });
  }

  function stop() {
    player.pause();
    player.currentTime = 0;
    if (activeBtn) {
      activeBtn.classList.remove("playing");
      activeBtn = null;
    }
    clearInterval(progressTimer);
    hideBar();
  }

  function togglePause() {
    if (!activeBtn) return;
    if (player.paused) {
      player.play();
      activeBtn.classList.add("playing");
    } else {
      player.pause();
      activeBtn.classList.remove("playing");
    }
    updateBar();
  }

  function advance() {
    if (!activeBtn) return;
    const next = nextButton(activeBtn);
    if (next) {
      play(next);
    } else {
      stop();
    }
  }

  function playPrev() {
    if (!activeBtn) return;
    const all = allPlayButtons();
    const idx = all.indexOf(activeBtn);
    if (idx > 0) play(all[idx - 1]);
  }

  function playNext() {
    if (!activeBtn) return;
    const next = nextButton(activeBtn);
    if (next) play(next);
  }

  player.addEventListener("ended", advance);
  player.addEventListener("timeupdate", updateBar);

  // Expose for memoir.js
  window.chapterAudioStop = stop;
  window.audioPlay = play;

  // ── Button factory ─────────────────────────────────────────────────────────

  function makePlayBtn(src, label, size = 14) {
    const btn = document.createElement("button");
    btn.className = "audio-play-btn";
    btn.dataset.src = src;
    btn.dataset.label = label;
    btn.title = "Play";
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="${size}" height="${size}">
      <path class="icon-play"  d="M8 5v14l11-7z"/>
      <path class="icon-pause" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" style="display:none"/>
    </svg>`;
    btn.addEventListener("click", () => {
      if (activeBtn === btn) {
        togglePause();
      } else {
        play(btn);
      }
    });
    return btn;
  }

  // ── Chapter buttons ────────────────────────────────────────────────────────

  function sessionFromPath() {
    return location.pathname.split("/").pop().replace(".html", "");
  }

  function chapterSlug(h2) {
    const text = h2.textContent.trim().replace(/^[IVXLC]+\.\s*/i, "");
    return text.toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
  }

  function addChapterButtons() {
    const session = sessionFromPath();
    document.querySelectorAll(".container h2").forEach((h2, idx) => {
      const src = h2.dataset.audio
        ? `audio/${session}/${h2.dataset.audio}`
        : `audio/${session}/${String(idx + 1).padStart(2, "0")}-${chapterSlug(h2)}.mp3`;

      const label = h2.textContent.trim().replace(/^[IVXLC]+\.\s*/i, "");
      const btn = makePlayBtn(src, label, 14);
      h2.appendChild(btn);
    });

    // Add continuation buttons on mid-scene breaks — visible so users can
    // trigger the second half manually; also picked up by auto-advance in
    // document order after the preceding memoir finishes.
    document.querySelectorAll(".container .scene-break[data-audio]").forEach(br => {
      const src = `audio/${session}/${br.dataset.audio}`;
      fetch(src, { method: "HEAD" }).then(r => {
        if (!r.ok) return;
        const btn = makePlayBtn(src, br.dataset.audio.replace(/\.mp3$/, ""), 14);
        br.appendChild(btn);
      }).catch(() => {});
    });
  }

  // ── Voice buttons (world.html) ─────────────────────────────────────────────

  function addVoiceButtons() {
    fetch("audio/introductions/index.json")
      .then(r => r.ok ? r.json() : [])
      .then(slugs => {
        const slugSet = new Set(slugs);
        document.querySelectorAll(".card").forEach(card => {
          const slug = card.id;
          if (!slug || !slugSet.has(slug)) return;
          const anchor = card.querySelector(".card-name a");
          if (!anchor) return;
          const src = `audio/introductions/${slug}.wav`;
          const btn = makePlayBtn(src, anchor.textContent.trim(), 12);
          btn.className += " voice-play-btn";
          anchor.parentElement.appendChild(btn);
        });
      })
      .catch(() => {});
  }

  // ── Init ───────────────────────────────────────────────────────────────────

  function initAudio() {
    const page = location.pathname.split("/").pop();
    if (!window.CAMPAIGN_AUDIO_ENABLED) return;
    if (/^session-\d+\.html$/.test(page)) {
      addChapterButtons();
    } else if (page === "world.html") {
      addVoiceButtons();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    let attempts = 0;
    const check = setInterval(() => {
      attempts++;
      if (window.CAMPAIGN_AUDIO_ENABLED !== undefined) {
        clearInterval(check);
        initAudio();
      } else if (attempts > 20) {
        clearInterval(check);
      }
    }, 100);
  });

})();
