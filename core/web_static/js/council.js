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

    const cards = data.map((m, i) => {
        const evoHtml = m.active_evolution
            ? `<span class="badge-evolution-trait">${escapeHtml(m.active_evolution.name)} Evolution</span>`
            : '';
        return `
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
            ${evoHtml ? `<div style="margin-bottom:var(--space-md)">${evoHtml}</div>` : ''}
            <div class="member-meta">
                ${m.specialties.map(s => `<span class="specialty-tag">${s}</span>`).join('')}
            </div>
        </div>`;
    }).join('');

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

    const detailEvoHtml = data.active_evolution
        ? `<div style="margin-top:var(--space-sm)"><span class="badge-evolution-trait">${escapeHtml(data.active_evolution.name)} Evolution</span></div>`
        : '';

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
                        ${detailEvoHtml}
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
                                <option value="lmstudio" ${data.api_provider === 'lmstudio' ? 'selected' : ''}>LM Studio</option>
                            </select>
                        </div>

                        <div class="council-field-group">
                            <label for="cf-model">Model</label>
                            <div id="cf-model-container">
                                ${renderModelField('cf-model', data.api_provider, data.model, true)}
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
    container.innerHTML = renderModelField('cf-model', provider, '', true);
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

