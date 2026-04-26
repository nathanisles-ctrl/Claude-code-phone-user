/* Creative Video Studio — frontend logic */
'use strict';

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  projects: [],
  characters: [],
  scenes: [],
  videos: [],
  pollingJobs: {},           // video_id → interval id
  videoStatuses: {},         // video_id → latest status response (cache for renderActiveJobs)
  activeProjectId: null,
};

// ── Utilities ─────────────────────────────────────────────────────────────────
const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  const data = await res.json().catch(e => { console.warn('[API] JSON parse failed:', e); return {}; });
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
  return data;
};

const toast = (() => {
  const el = document.getElementById('toast');
  let timer;
  return (msg, duration = 3000) => {
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(timer);
    timer = setTimeout(() => el.classList.remove('show'), duration);
  };
})();

const badge = (status) => {
  const map = {
    pending: 'badge-pending', generating_video: 'badge-generating',
    generating_audio: 'badge-generating', generating_captions: 'badge-generating',
    assembling: 'badge-generating', completed: 'badge-completed',
    failed: 'badge-failed', draft: 'badge-draft', ready: 'badge-ready',
    generating: 'badge-generating', generated: 'badge-generating', final: 'badge-completed',
    error: 'badge-failed',
  };
  const cls = map[status] || 'badge-pending';
  return `<span class="badge ${cls}">${status}</span>`;
};

const toggleForm = (id) => document.getElementById(id).classList.toggle('hidden');

const el = (id) => document.getElementById(id);

const fmt = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });

// ── Tabs ──────────────────────────────────────────────────────────────────────
const showTab = (name) => {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('tab-active');
    b.classList.add('tab-inactive');
  });
  el(`tab-${name}`).classList.add('active');
  const btn = document.querySelector(`[data-tab="${name}"]`);
  if (btn) { btn.classList.add('tab-active'); btn.classList.remove('tab-inactive'); }

  // Lazy-load data per tab
  if (name === 'dashboard') loadDashboard();
  if (name === 'projects')  loadProjects();
  if (name === 'characters') loadCharacters();
  if (name === 'scenes')    loadScenes();
  if (name === 'generate')  { loadSceneDropdowns(); loadGallery(); }
  if (name === 'gallery')   loadGallery();
  if (name === 'settings')  loadApiStatus();
};

// ── Health / status bar ───────────────────────────────────────────────────────
const loadHealth = async () => {
  try {
    const h = await api('/health');
    const dot = (ok) => ok ? 'dot-ok' : 'dot-err';
    el('dot-higgsfield').className = `status-dot ${dot(h.higgsfield_configured)}`;
    el('dot-elevenlabs').className  = `status-dot ${dot(h.elevenlabs_configured)}`;
    el('dot-notion').className      = `status-dot ${dot(h.notion_configured)}`;
    el('statusLine').textContent = h.notion_configured
      ? 'Higgsfield · ElevenLabs · Notion ✓'
      : 'Higgsfield · ElevenLabs configured · Notion: add API key';
  } catch { el('statusLine').textContent = 'Cannot reach server'; }
};

const loadApiStatus = async () => {
  try {
    const h = await api('/health');
    el('api-status-detail').innerHTML = `
      <div><span class="status-dot ${h.higgsfield_configured?'dot-ok':'dot-err'}"></span>Higgsfield — ${h.higgsfield_configured ? 'Configured' : 'Missing API ID/Secret'}</div>
      <div><span class="status-dot ${h.elevenlabs_configured?'dot-ok':'dot-err'}"></span>ElevenLabs — ${h.elevenlabs_configured ? 'Configured' : 'Missing API key'}</div>
      <div><span class="status-dot ${h.notion_configured?'dot-ok':'dot-warn'}"></span>Notion — ${h.notion_configured ? 'Configured' : 'Not configured (optional)'}</div>
      <div class="mt-1">Database: <span class="font-mono" style="color:#e8af6c;">${h.database}</span></div>
    `;
  } catch(e) { el('api-status-detail').textContent = 'Cannot reach server: ' + e.message; }
};

// ── Dashboard ─────────────────────────────────────────────────────────────────
const loadDashboard = async () => {
  const [projs, scns, vids] = await Promise.allSettled([
    api('/api/projects'), api('/api/scenes'), api('/api/videos'),
  ]);
  const p = projs.status === 'fulfilled' ? projs.value : [];
  const s = scns.status  === 'fulfilled' ? scns.value  : [];
  const v = vids.status  === 'fulfilled' ? vids.value  : [];

  state.projects = p; state.scenes = s; state.videos = v;
  el('stat-projects').textContent = p.length;
  el('stat-scenes').textContent   = s.length;
  el('stat-videos').textContent   = v.length;

  populateSelect('qs-scene', s, 'id', (sc) => sc.title || `Scene #${sc.id} — ${sc.scene_type}`);
  renderRecentVideos(v.slice(0, 5));
};

const renderRecentVideos = (videos) => {
  const el_ = el('recent-videos');
  if (!videos.length) { el_.innerHTML = '<div style="color:#963f16;">No videos yet. Generate your first!</div>'; return; }
  el_.innerHTML = videos.map(v => `
    <div class="flex items-center justify-between py-1 border-b" style="border-color:#3c2a18;">
      <div>
        <span class="text-xs font-mono" style="color:#e8af6c;">Video #${v.id}</span>
        <span class="ml-2">${badge(v.status)}</span>
      </div>
      <div class="text-xs" style="color:#963f16;">${fmt(v.created_at)}</div>
    </div>
  `).join('');
};

// ── Projects ──────────────────────────────────────────────────────────────────
const loadProjects = async () => {
  try {
    state.projects = await api('/api/projects');
    const list = el('projects-list');
    if (!state.projects.length) {
      list.innerHTML = '<div class="text-sm" style="color:#963f16;">No projects yet. Create one above.</div>';
      return;
    }
    list.innerHTML = state.projects.map(p => `
      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <div class="font-semibold" style="color:#e8af6c;">${esc(p.name)}</div>
            <div class="text-xs mt-1" style="color:#963f16;">${esc(p.description) || 'No description'}</div>
            <div class="text-xs mt-1" style="color:#7a3218;">${fmt(p.created_at)}</div>
          </div>
          <button class="btn-secondary text-xs px-3 py-1" onclick="deleteProject(${p.id})">Delete</button>
        </div>
      </div>
    `).join('');
    syncProjectDropdowns();
  } catch(e) { toast('Error loading projects: ' + e.message); }
};

const createProject = async () => {
  const name = el('proj-name').value.trim();
  if (!name) { toast('Project name is required'); return; }
  try {
    const proj = await api('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ name, description: el('proj-desc').value.trim() }),
    });
    toast(`Project "${proj.name}" created`);
    el('proj-name').value = ''; el('proj-desc').value = '';
    toggleForm('proj-form');
    await loadProjects();
  } catch(e) { toast('Error: ' + e.message); }
};

const deleteProject = async (id) => {
  if (!confirm('Delete this project and all its data?')) return;
  try {
    const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    toast('Project deleted');
    await loadProjects();
  } catch(e) { toast('Error deleting project: ' + e.message); }
};

const syncProjectDropdowns = () => {
  ['char-project', 'scene-project'].forEach(id => {
    populateSelect(id, state.projects, 'id', p => p.name);
  });
};

// ── Characters ────────────────────────────────────────────────────────────────
const loadCharacters = async () => {
  try {
    state.characters = await api('/api/characters');
    const list = el('characters-list');
    if (!state.characters.length) {
      list.innerHTML = '<div class="text-sm" style="color:#963f16;">No characters yet.</div>'; return;
    }
    list.innerHTML = state.characters.map(c => `
      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="font-semibold" style="color:#e8af6c;">${esc(c.name)}</div>
            <div class="text-xs mt-1" style="color:#963f16;">${esc(c.description) || 'No description'}</div>
            ${c.voice_id ? `<div class="text-xs mt-1 font-mono" style="color:#7a3218;">Voice: ${esc(c.voice_id)}</div>` : ''}
            ${c.reference_image_url ? `<div class="text-xs mt-1" style="color:#7a3218;">Ref image: ✓</div>` : ''}
          </div>
          <button class="btn-secondary text-xs px-3 py-1 ml-2" onclick="deleteCharacter(${c.id})">×</button>
        </div>
      </div>
    `).join('');
    syncCharacterDropdowns();
  } catch(e) { toast('Error loading characters: ' + e.message); }
};

const createCharacter = async () => {
  const name = el('char-name').value.trim();
  if (!name) { toast('Name is required'); return; }
  const project_id = parseInt(el('char-project').value);
  if (!project_id) { toast('Select a project'); return; }
  try {
    await api('/api/characters', {
      method: 'POST',
      body: JSON.stringify({
        project_id,
        name,
        description: el('char-desc').value.trim(),
        voice_id: el('char-voice').value.trim(),
        reference_image_url: el('char-img').value.trim(),
      }),
    });
    toast(`Character "${name}" saved`);
    el('char-name').value = ''; el('char-desc').value = '';
    el('char-voice').value = ''; el('char-img').value = '';
    toggleForm('char-form');
    await loadCharacters();
  } catch(e) { toast('Error: ' + e.message); }
};

const deleteCharacter = async (id) => {
  if (!confirm('Delete this character?')) return;
  try {
    const res = await fetch(`/api/characters/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Status ${res.status}`);
    toast('Character deleted');
    await loadCharacters();
  } catch(e) { toast('Error deleting character: ' + e.message); }
};

const syncCharacterDropdowns = () => {
  const select = el('scene-character');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">None</option>' +
    state.characters.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  select.value = current;
};

const loadVoices = async () => {
  const list = el('voices-list');
  list.textContent = 'Loading…';
  try {
    const data = await api('/api/voices');
    if (data.error) { list.textContent = data.error; return; }
    list.innerHTML = (data.voices || []).map(v => `
      <div class="flex items-center justify-between py-1 border-b" style="border-color:#3c2a18;">
        <div>
          <span style="color:#e8af6c;">${esc(v.name)}</span>
          <span class="ml-2 font-mono text-xs" style="color:#963f16;">${v.voice_id}</span>
        </div>
        <button class="text-xs px-2 py-0.5 rounded" style="background:#3c2a18; color:#f0c866;"
          onclick="copyVoiceId('${v.voice_id}')">Copy ID</button>
      </div>
    `).join('') || 'No voices found';
  } catch(e) { list.textContent = 'Error: ' + e.message; }
};

const copyVoiceId = (id) => {
  navigator.clipboard?.writeText(id);
  el('char-voice').value = id;
  toast(`Voice ID copied: ${id}`);
};

// ── Scenes ────────────────────────────────────────────────────────────────────
const loadScenes = async () => {
  try {
    state.scenes = await api('/api/scenes');
    populateSelect('qs-scene', state.scenes, 'id', sc => sc.title || `Scene #${sc.id} — ${sc.scene_type}`);
    const list = el('scenes-list');
    if (!state.scenes.length) {
      list.innerHTML = '<div class="text-sm" style="color:#963f16;">No scenes yet. Add a scene above.</div>'; return;
    }
    list.innerHTML = state.scenes.map(sc => `
      <div class="card p-4">
        <div class="flex items-start justify-between mb-2">
          <div>
            <div class="font-semibold" style="color:#e8af6c;">${esc(sc.title) || `Scene #${sc.id}`}</div>
            <div class="flex gap-2 mt-1">${badge(sc.status)} <span class="badge badge-pending">${sc.scene_type}</span></div>
          </div>
          <div class="text-right text-xs" style="color:#7a3218;">${sc.duration}s · ${sc.resolution}</div>
        </div>
        <div class="text-xs mb-3 line-clamp-2" style="color:#963f16;">${esc(sc.script.slice(0,120))}${sc.script.length>120?'…':''}</div>
        <div class="flex gap-2">
          <button class="btn-primary text-xs px-3 py-1" onclick="generateFromScene(${sc.id})">🎬 Generate</button>
          <button class="btn-secondary text-xs px-3 py-1" onclick="updateSceneStatus(${sc.id},'ready')">Mark Ready</button>
        </div>
      </div>
    `).join('');
  } catch(e) { toast('Error loading scenes: ' + e.message); }
};

const MODEL_FOR_TYPE = {
  dialogue: 'veo3', action: 'seedance2', transition: 'kling3',
  voiceover: 'veo3', montage: 'sora2', general: 'higgsfield',
};

const autoSelectModel = () => {
  const type = el('scene-type').value;
  el('scene-model-hint').value = MODEL_FOR_TYPE[type] || 'higgsfield';
};

const createScene = async () => {
  const script = el('scene-script').value.trim();
  if (!script) { toast('Script is required'); return; }
  const project_id = parseInt(el('scene-project').value);
  if (!project_id) { toast('Select a project'); return; }
  try {
    const sc = await api('/api/scenes', {
      method: 'POST',
      body: JSON.stringify({
        project_id,
        title: el('scene-title').value.trim(),
        scene_type: el('scene-type').value,
        script,
        character_id: parseInt(el('scene-character').value) || null,
        model: 'auto',
        duration: parseInt(el('scene-duration').value) || 5,
        resolution: el('scene-res').value,
      }),
    });
    toast(`Scene "${sc.title || '#'+sc.id}" saved`);
    el('scene-title').value = ''; el('scene-script').value = '';
    toggleForm('scene-form');
    await loadScenes();
  } catch(e) { toast('Error: ' + e.message); }
};

const updateSceneStatus = async (id, status) => {
  try {
    await api(`/api/scenes/${id}`, { method: 'PUT', body: JSON.stringify({ status }) });
    toast(`Scene marked as ${status}`);
    await loadScenes();
  } catch(e) { toast('Error updating scene: ' + e.message); }
};

const generateFromScene = async (sceneId) => {
  showTab('generate');
  await loadSceneDropdowns();
  const sel = el('gen-scene');
  if (sel) { sel.value = sceneId; previewScene(sceneId); }
};

// ── Generate ──────────────────────────────────────────────────────────────────
const MODELS      = ['veo3', 'seedance2', 'kling3', 'sora2', 'higgsfield'];
const RESOLUTIONS = ['480p', '720p', '1080p', '4k'];

const _pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

const resolveModel = (val) => {
  const v = (val || 'auto').trim().toLowerCase();
  if (v === 'random') return _pick(MODELS);
  return MODELS.includes(v) ? v : 'auto';
};

const resolveResolution = (val) => {
  const v = (val || '1080p').trim().toLowerCase();
  if (v === 'random') return _pick(RESOLUTIONS);
  return RESOLUTIONS.includes(v) ? v : '1080p';
};

const randomizePick = (inputId, options) => {
  const inp = el(inputId);
  if (inp) inp.value = _pick(options);
};

let _genSceneController = null;

const loadSceneDropdowns = async () => {
  if (!state.scenes.length) state.scenes = await api('/api/scenes').catch(() => []);
  populateSelect('gen-scene', state.scenes, 'id', sc => sc.title || `Scene #${sc.id} — ${sc.scene_type}`);
  populateSelect('qs-scene', state.scenes, 'id', sc => sc.title || `Scene #${sc.id} — ${sc.scene_type}`);
  // Remove previous change listener before adding new one to prevent accumulation
  if (_genSceneController) _genSceneController.abort();
  _genSceneController = new AbortController();
  el('gen-scene').addEventListener(
    'change',
    () => previewScene(el('gen-scene').value),
    { signal: _genSceneController.signal },
  );
};

const previewScene = (sceneId) => {
  const sc = state.scenes.find(s => s.id == sceneId);
  const prev = el('gen-scene-preview');
  if (!sc) { prev.textContent = '← Select a scene'; return; }
  prev.innerHTML = `
    <div class="font-semibold mb-1" style="color:#e8af6c;">${esc(sc.title) || 'Untitled'} · ${sc.scene_type} · ${sc.duration}s</div>
    <div class="whitespace-pre-wrap" style="color:#c0a080;">${esc(sc.script.slice(0,300))}${sc.script.length>300?'…':''}</div>
  `;
};

const startGeneration = async () => {
  const scene_id = parseInt(el('gen-scene').value);
  if (!scene_id) { toast('Select a scene first'); return; }
  const btn = el('gen-start-btn');
  btn.disabled = true; btn.textContent = '⏳ Starting…';
  const body = {
    scene_id,
    model: resolveModel(el('gen-model').value),
    resolution: resolveResolution(el('gen-res').value),
    generate_voiceover: el('gen-vo').checked,
    generate_captions: el('gen-cap').checked,
  };
  try {
    const resp = await api('/api/videos/generate', { method: 'POST', body: JSON.stringify(body) });
    toast(`Generation started! Video #${resp.video_id}`);
    startPolling(resp.video_id);
    showTab('gallery');
  } catch(e) {
    toast('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '🎬 Start Generation';
  }
};

const quickGenerate = async (btn) => {
  const scene_id = parseInt(el('qs-scene').value);
  if (!scene_id) { toast('No scene selected'); return; }
  btn.disabled = true; btn.textContent = '⏳ Starting…';
  el('qs-status').classList.remove('hidden');
  el('qs-status').textContent = 'Submitting generation job…';
  try {
    const resp = await api('/api/videos/generate', {
      method: 'POST',
      body: JSON.stringify({
        scene_id,
        model: resolveModel(el('qs-model').value),
        resolution: resolveResolution(el('qs-res').value),
        generate_voiceover: el('qs-vo').checked,
        generate_captions: el('qs-cap').checked,
      }),
    });
    el('qs-status').textContent = `Video #${resp.video_id} queued. Check Gallery tab for progress.`;
    toast(`Generation started! Video #${resp.video_id}`);
    startPolling(resp.video_id);
  } catch(e) {
    el('qs-status').textContent = 'Error: ' + e.message;
    toast('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '🚀 Generate Video';
  }
};

// ── Polling ────────────────────────────────────────────────────────────────────
const POLL_INTERVAL_MS = 8000;
const POLL_MAX_ATTEMPTS = 75; // 75 × 8s ≈ 10 minutes
const _pollAttempts = {};

const _stopPolling = (videoId) => {
  clearInterval(state.pollingJobs[videoId]);
  delete state.pollingJobs[videoId];
  delete _pollAttempts[videoId];
};

const startPolling = (videoId) => {
  if (state.pollingJobs[videoId]) return;
  _pollAttempts[videoId] = 0;
  state.pollingJobs[videoId] = setInterval(async () => {
    _pollAttempts[videoId] = (_pollAttempts[videoId] || 0) + 1;
    if (_pollAttempts[videoId] > POLL_MAX_ATTEMPTS) {
      _stopPolling(videoId);
      toast(`Video #${videoId}: timed out waiting. Check Gallery manually.`, 6000);
      return;
    }
    try {
      const s = await api(`/api/videos/${videoId}/status`);
      state.videoStatuses[videoId] = s;  // cache for renderActiveJobs
      renderActiveJobs();
      if (s.status === 'completed' || s.status === 'failed') {
        _stopPolling(videoId);
        if (s.status === 'completed') toast(`Video #${videoId} complete! Check Gallery.`);
        else toast(`Video #${videoId} failed: ${s.error_message}`, 6000);
        state.videos = await api('/api/videos').catch(() => state.videos);
        renderRecentVideos(state.videos.slice(0, 5));
        renderGallery();
      }
    } catch { /* network error — continue polling */ }
  }, POLL_INTERVAL_MS);
};

const renderActiveJobs = () => {
  const container = el('active-jobs');
  const ids = Object.keys(state.pollingJobs);
  if (!ids.length) {
    container.innerHTML = '<div style="color:#963f16; font-size:0.8rem;">No active jobs.</div>';
    return;
  }
  // Read from cached statuses — no API calls here
  container.innerHTML = ids.map(vid => {
    const s = state.videoStatuses[vid];
    if (!s) return `<div class="card p-3 text-xs" style="color:#963f16;">Video #${vid} — starting…</div>`;
    return `
      <div id="job-${vid}" class="card p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-semibold" style="color:#e8af6c;">Video #${vid}</span>
          ${badge(s.status)}
        </div>
        <div class="text-xs mb-2" style="color:#963f16;">${esc(s.progress_message || 'Working…')}</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${progressPct(s.status)}%"></div></div>
      </div>`;
  }).join('');
};

const progressPct = (status) => {
  const map = { pending:5, generating_video:30, generating_audio:60, generating_captions:75, assembling:90, completed:100, failed:100 };
  return map[status] || 10;
};

// ── Gallery ───────────────────────────────────────────────────────────────────
const loadGallery = async () => {
  state.videos = await api('/api/videos').catch(() => []);
  renderGallery();
  // Resume polling for in-progress jobs
  state.videos.filter(v => !['completed','failed'].includes(v.status)).forEach(v => startPolling(v.id));
  renderActiveJobs();
};

const renderGallery = () => {
  const list = el('gallery-list');
  if (!state.videos.length) {
    list.innerHTML = '<div style="color:#963f16;">No videos yet. Go to Generate tab to create one.</div>'; return;
  }
  list.innerHTML = state.videos.map(v => {
    const hasFinal = v.status === 'completed' && v.final_path;
    const videoUrl = hasFinal ? `/output/final/${v.final_path.split('/').pop()}` : '';
    return `
      <div class="card p-4" id="gv-${v.id}">
        <div class="flex items-center justify-between mb-2">
          <div class="font-semibold text-sm" style="color:#e8af6c;">Video #${v.id}</div>
          ${badge(v.status)}
        </div>
        ${v.model_used ? `<div class="text-xs mb-1" style="color:#963f16;">Model: ${v.model_used} · ${v.resolution}</div>` : ''}
        <div class="text-xs mb-2" style="color:#7a3218;">${fmt(v.created_at)}</div>
        ${hasFinal ? `
          <video controls class="mb-3" src="${videoUrl}"></video>
          <a href="/api/videos/${v.id}/download" class="btn-primary inline-block text-sm text-center w-full" style="text-decoration:none;">⬇ Download MP4</a>
        ` : ''}
        ${v.status === 'failed' ? `<div class="text-xs p-2 rounded mt-2" style="background:#2a0f0f; color:#f87171;">${esc(v.error_message)}</div>` : ''}
        ${!['completed','failed'].includes(v.status) ? `
          <div class="progress-bar mt-2"><div class="progress-fill" style="width:${progressPct(v.status)}%"></div></div>
          <div class="text-xs mt-1" style="color:#963f16;">Status: ${v.status}</div>
        ` : ''}
      </div>
    `;
  }).join('');
};

// ── Notion ────────────────────────────────────────────────────────────────────
const connectNotion = async () => {
  const key = el('notion-key').value.trim();
  if (!key) { toast('Enter your Notion API key'); return; }
  try {
    const r = await api('/api/notion/connect', {
      method: 'POST',
      body: JSON.stringify({ api_key: key, database_id: el('notion-db').value.trim() }),
    });
    el('notion-status').textContent = r.message;
    toast('Notion connected!');
    loadHealth();
  } catch(e) { el('notion-status').textContent = 'Error: ' + e.message; }
};

const setupNotion = async () => {
  const key = el('notion-key').value.trim();
  const parent = el('notion-parent').value.trim();
  if (!key || !parent) { toast('Enter API key and parent page ID'); return; }
  const status = el('notion-setup-status');
  status.textContent = 'Creating databases…';
  try {
    const r = await api('/api/notion/setup', {
      method: 'POST',
      body: JSON.stringify({ api_key: key, parent_page_id: parent }),
    });
    status.textContent = r.message;
    toast('Notion databases created!');
  } catch(e) { status.textContent = 'Error: ' + e.message; }
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const esc = (str) => String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

const populateSelect = (selectId, items, valueKey, labelFn, placeholder = '— select —') => {
  const sel = el(selectId);
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    items.map(it => `<option value="${it[valueKey]}">${esc(labelFn(it))}</option>`).join('');
  if (current) sel.value = current;
};

// ── PWA ───────────────────────────────────────────────────────────────────────

let _deferredPrompt = null;

/** True when running as installed PWA (standalone / fullscreen mode). */
const isPWA = () =>
  window.matchMedia('(display-mode: standalone)').matches ||
  window.navigator.standalone === true;

/** True when running on iOS Safari (no beforeinstallprompt). */
const isIOS = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;

/** Register the service worker so the app works offline and is installable. */
const registerServiceWorker = async () => {
  if (!('serviceWorker' in navigator)) return;
  try {
    const reg = await navigator.serviceWorker.register('/service-worker.js', {
      scope: '/',
      updateViaCache: 'none',
    });
    console.log('[PWA] Service worker registered, scope:', reg.scope);

    // Check for updates whenever the page loads
    reg.addEventListener('updatefound', () => {
      const worker = reg.installing;
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && navigator.serviceWorker.controller) {
          toast('App updated — reload to get the latest version.', 5000);
        }
      });
    });

    // Listen for the SW telling us to refresh job statuses (after reconnect)
    navigator.serviceWorker.addEventListener('message', (e) => {
      if (e.data?.type === 'SYNC_STATUS') {
        loadGallery();
      }
    });
  } catch (err) {
    console.warn('[PWA] Service worker registration failed:', err);
  }
};

/** Called by the "Install" button in the banner. */
const installPWA = async () => {
  if (!_deferredPrompt) return;
  _deferredPrompt.prompt();
  const { outcome } = await _deferredPrompt.userChoice;
  _deferredPrompt = null;
  el('pwa-banner').classList.add('hidden');
  if (outcome === 'accepted') {
    toast('Installing… check your home screen!');
  }
};

/** Dismiss the install banner and remember the choice. */
const dismissInstallBanner = () => {
  el('pwa-banner').classList.add('hidden');
  localStorage.setItem('pwa-install-dismissed', Date.now().toString());
};

const _showInstallBanner = () => {
  const dismissed = localStorage.getItem('pwa-install-dismissed');
  // Don't re-show within 7 days of dismissal
  if (dismissed && Date.now() - parseInt(dismissed) < 7 * 24 * 60 * 60 * 1000) return;
  if (!isPWA()) el('pwa-banner').classList.remove('hidden');
};

// Browser fires this when the app is installable (Chrome/Edge/Android)
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _deferredPrompt = e;
  _showInstallBanner();
});

// After installation completes
window.addEventListener('appinstalled', () => {
  el('pwa-banner').classList.add('hidden');
  _deferredPrompt = null;
  toast('🎉 Creative Video Studio installed on your home screen!');
});

/** Show iOS-specific "Add to Home Screen" instructions. */
const showIOSInstallInstructions = () => {
  el('ios-install-sheet').classList.remove('hidden');
};

// ── Settings tab: PWA install section ────────────────────────────────────────
const updatePWASettingsBlock = () => {
  const block = el('pwa-settings-block');
  if (!block) return;

  if (isPWA()) {
    block.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="status-dot dot-ok"></span>
        <span style="color:#4ade80; font-weight:600;">Running as installed app</span>
      </div>
      <div class="text-xs mt-1" style="color:#963f16;">You're using the full PWA experience.</div>
    `;
  } else if (isIOS()) {
    block.innerHTML = `
      <div class="text-sm mb-2" style="color:#e8af6c;">Install on iPhone / iPad</div>
      <div class="text-xs mb-3" style="color:#963f16;">Tap below for step-by-step Safari instructions.</div>
      <button class="btn-primary w-full" onclick="showIOSInstallInstructions()">📲 How to Install on iOS</button>
    `;
  } else if (_deferredPrompt) {
    block.innerHTML = `
      <div class="text-sm mb-2" style="color:#e8af6c;">Install on your device</div>
      <div class="text-xs mb-3" style="color:#963f16;">Add to home screen for full-screen, offline access.</div>
      <button class="btn-primary w-full" onclick="installPWA()">📲 Add to Home Screen</button>
    `;
  } else {
    block.innerHTML = `
      <div class="text-xs" style="color:#963f16;">
        Open in Chrome or Edge on Android for "Add to Home Screen" support.
        On iPhone, use Safari and tap the Share button → Add to Home Screen.
      </div>
    `;
  }
};

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  // Register service worker first (non-blocking)
  registerServiceWorker();

  // Handle URL params for shortcuts (e.g. /?tab=generate)
  const tabParam = new URLSearchParams(location.search).get('tab');
  if (tabParam) showTab(tabParam);

  await loadHealth();
  await loadDashboard();

  // Resume polling for in-progress videos
  const videos = await api('/api/videos').catch(() => []);
  state.videos = videos;
  videos.filter(v => !['completed','failed'].includes(v.status)).forEach(v => startPolling(v.id));

  // Update PWA install block in Settings (after _deferredPrompt might have fired)
  setTimeout(updatePWASettingsBlock, 500);
})();
