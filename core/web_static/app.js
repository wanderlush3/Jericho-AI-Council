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
    analyticsData: null,
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
            case 'analytics': await renderAnalytics(); break;
            case 'chat': detail ? await renderChatDetail(detail) : await renderChat(); break;
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
            <div class="page-header"><h2>Council Members</h2></div>
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
            <div class="page-header">
                <h2>Council Members</h2>
                <p>${data.length} members across ${new Set(data.map(m=>m.api_provider)).size} providers</p>
            </div>
            <div class="member-grid">${cards}</div>
        </div>`;
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
                            <select id="cf-provider" class="settings-input">
                                <option value="openrouter" ${data.api_provider === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                                <option value="mancer" ${data.api_provider === 'mancer' ? 'selected' : ''}>Mancer</option>
                            </select>
                        </div>

                        <div class="council-field-group">
                            <label for="cf-model">Model</label>
                            <input type="text" id="cf-model" class="settings-input" value="${escapeAttr(data.model)}" placeholder="e.g. anthropic/claude-3.5-sonnet" />
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

    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general']
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
                    ${memberAvatar(c.speaker, memberIdx >= 0 ? memberIdx : 0)}
                    <div>
                        <span class="discussion-speaker">${c.speaker}</span>
                        <span class="discussion-round">Round ${c.round_number}</span>
                    </div>
                </div>
                <div class="discussion-content">${escapeHtml(c.content)}</div>
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
                <p style="color:var(--text-secondary)">${escapeHtml(discussion.summary)}</p>
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
                <span class="vote-reason">${truncate(v.reason, 120) || '—'}</span>
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
                            <span class="vote-reason">${r.comment || '—'}</span>
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
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.body ? `<div class="detail-section"><h4>Body</h4><pre>${escapeHtml(data.body)}</pre></div>` : ''}

                ${discussionFeedHtml}
                ${summaryHtml}
                ${voteResultsHtml}
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
                                    ${memberAvatar(data.speaker, 0)}
                                    <div>
                                        <span class="discussion-speaker">${data.speaker}</span>
                                        <span class="discussion-round">Round ${data.round}</span>
                                    </div>
                                </div>
                                <div class="discussion-content">${escapeHtml(data.content)}</div>`;
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

    if (!data.length) {
        $main().innerHTML = `
            <div class="page-header"><h2>Characters</h2></div>
            <div class="empty-state"><div class="empty-icon">🎭</div><p>No characters found.</p></div>`;
        return;
    }

    const cards = data.map(c => {
        const traitsHtml = (c.traits || []).slice(0, 4).map(t => `
            <div class="trait-item">
                <span class="trait-name">${t.name}</span>
                <div class="trait-bar-bg">
                    <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
                </div>
                <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
            </div>`).join('');

        const tagsHtml = (c.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');

        return `
        <div class="card card-clickable character-card" onclick="navigateTo('characters','${c.id}')">
            <div class="char-header">
                <div>
                    <div class="char-name">${c.name}</div>
                    <div class="char-author">by ${c.author} · v${c.version || 1}</div>
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
                <h2>Characters</h2>
                <p>${data.length} AI character templates</p>
            </div>
            <div class="character-grid">${cards}</div>
        </div>`;
}

async function renderCharacterDetail(id) {
    showLoading();
    const data = await api(`/api/characters/${encodeURIComponent(id)}`);

    const traitsHtml = (data.traits || []).map(t => `
        <div class="trait-item">
            <span class="trait-name">${t.name}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <div class="trait-bar-bg" style="max-width:150px">
                <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
            </div>
            <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
        </div>`).join('');

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('characters')">← Back to Characters</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id} · v${data.version || 1}</div>
                        <div style="font-size:1.4rem;font-weight:700">${data.name}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${data.author}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm)">${badge(data.status)}</div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('characters')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${data.description}</p>
                </div>

                ${data.backstory ? `<div class="detail-section"><h4>Backstory</h4><p>${data.backstory}</p></div>` : ''}

                ${traitsHtml ? `<div class="detail-section"><h4>Traits (${data.traits.length})</h4><div class="traits-list">${traitsHtml}</div></div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                ${data.greeting ? `<div class="detail-section"><h4>Greeting</h4><p style="font-style:italic;color:var(--accent-cyan)">"${data.greeting}"</p></div>` : ''}

                ${data.system_prompt ? `<div class="detail-section"><h4>System Prompt</h4><pre>${data.system_prompt}</pre></div>` : ''}

                ${data.example_messages && data.example_messages.length ? `
                    <div class="detail-section">
                        <h4>Example Messages</h4>
                        ${data.example_messages.map(m => `<p style="color:var(--text-secondary);margin-bottom:var(--space-xs)">💬 ${m}</p>`).join('')}
                    </div>` : ''}
            </div>
        </div>`;
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

    const memberOptions = members.map(m =>
        `<option value="${m.name}">${m.name} — ${m.role}</option>`
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

        const members = c.council_members && c.council_members.length
            ? c.council_members : (c.member_name ? [c.member_name] : []);
        const membersLabel = members.join(', ');

        return `
        <div class="card card-clickable chat-card" onclick="navigateTo('chat','${c.chat_id}')">
            <div class="chat-card-header">
                <div class="chat-card-info">
                    <div class="chat-card-avatars">
                        ${members.slice(0, 3).map((m, i) => memberAvatar(m, idx + i)).join('')}
                        ${members.length > 3 ? `<span class="chat-card-more">+${members.length - 3}</span>` : ''}
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
                <p>Talk directly with council members</p>
            </div>

            <div class="chat-new-form card">
                <h3>New Conversation</h3>
                <div class="chat-new-row">
                    <div class="filter-group">
                        <label for="chat-member-select">Council Member</label>
                        <select id="chat-member-select" class="settings-input">
                            <option value="">Select a member…</option>
                            ${memberOptions}
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
    const memberSel = document.getElementById('chat-member-select');
    const titleInput = document.getElementById('chat-title-input');
    const topicInput = document.getElementById('chat-topic-input');
    const btn = document.getElementById('chat-create-btn');

    const member_name = memberSel.value;
    const title = titleInput.value.trim();
    const topic = topicInput.value.trim();

    if (!member_name) { memberSel.focus(); return; }
    if (!title) { titleInput.focus(); return; }

    btn.disabled = true;
    btn.textContent = 'Creating…';
    try {
        const data = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_name, title, topic }),
        }).then(r => { if (!r.ok) throw new Error('Failed to create chat'); return r.json(); });

        showToast(`Chat with ${member_name} started! ✅`);
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
    const members = data.council_members && data.council_members.length
        ? data.council_members : (data.member_name ? [data.member_name] : []);
    const primaryMember = members[0] || data.member_name || 'Agent';
    const isMultiMember = members.length > 1;

    // Fetch all council members for the add-member dropdown
    let allMembers = [];
    try { allMembers = await api('/api/council'); } catch { /* empty */ }
    const availableMembers = allMembers.filter(m =>
        !members.some(cm => cm.toLowerCase() === m.name.toLowerCase())
    );

    const messagesHtml = (data.messages || []).map(m => {
        const isHuman = m.role === 'human';
        const bubbleClass = isHuman ? 'chat-bubble-human' : 'chat-bubble-agent';
        const speakerName = isHuman ? 'You' : (m.speaker || primaryMember);
        const avatarIdx = members.findIndex(cm => cm.toLowerCase() === (m.speaker || '').toLowerCase());
        const avatar = !isHuman ? memberAvatar(speakerName, avatarIdx >= 0 ? avatarIdx : 0) : '';
        const time = m.timestamp ? new Date(m.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';

        return `
        <div class="chat-message ${bubbleClass}">
            ${!isHuman ? `<div class="chat-msg-avatar">${avatar}</div>` : ''}
            <div class="chat-msg-body">
                <div class="chat-msg-header">
                    <span class="chat-msg-speaker">${speakerName}</span>
                    <span class="chat-msg-time">${time}</span>
                </div>
                <div class="chat-msg-content">${escapeHtml(m.content)}</div>
            </div>
        </div>`;
    }).join('');

    // Member chips in topbar
    const memberChipsHtml = members.map((m, i) => {
        const removeBtn = (!isClosed && members.length > 1)
            ? `<button class="chip-remove" onclick="event.stopPropagation();removeChatMember('${chatId}','${m}')" title="Remove ${m}">✕</button>`
            : '';
        return `<div class="member-chip">${memberAvatar(m, i)}<span>${m}</span>${removeBtn}</div>`;
    }).join('');

    // Add member dropdown
    const addMemberHtml = (!isClosed && availableMembers.length > 0) ? `
        <div class="add-member-dropdown">
            <button class="btn btn-secondary btn-sm add-member-btn" onclick="toggleAddMemberDropdown()" id="add-member-toggle">
                ＋ Add Member
            </button>
            <div class="add-member-list" id="add-member-list" style="display:none">
                ${availableMembers.map(m => `
                    <button class="add-member-option" onclick="addChatMember('${chatId}','${m.name}')">
                        ${m.name} <span class="add-member-role">— ${m.role}</span>
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
                    ${pauseResumeHtml}
                    ${closeBtn}
                </div>
            </div>

            <div class="chat-members-bar">
                <div class="member-chips">${memberChipsHtml}</div>
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
                    appendAgentBubble(msgContainer, data.speaker, data.content);
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

function appendAgentBubble(container, speaker, content) {
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'chat-message chat-bubble-agent';
    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    bubble.innerHTML = `
        <div class="chat-msg-avatar">${memberAvatar(speaker, 0)}</div>
        <div class="chat-msg-body">
            <div class="chat-msg-header">
                <span class="chat-msg-speaker">${escapeHtml(speaker)}</span>
                <span class="chat-msg-time">${time}</span>
            </div>
            <div class="chat-msg-content">${escapeHtml(content)}</div>
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
            <div class="chat-msg-content">${escapeHtml(content)}</div>
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
                    appendAgentBubble(msgContainer, data.speaker, data.content);
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

async function renderSettings() {
    showLoading();
    const [keys, models] = await Promise.all([
        api('/api/settings/keys'),
        api('/api/settings/models'),
    ]);

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
        const modelLabel = isDefault ? 'Default Model' : 'Custom Model';
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
                <div class="settings-input-row">
                    <input type="text"
                           id="model-input-${k.provider}"
                           class="settings-input"
                           placeholder="e.g. ${k.provider === 'openrouter' ? 'anthropic/claude-3.5-sonnet' : 'nothingiisreal/MN-12B-Celeste-V1.9'}"
                           value="${currentModel}"
                           autocomplete="off"
                           spellcheck="false" />
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
                <p>Configure your API provider keys and models — keys are encrypted at rest and never displayed in full</p>
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
    const input = document.getElementById(`model-input-${provider}`);
    const model = input.value.trim();
    if (!model) { input.focus(); return; }

    input.disabled = true;
    try {
        await fetch('/api/settings/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, model }),
        });
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} model saved ✅`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        input.disabled = false;
    }
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

// ─── Nav Count Updater ────────────────────────────────────────

function updateNavCounts(data) {
    if (data.members) document.getElementById('count-council').textContent = data.members.count || 0;
    if (data.proposals) document.getElementById('count-proposals').textContent = data.proposals.count || 0;
    if (data.votes) document.getElementById('count-votes').textContent = data.votes.count || 0;
    if (data.characters) document.getElementById('count-characters').textContent = data.characters.count || 0;
}

// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    const hash = window.location.hash.slice(1) || 'dashboard';
    const [view, ...rest] = hash.split('/');
    navigateTo(view, rest.join('/') || null);
});
