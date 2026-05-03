/* ============================================================
   Creative Video Studio — Frontend SPA
   ============================================================ */

// ── State ─────────────────────────────────────────────────────────────────────
const S = {
  tab:        'dashboard',
  projects:   [],
  project:    null,          // active project
  characters: [],
  scenes:     [],
  voices:     [],
  videoJobs:  [],
  audioJobs:  [],
  models:     {},
  apiStatus:  {},
  _polls:     {},            // jobId → intervalId
};

// ── API Client ────────────────────────────────────────────────────────────────
const API = {
  async _req(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch('/api' + path, opts);
    if (!res.ok) {
      const txt = await res.text();
      let msg = txt;
      try { msg = JSON.parse(txt).detail || txt; } catch {}
      throw new Error(msg);
    }
    return res.json();
  },
  get:    (p)    => API._req('GET',    p),
  post:   (p, b) => API._req('POST',   p, b),
  put:    (p, b) => API._req('PUT',    p, b),
  del:    (p)    => API._req('DELETE', p),
};

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', dur = 3500) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : '●';
  el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), dur);
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openModal(html) {
  closeModal();
  const root = document.getElementById('modal-root');
  root.innerHTML = `
    <div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">${html}</div>
    </div>`;
}
function closeModal() {
  document.getElementById('modal-root').innerHTML = '';
}

// ── Badge ─────────────────────────────────────────────────────────────────────
function badge(status) {
  const s = (status || 'unknown').toLowerCase();
  return `<span class="badge badge-${s}">${status}</span>`;
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = ({ data }) => {
    try {
      const ev = JSON.parse(data);
      handleWSEvent(ev);
    } catch {}
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
}

function handleWSEvent(ev) {
  if (ev.event === 'job_update') {
    const { job_id, status, video_url, audio_url, error, type } = ev;
    if (type === 'audio') {
      updateAudioJobUI(job_id, status, audio_url, error);
    } else {
      updateVideoJobUI(job_id, status, video_url, error);
    }
    // Refresh scene list if on scenes tab
    if (S.tab === 'scenes') loadAndRenderScenes();
  }
}

function updateVideoJobUI(job_id, status, video_url, error) {
  const card = document.getElementById(`job-${job_id}`);
  if (!card) return;
  const bdg = card.querySelector('.job-badge');
  if (bdg) bdg.outerHTML = badge(status);
  if (status === 'completed' && video_url) {
    const preview = card.querySelector('.preview-area');
    if (preview) {
      preview.innerHTML = `
        <video class="video-preview mt-2" controls src="${video_url}"></video>
        <div class="flex gap-2 mt-2">
          <a href="${video_url}" target="_blank" class="btn btn-primary btn-sm">▶ Open</a>
          <a href="/api/download/${job_id}" class="btn btn-secondary btn-sm">⬇ Download</a>
        </div>`;
    }
    toast('Video ready!', 'success');
  }
  if (status === 'failed') {
    const preview = card.querySelector('.preview-area');
    if (preview) preview.innerHTML = `<p class="text-xs" style="color:#f87171;margin-top:6px">Error: ${error || 'Unknown'}</p>`;
    toast('Video generation failed', 'error');
  }
}

function updateAudioJobUI(job_id, status, audio_url, error) {
  const card = document.getElementById(`ajob-${job_id}`);
  if (!card) return;
  const bdg = card.querySelector('.job-badge');
  if (bdg) bdg.outerHTML = badge(status);
  if (status === 'completed' && audio_url) {
    const preview = card.querySelector('.preview-area');
    if (preview) preview.innerHTML = `<audio class="mt-2" controls src="${audio_url}"></audio>`;
    toast('Audio ready!', 'success');
  }
  if (status === 'failed') toast('Audio generation failed', 'error');
}

// ── Navigation ────────────────────────────────────────────────────────────────
const App = {
  async nav(tab) {
    S.tab = tab;
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tab);
    });
    const content = document.getElementById('content');
    content.innerHTML = `<div class="empty-state"><div class="spinner" style="margin:0 auto"></div></div>`;
    switch (tab) {
      case 'dashboard':  await renderDashboard(); break;
      case 'characters': await renderCharacters(); break;
      case 'scenes':     await renderScenes(); break;
      case 'generate':   await renderGenerate(); break;
      case 'settings':   await renderSettings(); break;
    }
  },
};

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  connectWS();
  await loadMeta();
  await App.nav('dashboard');
}

async function loadMeta() {
  try {
    const [status, models] = await Promise.all([API.get('/status'), API.get('/models')]);
    S.apiStatus = status;
    S.models    = models;
    renderHeaderStatus(status);
  } catch (e) {
    document.getElementById('header-status').textContent = 'API error';
  }
  try {
    S.projects = await API.get('/projects');
    if (S.projects.length && !S.project) S.project = S.projects[0];
  } catch {}
}

function renderHeaderStatus(status) {
  const chips = [];
  const hf = status.higgsfield?.ok;
  const el = status.elevenlabs?.ok;
  const no = status.notion?.ok;
  chips.push(`<span class="status-dot ${hf ? 'green' : 'yellow'}"></span>HF`);
  chips.push(`<span class="status-dot ${el ? 'green' : 'yellow'}"></span>EL`);
  chips.push(`<span class="status-dot ${no ? 'green' : 'red'}"></span>Notion`);
  document.getElementById('header-status').innerHTML = chips.join('&nbsp;&nbsp;');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function set(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html; }
function val(id)       { return document.getElementById(id)?.value?.trim() ?? ''; }
function checked(id)   { return document.getElementById(id)?.checked ?? false; }

function projectSelector(labelText = 'Project') {
  const opts = S.projects.map(p =>
    `<option value="${p.id}" ${S.project?.id === p.id ? 'selected' : ''}>${esc(p.name)}</option>`
  ).join('');
  return `
    <div class="form-group">
      <label class="form-label">${labelText}</label>
      <select id="sel-project" class="form-select" onchange="S.project=S.projects.find(p=>p.id===this.value)">
        <option value="">— select —</option>${opts}
      </select>
    </div>`;
}

function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function modelOptions(selected = 'veo-3') {
  return Object.entries(S.models.models || {}).map(([k, v]) =>
    `<option value="${k}" ${k === selected ? 'selected' : ''}>${v.display}</option>`
  ).join('');
}

function durationOptions(selected = '10s') {
  return (S.models.durations || ['5s','10s','15s']).map(d =>
    `<option value="${d}" ${d === selected ? 'selected' : ''}>${d}</option>`
  ).join('');
}

function resOptions(selected = '720p') {
  return (S.models.resolutions || ['480p','720p','1080p','4K']).map(r =>
    `<option value="${r}" ${r === selected ? 'selected' : ''}>${r}</option>`
  ).join('');
}

function sceneTypeOptions(selected = 'Dialogue') {
  return (S.models.scene_types || ['Dialogue','Action','Transition','Voiceover','Montage']).map(t =>
    `<option value="${t}" ${t === selected ? 'selected' : ''}>${t}</option>`
  ).join('');
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function renderDashboard() {
  try {
    S.projects = await API.get('/projects');
    if (S.projects.length && !S.project) S.project = S.projects[0];
  } catch {}

  const totalScenes = S.projects.reduce((a, p) => a + (p.scene_count || 0), 0);
  const totalChars  = S.projects.reduce((a, p) => a + (p.character_count || 0), 0);

  // Recent jobs
  let recentHTML = '';
  try {
    const jobs = await API.get('/video-jobs');
    const recent = jobs.slice(0, 4);
    recentHTML = recent.length ? recent.map(j => `
      <div class="card" id="job-${j.id}" style="padding:12px">
        <div class="flex items-center justify-between">
          <div class="flex-1 truncate">
            <p class="card-title text-sm truncate">${esc(j.prompt || 'Video job')}</p>
            <p class="card-sub">${esc(j.model)} · ${esc(j.resolution)}</p>
          </div>
          <span class="job-badge">${badge(j.status)}</span>
        </div>
        <div class="preview-area">
          ${j.video_url && j.status === 'completed' ? `
            <video class="video-preview mt-2" controls src="${esc(j.video_url)}"></video>
            <div class="flex gap-2 mt-2">
              <a href="${esc(j.video_url)}" target="_blank" class="btn btn-primary btn-sm">▶ Open</a>
              <a href="/api/download/${j.id}" class="btn btn-secondary btn-sm">⬇ Download</a>
            </div>` : ''}
          ${j.status === 'failed' ? `<p class="text-xs" style="color:#f87171;margin-top:6px">Error: ${esc(j.error_message)}</p>` : ''}
        </div>
      </div>`).join('') : `<div class="empty-state"><p>No video jobs yet</p></div>`;
  } catch { recentHTML = '<p class="text-muted text-sm">Could not load jobs</p>'; }

  let projectCards = '';
  if (S.projects.length) {
    projectCards = S.projects.map(p => `
      <div class="card" style="cursor:pointer" onclick="openProjectDetail('${p.id}')">
        <div class="flex items-center justify-between">
          <div>
            <p class="card-title">${esc(p.name)}</p>
            <p class="card-sub">${p.character_count || 0} cast · ${p.scene_count || 0} scenes</p>
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
        </div>
      </div>`).join('');
  } else {
    projectCards = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        <p>No projects yet</p>
      </div>`;
  }

  document.getElementById('content').innerHTML = `
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-val">${S.projects.length}</div><div class="stat-label">Projects</div></div>
      <div class="stat-card"><div class="stat-val">${totalScenes}</div><div class="stat-label">Scenes</div></div>
      <div class="stat-card"><div class="stat-val">${totalChars}</div><div class="stat-label">Characters</div></div>
      <div class="stat-card"><div class="stat-val" id="dash-jobs">…</div><div class="stat-label">Jobs Run</div></div>
    </div>

    <div class="flex gap-2 mb-4">
      <button class="btn btn-primary flex-1" onclick="showCreateProject()">+ New Project</button>
      <button class="btn btn-secondary flex-1" onclick="App.nav('generate')">⚡ Generate</button>
    </div>

    <div class="section-header"><h2 class="section-title">Projects</h2></div>
    ${projectCards}

    <div class="section-header mt-3"><h2 class="section-title">Recent Jobs</h2></div>
    ${recentHTML}`;

  // Total jobs count
  try {
    const jobs = await API.get('/video-jobs');
    set('dash-jobs', jobs.length);
  } catch { set('dash-jobs', '—'); }
}

// ── Project detail ────────────────────────────────────────────────────────────
async function openProjectDetail(id) {
  try {
    const p = await API.get(`/projects/${id}`);
    S.project = p;
    openModal(`
      <button class="modal-close" onclick="closeModal()">✕</button>
      <p class="modal-title">📁 ${esc(p.name)}</p>
      <p class="card-sub mb-0">${esc(p.description || 'No description')}</p>
      <hr class="divider">
      <p class="text-sm text-soft"><strong>${(p.characters||[]).length}</strong> characters · <strong>${(p.scenes||[]).length}</strong> scenes</p>
      ${p.notion_characters_db ? `<p class="text-xs text-muted">Notion Characters DB linked ✓</p>` : ''}
      ${p.notion_scenes_db     ? `<p class="text-xs text-muted">Notion Scenes DB linked ✓</p>` : ''}
      <div class="flex gap-2 mt-3">
        <button class="btn btn-primary flex-1" onclick="closeModal();App.nav('scenes')">View Scenes</button>
        <button class="btn btn-danger btn-sm" onclick="deleteProject('${p.id}')">Delete</button>
      </div>`);
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteProject(id) {
  if (!confirm('Delete this project and all its data?')) return;
  try {
    await API.del(`/projects/${id}`);
    S.projects = S.projects.filter(p => p.id !== id);
    if (S.project?.id === id) S.project = S.projects[0] || null;
    closeModal();
    toast('Project deleted', 'success');
    await renderDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Create project modal ──────────────────────────────────────────────────────
function showCreateProject() {
  openModal(`
    <button class="modal-close" onclick="closeModal()">✕</button>
    <p class="modal-title">New Project</p>
    <div class="form-group">
      <label class="form-label">Project Name</label>
      <input id="new-proj-name" class="form-input" placeholder="My Short Film" autofocus>
    </div>
    <div class="form-group">
      <label class="form-label">Description</label>
      <input id="new-proj-desc" class="form-input" placeholder="Optional description">
    </div>
    <button class="btn btn-primary btn-full mt-2" onclick="createProject()">Create Project</button>`);
}

async function createProject() {
  const name = val('new-proj-name');
  if (!name) { toast('Enter a project name', 'error'); return; }
  try {
    const p = await API.post('/projects', { name, description: val('new-proj-desc') });
    S.projects.push(p);
    S.project = p;
    closeModal();
    toast(`Project "${name}" created`, 'success');
    await renderDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Notion setup modal ────────────────────────────────────────────────────────
function showNotionSetup() {
  openModal(`
    <button class="modal-close" onclick="closeModal()">✕</button>
    <p class="modal-title">Connect Notion</p>
    <div class="tab-bar mb-3">
      <button class="tab-btn active" onclick="switchNotionTab('setup',this)">Auto Setup</button>
      <button class="tab-btn" onclick="switchNotionTab('import',this)">Import Existing</button>
    </div>
    <div id="notion-tab-setup">
      <p class="text-xs text-soft mb-3">Auto-create Characters and Scenes databases in your Notion workspace.</p>
      <div class="form-group">
        <label class="form-label">Notion API Token</label>
        <input id="notion-token" class="form-input" placeholder="secret_..." type="password">
      </div>
      <div class="form-group">
        <label class="form-label">Parent Page ID</label>
        <input id="notion-page-id" class="form-input" placeholder="Page ID from URL">
        <p class="text-xs text-muted mt-1">From your Notion page URL: notion.so/.../<strong>THIS-PART</strong></p>
      </div>
      <button class="btn btn-primary btn-full" onclick="setupNotion()">Create Databases</button>
    </div>
    <div id="notion-tab-import" style="display:none">
      <p class="text-xs text-soft mb-3">Link existing Notion databases to a new project.</p>
      <div class="form-group">
        <label class="form-label">Notion API Token</label>
        <input id="notion-token-imp" class="form-input" placeholder="secret_..." type="password">
      </div>
      <div class="form-group">
        <label class="form-label">Characters Database ID</label>
        <input id="notion-chars-db" class="form-input" placeholder="Database ID">
      </div>
      <div class="form-group">
        <label class="form-label">Scenes Database ID</label>
        <input id="notion-scenes-db" class="form-input" placeholder="Database ID">
      </div>
      <div class="form-group">
        <label class="form-label">Project Name</label>
        <input id="notion-proj-name" class="form-input" placeholder="Imported Project" value="Imported Project">
      </div>
      <button class="btn btn-primary btn-full" onclick="importNotion()">Import & Sync</button>
    </div>`);
}

function switchNotionTab(tab, btn) {
  document.querySelectorAll('#modal-root .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  set('notion-tab-setup',  tab === 'setup'  ? '' : '');
  document.getElementById('notion-tab-setup').style.display  = tab === 'setup'  ? '' : 'none';
  document.getElementById('notion-tab-import').style.display = tab === 'import' ? '' : 'none';
}

async function setupNotion() {
  const token = val('notion-token'), page_id = val('notion-page-id');
  if (!token || !page_id) { toast('Fill in all fields', 'error'); return; }
  try {
    toast('Creating Notion databases…', 'info', 8000);
    const res = await API.post('/setup', { notion_token: token, parent_page_id: page_id });
    S.projects = await API.get('/projects');
    S.project  = S.projects.find(p => p.id === res.project_id) || S.projects[0];
    closeModal();
    toast('Notion databases created!', 'success');
    await renderDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

async function importNotion() {
  const token      = val('notion-token-imp');
  const chars_db   = val('notion-chars-db');
  const scenes_db  = val('notion-scenes-db');
  const proj_name  = val('notion-proj-name') || 'Imported Project';
  if (!token || !chars_db || !scenes_db) { toast('Fill in all required fields', 'error'); return; }
  try {
    toast('Importing from Notion…', 'info', 8000);
    const res = await API.post('/import-notion', {
      notion_token: token,
      characters_db_id: chars_db,
      scenes_db_id: scenes_db,
      project_name: proj_name,
    });
    S.projects = await API.get('/projects');
    S.project  = S.projects.find(p => p.id === res.project_id) || S.projects[0];
    closeModal();
    toast('Notion workspace imported!', 'success');
    await renderDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Characters tab ────────────────────────────────────────────────────────────
async function renderCharacters() {
  await loadAndRenderCharacters();
}

async function loadAndRenderCharacters() {
  const pid = S.project?.id || '';
  try {
    S.characters = await API.get('/characters' + (pid ? `?project_id=${pid}` : ''));
  } catch { S.characters = []; }

  const cards = S.characters.length
    ? S.characters.map(c => `
        <div class="card">
          <div class="flex items-center justify-between">
            <div class="flex-1">
              <p class="card-title">${esc(c.name)} ${c.is_main_character ? '<span class="badge badge-generated" style="font-size:0.65rem">★ Lead</span>' : ''}</p>
              <p class="card-sub">${c.voice_id ? `Voice: <code style="font-size:0.75rem;color:var(--primary)">${esc(c.voice_id)}</code>` : 'No voice assigned'}</p>
              ${c.description ? `<p class="text-xs text-muted mt-1">${esc(c.description)}</p>` : ''}
            </div>
            <button class="btn btn-danger btn-sm" onclick="deleteCharacter('${c.id}')">✕</button>
          </div>
        </div>`).join('')
    : `<div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
        <p>No characters yet. Add your cast below.</p>
       </div>`;

  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <h2 class="section-title">Cast & Characters</h2>
      <button class="btn btn-secondary btn-sm" onclick="showVoicesModal()">🎤 Voices</button>
    </div>
    ${projectSelector('Filter by Project')}
    ${cards}
    <div class="card" style="border-style:dashed">
      <p class="card-title text-sm" style="margin-bottom:12px">Add Character</p>
      <div class="form-group">
        <label class="form-label">Name</label>
        <input id="char-name" class="form-input" placeholder="Character name">
      </div>
      <div class="form-group">
        <label class="form-label">ElevenLabs Voice ID</label>
        <input id="char-voice" class="form-input" placeholder="e.g. 21m00Tcm4TlvDq8ikWAM">
      </div>
      <div class="form-group">
        <label class="form-label">Description</label>
        <input id="char-desc" class="form-input" placeholder="Brief character description">
      </div>
      <label class="form-check mb-3">
        <input type="checkbox" id="char-main"> <span class="text-sm">Main character (your voice)</span>
      </label>
      <button class="btn btn-primary btn-full" onclick="addCharacter()">Add to Cast</button>
    </div>`;

  // Re-bind project selector
  document.getElementById('sel-project')?.addEventListener('change', async function() {
    S.project = S.projects.find(p => p.id === this.value) || null;
    await loadAndRenderCharacters();
  });
}

async function addCharacter() {
  if (!S.project) { toast('Select a project first', 'error'); return; }
  const name = val('char-name');
  if (!name) { toast('Character name is required', 'error'); return; }
  try {
    const c = await API.post('/characters', {
      project_id:        S.project.id,
      name,
      voice_id:          val('char-voice'),
      description:       val('char-desc'),
      is_main_character: checked('char-main'),
    });
    S.characters.push(c);
    toast(`${name} added to cast`, 'success');
    await loadAndRenderCharacters();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteCharacter(id) {
  if (!confirm('Remove this character?')) return;
  try {
    await API.del(`/characters/${id}`);
    S.characters = S.characters.filter(c => c.id !== id);
    toast('Character removed', 'success');
    await loadAndRenderCharacters();
  } catch (e) { toast(e.message, 'error'); }
}

async function showVoicesModal() {
  openModal(`<button class="modal-close" onclick="closeModal()">✕</button>
    <p class="modal-title">Available Voices</p>
    <div id="voices-list"><div class="spinner" style="margin:0 auto"></div></div>`);
  try {
    if (!S.voices.length) S.voices = await API.get('/voices');
    set('voices-list', S.voices.map(v => `
      <div class="card" style="padding:10px 12px;cursor:pointer" onclick="copyVoiceId('${esc(v.id)}')">
        <div class="flex items-center justify-between">
          <div>
            <p class="card-title text-sm">${esc(v.name)} <span class="text-xs text-muted">${esc(v.category)}</span></p>
            <code style="font-size:0.7rem;color:var(--primary)">${esc(v.id)}</code>
          </div>
          ${v.preview_url ? `<audio controls src="${esc(v.preview_url)}" style="width:110px;height:28px" onclick="event.stopPropagation()"></audio>` : ''}
        </div>
      </div>`).join('') || '<p class="text-muted text-sm">No voices found</p>');
  } catch (e) { set('voices-list', `<p class="text-xs" style="color:#f87171">${esc(e.message)}</p>`); }
}

function copyVoiceId(id) {
  navigator.clipboard?.writeText(id).then(() => toast(`Copied: ${id}`, 'success'));
}

// ── Scenes tab ────────────────────────────────────────────────────────────────
async function renderScenes() {
  await loadAndRenderScenes();
}

async function loadAndRenderScenes() {
  const pid = S.project?.id || '';
  try {
    S.scenes = await API.get('/scenes' + (pid ? `?project_id=${pid}` : ''));
  } catch { S.scenes = []; }

  const sceneCards = S.scenes.length
    ? S.scenes.sort((a,b) => a.scene_number - b.scene_number).map(sc => `
        <div class="card" id="scene-card-${sc.id}">
          <div class="flex items-center gap-2 mb-1">
            <div class="scene-number">${sc.scene_number || '?'}</div>
            <div class="flex-1">
              <p class="card-title">${esc(sc.title || 'Untitled Scene')}</p>
              <p class="card-sub">${esc(sc.scene_type)} · ${esc(sc.model)} · ${esc(sc.duration)}</p>
            </div>
            ${badge(sc.status)}
          </div>
          ${sc.script ? `<p class="text-xs text-muted" style="margin-top:6px;line-height:1.5;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${esc(sc.script)}</p>` : ''}
          ${sc.video_url ? `<video class="video-preview mt-2" controls src="${esc(sc.video_url)}"></video>` : ''}
          <div class="scene-actions">
            <button class="btn btn-primary btn-sm" onclick="quickGenerate('${sc.id}')">⚡ Generate</button>
            <button class="btn btn-secondary btn-sm" onclick="showEditScene('${sc.id}')">✏ Edit</button>
            <button class="btn btn-danger btn-sm" onclick="deleteScene('${sc.id}')">✕</button>
          </div>
        </div>`).join('')
    : `<div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="20" rx="2"/><path d="m7 2 0 20M17 2l0 20M2 12l20 0M2 7l5 0M2 17l5 0"/></svg>
        <p>No scenes yet. Add your first scene below.</p>
       </div>`;

  document.getElementById('content').innerHTML = `
    <div class="section-header">
      <h2 class="section-title">Scenes</h2>
      <span class="text-xs text-muted">${S.scenes.length} scene${S.scenes.length !== 1 ? 's' : ''}</span>
    </div>
    ${projectSelector()}
    ${sceneCards}
    <hr class="divider">
    <p class="section-title mb-3" style="font-size:0.9rem">Add Scene</p>
    <div class="form-group">
      <label class="form-label">Scene Number</label>
      <input id="sc-num" class="form-input" type="number" placeholder="${(S.scenes.length + 1)}" value="${S.scenes.length + 1}">
    </div>
    <div class="form-group">
      <label class="form-label">Title</label>
      <input id="sc-title" class="form-input" placeholder="Scene title">
    </div>
    <div class="form-group">
      <label class="form-label">Script / Dialogue</label>
      <textarea id="sc-script" class="form-textarea" placeholder="[Character]: &quot;dialogue&quot;&#10;OR narration text..."></textarea>
    </div>
    <div class="flex gap-2">
      <div class="form-group flex-1">
        <label class="form-label">Type</label>
        <select id="sc-type" class="form-select" onchange="autoSuggestModel(this.value)">${sceneTypeOptions()}</select>
      </div>
      <div class="form-group flex-1">
        <label class="form-label">Duration</label>
        <select id="sc-dur" class="form-select">${durationOptions()}</select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Model <span id="model-hint" class="text-xs text-muted">(auto-selected)</span></label>
      <select id="sc-model" class="form-select">${modelOptions()}</select>
    </div>
    <div class="form-group">
      <label class="form-label">Resolution</label>
      <select id="sc-res" class="form-select">${resOptions()}</select>
    </div>
    <button class="btn btn-primary btn-full" onclick="addScene()">Add Scene</button>`;

  document.getElementById('sel-project')?.addEventListener('change', async function() {
    S.project = S.projects.find(p => p.id === this.value) || null;
    await loadAndRenderScenes();
  });
}

function autoSuggestModel(sceneType) {
  const map = S.models.suggestion_map || {
    Dialogue:'veo-3', Action:'seedance-2', Transition:'kling-3.0', Voiceover:'veo-3', Montage:'sora-2'
  };
  const suggested = map[sceneType] || 'veo-3';
  const sel = document.getElementById('sc-model');
  if (sel) sel.value = suggested;
  const hint = document.getElementById('model-hint');
  if (hint) hint.textContent = `(suggested for ${sceneType})`;
}

async function addScene() {
  if (!S.project) { toast('Select a project first', 'error'); return; }
  const title = val('sc-title');
  const script = document.getElementById('sc-script')?.value?.trim() || '';
  try {
    const sc = await API.post('/scenes', {
      project_id:   S.project.id,
      scene_number: parseInt(val('sc-num')) || S.scenes.length + 1,
      title,
      script,
      scene_type:  val('sc-type') || 'Dialogue',
      model:       val('sc-model') || 'veo-3',
      duration:    val('sc-dur') || '10s',
      resolution:  val('sc-res') || '720p',
    });
    S.scenes.push(sc);
    toast('Scene added', 'success');
    await loadAndRenderScenes();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteScene(id) {
  if (!confirm('Delete this scene?')) return;
  try {
    await API.del(`/scenes/${id}`);
    S.scenes = S.scenes.filter(s => s.id !== id);
    toast('Scene deleted', 'success');
    await loadAndRenderScenes();
  } catch (e) { toast(e.message, 'error'); }
}

function showEditScene(id) {
  const sc = S.scenes.find(s => s.id === id);
  if (!sc) return;
  openModal(`
    <button class="modal-close" onclick="closeModal()">✕</button>
    <p class="modal-title">Edit Scene ${sc.scene_number}</p>
    <div class="form-group"><label class="form-label">Title</label>
      <input id="edit-sc-title" class="form-input" value="${esc(sc.title)}"></div>
    <div class="form-group"><label class="form-label">Script</label>
      <textarea id="edit-sc-script" class="form-textarea">${esc(sc.script)}</textarea></div>
    <div class="flex gap-2">
      <div class="form-group flex-1"><label class="form-label">Type</label>
        <select id="edit-sc-type" class="form-select">${sceneTypeOptions(sc.scene_type)}</select></div>
      <div class="form-group flex-1"><label class="form-label">Duration</label>
        <select id="edit-sc-dur" class="form-select">${durationOptions(sc.duration)}</select></div>
    </div>
    <div class="form-group"><label class="form-label">Model</label>
      <select id="edit-sc-model" class="form-select">${modelOptions(sc.model)}</select></div>
    <div class="form-group"><label class="form-label">Status</label>
      <select id="edit-sc-status" class="form-select">
        <option ${sc.status==='Draft'?'selected':''}>Draft</option>
        <option ${sc.status==='Ready'?'selected':''}>Ready</option>
        <option ${sc.status==='Generated'?'selected':''}>Generated</option>
        <option ${sc.status==='Final'?'selected':''}>Final</option>
      </select></div>
    <button class="btn btn-primary btn-full" onclick="saveScene('${id}')">Save Changes</button>`);
}

async function saveScene(id) {
  try {
    await API.put(`/scenes/${id}`, {
      title:      val('edit-sc-title'),
      script:     document.getElementById('edit-sc-script')?.value?.trim() || '',
      scene_type: val('edit-sc-type'),
      model:      val('edit-sc-model'),
      duration:   val('edit-sc-dur'),
      status:     val('edit-sc-status'),
    });
    const idx = S.scenes.findIndex(s => s.id === id);
    if (idx >= 0) S.scenes[idx] = await API.get(`/scenes`).then(all => all.find(s => s.id === id));
    closeModal();
    toast('Scene saved', 'success');
    await loadAndRenderScenes();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Quick-generate from scene card ────────────────────────────────────────────
async function quickGenerate(sceneId) {
  const sc = S.scenes.find(s => s.id === sceneId);
  if (!sc) return;
  openModal(`
    <button class="modal-close" onclick="closeModal()">✕</button>
    <p class="modal-title">Generate: ${esc(sc.title || 'Scene')}</p>
    <div class="form-group">
      <label class="form-label">Prompt</label>
      <textarea id="qg-prompt" class="form-textarea" rows="3">${esc(sc.script || sc.title || '')}</textarea>
    </div>
    <div class="flex gap-2">
      <div class="form-group flex-1"><label class="form-label">Model</label>
        <select id="qg-model" class="form-select">${modelOptions(sc.model)}</select></div>
      <div class="form-group flex-1"><label class="form-label">Duration</label>
        <select id="qg-dur" class="form-select">${durationOptions(sc.duration)}</select></div>
    </div>
    <div class="form-group"><label class="form-label">Resolution</label>
      <select id="qg-res" class="form-select">${resOptions(sc.resolution || '720p')}</select></div>
    <label class="form-check mb-2">
      <input type="checkbox" id="qg-prevframe"> <span class="text-sm">Use previous scene as reference frame</span>
    </label>
    <label class="form-check mb-2">
      <input type="checkbox" id="qg-vo"> <span class="text-sm">Generate voiceover (ElevenLabs)</span>
    </label>
    <label class="form-check mb-3">
      <input type="checkbox" id="qg-caps"> <span class="text-sm">Generate captions</span>
    </label>
    <button class="btn btn-primary btn-full" onclick="submitQuickGenerate('${sceneId}')">⚡ Generate Now</button>`);
}

async function submitQuickGenerate(sceneId) {
  if (!S.project) { toast('No active project', 'error'); return; }
  const prompt = document.getElementById('qg-prompt')?.value?.trim();
  if (!prompt) { toast('Prompt is required', 'error'); return; }
  try {
    closeModal();
    toast('Queued for generation…', 'info', 4000);
    const job = await API.post('/generate-video', {
      scene_id:           sceneId,
      project_id:         S.project.id,
      prompt,
      model:              val('qg-model'),
      duration:           val('qg-dur'),
      resolution:         val('qg-res'),
      use_previous_frame: checked('qg-prevframe'),
      generate_voiceover: checked('qg-vo'),
      generate_captions:  checked('qg-caps'),
      assemble:           checked('qg-vo') || checked('qg-caps'),
    });
    App.nav('generate');
  } catch (e) { toast(e.message, 'error'); }
}

// ── Generate tab ──────────────────────────────────────────────────────────────
async function renderGenerate() {
  // Load recent jobs
  let videoJobs = [], audioJobs = [];
  try { videoJobs = await API.get('/video-jobs' + (S.project ? `?project_id=${S.project.id}` : '')); } catch {}
  try { audioJobs = await API.get('/audio-jobs' + (S.project ? `?project_id=${S.project.id}` : '')); } catch {}

  const sceneOpts = S.scenes.map(sc =>
    `<option value="${sc.id}:${esc(sc.script||sc.title||'')}:${sc.model}:${sc.duration}">[${sc.scene_number}] ${esc(sc.title)}</option>`
  ).join('');

  const jobCards = videoJobs.slice(0, 10).map(j => `
    <div class="card" id="job-${j.id}" style="padding:12px">
      <div class="flex items-center gap-2">
        <div class="flex-1 min-width-0">
          <p class="card-title text-sm truncate">${esc(j.prompt || 'Video job')}</p>
          <p class="card-sub">${esc(j.model)} · ${esc(j.resolution)} · ${esc(j.duration)}</p>
        </div>
        <span class="job-badge">${badge(j.status)}</span>
      </div>
      <div class="preview-area">
        ${j.video_url && j.status === 'completed' ? `
          <video class="video-preview mt-2" controls src="${esc(j.video_url)}"></video>
          <div class="flex gap-2 mt-2">
            <a href="${esc(j.video_url)}" target="_blank" class="btn btn-primary btn-sm">▶ Open</a>
            <a href="/api/download/${j.id}" class="btn btn-secondary btn-sm">⬇ Download</a>
          </div>` : ''}
        ${j.status === 'failed' ? `<p class="text-xs" style="color:#f87171;margin-top:6px">${esc(j.error_message)}</p>` : ''}
        ${['queued','generating','polling'].includes(j.status) ? `<div class="progress-bar mt-2"><div class="progress-fill" style="width:60%;animation:progress-pulse 2s infinite"></div></div>` : ''}
      </div>
    </div>`).join('');

  const audioCards = audioJobs.slice(0, 5).map(j => `
    <div class="card" id="ajob-${j.id}" style="padding:12px">
      <div class="flex items-center gap-2">
        <div class="flex-1">
          <p class="card-title text-sm truncate">${esc((j.text_content||'').substring(0,60))}…</p>
          <p class="card-sub">Voice: ${esc(j.voice_id)}</p>
        </div>
        <span class="job-badge">${badge(j.status)}</span>
      </div>
      <div class="preview-area">
        ${j.audio_url && j.status === 'completed' ? `<audio class="mt-2" controls src="${esc(j.audio_url)}"></audio>` : ''}
        ${j.status === 'failed' ? `<p class="text-xs" style="color:#f87171;margin-top:6px">${esc(j.error_message)}</p>` : ''}
      </div>
    </div>`).join('');

  document.getElementById('content').innerHTML = `
    <div class="tab-bar">
      <button class="tab-btn active" id="gen-tab-video" onclick="switchGenTab('video',this)">Video</button>
      <button class="tab-btn" id="gen-tab-audio" onclick="switchGenTab('audio',this)">Voiceover</button>
      <button class="tab-btn" id="gen-tab-jobs"  onclick="switchGenTab('jobs', this)">Jobs</button>
    </div>

    <!-- VIDEO FORM -->
    <div id="gen-video-panel">
      ${projectSelector()}
      <div class="form-group">
        <label class="form-label">Load from Scene (optional)</label>
        <select id="gen-scene-sel" class="form-select" onchange="fillFromScene(this.value)">
          <option value="">— manual entry —</option>${sceneOpts}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Prompt *</label>
        <textarea id="gen-prompt" class="form-textarea" placeholder="Cinematic shot of a detective walking through rain-soaked streets at night…"></textarea>
      </div>
      <div class="flex gap-2">
        <div class="form-group flex-1">
          <label class="form-label">Model</label>
          <select id="gen-model" class="form-select">${modelOptions()}</select>
        </div>
        <div class="form-group flex-1">
          <label class="form-label">Duration</label>
          <select id="gen-dur" class="form-select">${durationOptions()}</select>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Resolution</label>
        <select id="gen-res" class="form-select">${resOptions()}</select>
      </div>
      <label class="form-check mb-2">
        <input type="checkbox" id="gen-prevframe"> <span class="text-sm">Use previous scene as continuity reference</span>
      </label>
      <label class="form-check mb-2">
        <input type="checkbox" id="gen-vo"> <span class="text-sm">Auto-generate voiceover</span>
      </label>
      <label class="form-check mb-3">
        <input type="checkbox" id="gen-caps"> <span class="text-sm">Auto-generate captions</span>
      </label>
      <button class="btn btn-primary btn-full" style="font-size:1rem;padding:14px" onclick="submitVideoGeneration()">
        ⚡ Generate Video
      </button>
    </div>

    <!-- AUDIO FORM -->
    <div id="gen-audio-panel" style="display:none">
      ${projectSelector('Project')}
      <div class="form-group">
        <label class="form-label">Text / Script *</label>
        <textarea id="aud-text" class="form-textarea" style="min-height:120px" placeholder="[Character]: &quot;Your dialogue here&quot;&#10;Or plain narration text…"></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Voice ID *</label>
        <input id="aud-voice" class="form-input" placeholder="ElevenLabs Voice ID">
        <button class="btn btn-secondary btn-sm mt-2 w-full" onclick="showVoicesModal()">Browse Voices</button>
      </div>
      <button class="btn btn-primary btn-full mt-2" onclick="submitAudioGeneration()">
        🎤 Generate Voiceover
      </button>
    </div>

    <!-- JOBS PANEL -->
    <div id="gen-jobs-panel" style="display:none">
      <p class="section-title mb-3">Video Jobs</p>
      ${jobCards || '<div class="empty-state"><p>No video jobs yet</p></div>'}
      <p class="section-title mt-3 mb-3">Audio Jobs</p>
      ${audioCards || '<div class="empty-state"><p>No audio jobs yet</p></div>'}
    </div>`;

  document.getElementById('sel-project')?.addEventListener('change', function() {
    S.project = S.projects.find(p => p.id === this.value) || null;
  });
}

function switchGenTab(tab, btn) {
  document.querySelectorAll('#content .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('gen-video-panel').style.display = tab === 'video' ? '' : 'none';
  document.getElementById('gen-audio-panel').style.display = tab === 'audio' ? '' : 'none';
  document.getElementById('gen-jobs-panel').style.display  = tab === 'jobs'  ? '' : 'none';
}

function fillFromScene(value) {
  if (!value) return;
  const [id, script, model, duration] = value.split(':');
  const prompt = document.getElementById('gen-prompt');
  if (prompt && script) prompt.value = script;
  const sel = document.getElementById('gen-model');
  if (sel && model) sel.value = model;
  const dur = document.getElementById('gen-dur');
  if (dur && duration) dur.value = duration;
}

async function submitVideoGeneration() {
  if (!S.project) { toast('Select a project first', 'error'); return; }
  const prompt = document.getElementById('gen-prompt')?.value?.trim();
  if (!prompt) { toast('Prompt is required', 'error'); return; }

  // Determine scene_id from selector if set
  const sceneSelVal = val('gen-scene-sel');
  const scene_id = sceneSelVal ? sceneSelVal.split(':')[0] : '';

  try {
    toast('Queued! Check the Jobs tab for progress.', 'info', 5000);
    await API.post('/generate-video', {
      scene_id,
      project_id:         S.project.id,
      prompt,
      model:              val('gen-model'),
      duration:           val('gen-dur'),
      resolution:         val('gen-res'),
      use_previous_frame: checked('gen-prevframe'),
      generate_voiceover: checked('gen-vo'),
      generate_captions:  checked('gen-caps'),
      assemble:           checked('gen-vo') || checked('gen-caps'),
    });
    // Switch to jobs tab
    const btn = document.getElementById('gen-tab-jobs');
    if (btn) switchGenTab('jobs', btn);
    await renderGenerate();
    switchGenTab('jobs', document.getElementById('gen-tab-jobs'));
  } catch (e) { toast(e.message, 'error'); }
}

async function submitAudioGeneration() {
  if (!S.project) { toast('Select a project first', 'error'); return; }
  const text     = document.getElementById('aud-text')?.value?.trim();
  const voice_id = val('aud-voice');
  if (!text)     { toast('Text is required', 'error'); return; }
  if (!voice_id) { toast('Voice ID is required', 'error'); return; }
  try {
    toast('Generating voiceover…', 'info', 4000);
    await API.post('/generate-audio', {
      scene_id:   '',
      project_id: S.project.id,
      text,
      voice_id,
    });
    const btn = document.getElementById('gen-tab-jobs');
    if (btn) switchGenTab('jobs', btn);
    await renderGenerate();
    switchGenTab('jobs', document.getElementById('gen-tab-jobs'));
  } catch (e) { toast(e.message, 'error'); }
}

// ── Settings tab ──────────────────────────────────────────────────────────────
async function renderSettings() {
  let current = {};
  try { current = await API.get('/settings'); } catch {}

  const { higgsfield, elevenlabs, notion } = S.apiStatus;

  document.getElementById('content').innerHTML = `
    <h2 class="section-title mb-3">Settings</h2>

    <!-- API Status -->
    <div class="card">
      <p class="card-title text-sm mb-2">API Connection Status</p>
      <div class="flex gap-2" style="flex-wrap:wrap">
        <span class="api-chip"><span class="status-dot ${higgsfield?.ok?'green':'red'}"></span>Higgsfield ${higgsfield?.ok?'✓':'✗'}</span>
        <span class="api-chip"><span class="status-dot ${elevenlabs?.ok?'green':'red'}"></span>ElevenLabs ${elevenlabs?.ok?'✓':'✗'}</span>
        <span class="api-chip"><span class="status-dot ${notion?.ok?'green':notion?.configured?'yellow':'red'}"></span>Notion ${notion?.ok?'✓':notion?.configured?'⚠':'✗'}</span>
      </div>
      <button class="btn btn-secondary btn-sm mt-2" onclick="recheckStatus()">↻ Recheck</button>
    </div>

    <!-- Notion -->
    <div class="card">
      <p class="card-title text-sm mb-2">Notion</p>
      <div class="form-group">
        <label class="form-label">API Token</label>
        <input id="set-notion" class="form-input" type="password" placeholder="secret_…" value="${esc(current.notion_api_key||'')}">
      </div>
      <button class="btn btn-secondary btn-sm" onclick="showNotionSetup()">Setup / Import Workspace</button>
    </div>

    <!-- ElevenLabs -->
    <div class="card">
      <p class="card-title text-sm mb-2">ElevenLabs</p>
      <div class="form-group">
        <label class="form-label">API Key</label>
        <input id="set-el" class="form-input" type="password" value="${esc(current.elevenlabs_api_key||'')}">
      </div>
    </div>

    <!-- Higgsfield -->
    <div class="card">
      <p class="card-title text-sm mb-2">Higgsfield AI</p>
      <div class="form-group">
        <label class="form-label">API Key ID</label>
        <input id="set-hfid" class="form-input" type="password" value="${esc(current.higgsfield_api_id||'')}">
      </div>
      <div class="form-group">
        <label class="form-label">API Secret</label>
        <input id="set-hfsec" class="form-input" type="password" value="${esc(current.higgsfield_api_secret||'')}">
      </div>
    </div>

    <button class="btn btn-primary btn-full" onclick="saveSettings()">Save All Settings</button>

    <hr class="divider">

    <!-- Notion quick-setup -->
    <div class="card" style="border-color:var(--gold);border-style:dashed">
      <p class="card-title text-sm mb-1">Quick Notion Setup</p>
      <p class="text-xs text-muted mb-3">Auto-create Characters and Scenes databases in your Notion workspace.</p>
      <button class="btn btn-secondary btn-full" onclick="showNotionSetup()">🔗 Connect Notion</button>
    </div>

    <!-- Models info -->
    <div class="card">
      <p class="card-title text-sm mb-2">Available Models</p>
      ${Object.entries(S.models.models || {}).map(([k,v]) => `
        <div style="margin-bottom:8px">
          <p class="text-sm font-bold" style="color:var(--primary)">${esc(v.display)}</p>
          <p class="text-xs text-muted">${esc(v.description)} <code style="font-size:0.65rem;color:var(--text-soft)">${k}</code></p>
        </div>`).join('')}
    </div>

    <div style="height:20px"></div>`;
}

async function saveSettings() {
  const body = {};
  const notion = val('set-notion');
  const el     = val('set-el');
  const hfid   = val('set-hfid');
  const hfsec  = val('set-hfsec');
  if (notion) body.notion_api_key        = notion;
  if (el)     body.elevenlabs_api_key    = el;
  if (hfid)   body.higgsfield_api_id     = hfid;
  if (hfsec)  body.higgsfield_api_secret = hfsec;
  try {
    await API.post('/settings', body);
    toast('Settings saved', 'success');
    await loadMeta();
    await renderSettings();
  } catch (e) { toast(e.message, 'error'); }
}

async function recheckStatus() {
  try {
    S.apiStatus = await API.get('/status');
    renderHeaderStatus(S.apiStatus);
    toast('Status refreshed', 'info');
    await renderSettings();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Kick off ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
