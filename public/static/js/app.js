/* ── Shopify Migration Toolkit – Dashboard JS ── */

const API = '/api';

// ── State ──
let projects = [];
let currentView = 'list';
let activeProject = null;
let pollTimer = null;

// ── DOM refs ──
const $projects = document.getElementById('projects');

// ── Helpers ──
function $(sel, ctx = document) { return ctx.querySelector(sel); }

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}

function toast(msg, type = 'info') {
  let container = $('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function badgeClass(status) {
  const map = { pending: 'badge-pending', crawling: 'badge-crawling', completed: 'badge-completed', failed: 'badge-failed' };
  return map[status] || 'badge-pending';
}

function timeAgo(iso) {
  if (!iso) return '—';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function esc(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ── Render: Project List ──
function renderList() {
  currentView = 'list';
  activeProject = null;
  stopPolling();

  if (projects.length === 0) {
    $projects.innerHTML = `
      <div class="empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
        </svg>
        <h3>No migration projects yet</h3>
        <p>Create your first project to start crawling and exporting store data.</p>
        <button class="btn btn-primary" onclick="openNewProjectModal()">+ New Project</button>
      </div>`;
    return;
  }

  $projects.innerHTML = `
    <div class="toolbar">
      <h2>Projects</h2>
      <button class="btn btn-primary" onclick="openNewProjectModal()">+ New Project</button>
    </div>
    <div class="project-grid">
      ${projects.map(p => `
        <div class="project-card" onclick="viewProject(${p.id})">
          <div class="project-info">
            <h3>${esc(p.name)}</h3>
            <div class="project-meta">
              <span>${esc(p.source_url)}</span>
              <span>${esc(p.platform)}</span>
              <span>${timeAgo(p.created_at)}</span>
            </div>
          </div>
          <div class="project-actions" onclick="event.stopPropagation()">
            <span class="badge ${badgeClass(p.status)}">${esc(p.status)}</span>
            <button class="btn btn-danger btn-sm" onclick="deleteProject(${p.id})" title="Delete">&#10005;</button>
          </div>
        </div>
      `).join('')}
    </div>`;
}

// ── Render: Project Detail ──
async function viewProject(id) {
  stopPolling();
  try {
    const [project, stats, logs] = await Promise.all([
      api(`/projects/${id}`),
      api(`/crawl/${id}/stats`),
      api(`/crawl/${id}/logs`),
    ]);
    activeProject = project;
    currentView = 'detail';

    const counts = stats.counts || {};
    const isCrawling = project.status === 'crawling';
    const isPending = project.status === 'pending';
    const isCompleted = project.status === 'completed';

    $projects.innerHTML = `
      <div class="detail-header">
        <div>
          <button class="btn btn-secondary btn-sm" onclick="loadProjects()" style="margin-bottom:.75rem">&larr; Back</button>
          <h2>${esc(project.name)}</h2>
          <div class="project-meta" style="margin-top:.3rem">
            <span>${esc(project.source_url)}</span>
            <span class="badge ${badgeClass(project.status)}">${esc(project.status)}</span>
            ${isCrawling ? '<span class="spinner" style="margin-left:.5rem"></span>' : ''}
          </div>
        </div>
        <div style="display:flex;gap:.5rem;align-items:flex-start">
          ${isPending || project.status === 'failed' ? `<button class="btn btn-primary" onclick="startCrawl(${id})">Start Crawl</button>` : ''}
          ${isCompleted ? `<button class="btn btn-primary" onclick="startCrawl(${id})">Re-crawl</button>` : ''}
          ${isCrawling ? `<button class="btn btn-secondary" disabled><span class="spinner" style="margin-right:.4rem"></span> Crawling...</button>` : ''}
          <button class="btn btn-secondary btn-sm" onclick="viewProject(${id})">Refresh</button>
        </div>
      </div>

      <div class="stats-grid">
        ${Object.entries(counts).map(([k, v]) => `
          <div class="stat-card">
            <div class="value">${v}</div>
            <div class="label">${esc(k.replace('_', ' '))}</div>
          </div>
        `).join('')}
      </div>

      <div class="card">
        <h3 style="font-size:.95rem;margin-bottom:.75rem;color:var(--text-muted)">Crawl Logs</h3>
        ${logs.length === 0
          ? '<p style="color:var(--text-muted);font-size:.85rem">No logs yet. Hit "Start Crawl" to begin extracting data.</p>'
          : `<table class="log-table">
              <thead><tr><th>URL</th><th>Status</th><th>Message</th><th>Time</th></tr></thead>
              <tbody>
                ${logs.slice(0, 30).map(l => `
                  <tr>
                    <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(l.url)}">${esc(l.url)}</td>
                    <td><span class="log-status ${l.status === 'ok' ? 'ok' : l.status === 'error' ? 'error' : 'pending'}">${esc(l.status)}</span></td>
                    <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(l.message || '')}">${esc(l.message || '—')}</td>
                    <td style="white-space:nowrap">${timeAgo(l.timestamp)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>`
        }
      </div>`;

    // Auto-poll while crawling
    if (isCrawling) {
      pollTimer = setInterval(() => viewProject(id), 4000);
    }

  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Start Crawl ──
async function startCrawl(id) {
  try {
    await api(`/crawl/${id}/start`, { method: 'POST' });
    toast('Crawl started — extracting data...', 'success');
    await viewProject(id);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Modal ──
function openNewProjectModal() {
  const old = $('.overlay');
  if (old) old.remove();

  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>New Migration Project</h2>
      <form id="new-project-form">
        <div class="form-group">
          <label>Project Name</label>
          <input type="text" name="name" placeholder="e.g. My Store Migration" required>
        </div>
        <div class="form-group">
          <label>Website URL</label>
          <input type="url" name="source_url" placeholder="https://example.com" required>
        </div>
        <div class="form-group">
          <label>Platform</label>
          <select name="platform">
            <option value="custom" selected>Auto-detect (Web Crawl)</option>
            <option value="shopify">Shopify (API)</option>
            <option value="woocommerce">WooCommerce (API)</option>
          </select>
        </div>
        <div id="api-fields" style="display:none">
          <div class="form-group">
            <label>API Key</label>
            <input type="text" name="api_key" placeholder="API key (optional)">
          </div>
          <div class="form-group">
            <label>Access Token</label>
            <input type="text" name="access_token" placeholder="Access token (optional)">
          </div>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
          <button type="submit" class="btn btn-primary">Create & Start Crawl</button>
        </div>
      </form>
    </div>`;

  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add('active'));
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });

  // Show/hide API fields
  const platformSelect = overlay.querySelector('[name="platform"]');
  const apiFields = overlay.querySelector('#api-fields');
  platformSelect.addEventListener('change', () => {
    apiFields.style.display = platformSelect.value === 'custom' ? 'none' : 'block';
  });

  $('#new-project-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd);
    try {
      const project = await api('/projects/', { method: 'POST', body: JSON.stringify(data) });
      closeModal();
      toast('Project created — starting crawl...', 'success');

      // Auto-start crawl
      try {
        await api(`/crawl/${project.id}/start`, { method: 'POST' });
      } catch (crawlErr) {
        toast('Project created but crawl failed to start: ' + crawlErr.message, 'error');
      }

      await loadProjects();
      await viewProject(project.id);
    } catch (err) {
      toast(err.message, 'error');
    }
  });
}

function closeModal() {
  const overlay = $('.overlay');
  if (overlay) {
    overlay.classList.remove('active');
    setTimeout(() => overlay.remove(), 200);
  }
}

// ── Delete ──
async function deleteProject(id) {
  if (!confirm('Delete this project and all its data?')) return;
  try {
    await api(`/projects/${id}`, { method: 'DELETE' });
    toast('Project deleted', 'success');
    await loadProjects();
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Load ──
async function loadProjects() {
  try {
    projects = await api('/projects/');
    renderList();
  } catch (err) {
    toast('Failed to load projects: ' + err.message, 'error');
    projects = [];
    renderList();
  }
}

// ── Boot ──
loadProjects();
