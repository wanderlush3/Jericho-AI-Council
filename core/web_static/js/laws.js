async function renderLaws() {
    showLoading();
    const data = await api('/api/laws');

    const createForm = `
        <div class="card location-create-form">
            <h3>⚖️ New Law</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Draft a new law for the council's governance framework.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="law-title-input">Title</label>
                    <input id="law-title-input" class="settings-input" placeholder="e.g. Trade Regulation Act" />
                </div>
                <div class="filter-group">
                    <label for="law-author-input">Author</label>
                    <input id="law-author-input" class="settings-input" placeholder="e.g. Council" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="law-desc-input">Description</label>
                <textarea id="law-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Brief summary of what this law enforces…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="law-body-input">Body</label>
                <textarea id="law-body-input" class="settings-input proposal-textarea" rows="3"
                    placeholder="Full text of the law…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="law-tags-input">Tags</label>
                    <input id="law-tags-input" class="settings-input" placeholder="trade, regulation, economy (comma-separated)" />
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createLaw()" id="law-create-btn">
                    ⚖️ Create Law
                </button>
                <span id="law-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    // Status counts
    const counts = { draft: 0, active: 0, archived: 0 };
    data.forEach(l => { counts[l.status] = (counts[l.status] || 0) + 1; });

    const cards = data.map(law => {
        const tagsHtml = (law.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');
        return `
        <div class="card card-clickable location-card" onclick="navigateTo('laws','${law.id}')">
            <div class="loc-header">
                <div>
                    <div class="loc-name">${escapeHtml(law.title)}</div>
                    <div class="loc-author">by ${escapeHtml(law.author)} · ${formatDate(law.created_at)}</div>
                </div>
                ${badge(law.status)}
            </div>
            <div class="loc-desc">${truncate(law.description, 120)}</div>
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>⚖️ Laws</h2>
                <p>${data.length} law${data.length !== 1 ? 's' : ''} —
                    <span class="badge badge-draft">Draft: ${counts.draft}</span>
                    <span class="badge badge-active">Active: ${counts.active}</span>
                    <span class="badge badge-archived">Archived: ${counts.archived}</span>
                </p>
            </div>
            ${createForm}
            ${data.length ? `<div class="location-grid">${cards}</div>` : ''}
        </div>`;
}

async function createLaw() {
    const btn = document.getElementById('law-create-btn');
    const status = document.getElementById('law-create-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    const title = (document.getElementById('law-title-input')?.value || '').trim();
    const author = (document.getElementById('law-author-input')?.value || '').trim();
    const description = (document.getElementById('law-desc-input')?.value || '').trim();
    const body = (document.getElementById('law-body-input')?.value || '').trim();
    const tagsRaw = (document.getElementById('law-tags-input')?.value || '').trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    if (!title || !author || !description) {
        showToast('Title, Author, and Description are required.', true);
        if (btn) { btn.disabled = false; btn.textContent = '⚖️ Create Law'; }
        return;
    }

    try {
        const resp = await fetch('/api/laws', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, author, body, tags }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Law "${data.title}" created ✅`);
        navigateTo('laws', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (status) status.textContent = '';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '⚖️ Create Law'; }
    }
}

async function renderLawDetail(id) {
    showLoading();
    const data = await api(`/api/laws/${encodeURIComponent(id)}`);

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');

    // Status action buttons
    let statusActions = '';
    if (data.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateLawStatus('${data.id}', 'active')">✅ Activate</button>`;
    } else if (data.status === 'active') {
        statusActions = `<button class="btn btn-secondary btn-sm" onclick="updateLawStatus('${data.id}', 'archived')">📁 Archive</button>`;
    } else if (data.status === 'archived') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateLawStatus('${data.id}', 'active')">♻️ Reactivate</button>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('laws')">← Back to Laws</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}${data.source_proposal_id ? ` · from ${data.source_proposal_id}` : ''}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.title)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:var(--space-sm)">
                        ${badge(data.status)}
                        ${statusActions}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.body ? `<div class="detail-section"><h4>Full Text</h4><div style="white-space:pre-wrap">${escapeHtml(data.body)}</div></div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                <div class="detail-section" style="font-size:0.82rem;color:var(--text-muted)">
                    Created: ${formatDate(data.created_at)} · Updated: ${formatDate(data.updated_at)}
                </div>
            </div>
        </div>`;
}

async function updateLawStatus(lawId, newStatus) {
    try {
        const resp = await fetch(`/api/laws/${encodeURIComponent(lawId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Update failed' }));
            throw new Error(err.detail);
        }
        showToast(`Law status updated to "${newStatus}" ✅`);
        await renderLawDetail(lawId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Law Shared Memory View
// ═══════════════════════════════════════════════════════════════

async function renderLawSharedMemory() {
    showLoading();
    const data = await api('/api/memories/law-shared');

    const lawRows = data.active_laws.length ? data.active_laws.map((law, i) => `
        <div class="event-item">
            <div class="event-header">
                <span class="badge badge-active">#${i + 1}</span>
                <strong>${escapeHtml(law.title || 'Untitled')}</strong>
                ${law.id ? `<span style="font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:var(--text-muted)">${law.id}</span>` : ''}
            </div>
            <div class="event-content">${escapeHtml(law.description || '')}</div>
            ${law.body ? `<div class="event-content" style="margin-top:var(--space-xs);color:var(--text-muted);font-size:0.82rem">${escapeHtml(truncate(law.body, 200))}</div>` : ''}
        </div>
    `).join('') : '<div class="empty-state"><div class="empty-icon">⚖️</div><p>No active laws. Activate a law to see it here.</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('memories')">← Back to Memories</button>
            <div class="page-header">
                <h2>⚖️ Law Shared Memory</h2>
                <p>${data.law_count} active law${data.law_count !== 1 ? 's' : ''} accessible to the LLM</p>
            </div>

            <div class="memory-detail-grid">
                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>⚖️ Active Laws</h3>
                        <span class="memory-panel-count">${data.law_count}</span>
                    </div>
                    <div class="event-list">
                        ${lawRows}
                    </div>
                </div>

                <div class="memory-panel">
                    <div class="memory-panel-header">
                        <h3>📄 LLM Context</h3>
                    </div>
                    ${data.context ? `<div class="shared-history-content">${escapeHtml(data.context)}</div>` : '<div class="empty-state"><div class="empty-icon">📄</div><p>No active laws — no LLM context generated.</p></div>'}
                </div>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Settings View
// ═══════════════════════════════════════════════════════════════

