/**
 * Jericho AI Council — Web Dashboard (F-021)
 *
 * Single-page application with hash-based routing.
 * Fetches data from /api/* endpoints and renders dynamic views.
 */

// ─── State ────────────────────────────────────────────────────

const state = {
    currentView: 'dashboard',
    statusData: null,
    councilData: null,
    proposalsData: null,
    votesData: null,
    charactersData: null,
    locationsData: null,
    analyticsData: null,
    silentpassaEnabled: localStorage.getItem('silentpassa') !== 'off',
};

const $main = () => document.getElementById('main-content');

// ─── API Helpers ──────────────────────────────────────────────

async function api(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}

// ─── Navigation ───────────────────────────────────────────────

function navigateTo(view, detail) {
    state.currentView = view;
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    window.location.hash = detail ? `${view}/${detail}` : view;
    renderView(view, detail);
}

function initNavigation() {
    document.querySelectorAll('.nav-item[data-view]').forEach(el => {
        el.addEventListener('click', e => {
            e.preventDefault();
            navigateTo(el.dataset.view);
        });
    });

    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1) || 'dashboard';
        const [view, ...rest] = hash.split('/');
        const detail = rest.join('/');
        navigateTo(view, detail || null);
    });
}

// ─── Badge Helper ─────────────────────────────────────────────

function badge(text, type) {
    type = type || text;
    return `<span class="badge badge-${type}">${text}</span>`;
}

function truncate(text, len) {
    if (!text) return '';
    len = len || 80;
    return text.length > len ? text.slice(0, len - 3) + '…' : text;
}

function formatDate(iso) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch { return iso; }
}

function approvalBar(rate, showText) {
    const pct = Math.round((rate || 0) * 100);
    const color = pct >= 60 ? '' : 'style="background: linear-gradient(90deg, var(--accent-rose), var(--accent-amber))"';
    return `
        <div class="approval-bar-container">
            <div class="approval-bar">
                <div class="approval-bar-fill" style="width: ${pct}%" ${color}></div>
            </div>
            ${showText !== false ? `<span class="approval-text">${pct}%</span>` : ''}
        </div>`;
}

// ─── Helpers ──────────────────────────────────────────────────

const AVATAR_GRADIENTS = [
    'linear-gradient(135deg, var(--accent-blue), var(--accent-violet))',
    'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))',
    'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
    'linear-gradient(135deg, var(--accent-violet), var(--accent-rose))',
    'linear-gradient(135deg, var(--accent-amber), var(--accent-rose))',
    'linear-gradient(135deg, var(--accent-indigo), var(--accent-violet))',
];

function badge(text, cssClass) {
    return `<span class="badge badge-${cssClass || text}">${text}</span>`;
}

function memberAvatar(name, idx) {
    const initial = (name || '?')[0].toUpperCase();
    const bg = AVATAR_GRADIENTS[(idx || 0) % AVATAR_GRADIENTS.length];
    return `<div class="member-avatar" style="background:${bg}">${initial}</div>`;
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.slice(0, max) + '…' : str;
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function showLoading() {
    $main().innerHTML = `<div class="loading"><div class="loading-spinner"></div><span>Loading…</span></div>`;
}

function showError(msg) {
    $main().innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${msg}</p></div>`;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    if (!text) return '';
    return text.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ─── Render Router ────────────────────────────────────────────

async function renderView(view, detail) {
    try {
        switch (view) {
            case 'dashboard': await renderDashboard(); break;
            case 'council': detail ? await renderCouncilDetail(detail) : await renderCouncil(); break;
            case 'proposals': detail ? await renderProposalDetail(detail) : await renderProposals(); break;
            case 'votes': detail ? await renderVoteDetail(detail) : await renderVotes(); break;
            case 'characters': detail ? await renderCharacterDetail(detail) : await renderCharacters(); break;
            case 'evolution': detail ? await renderEvolutionDetail(detail) : await renderEvolution(); break;
            case 'locations': detail ? await renderLocationDetail(detail) : await renderLocations(); break;
            case 'analytics': await renderAnalytics(); break;
            case 'chat': detail ? await renderChatDetail(detail) : await renderChat(); break;
            case 'memories': detail === 'shared' ? await renderSharedMemory() : detail ? await renderMemoryDetail(detail) : await renderMemories(); break;
            case 'settings': await renderSettings(); break;
            default: await renderDashboard();
        }
    } catch (err) {
        showError(err.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// Dashboard View
// ═══════════════════════════════════════════════════════════════

async function renderDashboard() {
    showLoading();
    const data = await api('/api/status');
    state.statusData = data;
    updateNavCounts(data);

    const m = data.members || {};
    const p = data.proposals || {};
    const v = data.votes || {};
    const c = data.characters || {};

    let providerChips = '';
    if (m.providers) {
        providerChips = Object.entries(m.providers)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    let proposalChips = '';
    if (p.by_status) {
        proposalChips = Object.entries(p.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    let voteChips = '';
    if (v.by_status) {
        voteChips = Object.entries(v.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    let charChips = '';
    if (c.by_status) {
        charChips = Object.entries(c.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    const l = data.locations || {};
    let locChips = '';
    if (l.by_status) {
        locChips = Object.entries(l.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    const ev = data.evolutions || {};
    let evoChips = '';
    if (ev.by_status) {
        evoChips = Object.entries(ev.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Dashboard</h2>
                <p>Jericho AI Council — collaborative AI character design through democratic governance</p>
            </div>

            <div class="stats-grid">
                <div class="stat-card blue">
                    <div class="stat-icon">👥</div>
                    <div class="stat-value">${m.count || 0}</div>
                    <div class="stat-label">Council Members</div>
                    ${providerChips ? `<div class="stat-breakdown">${providerChips}</div>` : ''}
                </div>
                <div class="stat-card emerald">
                    <div class="stat-icon">📜</div>
                    <div class="stat-value">${p.count || 0}</div>
                    <div class="stat-label">Proposals</div>
                    ${proposalChips ? `<div class="stat-breakdown">${proposalChips}</div>` : ''}
                </div>
                <div class="stat-card amber">
                    <div class="stat-icon">🗳️</div>
                    <div class="stat-value">${v.count || 0}</div>
                    <div class="stat-label">Vote Records</div>
                    ${voteChips ? `<div class="stat-breakdown">${voteChips}</div>` : ''}
                </div>
                <div class="stat-card violet">
                    <div class="stat-icon">🎭</div>
                    <div class="stat-value">${c.count || 0}</div>
                    <div class="stat-label">Characters</div>
                    ${charChips ? `<div class="stat-breakdown">${charChips}</div>` : ''}
                </div>
                <div class="stat-card rose">
                    <div class="stat-icon">🗺️</div>
                    <div class="stat-value">${l.count || 0}</div>
                    <div class="stat-label">Locations</div>
                    ${locChips ? `<div class="stat-breakdown">${locChips}</div>` : ''}
                </div>
                <div class="stat-card cyan">
                    <div class="stat-icon">🧬</div>
                    <div class="stat-value">${ev.count || 0}</div>
                    <div class="stat-label">Evolutions</div>
                    ${evoChips ? `<div class="stat-breakdown">${evoChips}</div>` : ''}
                </div>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Council View
// ═══════════════════════════════════════════════════════════════

const AVATAR_COLORS = [
    'linear-gradient(135deg, #3b82f6, #8b5cf6)',
    'linear-gradient(135deg, #10b981, #06b6d4)',
    'linear-gradient(135deg, #f59e0b, #f43f5e)',
    'linear-gradient(135deg, #8b5cf6, #ec4899)',
    'linear-gradient(135deg, #06b6d4, #3b82f6)',
    'linear-gradient(135deg, #f43f5e, #f59e0b)',
    'linear-gradient(135deg, #6366f1, #06b6d4)',
    'linear-gradient(135deg, #10b981, #6366f1)',
    'linear-gradient(135deg, #ec4899, #8b5cf6)',
];

function memberAvatar(name, idx, size) {
    const bg = AVATAR_COLORS[idx % AVATAR_COLORS.length];
    const initial = name.charAt(0).toUpperCase();
    const cls = size === 'lg' ? 'detail-avatar' : 'member-avatar';
    return `<div class="${cls}" style="background: ${bg}">${initial}</div>`;
}

function memberAvatarWithImage(name, idx, size, avatarUrl) {
    if (avatarUrl) {
        const cls = size === 'lg' ? 'detail-avatar' : 'member-avatar';
        return `<div class="${cls}" style="background: url('${avatarUrl}') center/cover no-repeat"></div>`;
    }
    return memberAvatar(name, idx, size);
}

async function renderCouncil() {
    showLoading();
    const data = await api('/api/council');
    state.councilData = data;

    if (!data.length) {
        $main().innerHTML = `
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>Council Members</h2></div>
                <button class="btn btn-primary" onclick="openPromoteModal()" id="btn-add-council">➕ Add Council Member</button>
            </div>
            <div class="empty-state"><div class="empty-icon">👥</div><p>No council members found.</p></div>`;
        return;
    }

    const cards = data.map((m, i) => `
        <div class="card card-clickable member-card" onclick="navigateTo('council','${m.name}')">
            <div class="member-header">
                ${memberAvatarWithImage(m.name, i, null, m.avatar_url)}
                <div>
                    <div class="member-name">${m.name}</div>
                    <div class="member-role">${m.role}</div>
                </div>
                ${badge(m.api_provider)}
            </div>
            <div class="member-desc">${truncate(m.description, 120)}</div>
            <div class="member-meta">
                ${m.specialties.map(s => `<span class="specialty-tag">${s}</span>`).join('')}
            </div>
        </div>`).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>Council Members</h2>
                    <p>${data.length} members across ${new Set(data.map(m=>m.api_provider)).size} providers</p>
                </div>
                <button class="btn btn-primary" onclick="openPromoteModal()" id="btn-add-council">➕ Add Council Member</button>
            </div>
            <div class="member-grid">${cards}</div>
        </div>`;
}

// ─── Council Promotion Modal ───────────────────────────────────

let _promoteSelectedId = null;

async function openPromoteModal() {
    try {
        const candidates = await api('/api/council/candidates');
        _promoteSelectedId = null;

        const listHTML = candidates.length
            ? candidates.map(c => `
                <div class="promote-candidate-item" id="cand-${c.id}"
                     onclick="selectCandidate('${c.id}', '${c.name.replace(/'/g, "\\'")}')">
                    <div>
                        <div class="promote-candidate-name">${c.name}</div>
                        <div class="promote-candidate-desc">${truncate(c.description || '', 80)}</div>
                    </div>
                </div>`).join('')
            : '<div class="promote-empty">No eligible characters found. Create an active character first.</div>';

        // Remove any existing modal
        const existing = document.getElementById('promote-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'promote-modal';
        modal.className = 'promote-modal';
        modal.style.display = 'flex';
        modal.innerHTML = `
            <div class="promote-modal-content">
                <div class="promote-modal-header">
                    <h3>➕ Add Council Member</h3>
                    <button class="detail-close" onclick="closePromoteModal()">✕</button>
                </div>
                <div class="promote-modal-body">
                    <div class="promote-form-group">
                        <label>Select Character to Promote</label>
                        <div class="promote-candidate-list">${listHTML}</div>
                    </div>
                    <div class="promote-form-group">
                        <label for="promote-role">Council Role *</label>
                        <input type="text" id="promote-role" class="form-input"
                               placeholder="e.g. Innovation Advisor, Security Lead" />
                    </div>
                    <div class="promote-form-group">
                        <label for="promote-desc">Role Description / Duties *</label>
                        <textarea id="promote-desc" class="form-input" rows="3"
                                  placeholder="Describe what this council role is responsible for..."></textarea>
                    </div>
                </div>
                <div class="promote-modal-footer">
                    <button class="btn" onclick="closePromoteModal()">Cancel</button>
                    <button class="btn btn-primary" onclick="promoteToCouncil()" id="btn-confirm-promote">Promote to Council</button>
                </div>
            </div>`;
        document.body.appendChild(modal);

        // Close on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closePromoteModal();
        });
    } catch (err) {
        showToast('Failed to load candidates: ' + err.message, true);
    }
}

function selectCandidate(id, name) {
    _promoteSelectedId = id;
    document.querySelectorAll('.promote-candidate-item').forEach(el => el.classList.remove('selected'));
    const item = document.getElementById('cand-' + id);
    if (item) item.classList.add('selected');
}

function closePromoteModal() {
    const modal = document.getElementById('promote-modal');
    if (modal) modal.remove();
    _promoteSelectedId = null;
}

async function promoteToCouncil() {
    if (!_promoteSelectedId) {
        showToast('Please select a character first.', true);
        return;
    }
    const role = (document.getElementById('promote-role')?.value || '').trim();
    const desc = (document.getElementById('promote-desc')?.value || '').trim();
    if (!role) { showToast('Council Role is required.', true); return; }
    if (!desc) { showToast('Role Description is required.', true); return; }

    const btn = document.getElementById('btn-confirm-promote');
    if (btn) { btn.disabled = true; btn.textContent = 'Promoting…'; }

    try {
        const resp = await fetch('/api/council/promote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                character_id: _promoteSelectedId,
                role: role,
                role_description: desc,
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Promotion failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`${result.name} promoted to Council as ${result.role}! ✅`);
        closePromoteModal();
        renderCouncil(); // refresh
    } catch (err) {
        showToast('Promotion failed: ' + err.message, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Promote to Council'; }
    }
}

async function renderCouncilDetail(name) {
    showLoading();
    const data = await api(`/api/council/${encodeURIComponent(name)}`);
    const idx = (state.councilData || []).findIndex(m => m.name === name);

    const personality = data.personality || {};
    const traits = personality.traits || [];
    const commStyle = personality.communication_style || '';
    const decisionApproach = personality.decision_approach || '';

    const avatarHtml = data.avatar_url
        ? `<div class="detail-avatar avatar-upload-area" onclick="openAvatarEditor('${data.name}')" title="Click to change avatar"
                style="background: url('${data.avatar_url}') center/cover no-repeat; cursor: pointer;">
             <div class="avatar-overlay">📷</div>
           </div>`
        : `<div class="detail-avatar avatar-upload-area" onclick="openAvatarEditor('${data.name}')" title="Click to upload avatar"
                style="background: ${AVATAR_COLORS[(idx >= 0 ? idx : 0) % AVATAR_COLORS.length]}; cursor: pointer;">
             ${data.name.charAt(0).toUpperCase()}
             <div class="avatar-overlay">📷</div>
           </div>`;

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('council')">← Back to Council</button>
            <div class="detail-panel">
                <div class="detail-header">
                    ${avatarHtml}
                    <div style="flex:1">
                        <div class="council-field-readonly">
                            <span class="council-readonly-label">Role</span>
                            <span class="council-readonly-value">${data.role}</span>
                        </div>
                        <div class="council-field-readonly" style="margin-top:var(--space-xs)">
                            <span class="council-readonly-label">Description</span>
                            <span class="council-readonly-value" style="font-size:0.85rem;color:var(--text-secondary)">${data.description}</span>
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('council')">✕</button>
                </div>

                <!-- Editable Fields Form -->
                <form id="council-edit-form" class="council-edit-form" onsubmit="event.preventDefault(); saveCouncilMember('${data.name}')">

                    <div class="council-fields-grid">
                        <div class="council-field-group">
                            <label for="cf-name">Name</label>
                            <input type="text" id="cf-name" class="settings-input" value="${escapeAttr(data.name)}" required />
                        </div>

                        <div class="council-field-group">
                            <label for="cf-provider">API Provider</label>
                            <select id="cf-provider" class="settings-input" onchange="updateModelFieldForProvider()">
                                <option value="openrouter" ${data.api_provider === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                                <option value="mancer" ${data.api_provider === 'mancer' ? 'selected' : ''}>Mancer</option>
                            </select>
                        </div>

                        <div class="council-field-group">
                            <label for="cf-model">Model</label>
                            <div id="cf-model-container">
                                ${data.api_provider === 'mancer'
                                    ? `<select id="cf-model" class="settings-input">
                                           ${MANCER_MODEL_OPTIONS.map(m => `<option value="${m}" ${data.model === m || (!data.model && m === 'Default') ? 'selected' : ''}>${m}</option>`).join('')}
                                       </select>`
                                    : `<select id="cf-model" class="settings-input">
                                           ${OPENROUTER_MODEL_OPTIONS.map(m => `<option value="${m}" ${data.model === m || (!data.model && m === 'Default') ? 'selected' : ''}>${m}</option>`).join('')}
                                       </select>`
                                }
                            </div>
                            <span class="council-field-hint">Set to "Default" to use the model configured in Settings</span>
                        </div>

                        <div class="council-field-group">
                            <label for="cf-weight">Vote Weight</label>
                            <input type="number" id="cf-weight" class="settings-input" value="${data.vote_weight}" step="0.1" min="0.1" />
                        </div>
                    </div>

                    <div class="council-field-group" style="margin-top:var(--space-md)">
                        <label for="cf-traits">Traits</label>
                        <input type="text" id="cf-traits" class="settings-input" value="${escapeAttr(Array.isArray(traits) ? traits.join(', ') : traits)}" placeholder="e.g. balanced, diplomatic, patient" />
                        <span class="council-field-hint">Comma-separated list of personality traits</span>
                    </div>

                    <div class="council-field-group">
                        <label for="cf-comm-style">Communication Style</label>
                        <input type="text" id="cf-comm-style" class="settings-input" value="${escapeAttr(commStyle)}" placeholder="Describe communication style…" />
                    </div>

                    <div class="council-field-group">
                        <label for="cf-decision">Decision Approach</label>
                        <input type="text" id="cf-decision" class="settings-input" value="${escapeAttr(decisionApproach)}" placeholder="Describe decision-making approach…" />
                    </div>

                    <div class="council-field-group">
                        <label for="cf-prompt">System Prompt</label>
                        <textarea id="cf-prompt" class="settings-input council-textarea" rows="8">${escapeHtml(data.system_prompt)}</textarea>
                    </div>

                    <!-- Read-only Specialties -->
                    <div class="detail-section" style="margin-top:var(--space-lg)">
                        <h4>Specialties <span style="font-weight:400;text-transform:none;letter-spacing:normal;font-size:0.7rem;color:var(--text-muted)">(read-only)</span></h4>
                        <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">
                            ${data.specialties.map(s => `<span class="specialty-tag">${s}</span>`).join('')}
                        </div>
                    </div>

                    <div class="council-save-bar">
                        <button type="submit" class="btn btn-primary btn-save-member" id="council-save-btn">
                            💾 Save Changes
                        </button>
                        <span class="council-save-hint" id="council-save-status"></span>
                    </div>
                </form>
            </div>
        </div>

        <!-- Avatar Editor Modal -->
        <div class="avatar-modal" id="avatar-modal" style="display:none">
            <div class="avatar-modal-content">
                <div class="avatar-modal-header">
                    <h3>Edit Avatar</h3>
                    <button class="detail-close" onclick="closeAvatarEditor()">✕</button>
                </div>
                <div class="avatar-modal-body">
                    <div class="avatar-drop-zone" id="avatar-drop-zone">
                        <input type="file" id="avatar-file-input" accept="image/png,image/jpeg,image/webp" style="display:none" onchange="handleAvatarFile(event)" />
                        <div class="avatar-drop-label" onclick="document.getElementById('avatar-file-input').click()">
                            📁 Click to select image or drag & drop a PNG
                        </div>
                    </div>
                    <div class="avatar-preview-section" id="avatar-preview-section" style="display:none">
                        <canvas id="avatar-canvas" class="avatar-preview-canvas" width="200" height="200"></canvas>
                        <div class="avatar-zoom-control">
                            <span class="avatar-zoom-label">🔍 Zoom</span>
                            <input type="range" id="avatar-zoom" class="avatar-zoom-slider" min="0.5" max="3" step="0.05" value="1" oninput="updateAvatarPreview()" />
                            <span id="avatar-zoom-value">1.0×</span>
                        </div>
                    </div>
                </div>
                <div class="avatar-modal-footer">
                    <button class="btn btn-secondary" onclick="closeAvatarEditor()">Cancel</button>
                    <button class="btn btn-primary" id="avatar-save-btn" onclick="saveAvatar('${data.name}')" disabled>💾 Save Avatar</button>
                </div>
            </div>
        </div>`;
}

function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Council Member Save ──────────────────────────────────────

/* Swap the model field between dropdown options when the provider
   dropdown changes in the council-edit form. */
function updateModelFieldForProvider() {
    const provider = document.getElementById('cf-provider').value;
    const container = document.getElementById('cf-model-container');
    if (!container) return;

    if (provider === 'mancer') {
        container.innerHTML = `<select id="cf-model" class="settings-input">
            ${MANCER_MODEL_OPTIONS.map(m => `<option value="${m}">${m}</option>`).join('')}
        </select>`;
    } else {
        container.innerHTML = `<select id="cf-model" class="settings-input">
            ${OPENROUTER_MODEL_OPTIONS.map(m => `<option value="${m}">${m}</option>`).join('')}
        </select>`;
    }
}

async function saveCouncilMember(originalName) {
    const btn = document.getElementById('council-save-btn');
    const status = document.getElementById('council-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const traitsRaw = document.getElementById('cf-traits').value;
    const traitsArr = traitsRaw.split(',').map(t => t.trim()).filter(Boolean);

    const body = {
        name: document.getElementById('cf-name').value.trim(),
        api_provider: document.getElementById('cf-provider').value,
        model: document.getElementById('cf-model').value.trim(),
        vote_weight: parseFloat(document.getElementById('cf-weight').value) || 1.0,
        traits: traitsArr,
        communication_style: document.getElementById('cf-comm-style').value.trim(),
        decision_approach: document.getElementById('cf-decision').value.trim(),
        system_prompt: document.getElementById('cf-prompt').value,
    };

    try {
        const resp = await fetch(`/api/council/${encodeURIComponent(originalName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`${data.name} updated successfully ✅`);
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';

        // If name changed, navigate to new name
        if (data.name !== originalName) {
            navigateTo('council', data.name);
        }
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

// ── Avatar Editor ────────────────────────────────────────────

let avatarEditorState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };

function openAvatarEditor(name) {
    const modal = document.getElementById('avatar-modal');
    modal.style.display = 'flex';
    avatarEditorState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };
    document.getElementById('avatar-preview-section').style.display = 'none';
    document.getElementById('avatar-save-btn').disabled = true;
    document.getElementById('avatar-file-input').value = '';

    // Setup drag-and-drop
    const dropZone = document.getElementById('avatar-drop-zone');
    dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); };
    dropZone.ondragleave = () => { dropZone.classList.remove('drag-over'); };
    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) loadAvatarImage(file);
    };

    // Setup canvas pan
    const canvas = document.getElementById('avatar-canvas');
    canvas.onmousedown = (e) => { avatarEditorState.dragging = true; avatarEditorState.lastX = e.clientX; avatarEditorState.lastY = e.clientY; };
    canvas.onmousemove = (e) => {
        if (!avatarEditorState.dragging) return;
        avatarEditorState.offsetX += e.clientX - avatarEditorState.lastX;
        avatarEditorState.offsetY += e.clientY - avatarEditorState.lastY;
        avatarEditorState.lastX = e.clientX;
        avatarEditorState.lastY = e.clientY;
        updateAvatarPreview();
    };
    canvas.onmouseup = () => { avatarEditorState.dragging = false; };
    canvas.onmouseleave = () => { avatarEditorState.dragging = false; };
}

function closeAvatarEditor() {
    document.getElementById('avatar-modal').style.display = 'none';
}

function handleAvatarFile(event) {
    const file = event.target.files[0];
    if (file) loadAvatarImage(file);
}

function loadAvatarImage(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            avatarEditorState.img = img;
            avatarEditorState.zoom = 1.0;
            avatarEditorState.offsetX = 0;
            avatarEditorState.offsetY = 0;
            document.getElementById('avatar-zoom').value = 1.0;
            document.getElementById('avatar-zoom-value').textContent = '1.0×';
            document.getElementById('avatar-preview-section').style.display = 'block';
            document.getElementById('avatar-save-btn').disabled = false;
            updateAvatarPreview();
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function updateAvatarPreview() {
    const canvas = document.getElementById('avatar-canvas');
    const ctx = canvas.getContext('2d');
    const zoom = parseFloat(document.getElementById('avatar-zoom').value);
    avatarEditorState.zoom = zoom;
    document.getElementById('avatar-zoom-value').textContent = zoom.toFixed(1) + '×';

    const img = avatarEditorState.img;
    if (!img) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw circular clip
    ctx.save();
    ctx.beginPath();
    ctx.arc(100, 100, 100, 0, Math.PI * 2);
    ctx.clip();

    // Fill background
    ctx.fillStyle = '#111827';
    ctx.fillRect(0, 0, 200, 200);

    // Calculate dimensions to fit image
    const scale = zoom * Math.max(200 / img.width, 200 / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const x = (200 - w) / 2 + avatarEditorState.offsetX;
    const y = (200 - h) / 2 + avatarEditorState.offsetY;

    ctx.drawImage(img, x, y, w, h);
    ctx.restore();

    // Draw border
    ctx.beginPath();
    ctx.arc(100, 100, 99, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
    ctx.lineWidth = 2;
    ctx.stroke();
}

async function saveAvatar(memberName) {
    const canvas = document.getElementById('avatar-canvas');
    const btn = document.getElementById('avatar-save-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Uploading…';

    try {
        const imageData = canvas.toDataURL('image/png');
        const resp = await fetch(`/api/council/${encodeURIComponent(memberName)}/avatar-upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_data: imageData,
                zoom: avatarEditorState.zoom,
                offsetX: avatarEditorState.offsetX,
                offsetY: avatarEditorState.offsetY,
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        showToast('Avatar saved ✅');
        closeAvatarEditor();
        // Re-render to show new avatar
        await renderCouncilDetail(memberName);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Avatar';
    }
}

// ═══════════════════════════════════════════════════════════════
// Proposals View
// ═══════════════════════════════════════════════════════════════

async function renderProposals() {
    showLoading();
    const data = await api('/api/proposals');
    state.proposalsData = data;

    // Fetch council members for the author selector
    let members = [];
    try { members = await api('/api/council'); } catch { /* empty */ }

    const memberOptions = members.map(m =>
        `<option value="${m.name}">${m.name} — ${m.role}</option>`
    ).join('');

    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general', 'evolution']
        .map(c => `<option value="${c}">${c.charAt(0).toUpperCase() + c.slice(1)}</option>`)
        .join('');

    const rows = data.map(p => {
        const statusClass = p.status === 'decided' ? 'badge-active'
            : p.status === 'withdrawn' ? 'badge-rejected'
            : p.status === 'open' ? 'badge-open'
            : `badge-${p.status}`;
        return `
        <tr class="proposal-row" onclick="navigateTo('proposals','${p.id}')">
            <td class="col-id">${p.id}</td>
            <td class="col-title">${truncate(p.title, 50)}</td>
            <td>${p.author}</td>
            <td>${badge(p.category)}</td>
            <td>${badge(p.status)}</td>
            <td>${p.reviews ? p.reviews.length : 0}</td>
            <td>${formatDate(p.created_at)}</td>
        </tr>`;
    }).join('');

    const tableHtml = data.length ? `
        <div class="table-wrapper">
            <table class="data-table" id="proposals-table">
                <thead>
                    <tr>
                        <th>ID</th><th>Title</th><th>Author</th>
                        <th>Category</th><th>Status</th><th>Reviews</th><th>Created</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>` : '<div class="empty-state"><div class="empty-icon">📜</div><p>No proposals yet. Create one below!</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>📜 Proposals</h2>
                <p>${data.length} governance proposal${data.length !== 1 ? 's' : ''}</p>
            </div>

            <div class="proposal-form card">
                <h3>📝 New Proposal</h3>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                    Select a council member to author and present a proposal to the full council for discussion and vote.
                </p>
                <div class="proposal-form-grid">
                    <div class="filter-group">
                        <label for="proposal-author-select">Author (Council Member)</label>
                        <select id="proposal-author-select" class="settings-input">
                            <option value="">Select author…</option>
                            ${memberOptions}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="proposal-category-select">Category</label>
                        <select id="proposal-category-select" class="settings-input">
                            ${categoryOptions}
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <label for="proposal-title-input">Title</label>
                        <input id="proposal-title-input" class="settings-input" placeholder="e.g. Expand Ethical Constraints" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="proposal-desc-input">Description</label>
                    <textarea id="proposal-desc-input" class="settings-input proposal-textarea" rows="3"
                        placeholder="Describe the proposal and its goals…"></textarea>
                </div>
                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="createNewProposal()" id="proposal-create-btn">
                        🚀 Submit Proposal
                    </button>
                    <span id="proposal-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>

            ${tableHtml}
        </div>`;
}

async function createNewProposal() {
    const author = document.getElementById('proposal-author-select').value;
    const title = document.getElementById('proposal-title-input').value.trim();
    const description = document.getElementById('proposal-desc-input').value.trim();
    const category = document.getElementById('proposal-category-select').value;
    const btn = document.getElementById('proposal-create-btn');
    const status = document.getElementById('proposal-create-status');

    if (!author) { document.getElementById('proposal-author-select').focus(); return; }
    if (!title) { document.getElementById('proposal-title-input').focus(); return; }
    if (!description) { document.getElementById('proposal-desc-input').focus(); return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = 'Creating proposal and opening discussion…';

    try {
        const resp = await fetch('/api/proposals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author, title, description, category }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create proposal' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Proposal ${data.id} created by ${author} ✅`);
        navigateTo('proposals', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Submit Proposal';
    }
}

async function renderProposalDetail(id) {
    showLoading();
    const data = await api(`/api/proposals/${encodeURIComponent(id)}`);

    // Try to load discussion data
    let discussion = null;
    try { discussion = await api(`/api/proposals/${encodeURIComponent(id)}/discussion`); } catch { /* no discussion */ }

    // Try to load vote data
    let voteData = null;
    try { voteData = await api(`/api/votes/${encodeURIComponent(id)}`); } catch { /* no vote */ }

    // Fetch council members for avatar URLs
    let proposalMembers = [];
    try { proposalMembers = await api('/api/council'); } catch { /* empty */ }
    const proposalAvatarMap = {};
    proposalMembers.forEach(m => { if (m.avatar_url) proposalAvatarMap[m.name.toLowerCase()] = m.avatar_url; });
    state.proposalAvatarMap = proposalAvatarMap;  // Store for SSE handlers

    const isTerminal = data.status === 'decided' || data.status === 'withdrawn';
    const hasDiscussion = !!discussion;
    const discussionOpen = hasDiscussion && discussion.status === 'open';
    const hasVote = !!voteData;

    // Lifecycle progress bar
    const stages = ['draft', 'open', 'under_review', 'decided'];
    const currentIdx = stages.indexOf(data.status);
    const isWithdrawn = data.status === 'withdrawn';
    const lifecycleHtml = `
        <div class="proposal-lifecycle">
            ${stages.map((s, i) => {
                let cls = 'lifecycle-step';
                if (isWithdrawn) {
                    cls += i === 0 ? ' lifecycle-done' : '';
                } else if (i < currentIdx) {
                    cls += ' lifecycle-done';
                } else if (i === currentIdx) {
                    cls += ' lifecycle-active';
                }
                const labels = { draft: 'Draft', open: 'Open', under_review: 'Review', decided: 'Decided' };
                return `<div class="${cls}"><span class="lifecycle-dot"></span><span class="lifecycle-label">${labels[s]}</span></div>`;
            }).join('<div class="lifecycle-connector"></div>')}
            ${isWithdrawn ? '<div class="lifecycle-connector"></div><div class="lifecycle-step lifecycle-active lifecycle-withdrawn"><span class="lifecycle-dot"></span><span class="lifecycle-label">Withdrawn</span></div>' : ''}
        </div>`;

    // Discussion feed
    let discussionFeedHtml = '';
    if (hasDiscussion && discussion.contributions && discussion.contributions.length) {
        const contribs = discussion.contributions.map(c => {
            const memberIdx = (discussion.participants || []).indexOf(c.speaker);
            return `
            <div class="discussion-message">
                <div class="discussion-message-header">
                    ${memberAvatarWithImage(c.speaker, memberIdx >= 0 ? memberIdx : 0, null, state.proposalAvatarMap && state.proposalAvatarMap[c.speaker.toLowerCase()])}
                    <div>
                        <span class="discussion-speaker">${c.speaker}</span>
                        <span class="discussion-round">Round ${c.round_number}</span>
                    </div>
                </div>
                <div class="discussion-content">${renderMarkdown(c.content)}</div>
            </div>`;
        }).join('');
        discussionFeedHtml = `
            <div class="detail-section">
                <h4>💬 Council Discussion (${discussion.contributions.length} contributions, Round ${discussion.current_round}/${discussion.round_count})</h4>
                <div class="discussion-feed" id="discussion-feed">${contribs}</div>
            </div>`;
    } else if (hasDiscussion) {
        discussionFeedHtml = `
            <div class="detail-section">
                <h4>💬 Council Discussion</h4>
                <div class="discussion-feed" id="discussion-feed">
                    <div class="empty-state" style="padding:var(--space-lg)"><div class="empty-icon">💬</div><p>No contributions yet. Start a discussion round!</p></div>
                </div>
            </div>`;
    }

    // Discussion summary (when closed)
    let summaryHtml = '';
    if (hasDiscussion && discussion.status === 'closed' && discussion.summary) {
        summaryHtml = `
            <div class="detail-section">
                <h4>📋 Discussion Summary</h4>
                <p style="color:var(--text-secondary)">${renderMarkdown(discussion.summary)}</p>
            </div>`;
    }

    // Action buttons
    let actionsHtml = '';
    if (!isTerminal) {
        const buttons = [];
        if (discussionOpen && discussion.current_round < discussion.round_count) {
            buttons.push(`<button class="btn btn-primary" onclick="runDiscussionRound('${id}')" id="discuss-btn">▶️ Continue Discussion</button>`);
        }
        if (discussionOpen) {
            buttons.push(`<button class="btn btn-secondary" onclick="pauseDiscussion('${id}')" id="pause-btn">⏸ Pause Discussion</button>`);
        }
        if (!hasVote && (data.status === 'open' || data.status === 'under_review')) {
            buttons.push(`<button class="btn btn-accent" onclick="callProposalVote('${id}')" id="vote-btn">🗳️ Call Vote</button>`);
        }
        if (data.status !== 'decided') {
            buttons.push(`<button class="btn btn-danger-outline" onclick="withdrawProposal('${id}','${escapeAttr(data.author)}')" id="withdraw-btn">↩️ Withdraw</button>`);
        }
        if (buttons.length) {
            actionsHtml = `<div class="proposal-actions">${buttons.join('')}</div>`;
        }
    }

    // Vote results
    let voteResultsHtml = '';
    if (hasVote) {
        const t = voteData.tally || {};
        const votesHtml = (voteData.votes || []).map(v => `
            <div class="vote-item">
                <span class="vote-voter">${v.voter}</span>
                ${badge(v.choice)}
                <span class="vote-reason">${renderMarkdown(v.reason) || '—'}</span>
            </div>`).join('');

        voteResultsHtml = `
            <div class="detail-section vote-results-panel">
                <h4>🗳️ Vote Results</h4>
                <div class="vote-summary-grid">
                    <div class="vote-summary-item vote-for">
                        <div class="vote-summary-count">${t.votes_for || 0}</div>
                        <div class="vote-summary-label">For</div>
                    </div>
                    <div class="vote-summary-item vote-against">
                        <div class="vote-summary-count">${t.votes_against || 0}</div>
                        <div class="vote-summary-label">Against</div>
                    </div>
                    <div class="vote-summary-item vote-abstain">
                        <div class="vote-summary-count">${t.votes_abstain || 0}</div>
                        <div class="vote-summary-label">Abstain</div>
                    </div>
                </div>
                <div style="margin:var(--space-md) 0;max-width:400px">
                    ${approvalBar(t.approval_rate)}
                </div>
                <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:var(--space-md)">
                    Quorum: ${t.quorum_met ? '✅ Met' : '❌ Not met'}
                    · Threshold: ${t.threshold_met ? '✅ Met' : '❌ Not met'}
                    · Result: <strong>${t.approved ? '✅ Approved' : '❌ Not approved'}</strong>
                    ${t.vetoed ? ' · 🚫 VETOED' : ''}
                </div>
                <div class="proposal-actions" style="margin-bottom:var(--space-md)">
                    ${voteData.vetoed
                        ? `<button class="btn btn-primary" onclick="liftVetoProposal('${id}')" id="lift-veto-btn">✅ Lift Veto</button>
                           <span style="font-size:0.82rem;color:var(--text-muted)">Reason: ${escapeHtml(voteData.veto_reason) || '—'}</span>`
                        : `<button class="btn btn-danger-outline" onclick="vetoProposal('${id}')" id="veto-btn">🚫 Veto</button>`
                    }
                </div>
                <h4 style="margin-top:var(--space-md)">Individual Votes (${(voteData.votes || []).length})</h4>
                <div class="votes-breakdown">${votesHtml || '<p style="color:var(--text-muted)">No votes cast.</p>'}</div>
            </div>`;
    }

    // Reviews section (from proposal reviews, not discussion)
    let reviewsHtml = '';
    if (data.reviews && data.reviews.length) {
        reviewsHtml = `
            <div class="detail-section">
                <h4>Reviews (${data.reviews.length})</h4>
                <div class="votes-breakdown">
                    ${data.reviews.map(r => `
                        <div class="vote-item">
                            <span class="vote-voter">${r.reviewer}</span>
                            ${badge(r.stance)}
                            <span class="vote-reason">${renderMarkdown(r.comment) || '—'}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('proposals')">← Back to Proposals</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.title)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${data.author}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${badge(data.category)}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('proposals')">✕</button>
                </div>

                ${lifecycleHtml}
                ${actionsHtml}

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${renderMarkdown(data.description)}</p>
                </div>

                ${data.body ? `<div class="detail-section"><h4>Body</h4><div style="white-space:pre-wrap">${renderMarkdown(data.body)}</div></div>` : ''}

                ${discussionFeedHtml}
                ${summaryHtml}
                ${voteResultsHtml}
                ${(data.category === 'evolution' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section evolution-handoff-banner">
                        <h4>🧬 Evolution Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This evolution proposal has been <strong>approved</strong> by the council. Proceed to the Evolution section to create and apply the character changes.</p>
                        <button class="btn btn-primary" onclick="navigateTo('evolution')" style="background:linear-gradient(135deg, hsl(275,60%,55%), hsl(300,50%,45%))">
                            🧬 Go to Evolution Section
                        </button>
                    </div>` : ''}
                ${reviewsHtml}
            </div>
        </div>`;
}

// ── Proposal Actions ─────────────────────────────────────────

async function runDiscussionRound(proposalId) {
    const btn = document.getElementById('discuss-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Council is discussing…'; }

    const feed = document.getElementById('discussion-feed');
    if (feed) {
        // Clear empty state if present
        const emptyState = feed.querySelector('.empty-state');
        if (emptyState) emptyState.remove();
    }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-stream`, {
            method: 'POST',
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let eventType = 'message';
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6);
                    try {
                        const data = JSON.parse(jsonStr);
                        if (eventType === 'message' && feed) {
                            const msgDiv = document.createElement('div');
                            msgDiv.className = 'discussion-message discussion-message-enter';
                            msgDiv.innerHTML = `
                                <div class="discussion-message-header">
                                    ${memberAvatarWithImage(data.speaker, 0, null, state.proposalAvatarMap && state.proposalAvatarMap[data.speaker.toLowerCase()])}
                                    <div>
                                        <span class="discussion-speaker">${data.speaker}</span>
                                        <span class="discussion-round">Round ${data.round}</span>
                                    </div>
                                </div>
                                <div class="discussion-content">${renderMarkdown(data.content)}</div>`;
                            feed.appendChild(msgDiv);
                            feed.scrollTop = feed.scrollHeight;
                        } else if (eventType === 'error') {
                            showToast(data.detail || 'Discussion error', true);
                        }
                    } catch { /* invalid JSON line */ }
                    eventType = 'message';
                }
            }
        }

        showToast('Discussion round complete ✅');
        // Refresh the full view to update state
        setTimeout(() => renderProposalDetail(proposalId), 500);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '▶️ Continue Discussion'; }
    }
}

async function pauseDiscussion(proposalId) {
    const btn = document.getElementById('pause-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Pausing…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-pause`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to pause' }));
            throw new Error(err.detail);
        }
        showToast('Discussion paused ⏸');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⏸ Pause Discussion'; }
    }
}

async function callProposalVote(proposalId) {
    const btn = document.getElementById('vote-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Council is voting…'; }

    // If discussion is still open, pause it first
    try {
        await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-pause`, {
            method: 'POST',
        });
    } catch { /* may already be closed */ }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/vote`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Vote failed' }));
            throw new Error(err.detail);
        }
        const results = await resp.json();
        const t = results.tally || {};
        const resultText = t.approved ? 'APPROVED ✅' : 'NOT APPROVED ❌';
        showToast(`Vote complete — ${resultText}`);
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🗳️ Call Vote'; }
    }
}

async function withdrawProposal(proposalId, author) {
    if (!confirm(`Withdraw this proposal? This cannot be undone.`)) return;
    const btn = document.getElementById('withdraw-btn');
    if (btn) { btn.disabled = true; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/withdraw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Withdraw failed' }));
            throw new Error(err.detail);
        }
        showToast('Proposal withdrawn ↩️');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; }
    }
}

async function vetoProposal(proposalId) {
    const reason = prompt('Veto reason (optional):') ?? '';
    if (reason === null) return;  // user cancelled
    const btn = document.getElementById('veto-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Vetoing…'; }

    try {
        const resp = await fetch(`/api/votes/${encodeURIComponent(proposalId)}/veto`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Veto failed' }));
            throw new Error(err.detail);
        }
        showToast('Proposal vetoed 🚫');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🚫 Veto'; }
    }
}

async function liftVetoProposal(proposalId) {
    if (!confirm('Remove the veto from this proposal?')) return;
    const btn = document.getElementById('lift-veto-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Lifting veto…'; }

    try {
        const resp = await fetch(`/api/votes/${encodeURIComponent(proposalId)}/lift-veto`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Lift veto failed' }));
            throw new Error(err.detail);
        }
        showToast('Veto lifted ✅');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '✅ Lift Veto'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Votes View
// ═══════════════════════════════════════════════════════════════

async function renderVotes() {
    showLoading();
    const data = await api('/api/votes');
    state.votesData = data;

    if (!data.length) {
        $main().innerHTML = `
            <div class="page-header"><h2>Vote Records</h2></div>
            <div class="empty-state"><div class="empty-icon">🗳️</div><p>No vote records found.</p></div>`;
        return;
    }

    const rows = data.map(r => {
        const t = r.tally || {};
        return `
        <tr onclick="navigateTo('votes','${r.proposal_id}')">
            <td class="col-id">${r.proposal_id}</td>
            <td>${badge(r.status)}</td>
            <td>${r.votes ? r.votes.length : 0}</td>
            <td>${approvalBar(t.approval_rate)}</td>
            <td>${t.quorum_met ? '✅' : '❌'}</td>
            <td>${r.vetoed ? '🚫' : '—'}</td>
        </tr>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Vote Records</h2>
                <p>${data.length} voting records</p>
            </div>
            <div class="table-wrapper">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Proposal</th><th>Status</th><th>Votes</th>
                            <th>Approval</th><th>Quorum</th><th>Vetoed</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
}

async function renderVoteDetail(proposalId) {
    showLoading();
    const data = await api(`/api/votes/${encodeURIComponent(proposalId)}`);
    const t = data.tally || {};

    const votesHtml = (data.votes || []).map(v => `
        <div class="vote-item">
            <span class="vote-voter">${v.voter}</span>
            ${badge(v.choice)}
            <span class="vote-reason">${v.reason || '—'}</span>
            <span class="vote-weight">w:${v.weight}</span>
        </div>`).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('votes')">← Back to Votes</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.proposal_id}</div>
                        <div style="font-size:1.3rem;font-weight:700">Vote Record</div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${data.vetoed ? '<span class="badge badge-rejected">🚫 VETOED</span>' : ''}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('votes')">✕</button>
                </div>

                <div class="stats-grid" style="margin-bottom:var(--space-xl)">
                    <div class="stat-card emerald">
                        <div class="stat-value">${t.votes_for || 0}</div>
                        <div class="stat-label">Votes For</div>
                    </div>
                    <div class="stat-card" style="border-top:3px solid var(--accent-rose)">
                        <div class="stat-value">${t.votes_against || 0}</div>
                        <div class="stat-label">Votes Against</div>
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-value">${t.votes_abstain || 0}</div>
                        <div class="stat-label">Abstentions</div>
                    </div>
                </div>

                <div class="detail-section">
                    <h4>Approval Rate</h4>
                    <div style="max-width:320px">${approvalBar(t.approval_rate)}</div>
                    <div style="margin-top:var(--space-sm);font-size:0.82rem;color:var(--text-muted)">
                        Quorum: ${t.quorum_met ? '✅ Met' : '❌ Not met'}
                        · Threshold: ${t.threshold_met ? '✅ Met' : '❌ Not met'}
                        · Result: ${t.approved ? '✅ Approved' : '❌ Not approved'}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>Individual Votes (${(data.votes || []).length})</h4>
                    <div class="votes-breakdown">${votesHtml || '<p style="color:var(--text-muted)">No votes cast yet.</p>'}</div>
                </div>

                ${data.veto_reason ? `<div class="detail-section"><h4>Veto Reason</h4><p>${data.veto_reason}</p></div>` : ''}
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Characters View
// ═══════════════════════════════════════════════════════════════

async function renderCharacters() {
    showLoading();
    const data = await api('/api/characters');
    state.charactersData = data;

    const createForm = `
        <div class="card character-create-form">
            <h3>🎭 New Character</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Create a new character template with traits, backstory, and system prompt.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="char-name-input">Name</label>
                    <input id="char-name-input" class="settings-input" placeholder="e.g. Atlas" />
                </div>
                <div class="filter-group">
                    <label for="char-author-input">Author</label>
                    <input id="char-author-input" class="settings-input" placeholder="e.g. Forge" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-desc-input">Description</label>
                <textarea id="char-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="A short summary of this character…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-backstory-input">Backstory</label>
                <textarea id="char-backstory-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Character history and background…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="char-greeting-input">Greeting</label>
                    <input id="char-greeting-input" class="settings-input" placeholder="First message the character says…" />
                </div>
                <div class="filter-group">
                    <label for="char-tags-input">Tags</label>
                    <input id="char-tags-input" class="settings-input" placeholder="explorer, brave (comma-separated)" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-prompt-input">System Prompt</label>
                <textarea id="char-prompt-input" class="settings-input proposal-textarea" rows="3"
                    placeholder="You are {{char}}, an adventurous AI who…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-examples-input">Example Messages</label>
                <textarea id="char-examples-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="One message per line…"></textarea>
            </div>

            <div class="char-trait-editor" style="margin-top:var(--space-md)">
                <label>Traits</label>
                <div id="char-trait-list"></div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group">
                        <input id="char-trait-name" class="settings-input" placeholder="Trait name (e.g. Curious)" />
                    </div>
                    <div class="filter-group">
                        <select id="char-trait-type" class="settings-input">
                            <option value="personality">Personality</option>
                            <option value="values">Values</option>
                            <option value="flaws">Flaws</option>
                            <option value="custom">Custom</option>
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <input id="char-trait-desc" class="settings-input" placeholder="Trait description…" />
                    </div>
                    <div class="filter-group" style="flex:0.5">
                        <input id="char-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5"
                            class="avatar-zoom-slider" oninput="document.getElementById('char-trait-intensity-val').textContent = this.value" />
                        <span id="char-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                    </div>
                </div>
                <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addPendingTrait()">
                    ➕ Add Trait
                </button>
            </div>

            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createCharacter()" id="char-create-btn">
                    🎭 Create Character
                </button>
                <span id="char-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🎭 Characters</h2>
                    <p>No characters yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const cards = data.map(c => {
        const traitsHtml = (c.traits || []).slice(0, 4).map(t => `
            <div class="trait-item">
                <span class="trait-name">${escapeHtml(t.name)}</span>
                <div class="trait-bar-bg">
                    <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
                </div>
                <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
            </div>`).join('');

        const tagsHtml = (c.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

        const avatarHtml = c.avatar_url
            ? `<div class="char-card-avatar" style="background:url('${c.avatar_url}') center/cover no-repeat"></div>`
            : '';

        return `
        <div class="card card-clickable character-card" onclick="navigateTo('characters','${c.id}')">
            <div class="char-header">
                ${avatarHtml}
                <div style="flex:1">
                    <div class="char-name">${escapeHtml(c.name)}</div>
                    <div class="char-author">by ${escapeHtml(c.author)} · v${c.version || 1} · <span style="color:var(--accent-cyan)">${escapeHtml(c.api_provider || 'openrouter')}</span> · ${escapeHtml(c.model || 'Default')}</div>
                </div>
                ${badge(c.status)}
            </div>
            <div class="char-desc">${truncate(c.description, 120)}</div>
            ${traitsHtml ? `<div class="traits-list">${traitsHtml}</div>` : ''}
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🎭 Characters</h2>
                <p>${data.length} AI character template${data.length !== 1 ? 's' : ''}</p>
            </div>
            ${createForm}
            <div class="character-grid">${cards}</div>
        </div>`;
}

async function renderCharacterDetail(id) {
    showLoading();
    const data = await api(`/api/characters/${encodeURIComponent(id)}`);

    const traitsHtml = (data.traits || []).map(t => `
        <div class="trait-item">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <div class="trait-bar-bg" style="max-width:150px">
                <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
            </div>
            <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeCharTrait('${data.id}', '${escapeAttr(t.name)}')" title="Delete trait">🗑️</button>
        </div>`).join('');

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

    // Avatar section
    const avatarHtml = data.avatar_url
        ? `<div class="char-detail-avatar" onclick="openCharAvatarEditor('${data.id}')" title="Click to change avatar"
                style="background: url('${data.avatar_url}') center/cover no-repeat; cursor: pointer;">
             <div class="avatar-overlay">📷</div>
           </div>`
        : `<div class="char-detail-avatar char-avatar-placeholder" onclick="openCharAvatarEditor('${data.id}')" title="Click to upload avatar"
                style="cursor: pointer;">
             🎭
             <div class="avatar-overlay">📷</div>
           </div>`;

    // Status action buttons
    let statusActions = '';
    if (data.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateCharacterStatus('${data.id}', 'active')">✅ Activate</button>`;
    } else if (data.status === 'active') {
        statusActions = `
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'archived')">📦 Archive</button>
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'draft')">📝 Revert to Draft</button>`;
    } else if (data.status === 'archived') {
        statusActions = `
            <button class="btn btn-primary btn-sm" onclick="updateCharacterStatus('${data.id}', 'active')">✅ Reactivate</button>
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'draft')">📝 Revert to Draft</button>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('characters')">← Back to Characters</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div style="display:flex;gap:var(--space-lg);align-items:flex-start">
                        ${avatarHtml}
                        <div>
                            <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id} · v${data.version || 1}</div>
                            <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.name)}</div>
                            <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                                by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                            </div>
                            <div style="margin-top:var(--space-sm);display:flex;align-items:center;gap:var(--space-sm)">
                                ${badge(data.status)}
                                ${statusActions}
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-secondary btn-sm" onclick="exportCharacterPng('${data.id}')" title="Download as TavernCard v2 PNG">
                            📥 Export PNG
                        </button>
                        <button class="detail-close" onclick="navigateTo('characters')">✕</button>
                    </div>
                </div>

                <div class="detail-section" style="margin-top:var(--space-md)">
                    <div class="analytics-row"><span class="label">🔌 Provider</span><span class="value">${escapeHtml(data.api_provider || 'openrouter')}</span></div>
                    <div class="analytics-row"><span class="label">🤖 Model</span><span class="value">${escapeHtml(data.model || 'Default')}</span></div>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.backstory ? `<div class="detail-section"><h4>📖 Backstory</h4><p style="white-space:pre-line">${escapeHtml(data.backstory)}</p></div>` : ''}

                ${traitsHtml ? `<div class="detail-section"><h4>🧬 Traits (${data.traits.length})</h4><div class="traits-list">${traitsHtml}</div>
                    <div style="margin-top:var(--space-md);padding:var(--space-sm);border:1px dashed var(--border-subtle);border-radius:var(--radius-md)">
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group">
                                <input id="detail-trait-name" class="settings-input" placeholder="Trait name" />
                            </div>
                            <div class="filter-group">
                                <select id="detail-trait-type" class="settings-input">
                                    <option value="personality">Personality</option>
                                    <option value="values">Values</option>
                                    <option value="flaws">Flaws</option>
                                    <option value="custom">Custom</option>
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="detail-trait-desc" class="settings-input" placeholder="Trait description…" />
                            </div>
                            <div class="filter-group" style="flex:0.5">
                                <input id="detail-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5" class="avatar-zoom-slider"
                                    oninput="document.getElementById('detail-trait-intensity-val').textContent = this.value" />
                                <span id="detail-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addCharTrait('${data.id}')">➕ Add Trait</button>
                    </div>
                </div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                ${data.greeting ? `<div class="detail-section"><h4>👋 Greeting</h4><p style="font-style:italic;color:var(--accent-cyan)">"${escapeHtml(data.greeting)}"</p></div>` : ''}

                ${data.system_prompt ? `<div class="detail-section"><h4>💻 System Prompt</h4><pre>${escapeHtml(data.system_prompt)}</pre></div>` : ''}

                ${data.example_messages && data.example_messages.length ? `
                    <div class="detail-section">
                        <h4>💬 Example Messages</h4>
                        ${data.example_messages.map(m => `<p style="color:var(--text-secondary);margin-bottom:var(--space-xs)">💬 ${escapeHtml(m)}</p>`).join('')}
                    </div>` : ''}

                <div class="detail-section" style="margin-top:var(--space-xl);border-top:1px solid var(--border-subtle);padding-top:var(--space-lg)">
                    <h4>✏️ Edit Character</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="char-edit-name">Name</label>
                            <input id="char-edit-name" class="settings-input" value="${escapeAttr(data.name)}" />
                        </div>
                        <div class="filter-group">
                            <label for="char-edit-tags">Tags</label>
                            <input id="char-edit-tags" class="settings-input" value="${escapeAttr((data.tags || []).join(', '))}" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-desc">Description</label>
                        <textarea id="char-edit-desc" class="settings-input proposal-textarea" rows="2">${escapeHtml(data.description)}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-backstory">Backstory</label>
                        <textarea id="char-edit-backstory" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.backstory || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-greeting">Greeting</label>
                        <input id="char-edit-greeting" class="settings-input" value="${escapeAttr(data.greeting || '')}" />
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-prompt">System Prompt</label>
                        <textarea id="char-edit-prompt" class="settings-input proposal-textarea" rows="4">${escapeHtml(data.system_prompt || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-examples">Example Messages (one per line)</label>
                        <textarea id="char-edit-examples" class="settings-input proposal-textarea" rows="2">${escapeHtml((data.example_messages || []).join('\n'))}</textarea>
                    </div>
                    <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveCharacterEdit('${data.id}')" id="char-save-btn">
                            💾 Save Changes
                        </button>
                        <span id="char-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Character Avatar Modal -->
        <div class="avatar-modal" id="char-avatar-modal" style="display:none">
            <div class="avatar-modal-content">
                <div class="avatar-modal-header">
                    <h3>Upload Character Avatar</h3>
                    <button class="detail-close" onclick="closeCharAvatarEditor()">✕</button>
                </div>
                <div class="avatar-modal-body">
                    <div class="avatar-drop-zone" id="char-avatar-drop-zone">
                        <input type="file" id="char-avatar-file-input" accept="image/png,image/jpeg,image/webp" style="display:none" onchange="handleCharAvatarFile(event)" />
                        <div class="avatar-drop-label" onclick="document.getElementById('char-avatar-file-input').click()">
                            📁 Click to select image or drag & drop a PNG
                        </div>
                    </div>
                    <div class="avatar-preview-section" id="char-avatar-preview-section" style="display:none">
                        <canvas id="char-avatar-canvas" class="avatar-preview-canvas" width="200" height="200"></canvas>
                        <div class="avatar-zoom-control">
                            <span class="avatar-zoom-label">🔍 Zoom</span>
                            <input type="range" id="char-avatar-zoom" class="avatar-zoom-slider" min="0.5" max="3" step="0.05" value="1" oninput="updateCharAvatarPreview()" />
                            <span id="char-avatar-zoom-value">1.0×</span>
                        </div>
                    </div>
                </div>
                <div class="avatar-modal-footer">
                    <button class="btn btn-secondary" onclick="closeCharAvatarEditor()">Cancel</button>
                    <button class="btn btn-primary" id="char-avatar-save-btn" onclick="saveCharAvatar('${data.id}')" disabled>💾 Save Avatar</button>
                </div>
            </div>
        </div>`;
}

// ── Character Create ────────────────────────────────────────

// ── Pending Traits (for creation form) ──────────────────────

let pendingTraits = [];

function addPendingTrait() {
    const nameEl = document.getElementById('char-trait-name');
    const name = nameEl.value.trim();
    const traitType = document.getElementById('char-trait-type').value;
    const desc = document.getElementById('char-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('char-trait-intensity').value);

    if (!name) { nameEl.focus(); return; }

    // Check for duplicates
    if (pendingTraits.some(t => t.name.toLowerCase() === name.toLowerCase())) {
        showToast('Trait with that name already added', true);
        return;
    }

    pendingTraits.push({
        trait_type: traitType,
        name: name,
        description: desc || name,
        intensity: intensity,
    });

    // Clear inputs
    nameEl.value = '';
    document.getElementById('char-trait-desc').value = '';
    document.getElementById('char-trait-intensity').value = '0.5';
    document.getElementById('char-trait-intensity-val').textContent = '0.5';

    renderPendingTraits();
}

function removePendingTrait(index) {
    pendingTraits.splice(index, 1);
    renderPendingTraits();
}

function renderPendingTraits() {
    const container = document.getElementById('char-trait-list');
    if (!container) return;
    if (!pendingTraits.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = pendingTraits.map((t, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <span class="trait-intensity">${Math.round(t.intensity * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removePendingTrait(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

async function createCharacter() {
    const name = document.getElementById('char-name-input').value.trim();
    const author = document.getElementById('char-author-input').value.trim();
    const description = document.getElementById('char-desc-input').value.trim();
    const backstory = document.getElementById('char-backstory-input').value.trim();
    const greeting = document.getElementById('char-greeting-input').value.trim();
    const systemPrompt = document.getElementById('char-prompt-input').value.trim();
    const tagsRaw = document.getElementById('char-tags-input').value.trim();
    const examplesRaw = document.getElementById('char-examples-input').value.trim();

    // Collect any trait currently in the input fields
    const traitName = document.getElementById('char-trait-name').value.trim();
    const traitType = document.getElementById('char-trait-type').value;
    const traitDesc = document.getElementById('char-trait-desc').value.trim();
    const traitIntensity = parseFloat(document.getElementById('char-trait-intensity').value);

    const btn = document.getElementById('char-create-btn');
    const status = document.getElementById('char-create-status');

    // Build final traits list from pending + any unsaved input
    const traits = [...pendingTraits];
    if (traitName) {
        traits.push({
            trait_type: traitType,
            name: traitName,
            description: traitDesc || traitName,
            intensity: traitIntensity,
        });
    }

    if (!name) { document.getElementById('char-name-input').focus(); return; }
    if (!author) { document.getElementById('char-author-input').focus(); return; }
    if (!description) { document.getElementById('char-desc-input').focus(); return; }
    if (!traits.length) { document.getElementById('char-trait-name').focus(); status.textContent = 'At least one trait is required'; return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = '';

    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
    const exampleMessages = examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [];

    try {
        const resp = await fetch('/api/characters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, description, author, backstory,
                system_prompt: systemPrompt, greeting,
                example_messages: exampleMessages, tags, traits,
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create character' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        pendingTraits = [];  // reset
        showToast(`Character ${data.id} created ✅`);
        navigateTo('characters', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🎭 Create Character';
    }
}

// ── Character Edit Save ─────────────────────────────────────

async function saveCharacterEdit(characterId) {
    const btn = document.getElementById('char-save-btn');
    const status = document.getElementById('char-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const tagsRaw = document.getElementById('char-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
    const examplesRaw = document.getElementById('char-edit-examples').value.trim();
    const exampleMessages = examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('char-edit-name').value.trim(),
        description: document.getElementById('char-edit-desc').value.trim(),
        backstory: document.getElementById('char-edit-backstory').value.trim(),
        greeting: document.getElementById('char-edit-greeting').value.trim(),
        system_prompt: document.getElementById('char-edit-prompt').value.trim(),
        example_messages: exampleMessages,
        tags,
    };

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Character updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

// ── Character Status ────────────────────────────────────────

async function updateCharacterStatus(characterId, newStatus) {
    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Character set to ${newStatus} ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Character PNG Export ─────────────────────────────────────

async function exportCharacterPng(characterId) {
    // Open a file picker for the user to select a base PNG
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/png';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) { document.body.removeChild(fileInput); return; }

        const reader = new FileReader();
        reader.onload = async (ev) => {
            try {
                const imageData = ev.target.result; // data:image/png;base64,...
                const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/export-png`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_data: imageData }),
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: 'Export failed' }));
                    throw new Error(err.detail);
                }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const cd = resp.headers.get('Content-Disposition') || '';
                const match = cd.match(/filename="(.+?)"/);
                a.download = match ? match[1] : `jericho_${characterId}.png`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Character exported as PNG ✅');
            } catch (err) {
                showToast(`Error: ${err.message}`, true);
            }
        };
        reader.readAsDataURL(file);
        document.body.removeChild(fileInput);
    });

    fileInput.click();
}

// ── Character Trait Management (detail view) ─────────────────

async function addCharTrait(characterId) {
    const name = document.getElementById('detail-trait-name').value.trim();
    const traitType = document.getElementById('detail-trait-type').value;
    const desc = document.getElementById('detail-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('detail-trait-intensity').value);

    if (!name) { document.getElementById('detail-trait-name').focus(); return; }

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/traits`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trait_type: traitType, name, description: desc || name, intensity }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to add trait' }));
            throw new Error(err.detail);
        }
        showToast(`Trait "${name}" added ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeCharTrait(characterId, traitName) {
    if (!confirm(`Remove trait "${traitName}"?`)) return;

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/traits/${encodeURIComponent(traitName)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to remove trait' }));
            throw new Error(err.detail);
        }
        showToast(`Trait "${traitName}" removed ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Character Avatar Editor ─────────────────────────────────

let charAvatarState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };

function openCharAvatarEditor(characterId) {
    const modal = document.getElementById('char-avatar-modal');
    modal.style.display = 'flex';
    charAvatarState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };
    document.getElementById('char-avatar-preview-section').style.display = 'none';
    document.getElementById('char-avatar-save-btn').disabled = true;
    document.getElementById('char-avatar-file-input').value = '';

    const dropZone = document.getElementById('char-avatar-drop-zone');
    dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); };
    dropZone.ondragleave = () => { dropZone.classList.remove('drag-over'); };
    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) loadCharAvatarImage(file);
    };

    const canvas = document.getElementById('char-avatar-canvas');
    canvas.onmousedown = (e) => { charAvatarState.dragging = true; charAvatarState.lastX = e.clientX; charAvatarState.lastY = e.clientY; };
    canvas.onmousemove = (e) => {
        if (!charAvatarState.dragging) return;
        charAvatarState.offsetX += e.clientX - charAvatarState.lastX;
        charAvatarState.offsetY += e.clientY - charAvatarState.lastY;
        charAvatarState.lastX = e.clientX;
        charAvatarState.lastY = e.clientY;
        updateCharAvatarPreview();
    };
    canvas.onmouseup = () => { charAvatarState.dragging = false; };
    canvas.onmouseleave = () => { charAvatarState.dragging = false; };
}

function closeCharAvatarEditor() {
    document.getElementById('char-avatar-modal').style.display = 'none';
}

function handleCharAvatarFile(event) {
    const file = event.target.files[0];
    if (file) loadCharAvatarImage(file);
}

function loadCharAvatarImage(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            charAvatarState.img = img;
            charAvatarState.zoom = 1.0;
            charAvatarState.offsetX = 0;
            charAvatarState.offsetY = 0;
            document.getElementById('char-avatar-zoom').value = 1.0;
            document.getElementById('char-avatar-zoom-value').textContent = '1.0×';
            document.getElementById('char-avatar-preview-section').style.display = 'block';
            document.getElementById('char-avatar-save-btn').disabled = false;
            updateCharAvatarPreview();
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function updateCharAvatarPreview() {
    const canvas = document.getElementById('char-avatar-canvas');
    const ctx = canvas.getContext('2d');
    const zoom = parseFloat(document.getElementById('char-avatar-zoom').value);
    charAvatarState.zoom = zoom;
    document.getElementById('char-avatar-zoom-value').textContent = zoom.toFixed(1) + '×';

    const img = charAvatarState.img;
    if (!img) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    // Square clip (not circular — for character cards)
    ctx.beginPath();
    ctx.roundRect(0, 0, 200, 200, 12);
    ctx.clip();

    ctx.fillStyle = '#111827';
    ctx.fillRect(0, 0, 200, 200);

    const scale = zoom * Math.max(200 / img.width, 200 / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const x = (200 - w) / 2 + charAvatarState.offsetX;
    const y = (200 - h) / 2 + charAvatarState.offsetY;
    ctx.drawImage(img, x, y, w, h);
    ctx.restore();

    // Border
    ctx.beginPath();
    ctx.roundRect(1, 1, 198, 198, 12);
    ctx.strokeStyle = 'rgba(139, 92, 246, 0.5)';
    ctx.lineWidth = 2;
    ctx.stroke();
}

async function saveCharAvatar(characterId) {
    const canvas = document.getElementById('char-avatar-canvas');
    const btn = document.getElementById('char-avatar-save-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Uploading…';

    try {
        const imageData = canvas.toDataURL('image/png');
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/avatar-upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_data: imageData }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        showToast('Avatar saved ✅');
        closeCharAvatarEditor();
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Avatar';
    }
}

// ═══════════════════════════════════════════════════════════════
// Locations View
// ═══════════════════════════════════════════════════════════════

const LOCATION_FEATURE_TYPES = ['landmark', 'district', 'building', 'natural', 'infrastructure', 'custom'];

async function renderLocations() {
    showLoading();
    const data = await api('/api/locations');
    state.locationsData = data;

    const createForm = `
        <div class="card location-create-form">
            <h3>🌍 New Location</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Define a new world location for the council's domain.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="loc-name-input">Name</label>
                    <input id="loc-name-input" class="settings-input" placeholder="e.g. Ironhaven" />
                </div>
                <div class="filter-group">
                    <label for="loc-author-input">Author</label>
                    <input id="loc-author-input" class="settings-input" placeholder="e.g. Council" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="loc-desc-input">Description</label>
                <textarea id="loc-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Describe this location…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="loc-lore-input">Lore</label>
                <textarea id="loc-lore-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="History and background of this place…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="loc-tags-input">Tags</label>
                    <input id="loc-tags-input" class="settings-input" placeholder="port, fortress, capital (comma-separated)" />
                </div>
                <div class="filter-group">
                    <label for="loc-coords-input">Coordinates</label>
                    <input id="loc-coords-input" class="settings-input" placeholder="e.g. 42.3N, 71.1W (optional)" />
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createLocation()" id="loc-create-btn">
                    🌍 Create Location
                </button>
                <span id="loc-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🗺️ Locations</h2>
                    <p>No locations defined yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const cards = data.map(loc => {
        const featuresHtml = (loc.features || []).slice(0, 3).map(f =>
            `<span class="location-feature-chip">
                <span class="feature-type-dot feature-type-${f.feature_type}"></span>
                ${escapeHtml(f.name)}
            </span>`
        ).join('');

        const tagsHtml = (loc.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');
        const moreFeats = (loc.features || []).length > 3 ? `<span class="location-feature-chip">+${loc.features.length - 3} more</span>` : '';

        return `
        <div class="card card-clickable location-card" onclick="navigateTo('locations','${loc.id}')">
            <div class="loc-header">
                <div>
                    <div class="loc-name">${escapeHtml(loc.name)}</div>
                    <div class="loc-author">by ${escapeHtml(loc.author)} · v${loc.version || 1}</div>
                </div>
                ${badge(loc.status)}
            </div>
            <div class="loc-desc">${truncate(loc.description, 120)}</div>
            ${featuresHtml || moreFeats ? `<div class="location-features-row">${featuresHtml}${moreFeats}</div>` : ''}
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🗺️ Locations</h2>
                <p>${data.length} world location${data.length !== 1 ? 's' : ''}</p>
            </div>
            ${createForm}
            <div class="location-grid">${cards}</div>
        </div>`;
}

async function renderLocationDetail(id) {
    showLoading();
    const data = await api(`/api/locations/${encodeURIComponent(id)}`);

    const featuresHtml = (data.features || []).map(f => `
        <div class="location-feature-detail">
            <div class="location-feature-detail-header">
                <span class="feature-type-dot feature-type-${f.feature_type}"></span>
                <strong>${escapeHtml(f.name)}</strong>
                <span class="specialty-tag">${f.feature_type}</span>
            </div>
            <p class="location-feature-detail-desc">${escapeHtml(f.description)}</p>
        </div>`).join('');

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');

    // Load children
    let childrenHtml = '';
    try {
        const children = await api(`/api/locations?parent_location_id=${encodeURIComponent(id)}`);
        if (children.length) {
            childrenHtml = `<div class="detail-section">
                <h4>🏛️ Sub-locations (${children.length})</h4>
                <div class="location-children-list">
                    ${children.map(c => `
                        <div class="card card-clickable location-child" onclick="navigateTo('locations','${c.id}')">
                            <strong>${escapeHtml(c.name)}</strong>
                            <span style="color:var(--text-muted);font-size:0.82rem">${truncate(c.description, 60)}</span>
                            ${badge(c.status)}
                        </div>`).join('')}
                </div>
            </div>`;
        }
    } catch { /* ignore */ }

    // Status action buttons
    let statusActions = '';
    if (data.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateLocationStatus('${data.id}', 'active')">✅ Activate</button>`;
    } else if (data.status === 'active') {
        statusActions = `<button class="btn btn-secondary btn-sm" onclick="updateLocationStatus('${data.id}', 'archived')">Archive</button>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('locations')">← Back to Locations</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id} · v${data.version || 1}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;align-items:center;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${statusActions}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('locations')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.lore ? `<div class="detail-section"><h4>📜 Lore</h4><p style="white-space:pre-line">${escapeHtml(data.lore)}</p></div>` : ''}

                ${data.coordinates ? `<div class="detail-section"><h4>📍 Coordinates</h4><p style="font-family:'JetBrains Mono',monospace;color:var(--accent-cyan)">${escapeHtml(data.coordinates)}</p></div>` : ''}

                ${featuresHtml ? `<div class="detail-section"><h4>⭐ Features (${data.features.length})</h4><div class="location-features-list">${featuresHtml}</div></div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                ${data.parent_location_id ? `<div class="detail-section"><h4>🔗 Parent Location</h4><a class="location-parent-link" onclick="navigateTo('locations','${data.parent_location_id}')">${data.parent_location_id}</a></div>` : ''}

                ${childrenHtml}

                <div class="detail-section" style="margin-top:var(--space-xl);border-top:1px solid var(--border-subtle);padding-top:var(--space-lg)">
                    <h4>✏️ Edit Location</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="loc-edit-name">Name</label>
                            <input id="loc-edit-name" class="settings-input" value="${escapeAttr(data.name)}" />
                        </div>
                        <div class="filter-group">
                            <label for="loc-edit-coords">Coordinates</label>
                            <input id="loc-edit-coords" class="settings-input" value="${escapeAttr(data.coordinates)}" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-desc">Description</label>
                        <textarea id="loc-edit-desc" class="settings-input proposal-textarea" rows="2">${escapeHtml(data.description)}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-lore">Lore</label>
                        <textarea id="loc-edit-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.lore || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-tags">Tags</label>
                        <input id="loc-edit-tags" class="settings-input" value="${escapeAttr((data.tags || []).join(', '))}" />
                    </div>
                    <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveLocationEdit('${data.id}')" id="loc-save-btn">
                            💾 Save Changes
                        </button>
                        <span id="loc-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>
        </div>`;
}

async function createLocation() {
    const name = document.getElementById('loc-name-input').value.trim();
    const author = document.getElementById('loc-author-input').value.trim();
    const description = document.getElementById('loc-desc-input').value.trim();
    const lore = document.getElementById('loc-lore-input').value.trim();
    const tagsRaw = document.getElementById('loc-tags-input').value.trim();
    const coordinates = document.getElementById('loc-coords-input').value.trim();
    const btn = document.getElementById('loc-create-btn');
    const status = document.getElementById('loc-create-status');

    if (!name) { document.getElementById('loc-name-input').focus(); return; }
    if (!author) { document.getElementById('loc-author-input').focus(); return; }
    if (!description) { document.getElementById('loc-desc-input').focus(); return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = '';

    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    try {
        const resp = await fetch('/api/locations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, lore, tags, coordinates }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create location' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Location ${data.id} created ✅`);
        navigateTo('locations', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🌍 Create Location';
    }
}

async function saveLocationEdit(locationId) {
    const btn = document.getElementById('loc-save-btn');
    const status = document.getElementById('loc-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const tagsRaw = document.getElementById('loc-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('loc-edit-name').value.trim(),
        description: document.getElementById('loc-edit-desc').value.trim(),
        lore: document.getElementById('loc-edit-lore').value.trim(),
        coordinates: document.getElementById('loc-edit-coords').value.trim(),
        tags,
    };

    try {
        const resp = await fetch(`/api/locations/${encodeURIComponent(locationId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Location updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderLocationDetail(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

async function updateLocationStatus(locationId, newStatus) {
    try {
        const resp = await fetch(`/api/locations/${encodeURIComponent(locationId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Location set to ${newStatus} ✅`);
        await renderLocationDetail(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Analytics View
// ═══════════════════════════════════════════════════════════════

async function renderAnalytics() {
    showLoading();
    const data = await api('/api/analytics');
    state.analyticsData = data;

    const ps = data.proposal_stats || {};
    const vs = data.voting_stats || {};
    const ss = data.session_stats || {};
    const top = data.top_participants || [];

    let topHtml = '';
    if (top.length) {
        const maxScore = top[0] ? top[0][1] : 1;
        topHtml = top.map(([name, score], i) => `
            <div class="top-member-row">
                <span class="top-member-rank">#${i + 1}</span>
                <span class="top-member-name">${name}</span>
                <div class="top-member-bar-bg">
                    <div class="top-member-bar-fill" style="width:${maxScore ? Math.round(score / maxScore * 100) : 0}%"></div>
                </div>
                <span class="top-member-score">${score}</span>
            </div>`).join('');
    }

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Analytics</h2>
                <p>Participation rates, voting patterns, and member activity</p>
            </div>

            <div class="analytics-grid">
                <div class="card analytics-card">
                    <h3>📜 Proposal Statistics</h3>
                    <div class="analytics-row"><span class="label">Total Proposals</span><span class="value">${ps.total || 0}</span></div>
                    <div class="analytics-row"><span class="label">Approval Rate</span><span class="value">${Math.round((ps.approval_rate || 0) * 100)}%</span></div>
                    ${Object.entries(ps.by_status || {}).map(([k, v]) => `
                        <div class="analytics-row"><span class="label">${badge(k)}</span><span class="value">${v}</span></div>`).join('')}
                    ${Object.entries(ps.by_category || {}).map(([k, v]) => `
                        <div class="analytics-row"><span class="label">${badge(k)}</span><span class="value">${v}</span></div>`).join('')}
                </div>

                <div class="card analytics-card">
                    <h3>🗳️ Voting Statistics</h3>
                    <div class="analytics-row"><span class="label">Total Records</span><span class="value">${vs.total_records || 0}</span></div>
                    <div class="analytics-row"><span class="label">Total Votes Cast</span><span class="value">${vs.total_votes_cast || 0}</span></div>
                    <div class="analytics-row"><span class="label">Avg Votes / Record</span><span class="value">${vs.avg_votes_per_record || 0}</span></div>
                    <div class="analytics-row"><span class="label">Quorum Achievement</span><span class="value">${Math.round((vs.quorum_achievement_rate || 0) * 100)}%</span></div>
                    <div class="analytics-row"><span class="label">Approval Rate</span><span class="value">${Math.round((vs.approval_rate || 0) * 100)}%</span></div>
                    <div class="analytics-row"><span class="label">Vetoes</span><span class="value">${vs.veto_count || 0}</span></div>
                </div>

                <div class="card analytics-card">
                    <h3>📊 Session Statistics</h3>
                    <div class="analytics-row"><span class="label">Total Sessions</span><span class="value">${ss.total_sessions || 0}</span></div>
                    <div class="analytics-row"><span class="label">Avg Messages / Session</span><span class="value">${ss.avg_messages_per_session || 0}</span></div>
                    <div class="analytics-row"><span class="label">Avg Participants</span><span class="value">${ss.avg_participants || 0}</span></div>
                    ${Object.entries(ss.by_phase || {}).map(([k, v]) => `
                        <div class="analytics-row"><span class="label">${k}</span><span class="value">${v}</span></div>`).join('')}
                </div>

                ${topHtml ? `
                <div class="card analytics-card">
                    <h3>🏆 Top Participants</h3>
                    <div class="top-members-list">${topHtml}</div>
                </div>` : ''}
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Chat View
// ═══════════════════════════════════════════════════════════════

async function renderChat() {
    showLoading();
    let chats = [];
    try { chats = await api('/api/chat'); } catch { /* empty */ }

    // Fetch council members for the "New Chat" selector
    let members = [];
    try { members = await api('/api/council'); } catch { /* empty */ }

    // Fetch active characters for the "New Chat" selector
    let characters = [];
    try { characters = await api('/api/characters?status=active'); } catch { /* empty */ }

    // Build avatar URL lookup: { "sage": "/api/council/Sage/avatar", ... }
    const avatarMap = {};
    members.forEach(m => { if (m.avatar_url) avatarMap[m.name.toLowerCase()] = m.avatar_url; });
    characters.forEach(c => { if (c.avatar_url) avatarMap[c.name.toLowerCase()] = c.avatar_url; });

    const memberOptions = members.map(m =>
        `<option value="member:${m.name}">${m.name} — ${m.role}</option>`
    ).join('');

    const characterOptions = characters.map(c =>
        `<option value="char:${c.id}">🎭 ${c.name} — ${c.description ? c.description.substring(0, 40) : 'Character'}</option>`
    ).join('');

    const activeChats = chats.filter(c => !c.closed_at);
    const closedChats = chats.filter(c => c.closed_at);

    function chatCard(c, idx) {
        const isOpen = !c.closed_at;
        const msgCount = (c.messages || []).length;
        const lastMsg = c.messages && c.messages.length
            ? c.messages[c.messages.length - 1]
            : null;
        const preview = lastMsg ? truncate(lastMsg.content, 80) : 'No messages yet';
        const statusBadge = isOpen
            ? (c.paused ? badge('paused', 'paused') : badge('active', 'active'))
            : badge('closed', 'closed');

        const hasCharacters = c.characters && c.characters.length > 0;
        // Resolve character IDs to names for display
        const charNames = hasCharacters ? c.characters.map(cid => {
            const found = characters.find(ch => ch.id === cid);
            return found ? found.name : cid;
        }) : [];
        const charNamesLower = charNames.map(n => n.toLowerCase());
        // Filter council_members to exclude names that are actually characters (legacy data fix)
        const rawMembers = c.council_members && c.council_members.length
            ? c.council_members : (!hasCharacters && c.member_name ? [c.member_name] : []);
        const chatMembers = rawMembers.filter(m => !charNamesLower.includes(m.toLowerCase()));
        const membersLabel = [...chatMembers, ...charNames.map(n => '🎭 ' + n)].join(', ');

        // Build avatar list: council members + character names (for character-only chats)
        const allCardParticipants = [...chatMembers, ...charNames];

        return `
        <div class="card card-clickable chat-card" onclick="navigateTo('chat','${c.chat_id}')">
            <div class="chat-card-header">
                <div class="chat-card-info">
                    <div class="chat-card-avatars">
                        ${allCardParticipants.slice(0, 3).map((m, i) => memberAvatarWithImage(m, idx + i, null, avatarMap[m.toLowerCase()])).join('')}
                        ${allCardParticipants.length > 3 ? `<span class="chat-card-more">+${allCardParticipants.length - 3}</span>` : ''}
                    </div>
                    <div>
                        <div class="chat-card-title">${c.title}</div>
                        <div class="chat-card-member">${membersLabel}${c.topic ? ' · ' + c.topic : ''}</div>
                    </div>
                </div>
                <div class="chat-card-meta">
                    ${statusBadge}
                    <span class="chat-card-count">${msgCount} msg${msgCount !== 1 ? 's' : ''}</span>
                </div>
            </div>
            <div class="chat-card-preview">${preview}</div>
            <div class="chat-card-date">${formatDate(c.created_at)}</div>
        </div>`;
    }

    const activeHtml = activeChats.length
        ? activeChats.map((c, i) => chatCard(c, i)).join('')
        : '<div class="empty-state"><div class="empty-icon">💬</div><p>No active chats. Start a new conversation!</p></div>';

    const closedHtml = closedChats.length
        ? `<details class="chat-closed-section">
            <summary class="chat-closed-toggle">Closed Chats (${closedChats.length})</summary>
            <div class="chat-list">${closedChats.map((c, i) => chatCard(c, i + activeChats.length)).join('')}</div>
           </details>`
        : '';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>💬 Chat</h2>
                <p>Talk directly with council members and characters</p>
            </div>

            <div class="chat-new-form card">
                <h3>New Conversation</h3>
                <div class="chat-new-row">
                    <div class="filter-group">
                        <label for="chat-participant-select">Participant</label>
                        <select id="chat-participant-select" class="settings-input">
                            <option value="">Select a participant…</option>
                            <optgroup label="Council Members">
                                ${memberOptions}
                            </optgroup>
                            ${characterOptions ? `<optgroup label="Characters (Active)">${characterOptions}</optgroup>` : ''}
                        </select>
                    </div>
                    <div class="filter-group" style="flex:1">
                        <label for="chat-title-input">Chat Title</label>
                        <input id="chat-title-input" class="settings-input" placeholder="e.g. Ethics Discussion" />
                    </div>
                    <div class="filter-group" style="flex:1">
                        <label for="chat-topic-input">Topic (optional)</label>
                        <input id="chat-topic-input" class="settings-input" placeholder="e.g. AI alignment" />
                    </div>
                    <button class="btn btn-primary chat-new-btn" onclick="createNewChat()" id="chat-create-btn">
                        🚀 Start Chat
                    </button>
                </div>
            </div>

            <div class="chat-list">${activeHtml}</div>
            ${closedHtml}
        </div>`;
}

async function createNewChat() {
    const participantSel = document.getElementById('chat-participant-select');
    const titleInput = document.getElementById('chat-title-input');
    const topicInput = document.getElementById('chat-topic-input');
    const btn = document.getElementById('chat-create-btn');

    const participantVal = participantSel.value;
    const title = titleInput.value.trim();
    const topic = topicInput.value.trim();

    if (!participantVal) { participantSel.focus(); return; }
    if (!title) { titleInput.focus(); return; }

    // Parse participant type: "member:Name" or "char:CH-0001"
    let payload = { title, topic };
    let displayName = '';
    if (participantVal.startsWith('member:')) {
        payload.member_name = participantVal.substring(7);
        displayName = payload.member_name;
    } else if (participantVal.startsWith('char:')) {
        payload.character_id = participantVal.substring(5);
        displayName = participantSel.options[participantSel.selectedIndex].text.replace('🎭 ', '');
    }

    btn.disabled = true;
    btn.textContent = 'Creating…';
    try {
        const data = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(r => { if (!r.ok) throw new Error('Failed to create chat'); return r.json(); });

        showToast(`Chat with ${displayName} started! ✅`);
        navigateTo('chat', data.chat_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Start Chat';
    }
}

async function renderChatDetail(chatId) {
    showLoading();
    let data;
    try {
        data = await api(`/api/chat/${encodeURIComponent(chatId)}`);
    } catch (err) {
        showError(err.message);
        return;
    }

    const isClosed = !!data.closed_at;
    const isPaused = !!data.paused;
    const chatCharacters = data.characters || [];
    const rawMembers = data.council_members && data.council_members.length
        ? data.council_members : (data.member_name ? [data.member_name] : []);
    // We'll filter members after resolving character names (below)
    const primaryMember = rawMembers[0] || data.member_name || 'Agent';

    // Fetch all council members for the add-member dropdown
    let allMembers = [];
    try { allMembers = await api('/api/council'); } catch { /* empty */ }
    // Fetch all active characters for the add-character dropdown
    let allCharacters = [];
    try { allCharacters = await api('/api/characters?status=active'); } catch { /* empty */ }
    // Build avatar URL lookup: { "sage": "/api/council/Sage/avatar", ... }
    const avatarMap = {};
    allMembers.forEach(m => { if (m.avatar_url) avatarMap[m.name.toLowerCase()] = m.avatar_url; });
    allCharacters.forEach(c => { if (c.avatar_url) avatarMap[c.name.toLowerCase()] = c.avatar_url; });
    state.chatAvatarMap = avatarMap;  // Store for SSE handlers
    const availableMembers = allMembers.filter(m =>
        !rawMembers.some(cm => cm.toLowerCase() === m.name.toLowerCase())
    );
    const availableCharacters = allCharacters.filter(c =>
        !chatCharacters.includes(c.id)
    );

    // Build a name lookup for character IDs
    const charNameMap = {};
    allCharacters.forEach(c => { charNameMap[c.id] = c.name; });
    // Also resolve from the chat data messages
    const resolvedCharNames = chatCharacters.map(cid => charNameMap[cid] || cid);
    // Filter out council_members entries that are actually characters (legacy data fix)
    const resolvedCharNamesLower = resolvedCharNames.map(n => n.toLowerCase());
    const members = rawMembers.filter(m => !resolvedCharNamesLower.includes(m.toLowerCase()));
    const totalParticipants = members.length + chatCharacters.length;
    const isMultiMember = totalParticipants > 1;
    const allParticipantNames = [...members, ...resolvedCharNames];

    const messagesHtml = (data.messages || []).map(m => {
        const isHuman = m.role === 'human';
        const bubbleClass = isHuman ? 'chat-bubble-human' : 'chat-bubble-agent';
        const speakerName = isHuman ? 'You' : (m.speaker || primaryMember);
        const avatarIdx = allParticipantNames.findIndex(cm => cm.toLowerCase() === (m.speaker || '').toLowerCase());
        const avatar = !isHuman ? memberAvatarWithImage(speakerName, avatarIdx >= 0 ? avatarIdx : 0, null, avatarMap[speakerName.toLowerCase()]) : '';
        const time = m.timestamp ? new Date(m.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';

        const renderedContent = renderMarkdown(m.content);
        const displayContent = (!isHuman && state.silentpassaEnabled)
            ? wrapPresenceContent(renderedContent, speakerName)
            : renderedContent;

        return `
        <div class="chat-message ${bubbleClass}">
            ${!isHuman ? `<div class="chat-msg-avatar">${avatar}</div>` : ''}
            <div class="chat-msg-body">
                <div class="chat-msg-header">
                    <span class="chat-msg-speaker">${speakerName}</span>
                    <span class="chat-msg-time">${time}</span>
                </div>
                <div class="chat-msg-content">${displayContent}</div>
            </div>
        </div>`;
    }).join('');

    // Member chips in topbar
    const memberChipsHtml = members.map((m, i) => {
        const removeBtn = (!isClosed && totalParticipants > 1)
            ? `<button class="chip-remove" onclick="event.stopPropagation();removeChatMember('${chatId}','${m}')" title="Remove ${m}">✕</button>`
            : '';
        return `<div class="member-chip">${memberAvatarWithImage(m, i, null, avatarMap[m.toLowerCase()])}<span>${m}</span>${removeBtn}</div>`;
    }).join('');

    // Character chips in topbar
    const characterChipsHtml = chatCharacters.map((cid, i) => {
        const cname = charNameMap[cid] || cid;
        const removeBtn = (!isClosed && totalParticipants > 1)
            ? `<button class="chip-remove" onclick="event.stopPropagation();removeChatCharacter('${chatId}','${cid}')" title="Remove ${cname}">✕</button>`
            : '';
        return `<div class="member-chip"><span class="char-chip-icon">🎭</span>${memberAvatarWithImage(cname, members.length + i, null, avatarMap[cname.toLowerCase()])}<span>${cname}</span>${removeBtn}</div>`;
    }).join('');

    // Add member dropdown (includes both council members and characters)
    const hasAvailable = availableMembers.length > 0 || availableCharacters.length > 0;
    const addMemberHtml = (!isClosed && hasAvailable) ? `
        <div class="add-member-dropdown">
            <button class="btn btn-secondary btn-sm add-member-btn" onclick="toggleAddMemberDropdown()" id="add-member-toggle">
                ＋ Add Participant
            </button>
            <div class="add-member-list" id="add-member-list" style="display:none">
                ${availableMembers.map(m => `
                    <button class="add-member-option" onclick="addChatMember('${chatId}','${m.name}')">
                        ${m.name} <span class="add-member-role">— ${m.role}</span>
                    </button>`).join('')}
                ${availableCharacters.map(c => `
                    <button class="add-member-option" onclick="addChatCharacter('${chatId}','${c.id}')">
                        🎭 ${c.name} <span class="add-member-role">— Character</span>
                    </button>`).join('')}
            </div>
        </div>` : '';

    // Pause / Resume button (only when multi-member)
    const pauseResumeHtml = (!isClosed && isMultiMember) ? (
        isPaused
            ? `<button class="btn btn-primary btn-sm chat-pause-btn" onclick="resumeChat('${chatId}')">▶ Resume</button>
               <button class="btn btn-primary btn-sm chat-continue-btn" onclick="continueChat('${chatId}')">🔄 Continue</button>`
            : `<button class="btn btn-secondary btn-sm chat-pause-btn" onclick="pauseChat('${chatId}')">⏸ Pause</button>`
    ) : '';

    // Paused notice
    const pausedNotice = isPaused ? `
        <div class="chat-paused-notice">
            <span>⏸ Chat is paused.</span>
            <span>Send a message or click <strong>Resume</strong> to continue the conversation.</span>
        </div>` : '';

    const inputBarHtml = isClosed
        ? `<div class="chat-closed-notice">This conversation has been closed.</div>`
        : `
        ${pausedNotice}
        <div class="chat-input-bar">
            <input id="chat-input" class="chat-input" type="text"
                   placeholder="${isPaused ? 'Type to resume and send…' : 'Type your message…'}" autocomplete="off"
                   onkeydown="if(event.key==='Enter')sendChatMessage('${chatId}')" />
            <button class="btn btn-primary chat-send-btn" id="chat-send-btn"
                    onclick="sendChatMessage('${chatId}')">
                Send ➤
            </button>
        </div>`;

    const closeBtn = !isClosed
        ? `<button class="btn btn-danger chat-close-btn" onclick="closeChatConversation('${chatId}')">End Chat</button>`
        : '';

    $main().innerHTML = `
        <div class="view-enter chat-detail-view">
            <div class="chat-detail-topbar">
                <button class="back-btn" onclick="navigateTo('chat')">← Back to Chats</button>
                <div class="chat-detail-info">
                    <div>
                        <div style="font-weight:700">${data.title}</div>
                        <div style="font-size:0.8rem;color:var(--text-muted)">
                            ${data.topic ? data.topic + ' · ' : ''}
                            ${isClosed ? badge('closed', 'closed') : (isPaused ? badge('paused', 'paused') : badge('active', 'active'))}
                        </div>
                    </div>
                </div>
                <div class="chat-topbar-actions">
                    <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPassa('${chatId}')" id="silentpassa-btn" title="Toggle [PRESENT]/[SILENCE] wrappers">
                        ${state.silentpassaEnabled ? '🔔 SilentPassa' : '🔕 SilentPassa'}
                    </button>
                    ${pauseResumeHtml}
                    ${closeBtn}
                </div>
            </div>

            <div class="chat-members-bar">
                <div class="member-chips">${memberChipsHtml}${characterChipsHtml}</div>
                ${addMemberHtml}
            </div>

            <div class="chat-messages" id="chat-messages">
                ${messagesHtml || '<div class="chat-empty">Send a message to start the conversation.</div>'}
            </div>

            ${inputBarHtml}
        </div>`;

    // Auto-scroll to bottom
    const msgContainer = document.getElementById('chat-messages');
    if (msgContainer) msgContainer.scrollTop = msgContainer.scrollHeight;

    // Auto-focus input
    const inp = document.getElementById('chat-input');
    if (inp) inp.focus();
}

function toggleAddMemberDropdown() {
    const list = document.getElementById('add-member-list');
    if (list) list.style.display = list.style.display === 'none' ? 'block' : 'none';
}

async function addChatMember(chatId, memberName) {
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/add-member`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_name: memberName }),
        }).then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast(`${memberName} joined the chat ✅`);
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeChatMember(chatId, memberName) {
    if (!confirm(`Remove ${memberName} from this chat?`)) return;
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/remove-member`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_name: memberName }),
        }).then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast(`${memberName} removed from chat`);
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function addChatCharacter(chatId, characterId) {
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/add-character`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ character_id: characterId }),
        }).then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast('Character joined the chat \u2705');
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeChatCharacter(chatId, characterId) {
    if (!confirm('Remove this character from the chat?')) return;
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/remove-character`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ character_id: characterId }),
        }).then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast('Character removed from chat');
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function pauseChat(chatId) {
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/pause`, { method: 'POST' })
            .then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast('Chat paused ⏸');
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function resumeChat(chatId) {
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/resume`, { method: 'POST' })
            .then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
        showToast('Chat resumed ▶');
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function continueChat(chatId) {
    // Show typing indicator
    const msgContainer = document.getElementById('chat-messages');
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-msg-header"><span class="chat-msg-speaker">Council deliberating…</span></div><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    if (msgContainer) {
        msgContainer.appendChild(typingEl);
        msgContainer.scrollTop = msgContainer.scrollHeight;
    }

    // Disable all action buttons
    document.querySelectorAll('.chat-continue-btn, .chat-pause-btn').forEach(b => b.disabled = true);

    try {
        const resp = await fetch(`/api/chat/${encodeURIComponent(chatId)}/continue-stream`, { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Continue failed' }));
            throw new Error(err.detail);
        }

        // Remove typing indicator once stream starts
        if (typingEl.parentNode) typingEl.remove();

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events from buffer
            const parts = buffer.split('\n\n');
            buffer = parts.pop(); // keep incomplete tail

            for (const part of parts) {
                if (!part.trim()) continue;
                const eventMatch = part.match(/^event:\s*(.+)$/m);
                const dataMatch = part.match(/^data:\s*(.+)$/m);
                if (!eventMatch || !dataMatch) continue;

                const eventType = eventMatch[1].trim();
                const data = JSON.parse(dataMatch[1]);

                if (eventType === 'message') {
                    const avatarUrl = state.chatAvatarMap && state.chatAvatarMap[data.speaker.toLowerCase()];
                    appendAgentBubble(msgContainer, data.speaker, data.content, avatarUrl);
                } else if (eventType === 'done') {
                    await renderChatDetail(chatId);
                    return;
                } else if (eventType === 'error') {
                    throw new Error(data.detail);
                }
            }
        }

        // Fallback re-render
        await renderChatDetail(chatId);
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Error: ${err.message}`, true);
        document.querySelectorAll('.chat-continue-btn, .chat-pause-btn').forEach(b => b.disabled = false);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Render basic markdown (bold, italic, line breaks) to HTML.
 * Escapes HTML first for XSS safety, then converts markdown syntax.
 */
function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    // Bold: **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text* (but not inside <strong> tags already converted)
    html = html.replace(/(?<!\w)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    return html;
}

/**
 * Wrap rendered HTML content with [PRESENT] or [SILENCE] tags.
 * Called only for agent messages when silentpassa is enabled.
 */
function wrapPresenceContent(renderedHtml, speakerName) {
    const stripped = renderedHtml.replace(/<[^>]*>/g, '').trim();
    if (!stripped) {
        return `<div class="silence-wrapper"><span class="silence-tag">[SILENCE]</span> <span class="silence-speaker">${escapeHtml(speakerName)}</span> <span class="silence-tag">[/SILENCE]</span></div>`;
    }
    return `<div class="presence-wrapper"><span class="presence-tag">[PRESENT]</span>${renderedHtml}<span class="presence-tag">[/PRESENT]</span></div>`;
}

/**
 * Toggle the SilentPassa feature on/off and re-render the current chat.
 */
async function toggleSilentPassa(chatId) {
    state.silentpassaEnabled = !state.silentpassaEnabled;
    localStorage.setItem('silentpassa', state.silentpassaEnabled ? 'on' : 'off');
    if (chatId) {
        await renderChatDetail(chatId);
    }
}

function appendAgentBubble(container, speaker, content, avatarUrl) {
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'chat-message chat-bubble-agent';
    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    bubble.innerHTML = `
        <div class="chat-msg-avatar">${memberAvatarWithImage(speaker, 0, null, avatarUrl)}</div>
        <div class="chat-msg-body">
            <div class="chat-msg-header">
                <span class="chat-msg-speaker">${escapeHtml(speaker)}</span>
                <span class="chat-msg-time">${time}</span>
            </div>
            <div class="chat-msg-content">${state.silentpassaEnabled ? wrapPresenceContent(renderMarkdown(content), speaker) : renderMarkdown(content)}</div>
        </div>`;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

async function sendChatMessage(chatId) {
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('chat-send-btn');
    const content = input.value.trim();
    if (!content) { input.focus(); return; }

    input.disabled = true;
    btn.disabled = true;
    btn.textContent = '⏳ Thinking…';

    // Immediately show the human message as a preview
    const msgContainer = document.getElementById('chat-messages');
    const emptyMsg = msgContainer.querySelector('.chat-empty');
    if (emptyMsg) emptyMsg.remove();

    const humanBubble = document.createElement('div');
    humanBubble.className = 'chat-message chat-bubble-human';
    humanBubble.innerHTML = `
        <div class="chat-msg-body">
            <div class="chat-msg-header">
                <span class="chat-msg-speaker">You</span>
                <span class="chat-msg-time">now</span>
            </div>
            <div class="chat-msg-content">${renderMarkdown(content)}</div>
        </div>`;
    msgContainer.appendChild(humanBubble);
    msgContainer.scrollTop = msgContainer.scrollHeight;
    input.value = '';

    // Show typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    try {
        const resp = await fetch(`/api/chat/${encodeURIComponent(chatId)}/send-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Send failed' }));
            throw new Error(err.detail);
        }

        // Remove typing indicator once first response arrives
        if (typingEl.parentNode) typingEl.remove();

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events from buffer
            const parts = buffer.split('\n\n');
            buffer = parts.pop(); // keep incomplete tail

            for (const part of parts) {
                if (!part.trim()) continue;
                const eventMatch = part.match(/^event:\s*(.+)$/m);
                const dataMatch = part.match(/^data:\s*(.+)$/m);
                if (!eventMatch || !dataMatch) continue;

                const eventType = eventMatch[1].trim();
                const data = JSON.parse(dataMatch[1]);

                if (eventType === 'message') {
                    const avatarUrl = state.chatAvatarMap && state.chatAvatarMap[data.speaker.toLowerCase()];
                    appendAgentBubble(msgContainer, data.speaker, data.content, avatarUrl);
                } else if (eventType === 'done') {
                    // Re-render with full server state
                    await renderChatDetail(chatId);
                    return;
                } else if (eventType === 'error') {
                    throw new Error(data.detail);
                }
            }
        }

        // Fallback re-render
        await renderChatDetail(chatId);
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Error: ${err.message}`, true);
        input.disabled = false;
        btn.disabled = false;
        btn.textContent = 'Send ➤';
    }
}

async function closeChatConversation(chatId) {
    if (!confirm('End this conversation?')) return;
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        showToast('Chat closed ✅');
        await renderChatDetail(chatId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Settings View
// ═══════════════════════════════════════════════════════════════

const PROVIDER_LABELS = {
    openrouter: { name: 'OpenRouter', icon: '🌐', url: 'https://openrouter.ai/keys' },
    mancer:     { name: 'Mancer',     icon: '🧠', url: 'https://mancer.tech' },
};

// Model dropdown options (fetched from API, cached here)
let MANCER_MODEL_OPTIONS = ['Default'];
let OPENROUTER_MODEL_OPTIONS = ['Default'];

async function renderSettings() {
    showLoading();
    const [keys, models, userDescData, mancerModels, openrouterModels] = await Promise.all([
        api('/api/settings/keys'),
        api('/api/settings/models'),
        api('/api/settings/user-description'),
        api('/api/settings/mancer-models').catch(() => ['Default']),
        api('/api/settings/openrouter-models').catch(() => ['Default']),
    ]);

    // Cache model options for use in council member editing
    if (mancerModels && mancerModels.length) MANCER_MODEL_OPTIONS = mancerModels;
    if (openrouterModels && openrouterModels.length) OPENROUTER_MODEL_OPTIONS = openrouterModels;

    const userDesc = userDescData.description || '';
    const maxLen = 700;

    // Build a map of provider -> model info
    const modelMap = {};
    models.forEach(m => { modelMap[m.provider] = m; });

    const cards = keys.map(k => {
        const info = PROVIDER_LABELS[k.provider] || { name: k.provider, icon: '🔑', url: '#' };
        const configured = k.configured;
        const statusBadge = configured
            ? `<span class="badge badge-active">✅ Configured</span>`
            : `<span class="badge badge-draft">❌ Not Set</span>`;
        const maskedDisplay = configured
            ? `<div class="key-masked"><code>${k.masked}</code></div>`
            : '';

        const modelInfo = modelMap[k.provider] || {};
        const currentModel = modelInfo.model || '';
        const isDefault = modelInfo.is_default !== false;
        const modelLabel = 'Default Model (fallback)';
        const modelBadge = isDefault
            ? `<span class="badge badge-draft" style="font-size:0.7rem">default</span>`
            : `<span class="badge badge-active" style="font-size:0.7rem">custom</span>`;

        return `
        <div class="card settings-card" id="key-card-${k.provider}">
            <div class="settings-card-header">
                <div class="settings-provider-info">
                    <span class="settings-provider-icon">${info.icon}</span>
                    <div>
                        <div class="settings-provider-name">${info.name}</div>
                        <a href="${info.url}" target="_blank" rel="noopener" class="settings-provider-link">Get API key ↗</a>
                    </div>
                </div>
                ${statusBadge}
            </div>
            ${maskedDisplay}
            <div class="settings-form">
                <div class="settings-input-row">
                    <input type="password"
                           id="key-input-${k.provider}"
                           class="settings-input"
                           placeholder="Paste your ${info.name} API key…"
                           autocomplete="off"
                           spellcheck="false" />
                    <button class="btn btn-primary" onclick="saveApiKey('${k.provider}')">
                        💾 Save
                    </button>
                    ${configured ? `<button class="btn btn-danger" onclick="deleteApiKey('${k.provider}')">🗑️ Delete</button>` : ''}
                </div>
            </div>
            <div class="settings-model-section">
                <div class="settings-model-header">
                    <span class="settings-model-label">🤖 ${modelLabel}</span>
                    ${modelBadge}
                </div>
                <p style="font-size:0.8rem;color:var(--text-muted);margin:var(--space-xs) 0">Used when a council member's model is set to "Default".</p>
                <div class="settings-input-row">
                    ${k.provider === 'mancer'
                        ? `<select id="model-input-${k.provider}" class="settings-input">
                               ${mancerModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                           </select>`
                        : `<select id="model-input-${k.provider}" class="settings-input">
                               ${openrouterModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                           </select>`
                    }
                    <button class="btn btn-primary" onclick="saveModel('${k.provider}')">
                        💾 Save
                    </button>
                </div>
            </div>
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>⚙️ Settings</h2>
                <p>Configure your profile, API provider keys, and models</p>
            </div>

            <div class="card settings-card user-profile-card">
                <div class="settings-card-header">
                    <div class="settings-provider-info">
                        <span class="settings-provider-icon">👤</span>
                        <div>
                            <div class="settings-provider-name">User Profile</div>
                            <span class="settings-provider-link" style="cursor:default">Tell the AI council about yourself</span>
                        </div>
                    </div>
                </div>
                <div class="settings-form" style="margin-top:var(--space-sm)">
                    <label for="user-desc-input" class="user-desc-label">
                        About You
                        <span class="user-desc-hint">This description is shared with council members so they know who they're speaking with.</span>
                    </label>
                    <textarea id="user-desc-input"
                              class="settings-input user-desc-textarea"
                              rows="5"
                              maxlength="${maxLen}"
                              placeholder="Write a brief description about yourself — your interests, role, what you're working on…"
                              oninput="updateCharCount()">${escapeHtml(userDesc)}</textarea>
                    <div class="user-desc-footer">
                        <span class="user-desc-counter" id="user-desc-counter">
                            <span id="user-desc-count">${userDesc.length}</span> / ${maxLen}
                        </span>
                        <div style="display:flex;align-items:center;gap:var(--space-sm)">
                            <span id="user-desc-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                            <button class="btn btn-primary" onclick="saveUserDescription()" id="user-desc-save-btn">
                                💾 Save
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="settings-notice">
                <span class="settings-notice-icon">🔒</span>
                <div>
                    <strong>Your keys are safe.</strong>
                    Keys are encrypted with AES before being stored locally in <code>config/.env</code>.
                    They are never transmitted to any third party — only to the API providers you configure.
                </div>
            </div>

            <div class="settings-grid">${cards}</div>
        </div>`;

    // Initialize character count display color
    updateCharCount();
}

async function saveApiKey(provider) {
    const input = document.getElementById(`key-input-${provider}`);
    const key = input.value.trim();
    if (!key) { input.focus(); return; }

    input.disabled = true;
    try {
        await fetch('/api/settings/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: key }),
        });
        input.value = '';
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} key saved & encrypted ✅`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        input.disabled = false;
    }
}

async function deleteApiKey(provider) {
    if (!confirm(`Remove the ${PROVIDER_LABELS[provider]?.name || provider} API key?`)) return;
    try {
        await fetch(`/api/settings/keys/${provider}`, { method: 'DELETE' });
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} key removed`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function saveModel(provider) {
    const el = document.getElementById(`model-input-${provider}`);
    const model = el.value.trim();
    if (!model) { el.focus(); return; }

    el.disabled = true;
    try {
        await fetch('/api/settings/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, model }),
        });
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} default model saved ✅`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        el.disabled = false;
    }
}

function updateCharCount() {
    const textarea = document.getElementById('user-desc-input');
    const countEl = document.getElementById('user-desc-count');
    const counterEl = document.getElementById('user-desc-counter');
    if (!textarea || !countEl || !counterEl) return;

    const len = textarea.value.length;
    countEl.textContent = len;

    // Color feedback
    if (len >= 700) {
        counterEl.classList.add('at-limit');
        counterEl.classList.remove('near-limit');
    } else if (len >= 600) {
        counterEl.classList.add('near-limit');
        counterEl.classList.remove('at-limit');
    } else {
        counterEl.classList.remove('near-limit', 'at-limit');
    }
}

async function saveUserDescription() {
    const textarea = document.getElementById('user-desc-input');
    const btn = document.getElementById('user-desc-save-btn');
    const status = document.getElementById('user-desc-status');
    const description = textarea.value;

    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    try {
        const resp = await fetch('/api/settings/user-description', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('User description saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save';
    }
}

function escapeHtml(text) {
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
}

function showToast(msg, isError) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'toast-error' : 'toast-success'}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('toast-exit'); }, 2500);
    setTimeout(() => { toast.remove(); }, 3000);
}

// ═══════════════════════════════════════════════════════════════
// Memory Explorer Views (F-028)
// ═══════════════════════════════════════════════════════════════

async function renderMemories() {
    showLoading();
    const data = await api('/api/memories');
    let sharedData = { decision_count: 0, history: '' };
    try { sharedData = await api('/api/memories/shared'); } catch { /* empty */ }

    const memberCards = data.map((m, i) => {
        const avatarHtml = m.avatar_url
            ? `<div class="memory-avatar" style="background: url('${m.avatar_url}') center/cover no-repeat"></div>`
            : `<div class="memory-avatar" style="background: ${AVATAR_COLORS[i % AVATAR_COLORS.length]}">${m.name.charAt(0).toUpperCase()}</div>`;
        return `
        <div class="card card-clickable memory-card" onclick="navigateTo('memories','${m.name}')">
            <div class="memory-card-header">
                ${avatarHtml}
                <div>
                    <div class="member-name">${m.name}</div>
                    <div class="member-role">${m.role}</div>
                </div>
            </div>
            <div class="memory-stats">
                <div class="memory-stat">
                    <span class="memory-stat-value">${m.belief_count}</span>
                    <span class="memory-stat-label">Core Beliefs</span>
                </div>
                <div class="memory-stat">
                    <span class="memory-stat-value">${m.event_count}</span>
                    <span class="memory-stat-label">Events</span>
                </div>
            </div>
        </div>`;
    }).join('');

    const sharedCard = `
        <div class="card card-clickable memory-card memory-card-shared" onclick="navigateTo('memories','shared')">
            <div class="memory-card-header">
                <div class="memory-avatar memory-avatar-shared">🌐</div>
                <div>
                    <div class="member-name">Shared Memory</div>
                    <div class="member-role">Council-wide decisions & history</div>
                </div>
            </div>
            <div class="memory-stats">
                <div class="memory-stat">
                    <span class="memory-stat-value">${sharedData.decision_count}</span>
                    <span class="memory-stat-label">Decisions</span>
                </div>
                <div class="memory-stat">
                    <span class="memory-stat-value">${sharedData.history ? '✓' : '—'}</span>
                    <span class="memory-stat-label">History</span>
                </div>
            </div>
        </div>`;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🧠 Memories</h2>
                <p>Explore council member beliefs, session events, and shared council memory</p>
            </div>
            <div class="member-grid">
                ${sharedCard}
                ${memberCards}
            </div>
        </div>`;
}

async function renderMemoryDetail(memberName) {
    showLoading();
    const limit = 25;
    const data = await api(`/api/memories/${encodeURIComponent(memberName)}?limit=${limit}`);

    const beliefRows = data.beliefs.length ? data.beliefs.map(b => `
        <div class="belief-item">
            <div class="belief-header">
                <span class="belief-topic">${escapeHtml(b.topic)}</span>
                <button class="btn-icon belief-delete" onclick="deleteCoreBelief('${escapeAttr(data.name)}', '${escapeAttr(b.topic)}')" title="Delete belief">
                    🗑️
                </button>
            </div>
            <div class="belief-content">${escapeHtml(b.content)}</div>
            <div class="belief-meta">
                ${b.source ? `<span class="belief-source">Source: ${escapeHtml(b.source)}</span>` : ''}
                ${b.added_timestamp ? `<span class="belief-timestamp">${formatDate(b.added_timestamp)}</span>` : ''}
            </div>
        </div>`).join('') : '<div class="empty-state"><div class="empty-icon">💭</div><p>No core beliefs recorded yet.</p></div>';

    const eventRows = data.events.length ? data.events.map(e => {
        const typeBadge = e.event_type || 'event';
        return `
        <div class="event-item">
            <div class="event-header">
                <span class="badge badge-${typeBadge}">${typeBadge}</span>
                <span class="event-session">${escapeHtml(e.session_id || '')}</span>
                <span class="event-timestamp">${formatDate(e.timestamp)}</span>
            </div>
            <div class="event-content">${escapeHtml(e.content)}</div>
            ${e.source ? `<div class="event-source">— ${escapeHtml(e.source)}</div>` : ''}
        </div>`;
    }).join('') : '<div class="empty-state"><div class="empty-icon">📝</div><p>No session events recorded yet.</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('memories')">← Back to Memories</button>
            <div class="page-header">
                <h2>🧠 ${escapeHtml(data.name)}'s Memory</h2>
                <p>${data.belief_count} core belief${data.belief_count !== 1 ? 's' : ''} · ${data.event_count} total event${data.event_count !== 1 ? 's' : ''}</p>
            </div>

            <div class="memory-detail-grid">
                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>💎 Core Beliefs</h3>
                        <span class="memory-panel-count">${data.belief_count}</span>
                    </div>
                    <div class="belief-list" id="belief-list">
                        ${beliefRows}
                    </div>
                </div>

                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>📋 Recent Events</h3>
                        <span class="memory-panel-count">Showing ${data.events.length} of ${data.event_count}</span>
                    </div>
                    <div class="event-list">
                        ${eventRows}
                    </div>
                </div>
            </div>
        </div>`;
}

async function renderSharedMemory() {
    showLoading();
    const data = await api('/api/memories/shared');

    const decisionRows = data.decisions.length ? data.decisions.map((d, i) => {
        const summary = typeof d === 'object' ? (d.summary || d.decision || d.content || JSON.stringify(d)) : String(d);
        const ts = d.timestamp || d.decided_at || '';
        return `
        <div class="event-item">
            <div class="event-header">
                <span class="badge badge-decided">#${i + 1}</span>
                ${ts ? `<span class="event-timestamp">${formatDate(ts)}</span>` : ''}
            </div>
            <div class="event-content">${escapeHtml(summary)}</div>
        </div>`;
    }).join('') : '<div class="empty-state"><div class="empty-icon">📜</div><p>No council decisions recorded yet.</p></div>';

    const historyHtml = data.history
        ? `<div class="shared-history-content">${escapeHtml(data.history)}</div>`
        : '<div class="empty-state"><div class="empty-icon">📖</div><p>No narrative history written yet.</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('memories')">← Back to Memories</button>
            <div class="page-header">
                <h2>🌐 Shared Council Memory</h2>
                <p>${data.decision_count} decision${data.decision_count !== 1 ? 's' : ''} recorded</p>
            </div>

            <div class="memory-detail-grid">
                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>⚖️ Council Decisions</h3>
                        <span class="memory-panel-count">${data.decision_count}</span>
                    </div>
                    <div class="event-list">
                        ${decisionRows}
                    </div>
                </div>

                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>📖 Narrative History</h3>
                    </div>
                    ${historyHtml}
                </div>
            </div>
        </div>`;
}

async function deleteCoreBelief(memberName, topic) {
    if (!confirm(`Delete belief "${topic}" from ${memberName}?`)) return;
    try {
        const resp = await fetch(`/api/memories/${encodeURIComponent(memberName)}/beliefs?topic=${encodeURIComponent(topic)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast(`Belief "${topic}" deleted ✅`);
        await renderMemoryDetail(memberName);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ─── Nav Count Updater ────────────────────────────────────────

function updateNavCounts(data) {
    if (data.members) document.getElementById('count-council').textContent = data.members.count || 0;
    if (data.proposals) document.getElementById('count-proposals').textContent = data.proposals.count || 0;
    if (data.votes) document.getElementById('count-votes').textContent = data.votes.count || 0;
    if (data.characters) document.getElementById('count-characters').textContent = data.characters.count || 0;
    if (data.locations) document.getElementById('count-locations').textContent = data.locations.count || 0;
    if (data.memories) {
        const memEl = document.getElementById('count-memories');
        if (memEl) memEl.textContent = data.memories.total_beliefs + data.memories.total_events;
    }
    if (data.evolutions) {
        const evoEl = document.getElementById('count-evolutions');
        if (evoEl) evoEl.textContent = data.evolutions.count || 0;
    }
}

// ═══════════════════════════════════════════════════════════════
// Evolution View
// ═══════════════════════════════════════════════════════════════

async function renderEvolution() {
    showLoading();
    const data = await api('/api/evolutions');

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🧬 Character Evolution</h2>
                    <p>No evolution records yet.</p>
                </div>
                <div class="empty-state">
                    <div class="empty-icon">🧬</div>
                    <p>No evolution proposals have been created.</p>
                </div>
            </div>`;
        return;
    }

    const rows = data.map(e => {
        const statusBadge = badge(e.status);
        const changeCount = (e.changes || []).length;
        return `
        <tr class="proposal-row" onclick="navigateTo('evolution','${e.evolution_id}')">
            <td class="col-id">${e.evolution_id}</td>
            <td>${e.character_id}</td>
            <td>${e.author}</td>
            <td>${changeCount} change${changeCount !== 1 ? 's' : ''}</td>
            <td>${statusBadge}</td>
            <td>${formatDate(e.created_at)}</td>
        </tr>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🧬 Character Evolution</h2>
                <p>${data.length} evolution record${data.length !== 1 ? 's' : ''}</p>
            </div>

            <div class="evo-controls">
                <button class="btn btn-secondary" onclick="renderEvolutionTimelines()">📊 View Timelines</button>
            </div>

            <div class="table-wrapper">
                <table class="data-table" id="evolutions-table">
                    <thead>
                        <tr>
                            <th>ID</th><th>Character</th><th>Author</th>
                            <th>Changes</th><th>Status</th><th>Created</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
}

async function renderEvolutionDetail(evolutionId) {
    showLoading();
    let evo;
    try {
        evo = await api(`/api/evolutions/${encodeURIComponent(evolutionId)}`);
    } catch (err) {
        showError(`Evolution not found: ${err.message}`);
        return;
    }

    const changes = (evo.changes || []).map(c => `
        <div class="evo-change-card">
            <div class="evo-change-header">
                ${badge(c.change_type)}
                <span class="evo-change-field">${escapeHtml(c.field_name)}</span>
            </div>
            ${c.rationale ? `<div class="evo-change-rationale">${escapeHtml(c.rationale)}</div>` : ''}
            <div class="evo-change-values">
                ${c.old_value ? `<div class="evo-val evo-val-old"><span class="evo-val-label">Old:</span> <code>${escapeHtml(typeof c.old_value === 'object' ? JSON.stringify(c.old_value) : String(c.old_value))}</code></div>` : ''}
                ${c.new_value ? `<div class="evo-val evo-val-new"><span class="evo-val-label">New:</span> <code>${escapeHtml(typeof c.new_value === 'object' ? JSON.stringify(c.new_value) : String(c.new_value))}</code></div>` : ''}
            </div>
        </div>
    `).join('');

    const meta = evo.metadata || {};
    const tallyHtml = meta.tally ? `
        <div class="detail-section">
            <h4>Vote Tally</h4>
            <div class="evo-tally">
                <span>👍 ${meta.tally.votes_for || 0}</span>
                <span>👎 ${meta.tally.votes_against || 0}</span>
                <span>🤷 ${meta.tally.votes_abstain || 0}</span>
                ${approvalBar(meta.tally.approval_rate)}
            </div>
        </div>` : '';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('evolution')">← Back to Evolutions</button>
            <div class="detail-panel">
                <div class="detail-header">
                    <div class="detail-avatar" style="background: linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))">🧬</div>
                    <div style="flex:1">
                        <h3>${evo.evolution_id}</h3>
                        <div class="member-role">Character: ${evo.character_id} · Author: ${evo.author}</div>
                    </div>
                    ${badge(evo.status)}
                    <button class="detail-close" onclick="navigateTo('evolution')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Status</h4>
                    <div class="evo-lifecycle">
                        ${['draft','proposed','voting','decided','applied'].map(s => {
                            const active = s === evo.status ? 'evo-step-active' : '';
                            const done = ['draft','proposed','voting','decided','applied'].indexOf(s) < ['draft','proposed','voting','decided','applied'].indexOf(evo.status) ? 'evo-step-done' : '';
                            const rejected = evo.status === 'rejected' && s === 'decided' ? 'evo-step-rejected' : '';
                            return `<div class="evo-step ${active} ${done} ${rejected}">${s}</div>`;
                        }).join('<div class="evo-step-arrow">→</div>')}
                    </div>
                    ${evo.summary ? `<p class="evo-summary">${escapeHtml(evo.summary)}</p>` : ''}
                </div>

                ${tallyHtml}

                <div class="detail-section">
                    <h4>Proposed Changes (${evo.changes.length})</h4>
                    <div class="evo-changes-list">
                        ${changes}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>Metadata</h4>
                    <div class="detail-meta-grid">
                        <div><span class="meta-label">Proposal ID</span><span>${evo.proposal_id || '—'}</span></div>
                        <div><span class="meta-label">Vote Record</span><span>${evo.vote_record_id || '—'}</span></div>
                        <div><span class="meta-label">Applied As</span><span>${evo.applied_character_id || '—'}</span></div>
                        <div><span class="meta-label">Created</span><span>${formatDate(evo.created_at)}</span></div>
                        <div><span class="meta-label">Updated</span><span>${formatDate(evo.updated_at)}</span></div>
                    </div>
                </div>
            </div>
        </div>`;
}

async function renderEvolutionTimelines() {
    showLoading();
    let timelines;
    try {
        timelines = await api('/api/evolutions/timelines');
    } catch (err) {
        showError(`Failed to load timelines: ${err.message}`);
        return;
    }

    if (!timelines.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <button class="back-btn" onclick="navigateTo('evolution')">← Back to Evolutions</button>
                <div class="page-header">
                    <h2>📊 Character Timelines</h2>
                    <p>No character timelines available.</p>
                </div>
                <div class="empty-state"><div class="empty-icon">📊</div><p>No characters found.</p></div>
            </div>`;
        return;
    }

    const cards = timelines.map(t => {
        const versions = t.version_chain || [];
        const events = t.events || [];
        return `
        <div class="card card-clickable evo-timeline-card" onclick="renderEvolutionTimelineDetail('${t.latest_version}')">
            <div class="evo-timeline-header">
                <span class="evo-timeline-name">${escapeHtml(t.character_name)}</span>
                <span class="badge badge-active">${versions.length} version${versions.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="evo-timeline-meta">
                <span>Latest: ${t.latest_version}</span>
                <span>${events.length} evolution event${events.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="evo-version-chain">
                ${versions.map(v => `<span class="evo-version-chip">${v}</span>`).join('<span class="evo-chain-arrow">→</span>')}
            </div>
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('evolution')">← Back to Evolutions</button>
            <div class="page-header">
                <h2>📊 Character Timelines</h2>
                <p>${timelines.length} character lineage${timelines.length !== 1 ? 's' : ''}</p>
            </div>
            <div class="member-grid">${cards}</div>
        </div>`;
}

async function renderEvolutionTimelineDetail(characterId) {
    showLoading();
    let timeline;
    try {
        timeline = await api(`/api/evolutions/timelines/${encodeURIComponent(characterId)}`);
    } catch (err) {
        showError(`Timeline not found: ${err.message}`);
        return;
    }

    const snapshots = (timeline.snapshots || []).map(s => `
        <div class="card evo-snapshot-card">
            <div class="evo-snapshot-header">
                <span class="evo-snapshot-id">${s.character_id}</span>
                <span class="evo-snapshot-name">${escapeHtml(s.name)} v${s.version}</span>
                ${badge(s.status)}
            </div>
            <div class="evo-snapshot-traits">${escapeHtml(s.traits_summary)}</div>
            <div class="evo-snapshot-meta">
                <span>Author: ${s.author}</span>
                <span>Traits: ${s.trait_count}</span>
                <span>${formatDate(s.created_at)}</span>
            </div>
        </div>
    `).join('');

    const events = (timeline.events || []).map(e => `
        <div class="evo-event-item">
            <div class="evo-event-header">
                <span class="evo-event-id">${e.evolution_id}</span>
                ${badge(e.status)}
                ${e.vote_result ? `<span class="evo-vote-result">${escapeHtml(e.vote_result)}</span>` : ''}
            </div>
            <div class="evo-event-summary">${escapeHtml(e.changes_summary)}</div>
            <div class="evo-event-meta">
                <span>By ${e.author}</span>
                <span>${formatDate(e.timestamp)}</span>
            </div>
        </div>
    `).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="renderEvolutionTimelines()">← Back to Timelines</button>
            <div class="detail-panel">
                <div class="detail-header">
                    <div class="detail-avatar" style="background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))">📊</div>
                    <div style="flex:1">
                        <h3>${escapeHtml(timeline.character_name)}</h3>
                        <div class="member-role">Latest: ${timeline.latest_version} · ${(timeline.version_chain || []).length} version(s)</div>
                    </div>
                    <button class="detail-close" onclick="renderEvolutionTimelines()">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Version Chain</h4>
                    <div class="evo-version-chain evo-chain-large">
                        ${(timeline.version_chain || []).map(v => `<span class="evo-version-chip">${v}</span>`).join('<span class="evo-chain-arrow">→</span>')}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>Version Snapshots</h4>
                    <div class="evo-snapshots-list">
                        ${snapshots || '<p class="text-muted">No snapshots.</p>'}
                    </div>
                </div>

                ${events.length ? `
                <div class="detail-section">
                    <h4>Evolution Events</h4>
                    <div class="evo-events-list">
                        ${events}
                    </div>
                </div>` : ''}
            </div>
        </div>`;
}

// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    const hash = window.location.hash.slice(1) || 'dashboard';
    const [view, ...rest] = hash.split('/');
    navigateTo(view, rest.join('/') || null);
});
