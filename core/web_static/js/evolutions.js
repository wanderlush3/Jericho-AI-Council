async function renderEvolution() {
    showLoading();
    const params = new URLSearchParams();
    if (_evoOverlayFilter !== 'all') params.set('overlay_status', _evoOverlayFilter);
    const data = await api('/api/evolutions' + (params.toString() ? '?' + params : ''));

    const tabClass = (val) => `evo-overlay-tab${_evoOverlayFilter === val ? ' active' : ''}`;

    if (!data.length && _evoOverlayFilter === 'all') {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <div class="evo-list-header">
                        <div><h2>🧬 Character Evolution</h2><p>No evolution records yet.</p></div>
                        <div class="evo-list-header-actions">
                            <button class="btn btn-primary" onclick="openCreateEvolutionModal()" id="evo-create-btn">+ New Evolution</button>
                        </div>
                    </div>
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
        const overlayBadge = `<span class="evo-overlay-badge evo-overlay-badge-${e.overlay_status || 'draft'}">${e.overlay_status === 'active' ? '✨ ' : ''}${e.overlay_status || 'draft'}</span>`;
        const targetBadge = `<span class="evo-target-badge evo-target-badge-${e.target_type || 'character'}">${e.target_type === 'council_member' ? '👑 Council' : '👤 Char'}</span>`;
        const nameDisplay = e.name ? escapeHtml(truncate(e.name, 30)) : e.evolution_id;
        const activeIcon = e.overlay_status === 'active' ? '<span class="evo-active-icon">✨ LIVE</span>' : '';
        return `
        <tr class="proposal-row" onclick="navigateTo('evolution','${e.evolution_id}')">
            <td class="col-id">${e.evolution_id}</td>
            <td>${nameDisplay}${activeIcon}</td>
            <td>${targetBadge} ${escapeHtml(e.target_id || e.character_id)}</td>
            <td>${e.author}</td>
            <td>${changeCount} change${changeCount !== 1 ? 's' : ''}</td>
            <td>${statusBadge}</td>
            <td>${overlayBadge}</td>
            <td>${formatDate(e.created_at)}</td>
        </tr>`;
    }).join('');

    const totalCount = data.length;
    const emptyMsg = _evoOverlayFilter !== 'all'
        ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:var(--space-lg)">No ${_evoOverlayFilter} evolutions found.</td></tr>`
        : '';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <div class="evo-list-header">
                    <div>
                        <h2>🧬 Character Evolution</h2>
                        <p>${totalCount} evolution record${totalCount !== 1 ? 's' : ''}${_evoOverlayFilter !== 'all' ? ` (${_evoOverlayFilter})` : ''}</p>
                    </div>
                    <div class="evo-list-header-actions">
                        <button class="btn btn-secondary" onclick="renderEvolutionTimelines()">📊 View Timelines</button>
                        <button class="btn btn-primary" onclick="openCreateEvolutionModal()" id="evo-create-btn">+ New Evolution</button>
                    </div>
                </div>
            </div>

            <div class="evo-overlay-tabs">
                <button class="${tabClass('all')}" onclick="_evoOverlayFilter='all';renderEvolution()">All</button>
                <button class="${tabClass('draft')}" onclick="_evoOverlayFilter='draft';renderEvolution()">📝 Draft</button>
                <button class="${tabClass('active')}" onclick="_evoOverlayFilter='active';renderEvolution()">✨ Active</button>
                <button class="${tabClass('archived')}" onclick="_evoOverlayFilter='archived';renderEvolution()">📦 Archived</button>
            </div>

            <div class="table-wrapper">
                <table class="data-table" id="evolutions-table">
                    <thead>
                        <tr>
                            <th>ID</th><th>Name</th><th>Target</th><th>Author</th>
                            <th>Changes</th><th>Status</th><th>Overlay</th><th>Created</th>
                        </tr>
                    </thead>
                    <tbody>${rows || emptyMsg}</tbody>
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

    // ── Active overlay banner
    const activeBanner = evo.overlay_status === 'active' ? `
        <div class="evo-active-banner">
            <div class="evo-active-banner-icon">✨</div>
            <div class="evo-active-banner-text">
                Active Overlay
                <span>This evolution's changes are currently overriding the base configuration for ${escapeHtml(evo.target_id || evo.character_id)}.</span>
            </div>
        </div>` : '';

    // ── Rollback indicator
    const rollbackHtml = evo.rollback_of ? `
        <div class="evo-rollback-indicator" onclick="navigateTo('evolution','${evo.rollback_of}')">
            ↩ Rolls back: ${evo.rollback_of}
        </div>` : '';

    // ── Name and sequence display
    const nameHtml = evo.name ? `
        <div class="evo-name-display">
            ${escapeHtml(evo.name)}
            ${evo.sequence_number ? `<span class="evo-seq-badge">#${evo.sequence_number}</span>` : ''}
            <span class="evo-target-badge evo-target-badge-${evo.target_type || 'character'}">${evo.target_type === 'council_member' ? '👑 Council' : '👤 Character'}</span>
        </div>` : '';

    // ── Overlay status lifecycle
    const overlayLifecycle = `
        <div class="evo-overlay-lifecycle">
            ${['draft', 'active', 'archived'].map(s => {
                const isCurrent = s === evo.overlay_status;
                const cls = isCurrent ? 'evo-overlay-step-active' : '';
                return `<div class="evo-overlay-step ${cls}">${s}</div>`;
            }).join('<div class="evo-overlay-step-arrow">→</div>')}
        </div>`;

    // ── Overlay status action buttons
    let overlayActions = '';
    const os = evo.overlay_status || 'draft';
    const actionBtns = [];
    if (os === 'draft') {
        actionBtns.push(`<button class="btn btn-primary btn-sm" onclick="updateEvoOverlayStatus('${evolutionId}','active')">▶ Activate</button>`);
        actionBtns.push(`<button class="btn btn-sm" onclick="updateEvoOverlayStatus('${evolutionId}','archived')">📦 Archive</button>`);
    } else if (os === 'active') {
        actionBtns.push(`<button class="btn btn-sm" onclick="updateEvoOverlayStatus('${evolutionId}','archived')">📦 Archive</button>`);
    } else if (os === 'archived') {
        actionBtns.push(`<button class="btn btn-sm" onclick="updateEvoOverlayStatus('${evolutionId}','draft')">📝 Return to Draft</button>`);
        actionBtns.push(`<button class="btn btn-primary btn-sm" onclick="updateEvoOverlayStatus('${evolutionId}','active')">▶ Re-activate</button>`);
    }
    if (actionBtns.length) {
        overlayActions = `<div class="evo-status-actions">${actionBtns.join('')}</div>`;
    }

    // ── Rollback button (for applied/decided/active overlays)
    let rollbackBtn = '';
    const canRollback = evo.status === 'applied' || evo.status === 'decided' || evo.overlay_status === 'active';
    if (canRollback) {
        rollbackBtn = `<button class="btn btn-sm" style="border-color:var(--accent-amber)" onclick="confirmRollbackEvolution('${evolutionId}')">↩ Rollback</button>`;
    }

    // ── Changes list
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

            ${activeBanner}

            <div class="detail-panel">
                <div class="detail-header">
                    <div class="detail-avatar" style="background: linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))">🧬</div>
                    <div style="flex:1">
                        <h3>${evo.evolution_id}</h3>
                        ${nameHtml}
                        <div class="member-role">Target: ${escapeHtml(evo.target_id || evo.character_id)} · Author: ${evo.author}</div>
                    </div>
                    <span class="evo-overlay-badge evo-overlay-badge-${os}">${os === 'active' ? '✨ ' : ''}${os}</span>
                    ${badge(evo.status)}
                    <button class="detail-close" onclick="navigateTo('evolution')">✕</button>
                </div>

                ${rollbackHtml}

                <div class="detail-section">
                    <h4>Governance Lifecycle</h4>
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

                <div class="detail-section">
                    <h4>Overlay Status</h4>
                    ${overlayLifecycle}
                    ${overlayActions}
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
                        <div><span class="meta-label">Target Type</span><span class="evo-target-badge evo-target-badge-${evo.target_type || 'character'}">${evo.target_type || 'character'}</span></div>
                        <div><span class="meta-label">Target ID</span><span>${escapeHtml(evo.target_id || evo.character_id)}</span></div>
                        <div><span class="meta-label">Sequence</span><span>${evo.sequence_number ? '#' + evo.sequence_number : '—'}</span></div>
                        <div><span class="meta-label">Proposal ID</span><span>${evo.proposal_id || '—'}</span></div>
                        <div><span class="meta-label">Vote Record</span><span>${evo.vote_record_id || '—'}</span></div>
                        <div><span class="meta-label">Applied As</span><span>${evo.applied_character_id || '—'}</span></div>
                        <div><span class="meta-label">Rollback Of</span><span>${evo.rollback_of ? `<span class="evo-rollback-indicator" onclick="event.stopPropagation();navigateTo('evolution','${evo.rollback_of}')">↩ ${evo.rollback_of}</span>` : '—'}</span></div>
                        <div><span class="meta-label">Created</span><span>${formatDate(evo.created_at)}</span></div>
                        <div><span class="meta-label">Updated</span><span>${formatDate(evo.updated_at)}</span></div>
                    </div>
                    ${rollbackBtn ? `<div style="margin-top:var(--space-md)">${rollbackBtn}</div>` : ''}
                </div>
            </div>
        </div>`;
}

// ── Overlay Status Management ───────────────────────────────────

async function updateEvoOverlayStatus(evolutionId, newStatus) {
    if (newStatus === 'active') {
        if (!confirm('⚠ Activating this overlay will archive any existing active overlay for this target. Continue?')) return;
    }
    try {
        await fetch(`/api/evolutions/${encodeURIComponent(evolutionId)}/overlay-status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ overlay_status: newStatus }),
        });
        showToast(`Overlay status → ${newStatus} ✅`);
        await renderEvolutionDetail(evolutionId);
    } catch (err) {
        showToast(`Failed: ${err.message}`, true);
    }
}

// ── Rollback ────────────────────────────────────────────────────

function confirmRollbackEvolution(evolutionId) {
    const existing = document.getElementById('evo-rollback-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'evo-rollback-modal';
    modal.className = 'evo-confirm-modal';
    modal.innerHTML = `
        <div class="evo-confirm-content">
            <h3>↩ Confirm Rollback</h3>
            <p>This will create a new rollback evolution that reverses all changes from <strong>${escapeHtml(evolutionId)}</strong>. Any active overlay will be archived.</p>
            <div class="evo-confirm-actions">
                <button class="btn" onclick="document.getElementById('evo-rollback-modal').remove()">Cancel</button>
                <button class="btn btn-primary" onclick="executeRollbackEvolution('${evolutionId}')" id="evo-rollback-confirm-btn" style="background:linear-gradient(135deg,hsl(35,90%,50%),hsl(15,80%,50%))">↩ Rollback</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

async function executeRollbackEvolution(evolutionId) {
    const btn = document.getElementById('evo-rollback-confirm-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Rolling back…'; }
    try {
        const resp = await fetch(`/api/evolutions/${encodeURIComponent(evolutionId)}/rollback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Rollback failed' }));
            throw new Error(err.detail);
        }
        const newEvo = await resp.json();
        showToast(`Rollback created: ${newEvo.evolution_id} ✅`);
        const modal = document.getElementById('evo-rollback-modal');
        if (modal) modal.remove();
        navigateTo('evolution', newEvo.evolution_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '↩ Rollback'; }
    }
}

// ── Rollback to Version (from timeline detail) ──────────────────

function openRollbackToVersionModal(targetId, versions) {
    const existing = document.getElementById('evo-rollback-version-modal');
    if (existing) existing.remove();

    const options = versions.map(v => `<option value="${v}">${v}</option>`).join('');
    const modal = document.createElement('div');
    modal.id = 'evo-rollback-version-modal';
    modal.className = 'evo-confirm-modal';
    modal.innerHTML = `
        <div class="evo-confirm-content">
            <h3>↩ Rollback to Version</h3>
            <p>Select a version to restore for <strong>${escapeHtml(targetId)}</strong>. This will archive any active overlays and create a new evolution capturing the target version's state.</p>
            <div style="margin-bottom:var(--space-lg)">
                <label class="evo-form-label">Target Version</label>
                <select id="evo-rollback-version-select" class="settings-input">${options}</select>
            </div>
            <div class="evo-confirm-actions">
                <button class="btn" onclick="document.getElementById('evo-rollback-version-modal').remove()">Cancel</button>
                <button class="btn btn-primary" onclick="executeRollbackToVersion('${targetId}')" id="evo-rollback-version-btn" style="background:linear-gradient(135deg,hsl(35,90%,50%),hsl(15,80%,50%))">↩ Rollback to Version</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

async function executeRollbackToVersion(targetId) {
    const select = document.getElementById('evo-rollback-version-select');
    const btn = document.getElementById('evo-rollback-version-btn');
    if (!select) return;
    const versionId = select.value;
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Rolling back…'; }
    try {
        const resp = await fetch(`/api/evolutions/rollback-to/${encodeURIComponent(targetId)}/${encodeURIComponent(versionId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Rollback failed' }));
            throw new Error(err.detail);
        }
        const newEvo = await resp.json();
        showToast(`Rollback to ${versionId} created: ${newEvo.evolution_id} ✅`);
        const modal = document.getElementById('evo-rollback-version-modal');
        if (modal) modal.remove();
        navigateTo('evolution', newEvo.evolution_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '↩ Rollback to Version'; }
    }
}

// ── Create Evolution Modal ──────────────────────────────────────

// Module-level cache for entity data used by change-type auto-fill
let _evoCharactersCache = [];
let _evoCouncilCache = [];

async function openCreateEvolutionModal(prefillProposalId) {
    const existing = document.getElementById('evo-create-modal');
    if (existing) existing.remove();

    // If auto-filling from a proposal, just call the API directly
    if (prefillProposalId) {
        try {
            const resp = await fetch(`/api/evolutions/from-proposal/${encodeURIComponent(prefillProposalId)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Failed' }));
                throw new Error(err.detail);
            }
            const newEvo = await resp.json();
            showToast(`Evolution ${newEvo.evolution_id} created from proposal ✅`);
            navigateTo('evolution', newEvo.evolution_id);
        } catch (err) {
            showToast(`Error: ${err.message}`, true);
        }
        return;
    }

    // Fetch characters and council members for dropdowns
    let characters = [], council = [];
    try { characters = await api('/api/characters?status=active'); } catch { /* empty */ }
    try { council = await api('/api/council'); } catch { /* empty */ }

    // Cache for auto-fill access
    _evoCharactersCache = characters;
    _evoCouncilCache = council;

    const charOptions = characters.map(c =>
        `<option value="${c.id}">${escapeHtml(c.name)} (${c.id})</option>`
    ).join('');
    const councilOptions = council.map(m =>
        `<option value="${m.name}">${escapeHtml(m.name)} — ${m.role}</option>`
    ).join('');

    const changeTypes = ['trait_add','trait_remove','trait_modify','field_update','version_bump','system_prompt_update','personality_update'];
    const changeTypeOptions = changeTypes.map(t => `<option value="${t}">${t}</option>`).join('');

    const modal = document.createElement('div');
    modal.id = 'evo-create-modal';
    modal.className = 'evo-create-modal';
    modal.innerHTML = `
        <div class="evo-create-content">
            <div class="evo-create-header">
                <h3>🧬 Create Evolution</h3>
                <button class="detail-close" onclick="document.getElementById('evo-create-modal').remove()">✕</button>
            </div>
            <div class="evo-create-body">
                <div>
                    <label class="evo-form-label">Target Type</label>
                    <div class="evo-target-toggle" id="evo-target-toggle">
                        <input type="radio" name="evo-target-type" id="evo-tt-char" value="character" checked>
                        <label for="evo-tt-char" class="active" onclick="switchEvoTargetType('character')">👤 Character</label>
                        <input type="radio" name="evo-target-type" id="evo-tt-council" value="council_member">
                        <label for="evo-tt-council" onclick="switchEvoTargetType('council_member')">👑 Council Member</label>
                    </div>
                </div>

                <div id="evo-target-char-group">
                    <label class="evo-form-label">Target Character</label>
                    <select id="evo-target-char" class="settings-input">${charOptions || '<option value="">No active characters</option>'}</select>
                </div>

                <div id="evo-target-council-group" style="display:none">
                    <label class="evo-form-label">Council Member</label>
                    <select id="evo-target-council" class="settings-input">${councilOptions || '<option value="">No council members</option>'}</select>
                </div>

                <div>
                    <label class="evo-form-label">Evolution Name</label>
                    <input id="evo-create-name" class="settings-input" placeholder="e.g. Courage Boost, System Prompt v3…" />
                    <span class="evo-form-hint">Optional — auto-generated if left empty</span>
                </div>

                <div>
                    <label class="evo-form-label">Author</label>
                    <input id="evo-create-author" class="settings-input" placeholder="Who is proposing this evolution?" value="User" />
                </div>

                <div>
                    <label class="evo-form-label">Changes</label>
                    <div class="evo-change-builder" id="evo-change-builder">
                        <div class="evo-change-row" data-idx="0">
                            <button class="evo-change-remove" onclick="removeEvoChangeRow(this)" title="Remove">✕</button>
                            <div class="evo-change-row-header">
                                <select class="settings-input evo-ct-select" onchange="onEvoChangeTypeSelect(this)">${changeTypeOptions}</select>
                                <input class="settings-input evo-fn-input" placeholder="Field name (e.g. courage, backstory)" />
                            </div>
                            <div class="evo-change-row-autofill" style="display:none">
                                <button class="btn btn-sm evo-load-prompt-btn" type="button" onclick="loadCurrentSystemPrompt(this)">📋 Load Current System Prompt</button>
                                <span class="evo-form-hint">Auto-fills Old Value with the selected target's current system prompt</span>
                            </div>
                            <div class="evo-change-row-fields">
                                <div>
                                    <label class="evo-form-label" style="font-size:0.68rem">Old Value</label>
                                    <textarea class="settings-input evo-ov-input" rows="2" placeholder="Previous value (optional)"></textarea>
                                </div>
                                <div>
                                    <label class="evo-form-label" style="font-size:0.68rem">New Value</label>
                                    <textarea class="settings-input evo-nv-input" rows="2" placeholder="New value"></textarea>
                                </div>
                            </div>
                            <div class="evo-change-row-rationale">
                                <label class="evo-form-label" style="font-size:0.68rem">Rationale</label>
                                <input class="settings-input evo-rat-input" placeholder="Why this change?" />
                            </div>
                        </div>
                    </div>
                    <button class="evo-change-add-btn" onclick="addEvoChangeRow()">+ Add Change</button>
                </div>
            </div>
            <div class="evo-create-footer">
                <button class="btn" onclick="document.getElementById('evo-create-modal').remove()">Cancel</button>
                <button class="btn btn-primary" onclick="submitCreateEvolution()" id="evo-submit-btn">🧬 Create Evolution</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

function switchEvoTargetType(type) {
    const charGroup = document.getElementById('evo-target-char-group');
    const councilGroup = document.getElementById('evo-target-council-group');
    const labels = document.querySelectorAll('#evo-target-toggle label');
    labels.forEach(l => l.classList.remove('active'));
    if (type === 'council_member') {
        charGroup.style.display = 'none';
        councilGroup.style.display = '';
        labels[1].classList.add('active');
        document.getElementById('evo-tt-council').checked = true;
    } else {
        charGroup.style.display = '';
        councilGroup.style.display = 'none';
        labels[0].classList.add('active');
        document.getElementById('evo-tt-char').checked = true;
    }
}

let _evoChangeRowIdx = 1;
function addEvoChangeRow() {
    const changeTypes = ['trait_add','trait_remove','trait_modify','field_update','version_bump','system_prompt_update','personality_update'];
    const changeTypeOptions = changeTypes.map(t => `<option value="${t}">${t}</option>`).join('');
    const builder = document.getElementById('evo-change-builder');
    const row = document.createElement('div');
    row.className = 'evo-change-row';
    row.dataset.idx = _evoChangeRowIdx++;
    row.innerHTML = `
        <button class="evo-change-remove" onclick="removeEvoChangeRow(this)" title="Remove">✕</button>
        <div class="evo-change-row-header">
            <select class="settings-input evo-ct-select" onchange="onEvoChangeTypeSelect(this)">${changeTypeOptions}</select>
            <input class="settings-input evo-fn-input" placeholder="Field name" />
        </div>
        <div class="evo-change-row-autofill" style="display:none">
            <button class="btn btn-sm evo-load-prompt-btn" type="button" onclick="loadCurrentSystemPrompt(this)">📋 Load Current System Prompt</button>
            <span class="evo-form-hint">Auto-fills Old Value with the selected target's current system prompt</span>
        </div>
        <div class="evo-change-row-fields">
            <div>
                <label class="evo-form-label" style="font-size:0.68rem">Old Value</label>
                <textarea class="settings-input evo-ov-input" rows="2" placeholder="Previous value (optional)"></textarea>
            </div>
            <div>
                <label class="evo-form-label" style="font-size:0.68rem">New Value</label>
                <textarea class="settings-input evo-nv-input" rows="2" placeholder="New value"></textarea>
            </div>
        </div>
        <div class="evo-change-row-rationale">
            <label class="evo-form-label" style="font-size:0.68rem">Rationale</label>
            <input class="settings-input evo-rat-input" placeholder="Why this change?" />
        </div>`;
    builder.appendChild(row);
}

function removeEvoChangeRow(btn) {
    const builder = document.getElementById('evo-change-builder');
    if (builder.children.length <= 1) {
        showToast('At least one change is required.', true);
        return;
    }
    btn.closest('.evo-change-row').remove();
}

// ── Change Type Auto-Fill ───────────────────────────────────────

function onEvoChangeTypeSelect(selectEl) {
    const row = selectEl.closest('.evo-change-row');
    const ct = selectEl.value;
    const autofillDiv = row.querySelector('.evo-change-row-autofill');
    const fnInput = row.querySelector('.evo-fn-input');
    const ovInput = row.querySelector('.evo-ov-input');
    const nvInput = row.querySelector('.evo-nv-input');

    if (ct === 'system_prompt_update') {
        // Auto-set field name and show the load button
        fnInput.value = 'system_prompt';
        if (autofillDiv) autofillDiv.style.display = '';
        // Expand textareas for system prompt editing
        ovInput.rows = 8;
        nvInput.rows = 8;
        // Auto-load immediately
        loadCurrentSystemPrompt(autofillDiv ? autofillDiv.querySelector('.evo-load-prompt-btn') : null);
    } else if (ct === 'personality_update') {
        fnInput.value = 'personality';
        if (autofillDiv) autofillDiv.style.display = 'none';
        ovInput.rows = 2;
        nvInput.rows = 2;
    } else if (ct === 'field_update') {
        // Show auto-fill for field_update too (in case they type system_prompt manually)
        if (autofillDiv) autofillDiv.style.display = 'none';
        ovInput.rows = 2;
        nvInput.rows = 2;
    } else {
        if (autofillDiv) autofillDiv.style.display = 'none';
        ovInput.rows = 2;
        nvInput.rows = 2;
    }
}

function loadCurrentSystemPrompt(btn) {
    const targetType = document.querySelector('input[name="evo-target-type"]:checked')?.value || 'character';
    let currentPrompt = '';

    if (targetType === 'council_member') {
        const memberName = document.getElementById('evo-target-council')?.value;
        if (memberName) {
            const member = _evoCouncilCache.find(m => m.name === memberName);
            if (member) currentPrompt = member.system_prompt || '';
        }
    } else {
        const charId = document.getElementById('evo-target-char')?.value;
        if (charId) {
            const char = _evoCharactersCache.find(c => c.id === charId);
            if (char) currentPrompt = char.system_prompt || '';
        }
    }

    if (!currentPrompt) {
        showToast('No system prompt found for the selected target.', true);
        return;
    }

    // Find the row and set the old value
    if (btn) {
        const row = btn.closest('.evo-change-row');
        if (row) {
            const ovInput = row.querySelector('.evo-ov-input');
            if (ovInput) {
                ovInput.value = currentPrompt;
                ovInput.rows = Math.max(8, Math.min(20, currentPrompt.split('\n').length + 2));
                showToast('Current system prompt loaded into Old Value ✅');
            }
        }
    }
}

async function submitCreateEvolution() {
    const btn = document.getElementById('evo-submit-btn');
    const targetType = document.querySelector('input[name="evo-target-type"]:checked')?.value || 'character';
    const name = document.getElementById('evo-create-name').value.trim();
    const author = document.getElementById('evo-create-author').value.trim();

    if (!author) { showToast('Author is required.', true); return; }

    let characterId = '', memberName = '';
    if (targetType === 'council_member') {
        memberName = document.getElementById('evo-target-council').value;
        if (!memberName) { showToast('Select a council member.', true); return; }
        characterId = `CM-${memberName}`;
    } else {
        characterId = document.getElementById('evo-target-char').value;
        if (!characterId) { showToast('Select a character.', true); return; }
    }

    // Gather changes
    const rows = document.querySelectorAll('#evo-change-builder .evo-change-row');
    const changes = [];
    for (const row of rows) {
        const ct = row.querySelector('.evo-ct-select').value;
        const fn = row.querySelector('.evo-fn-input').value.trim();
        const ov = row.querySelector('.evo-ov-input').value.trim();
        const nv = row.querySelector('.evo-nv-input').value.trim();
        const rat = row.querySelector('.evo-rat-input').value.trim();
        if (!fn) { showToast('Field name is required for all changes.', true); return; }

        // Try to parse JSON values
        let oldVal = ov, newVal = nv;
        try { oldVal = JSON.parse(ov); } catch { /* keep as string */ }
        try { newVal = JSON.parse(nv); } catch { /* keep as string */ }

        changes.push({
            change_type: ct,
            field_name: fn,
            old_value: oldVal,
            new_value: newVal,
            rationale: rat,
        });
    }

    if (!changes.length) { showToast('At least one change is required.', true); return; }

    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    try {
        const body = {
            character_id: characterId,
            author,
            changes,
            name,
            target_type: targetType,
        };
        if (targetType === 'council_member') {
            body.member_name = memberName;
        }

        const resp = await fetch('/api/evolutions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Creation failed' }));
            throw new Error(err.detail);
        }
        const newEvo = await resp.json();
        showToast(`Evolution ${newEvo.evolution_id} created ✅`);
        document.getElementById('evo-create-modal').remove();
        navigateTo('evolution', newEvo.evolution_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🧬 Create Evolution'; }
    }
}

// ── Auto-fill from Proposal ─────────────────────────────────────

async function createEvolutionFromProposal(proposalId) {
    try {
        const resp = await fetch(`/api/evolutions/from-proposal/${encodeURIComponent(proposalId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        const newEvo = await resp.json();
        showToast(`Evolution ${newEvo.evolution_id} created from proposal ✅`);
        navigateTo('evolution', newEvo.evolution_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Timelines (preserved from Conv 1, with rollback-to-version) ─

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

    const versions = timeline.version_chain || [];

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

    // Rollback-to-version button
    const rollbackToBtn = versions.length > 1
        ? `<button class="btn btn-sm" style="border-color:var(--accent-amber)" onclick="openRollbackToVersionModal('${characterId}', ${JSON.stringify(versions)})">↩ Rollback to Version…</button>`
        : '';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="renderEvolutionTimelines()">← Back to Timelines</button>
            <div class="detail-panel">
                <div class="detail-header">
                    <div class="detail-avatar" style="background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))">📊</div>
                    <div style="flex:1">
                        <h3>${escapeHtml(timeline.character_name)}</h3>
                        <div class="member-role">Latest: ${timeline.latest_version} · ${versions.length} version(s)</div>
                    </div>
                    ${rollbackToBtn}
                    <button class="detail-close" onclick="renderEvolutionTimelines()">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Version Chain</h4>
                    <div class="evo-version-chain evo-chain-large">
                        ${versions.map(v => `<span class="evo-version-chip">${v}</span>`).join('<span class="evo-chain-arrow">→</span>')}
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


// ═══════════════════════════════════════════════════════════════
// Council Sessions View
// ═══════════════════════════════════════════════════════════════

