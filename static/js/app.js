/* ── Shopify Migration Toolkit – Dashboard JS ── */

const API = '/api';

// ── State ──
let projects = [];
let currentView = 'list';   // 'list' | 'detail'
let activeProject = null;

// ── DOM refs ──
const $app      = document.getElementById('app');
const $projects = document.getElementById('projects');

// ── Helpers ──
function $(sel, ctx = document) { return ctx.querySelector(sel); }
function $$(sel, ctx = document) { return [...ctx.querySelectorAll(sel)]; }

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

// ── Render: Project List ──
function renderList() {
  currentView = 'list';
  activeProject = null;

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
  try {
    const [project, stats, logs] = await Promise.all([
      api(`/projects/${id}`),
      api(`/crawl/${id}/stats`),
      api(`/crawl/${id}/logs`),
    ]);
    activeProject = project;
    currentView = 'detail';

    const counts = stats.counts || {};

    $projects.innerHTML = `
      <div class="detail-header">
        <div>
          <button class="btn btn-secondary btn-sm" onclick="loadProjects()" style="margin-bottom:.75rem">&larr; Back</button>
          <h2>${esc(project.name)}</h2>
          <div class="project-meta" style="margin-top:.3rem">
            <span>${esc(project.source_url)}</span>
            <span class="badge ${badgeClass(project.status)}">${esc(project.status)}</span>
          </div>
        </div>
        <div style="display:flex;gap:.5rem">
          <button class="btn btn-secondary btn-sm" onclick="refreshDetail(${id})">Refresh</button>
        </div>
      </div>

      <div class="stats-grid">
        ${Object.entries(counts).map(([k, v]) => `
          <div class="stat-card">
            <div class="value">${v}</div>
            <div class="label">${esc(k)}</div>
          </div>
        `).join('')}
      </div>

      <div class="card">
        <h3 style="font-size:.95rem;margin-bottom:.75rem;color:var(--text-muted)">Recent Crawl Logs</h3>
        ${logs.length === 0
          ? '<p style="color:var(--text-muted);font-size:.85rem">No logs yet. Start a crawl to see activity here.</p>'
          : `<table class="log-table">
              <thead><tr><th>URL</th><th>Status</th><th>Message</th><th>Time</th></tr></thead>
              <tbody>
                ${logs.slice(0, 20).map(l => `
                  <tr>
                    <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(l.url)}">${esc(l.url)}</td>
                    <td><span class="log-status ${l.status === 'ok' ? 'ok' : l.status === 'error' ? 'error' : 'pending'}">${esc(l.status)}</span></td>
                    <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.message || '—')}</td>
                    <td style="white-space:nowrap">${timeAgo(l.timestamp)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>`
        }
      </div>`;
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function refreshDetail(id) {
  await viewProject(id);
  toast('Refreshed', 'info');
}

// ── Modal ──
function openNewProjectModal() {
  // Remove any existing overlay
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
          <input type="text" name="name" placeholder="e.g. My Shopify Store" required>
        </div>
        <div class="form-group">
          <label>Source URL</label>
          <input type="url" name="source_url" placeholder="https://example.com" required>
        </div>
        <div class="form-group">
          <label>Platform</label>
          <select name="platform">
            <option value="shopify">Shopify</option>
            <option value="woocommerce">WooCommerce</option>
            <option value="bigcommerce">BigCommerce</option>
            <option value="magento">Magento</option>
            <option value="custom" selected>Custom / Other</option>
          </select>
        </div>
        <div class="form-group">
          <label>Auth Method</label>
          <select name="auth_type">
            <option value="crawl" selected>Web Crawl</option>
            <option value="api">API Key</option>
          </select>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
          <button type="submit" class="btn btn-primary">Create Project</button>
        </div>
      </form>
    </div>`;

  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add('active'));
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });

  $('#new-project-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd);
    try {
      await api('/projects/', { method: 'POST', body: JSON.stringify(data) });
      closeModal();
      toast('Project created', 'success');
      await loadProjects();
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
    toast(err.message, 'error');
    projects = [];
    renderList();
  }
}

// ── Escape HTML ──
function esc(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

// ── Boot ──
loadProjects();
