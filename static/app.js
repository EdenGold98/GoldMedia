// static/app.js

document.addEventListener('DOMContentLoaded', () => {
  console.log('[app.js] DOMContentLoaded — wiring UI');

  // ============================================================
  // Element refs (must match index.html)
  // ============================================================
  const navPanel = document.getElementById('folder-tree');
  const contentPanel = document.getElementById('media-grid');
  const currentFolderTitle = document.getElementById('current-folder-title');

  const videoOverlay = document.getElementById('video-player-overlay');
  const videoPlayer  = document.getElementById('video-player');

  const controlsContainer   = document.getElementById('custom-controls-container');
  const playPauseBtn        = document.getElementById('play-pause-btn');
  const backToBrowseBtn     = document.getElementById('back-to-browse-btn');

  const progressBarContainer = document.querySelector('.progress-bar-container');
  const progressBarFilled    = document.getElementById('progress-bar-filled');
  const progressBarHover     = document.getElementById('progress-bar-hover');
  const progressBarTooltip   = document.getElementById('progress-bar-tooltip');

  const volumeSlider = document.getElementById('volume-slider');
  const volumeIcon   = document.getElementById('volume-icon');

  const currentTimeEl = document.getElementById('current-time');
  const durationEl    = document.getElementById('duration');

  const settingsPanel     = document.getElementById('settings-panel');
  const settingsBtn       = document.getElementById('settings-btn');
  const closeSettingsBtn  = document.getElementById('close-settings-button');
  const fullscreenBtn     = document.getElementById('fullscreen-btn');
  const refreshNavBtn     = document.getElementById('refresh-nav-btn');

  const subtitleStyler = document.getElementById('subtitle-styler');

  // Quick sanity log so we know we’re on the right page/file
  console.log('[app.js] Elements:', {
    videoOverlay: !!videoOverlay, videoPlayer: !!videoPlayer,
    progressBarContainer: !!progressBarContainer,
    progressBarFilled: !!progressBarFilled, currentTimeEl: !!currentTimeEl, durationEl: !!durationEl
  });

  // Ensure iOS/Safari keeps video inline & eligible for fullscreen
  videoPlayer.setAttribute('playsinline', '');
  videoPlayer.setAttribute('webkit-playsinline', '');

  // ============================================================
  // State
  // ============================================================
  let controlsTimeout;
  let firstSubtitleEnabled = false;
  let originalCues = [];

  // ============================================================
  // Helpers
  // ============================================================
  function formatTime(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || isNaN(totalSeconds)) return '00:00';
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = Math.floor(totalSeconds % 60);
    const mm = String(m).padStart(2, '0');
    const ss = String(s).padStart(2, '0');
    return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
  }
  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function storeOriginalCues() {
    originalCues = [];
    for (const track of videoPlayer.textTracks) {
      const cueList = [];
      if (track.cues) for (const cue of track.cues) cueList.push({ start: cue.startTime, end: cue.endTime });
      originalCues.push(cueList);
    }
  }
  function applySubtitleDelay(delay) {
    if (!originalCues.length) return;
    for (let i = 0; i < videoPlayer.textTracks.length; i++) {
      const track = videoPlayer.textTracks[i];
      if (track.cues) for (let j = 0; j < track.cues.length; j++) {
        const base = originalCues[i][j];
        if (base) { track.cues[j].startTime = base.start + delay; track.cues[j].endTime = base.end + delay; }
      }
    }
  }
  function applySubtitleStyle(size, color) {
    subtitleStyler.innerHTML = `::cue { will-change: contents; font-size:${size}%; color:${color}!important; background-color:rgba(0,0,0,.7)!important; }`;
  }

  // ============================================================
  // Navigation / Library
  // ============================================================
  async function initializeNav() {
    try {
      const res = await fetch('/api/get_structure');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const structure = await res.json();
      navPanel.innerHTML = createTreeHTML(structure);
      navPanel.querySelectorAll('a[data-path]').forEach(link => {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          const path = e.currentTarget.dataset.path;
          loadContent(path);
          updateNavSelection(path);
        });
      });
    } catch (err) {
      console.error('Error loading library tree:', err);
      navPanel.innerHTML = "<p style='color:red'>Error loading library.</p>";
    }
  }
  function createTreeHTML(nodes) {
    if (!nodes?.length) return '';
    let html = '<ul>';
    nodes.forEach(node => {
      const normalizedPath = node.path.replace(/\\/g, '/');
      html += `<li><a href="#" data-path="${normalizedPath}">${node.name}</a>`;
      if (node.children?.length) html += createTreeHTML(node.children);
      html += '</li>';
    });
    html += '</ul>';
    return html;
  }
  function updateNavSelection(path) {
    const norm = (path || '').replace(/\\/g, '/');
    navPanel.querySelectorAll('a').forEach(a => a.classList.remove('currently-selected'));
    navPanel.querySelectorAll('li').forEach(li => li.classList.remove('active-branch'));
    const active = navPanel.querySelector(`a[data-path="${norm.replace(/\"/g, '\\"')}"]`);
    if (active) {
      active.classList.add('currently-selected');
      let parentLi = active.closest('li');
      while (parentLi) { parentLi.classList.add('active-branch'); parentLi = parentLi.parentElement.closest('li'); }
    }
  }
  async function loadContent(path) {
    try {
      const normalizedPath = path ? path.replace(/\\/g, '/') : '';
      const url = normalizedPath ? `/api/browse/${encodeURIComponent(normalizedPath)}` : '/api/browse/';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      let html = '';
      const isAtRoot = !normalizedPath || data.folders.some(f => f.path.replace(/\\/g, '/') === normalizedPath);

      if (!isAtRoot) {
        let parentPath = normalizedPath.substring(0, normalizedPath.lastIndexOf('/'));
        if (!parentPath.includes('/')) parentPath = '';
        html += `<div class="media-card folder go-back" data-path="${parentPath}">
                  <div class="card-icon">↩️</div><h3>Go Back</h3>
                </div>`;
      }
      data.folders.forEach(folder => {
        html += `<div class="media-card folder" data-path="${folder.path.replace(/\\/g, '/')}">
                  <div class="card-icon">📁</div><div class="card-content"><h3>${folder.name}</h3></div>
                </div>`;
      });
      data.files.forEach(file => {
        html += `<div class="media-card video" data-path="${file.path.replace(/\\/g, '/')}">
                  <div class="card-thumbnail" data-thumb-hash="${file.thumb_hash}"></div>
                  <div class="card-content"><h3>${file.name}</h3></div>
                </div>`;
      });

      contentPanel.innerHTML = html;
      contentPanel.querySelectorAll('.card-thumbnail').forEach(loadThumbnail);

      currentFolderTitle.textContent = path ? path.split(/[\\/]/).pop() : 'Home';

      if (window.history.state?.path !== normalizedPath) {
        history.pushState({ path: normalizedPath }, '', `?path=${encodeURIComponent(normalizedPath) || ''}`);
      }

      bindContentListeners();
    } catch (err) {
      console.error('Failed to load content:', path, err);
    }
  }
  function loadThumbnail(thumbDiv) {
    const thumbHash = thumbDiv.dataset.thumbHash;
    if (!thumbHash) return;
    const url = `/static/.thumbnails/${thumbHash}.jpg`;
    const img = new Image();
    img.src = url;
    img.onload = () => { thumbDiv.style.backgroundImage = `url(${url})`; };
    img.onerror = () => pollForThumbnail(thumbDiv, thumbHash);
  }
  function pollForThumbnail(thumbDiv, thumbHash) {
    const pollInterval = 3000, maxPolls = 10;
    let count = 0;
    const id = setInterval(async () => {
      if (count++ >= maxPolls) return clearInterval(id);
      try {
        const res = await fetch(`/api/check_thumb/${thumbHash}`);
        if (res.ok) {
          const data = await res.json();
          if (data.status === 'ready') {
            clearInterval(id);
            const url = `/static/.thumbnails/${thumbHash}.jpg`;
            thumbDiv.style.backgroundImage = `url(${url})`;
          }
        }
      } catch {}
    }, pollInterval);
  }

  function bindContentListeners() {
    // Request fullscreen synchronously on user gesture (before awaits)
    contentPanel.querySelectorAll('.video').forEach(el => {
      el.addEventListener('click', async () => {
        const path = el.dataset.path;
        videoOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        try { await (videoOverlay.requestFullscreen?.() || Promise.resolve()); } catch(e){}

        await playVideo(path);
      });
    });
    contentPanel.querySelectorAll('.folder').forEach(el => {
      el.addEventListener('click', () => {
        const newPath = el.dataset.path;
        loadContent(newPath);
        updateNavSelection(newPath);
      });
    });
  }

  // ============================================================
  // Player
  // ============================================================
  async function playVideo(path) {
    videoPlayer.innerHTML = '';       // clear old <track>s
    firstSubtitleEnabled = false;

    try {
      const trackRes = await fetch(`/api/get_tracks/${encodeURIComponent(path)}`);
      const trackData = await trackRes.json();
      populateTrackSelectors(trackData);
    } catch (e) {
      console.warn('Failed to load tracks:', e);
    }

    videoPlayer.src = `/stream/${encodeURIComponent(path)}`;
    try { await videoPlayer.play(); } catch (e) { console.warn('Autoplay may be blocked:', e); }

    // Make sure clocks are running for this new media
    ensureRAF();
    updateProgressOnce();
  }

  function populateTrackSelectors(trackData) {
    const audioSelect = document.getElementById('audio-track-select');
    const subtitleSelect = document.getElementById('subtitle-track-select');

    audioSelect.innerHTML = '';
    subtitleSelect.innerHTML = '<option value="off">Off</option>';

    if (trackData?.audio?.length) {
      trackData.audio.forEach(t => audioSelect.add(new Option(`${t.lang} - ${t.label}`, t.id)));
    }
    if (trackData?.subtitles?.length) {
      firstSubtitleEnabled = false;
      trackData.subtitles.forEach((sub, idx) => {
        const trackEl = document.createElement('track');
        trackEl.kind = 'subtitles';
        trackEl.label = sub.label;
        trackEl.srclang = (/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(sub.lang) ? sub.lang : 'en');
        trackEl.src = sub.path.startsWith('/') ? sub.path : `/subtitle/${encodeURIComponent(sub.path)}`;
        if (idx === 0) trackEl.setAttribute('default', '');

        trackEl.addEventListener('load', () => {
          const tracks = videoPlayer.textTracks;
          if (idx === 0 && tracks?.length && !firstSubtitleEnabled) {
            for (let i = 0; i < tracks.length; i++) tracks[i].mode = 'hidden';
            tracks[idx].mode = 'showing';
            subtitleSelect.value = String(idx);
            firstSubtitleEnabled = true;
            storeOriginalCues();
          }
        });

        videoPlayer.appendChild(trackEl);
        subtitleSelect.add(new Option(sub.label, idx));
      });
    }
  }

  // Prevent overlay toggle when clicking controls/settings
  controlsContainer.addEventListener('click', e => e.stopPropagation());
  settingsPanel.addEventListener('click', e => e.stopPropagation());

  // Toggle playback when clicking the video area
  videoOverlay.addEventListener('click', () => {
    if (videoPlayer.paused) videoPlayer.play(); else videoPlayer.pause();
  });

  playPauseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (videoPlayer.paused) videoPlayer.play(); else videoPlayer.pause();
  });

  videoPlayer.addEventListener('play',   () => { playPauseBtn.textContent = '⏸️'; ensureRAF(); ensureFrameClock();});
  videoPlayer.addEventListener('pause',  () => { playPauseBtn.textContent = '▶️'; /* keep HUD running */ });
  videoPlayer.addEventListener('ended',  () => { /* nothing special */ });

  // Keyboard shortcuts (Space, F)
  document.addEventListener('keydown', (e) => {
    if (videoOverlay.classList.contains('hidden')) return;
    if (e.code === 'Space') { e.preventDefault(); videoPlayer.paused ? videoPlayer.play() : videoPlayer.pause(); }
    if (e.key.toLowerCase() === 'f') { toggleFullscreen(); }
  });
  fullscreenBtn.addEventListener('click', toggleFullscreen);
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else videoOverlay.requestFullscreen?.().catch(() => {});
  }
  backToBrowseBtn.addEventListener('click', () => {
    videoPlayer.pause();
    videoPlayer.src = '';
    videoOverlay.classList.add('hidden');
    settingsPanel.classList.add('hidden');
    document.body.style.overflow = 'auto';
    if (document.fullscreenElement) document.exitFullscreen();
    videoOverlay.style.cursor = 'default';
  });

  // Settings
  settingsBtn.addEventListener('click', () => settingsPanel.classList.toggle('hidden'));
  closeSettingsBtn?.addEventListener('click', (e) => { e.stopPropagation(); settingsPanel.classList.add('hidden'); });
  document.getElementById('subtitle-track-select').addEventListener('change', (e) => {
    const val = e.target.value;
    for (let i = 0; i < videoPlayer.textTracks.length; i++) videoPlayer.textTracks[i].mode = 'hidden';
    if (val !== 'off') videoPlayer.textTracks[parseInt(val, 10)].mode = 'showing';
  });
  document.getElementById('sub-size').addEventListener('input', (e) =>
    applySubtitleStyle(e.target.value, document.getElementById('sub-color').value)
  );
  document.getElementById('sub-color').addEventListener('input', (e) =>
    applySubtitleStyle(document.getElementById('sub-size').value, e.target.value)
  );
  document.getElementById('sub-delay').addEventListener('change', (e) =>
    applySubtitleDelay(parseFloat(e.target.value))
  );

  // ============================================================
    // PROGRESS/TIME — frame-driven clock (RVFC) + fallbacks
    // ============================================================
    const PROGRESS_INTERVAL_MS = 125; // ~8 Hz fallback
    
    let rafId = null;
    let frameReqId = null;
    let timeupdateCount = 0;
    let rafCount = 0;
    let lastMediaTime = 0;
    
    /*
    // Attach HUD *inside* the overlay so it's always on top of the video
    (function attachHUD() {
      if (!videoOverlay) return;
      const hud = document.createElement('div');
      hud.id = 'progress-debug-hud';
      Object.assign(hud.style, {
        position: 'absolute', left: '8px', bottom: '8px',
        zIndex: 2147483647, pointerEvents: 'none',
        font: '12px/1.2 monospace', background: 'rgba(0,0,0,.6)', color: '#0f0',
        padding: '6px 8px', borderRadius: '6px'
      });
      videoOverlay.appendChild(hud);
      setInterval(() => {
        const d = getDuration();
        hud.textContent = [
          `ct=${Number.isFinite(videoPlayer.currentTime)?videoPlayer.currentTime.toFixed(2):String(videoPlayer.currentTime)}`,
          `mt=${Number.isFinite(lastMediaTime)?lastMediaTime.toFixed(2):String(lastMediaTime)}`,
          `dur=${Number.isFinite(d)?d.toFixed(2):String(d)}`,
          `timeupdate/s=${timeupdateCount}`, `raf/s=${rafCount}`,
          `paused=${videoPlayer.paused}`, `ended=${videoPlayer.ended}`,
          `rvfc=${'requestVideoFrameCallback' in videoPlayer}`
        ].join(' | ');
        timeupdateCount = 0; rafCount = 0;
      }, 1000);
    })();
    */
    
    function getDuration() {
      const d = videoPlayer.duration;
      if (Number.isFinite(d) && d > 0) return d;
      const s = videoPlayer.seekable;
      if (s && s.length) { try { return s.end(s.length - 1); } catch {} }
      return NaN;
    }
    function clamp01(x){ return x < 0 ? 0 : x > 1 ? 1 : x; }
    
    // The one true updater — takes an explicit time 't' (mediaTime preferred)
    function updateProgressAt(t) {
      const dur = getDuration();
      const ct  = Number.isFinite(t) ? t : (Number.isFinite(lastMediaTime) ? lastMediaTime : 0);
    
      if (currentTimeEl) currentTimeEl.textContent = formatTime(ct);
      if (durationEl && Number.isFinite(dur)) durationEl.textContent = formatTime(dur);
    
      let pct = 0;
      if (Number.isFinite(dur) && dur > 0) pct = clamp01(ct / dur);
      if (progressBarFilled) {
        progressBarFilled.style.width = (pct * 100).toFixed(4) + '%';
        // nudge paints in stubborn stacks
        progressBarFilled.style.willChange = 'width';
        progressBarFilled.style.transform = 'translateZ(0)';
        void progressBarFilled.offsetWidth;
      }
    }
    
    // --- Frame clock (primary) ---
    function frameTick(now, metadata) {
      // metadata.mediaTime is the exact playhead time of the presented frame
      lastMediaTime = (metadata && Number.isFinite(metadata.mediaTime)) ? metadata.mediaTime : videoPlayer.currentTime;
      updateProgressAt(lastMediaTime);
      if (!videoPlayer.paused && !videoPlayer.ended) {
        frameReqId = videoPlayer.requestVideoFrameCallback(frameTick);
      } else {
        frameReqId = null;
      }
    }
    function ensureFrameClock() {
      if ('requestVideoFrameCallback' in videoPlayer && frameReqId === null) {
        frameReqId = videoPlayer.requestVideoFrameCallback(frameTick);
      }
    }
    function stopFrameClock() {
      if (frameReqId !== null && 'cancelVideoFrameCallback' in videoPlayer) {
        try { videoPlayer.cancelVideoFrameCallback(frameReqId); } catch {}
      }
      frameReqId = null;
    }
    
    // --- RAF (smooth fallback) ---
    function rafTick() { rafCount++; updateProgressAt(NaN); rafId = requestAnimationFrame(rafTick); }
    function ensureRAF() { if (rafId === null) rafId = requestAnimationFrame(rafTick); }
    function stopRAF()   { if (rafId !== null) cancelAnimationFrame(rafId); rafId = null; }
    
    // --- timeupdate (event fallback) ---
    videoPlayer.addEventListener('timeupdate', () => { timeupdateCount++; updateProgressAt(NaN); });
    
    // --- persistent safety interval (always runs) ---
    setInterval(() => { if (!videoPlayer.paused && !videoPlayer.ended) updateProgressAt(lastMediaTime || NaN); }, PROGRESS_INTERVAL_MS);
    
    // Keep clocks alive in common transitions
    ['playing','ratechange','seeked'].forEach(ev => videoPlayer.addEventListener(ev, () => {
      ensureFrameClock(); ensureRAF(); updateProgressAt(lastMediaTime || NaN);
    }));
    ['pause','ended'].forEach(ev => videoPlayer.addEventListener(ev, () => {
      stopFrameClock(); stopRAF(); updateProgressAt(lastMediaTime || NaN);
    }));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { ensureFrameClock(); ensureRAF(); } });
    ['fullscreenchange','webkitfullscreenchange','mozfullscreenchange','MSFullscreenChange']
      .forEach(ev => document.addEventListener(ev, () => { ensureFrameClock(); ensureRAF(); }));
    
    // Kick on metadata
    videoPlayer.addEventListener('loadedmetadata', () => {
      lastMediaTime = Number.isFinite(videoPlayer.currentTime) ? videoPlayer.currentTime : 0;
      updateProgressAt(lastMediaTime);
      ensureFrameClock();
      ensureRAF();
    });
    
    // Seek & hover use the same duration getter so % matches the clocks
    progressBarContainer?.addEventListener('click', (e) => {
      const dur = getDuration();
      if (Number.isFinite(dur) && dur > 0) {
        const rect = progressBarContainer.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        videoPlayer.currentTime = (clickX / rect.width) * dur;
        lastMediaTime = videoPlayer.currentTime;
        updateProgressAt(lastMediaTime);
      }
    });
    progressBarContainer?.addEventListener('mousemove', (e) => {
      const dur = getDuration();
      if (!Number.isFinite(dur) || dur <= 0) return;
      const rect = progressBarContainer.getBoundingClientRect();
      const hoverX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      const pct = hoverX / rect.width;
      const t = pct * dur;
      if (progressBarHover)   progressBarHover.style.width = `${(pct*100).toFixed(2)}%`;
      if (progressBarTooltip) { progressBarTooltip.style.left = `${hoverX}px`; progressBarTooltip.textContent = formatTime(t); }
    });

  // ============================================================
  // Seek & hover preview
  // ============================================================
  progressBarContainer?.addEventListener('click', (e) => {
    const dur = getDuration();
    if (Number.isFinite(dur) && dur > 0) {
      const rect = progressBarContainer.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      videoPlayer.currentTime = (clickX / rect.width) * dur;
      updateProgressOnce();
    }
  });
  progressBarContainer?.addEventListener('mousemove', (e) => {
    const dur = getDuration();
    if (!Number.isFinite(dur) || dur <= 0) return;
    const rect = progressBarContainer.getBoundingClientRect();
    const hoverX = clamp(e.clientX - rect.left, 0, rect.width);
    const pct = (hoverX / rect.width);
    const t = pct * dur;
    if (progressBarHover) progressBarHover.style.width = `${(pct*100).toFixed(2)}%`;
    if (progressBarTooltip) { progressBarTooltip.style.left = `${hoverX}px`; progressBarTooltip.textContent = formatTime(t); }
  });

  // Controls autohide
  videoOverlay.addEventListener('mousemove', () => {
    videoOverlay.style.cursor = 'default';
    controlsContainer.classList.add('visible');
    clearTimeout(controlsTimeout);
    controlsTimeout = setTimeout(() => {
      if (settingsPanel.classList.contains('hidden') && !videoPlayer.paused) {
        controlsContainer.classList.remove('visible');
        videoOverlay.style.cursor = 'none';
      }
    }, 3000);
  });

  // ============================================================
  // Refresh & Initial Load
  // ============================================================
  refreshNavBtn?.addEventListener('click', async () => {
    try {
      await fetch('/api/refresh_nav', { method: 'POST' });
      await initializeNav();
      const currentPath = new URLSearchParams(window.location.search).get('path') || '';
      loadContent(decodeURIComponent(currentPath));
      updateNavSelection(decodeURIComponent(currentPath));
    } catch (e) {
      console.error('Refresh failed:', e);
    }
  });

  const initialPath = new URLSearchParams(window.location.search).get('path') || '';
  initializeNav().then(() => {
    loadContent(decodeURIComponent(initialPath));
    updateNavSelection(decodeURIComponent(initialPath));
  });
});
