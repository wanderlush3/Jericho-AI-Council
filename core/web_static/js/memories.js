async function renderMemories() {
    showLoading();
    const data = await api('/api/memories');
    let sharedData = { decision_count: 0, history: '' };
    try { sharedData = await api('/api/memories/shared'); } catch { /* empty */ }
    let lawSharedData = { law_count: 0 };
    try { lawSharedData = await api('/api/memories/law-shared'); } catch { /* empty */ }

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

    const lawSharedCard = `
        <div class="card card-clickable memory-card memory-card-shared" onclick="navigateTo('memories','law_shared')">
            <div class="memory-card-header">
                <div class="memory-avatar memory-avatar-shared" style="background:linear-gradient(135deg, var(--accent-blue), var(--accent-indigo))">⚖️</div>
                <div>
                    <div class="member-name">Law Shared Memory</div>
                    <div class="member-role">Active laws accessible to the LLM</div>
                </div>
            </div>
            <div class="memory-stats">
                <div class="memory-stat">
                    <span class="memory-stat-value">${lawSharedData.law_count}</span>
                    <span class="memory-stat-label">Active Laws</span>
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
                ${lawSharedCard}
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
                <button class="btn-icon belief-delete" onclick="deleteSharedDecision(${i}, '${escapeAttr(truncate(summary, 50))}')" title="Delete decision">
                    🗑️
                </button>
            </div>
            <div class="event-content">${escapeHtml(summary)}</div>
        </div>`;
    }).join('') : '<div class="empty-state"><div class="empty-icon">📜</div><p>No council decisions recorded yet.</p></div>';

    // Narrative History with sort toggle
    const historyNewestFirst = localStorage.getItem('jericho-history-sort') === 'newest';
    let historyHtml;
    if (data.history) {
        let displayHistory = data.history;
        if (historyNewestFirst) {
            // Split by ## headings and reverse sections
            const sections = data.history.split(/(?=^## )/m);
            // Separate any preamble (content before first ## heading)
            let preamble = '';
            let headingSections = sections;
            if (sections.length > 0 && !sections[0].startsWith('## ')) {
                preamble = sections[0];
                headingSections = sections.slice(1);
            }
            displayHistory = preamble + headingSections.reverse().join('');
        }
        historyHtml = `<div class="shared-history-content">${escapeHtml(displayHistory)}</div>`;
    } else {
        historyHtml = '<div class="empty-state"><div class="empty-icon">📖</div><p>No narrative history written yet.</p></div>';
    }

    const sortLabel = historyNewestFirst ? 'Newest First' : 'Oldest First';
    const sortIcon = historyNewestFirst ? '⬇️' : '⬆️';

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
                        <button class="btn btn-sm" onclick="toggleHistorySort()" title="Toggle sort order" id="history-sort-btn">
                            ${sortIcon} ${sortLabel}
                        </button>
                    </div>
                    ${historyHtml}
                </div>
            </div>
        </div>`;
}

function toggleHistorySort() {
    const current = localStorage.getItem('jericho-history-sort') === 'newest';
    localStorage.setItem('jericho-history-sort', current ? 'oldest' : 'newest');
    renderSharedMemory();
}

async function deleteSharedDecision(index, label) {
    if (!confirm(`Delete decision "${label}"?`)) return;
    try {
        const resp = await fetch(`/api/memories/shared/decisions?index=${index}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast(`Decision deleted ✅`);
        await renderSharedMemory();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
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
    if (data.treasury) {
        const tEl = document.getElementById('count-treasury');
        if (tEl) tEl.textContent = data.treasury.total_accounts || 0;
    }
    if (data.items) {
        const iEl = document.getElementById('count-items');
        if (iEl) iEl.textContent = data.items.count || 0;
    }
    if (data.laws) {
        const lawEl = document.getElementById('count-laws');
        if (lawEl) lawEl.textContent = data.laws.count || 0;
    }
    if (data.stores) {
        const sEl = document.getElementById('count-stores');
        if (sEl) sEl.textContent = data.stores.count || 0;
    }
}
// ═══════════════════════════════════════════════════════════════
// Treasury View
// ═══════════════════════════════════════════════════════════════

const ACCT_TYPE_LABELS = {
    council_member: { icon: '👥', label: 'Council Member', badge: 'council_member' },
    character:      { icon: '🎭', label: 'Character',      badge: 'character' },
    user:           { icon: '👤', label: 'User',            badge: 'user' },
    government:     { icon: '🏛️', label: 'Government',     badge: 'government' },
};

