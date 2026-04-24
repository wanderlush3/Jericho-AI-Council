async function renderMemories() {
    showLoading();
    const data = await api('/api/memories');
    let sharedData = { decision_count: 0, history: '' };
    try { sharedData = await api('/api/memories/shared'); } catch { /* empty */ }
    let lawSharedData = { law_count: 0 };
    try { lawSharedData = await api('/api/memories/law-shared'); } catch { /* empty */ }

    // Separate council members and characters (F-074)
    const councilItems = data.filter(m => m.type === 'council_member');
    const characterItems = data.filter(m => m.type === 'character');

    const makeCard = (m, i, isCharacter) => {
        const navKey = isCharacter ? (m.memory_key || m.name) : m.name;
        const typeBadge = isCharacter
            ? `<span class="memory-type-badge memory-type-character">🎭 Character</span>`
            : '';
        const statusBadge = (isCharacter && m.character_status)
            ? `<span class="badge badge-${m.character_status}" style="font-size:0.7rem; margin-left:4px;">${m.character_status}</span>`
            : '';
        const avatarHtml = m.avatar_url
            ? `<div class="memory-avatar" style="background: url('${m.avatar_url}') center/cover no-repeat"></div>`
            : `<div class="memory-avatar" style="background: ${AVATAR_COLORS[i % AVATAR_COLORS.length]}">${m.name.charAt(0).toUpperCase()}</div>`;
        return `
        <div class="card card-clickable memory-card${isCharacter ? ' memory-card-character' : ''}" onclick="navigateTo('memories','${escapeAttr(navKey)}')">
            <div class="memory-card-header">
                ${avatarHtml}
                <div>
                    <div class="member-name">${escapeHtml(m.name)} ${statusBadge}</div>
                    <div class="member-role">${escapeHtml(truncate(m.role, 60))}</div>
                    ${typeBadge}
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
    };

    const memberCards = councilItems.map((m, i) => makeCard(m, i, false)).join('');
    const charCards = characterItems.map((m, i) => makeCard(m, i + councilItems.length, true)).join('');

    const sharedCard = `
        <div class="card card-clickable memory-card memory-card-shared" onclick="navigateTo('memories','shared')">
            <div class="memory-card-header">
                <div class="memory-avatar memory-avatar-shared">🌐</div>
                <div>
                    <div class="member-name">Shared Memory</div>
                    <div class="member-role">Council-wide decisions &amp; history</div>
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

    // Build character section if any characters have memories
    const charSection = charCards ? `
        <div class="memory-section-divider">
            <span class="memory-section-title">🎭 Character Memories</span>
        </div>
        <div class="member-grid">
            ${charCards}
        </div>` : '';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🧠 Memories</h2>
                <p>Explore council member beliefs, character memories, session events, and shared council memory</p>
            </div>
            <div class="member-grid">
                ${sharedCard}
                ${lawSharedCard}
                ${memberCards}
            </div>
            ${charSection}
        </div>`;
}

async function renderMemoryDetail(memberName) {
    showLoading();
    const limit = 25;
    const data = await api(`/api/memories/${encodeURIComponent(memberName)}?limit=${limit}`);

    // Show type badge for character memories
    const typeBadge = data.type === 'character'
        ? `<span class="memory-type-badge memory-type-character" style="margin-left:8px;">🎭 Character</span>`
        : '';

    // F-075: Stats line
    const statsLine = [
        `${data.belief_count} belief${data.belief_count !== 1 ? 's' : ''}`,
        `${data.event_count} event${data.event_count !== 1 ? 's' : ''}`,
        `${data.session_count || 0} session${(data.session_count || 0) !== 1 ? 's' : ''}`,
    ];
    if (data.contested_count > 0) statsLine.push(`${data.contested_count} contested`);
    if (data.summarized_count > 0) statsLine.push(`${data.summarized_count} summarized`);
    // F-077: Scoring mode indicator
    const scoringBadge = data.scoring_mode === 'keyword_only'
        ? '🔤 Keyword Only'
        : data.embeddings_available
            ? '🧠 Semantic + Keyword'
            : '🔤 Keyword Only (model unavailable)';
    statsLine.push(scoringBadge);

    const beliefRows = data.beliefs.length ? data.beliefs.map(b => `
        <div class="belief-item">
            <div class="belief-header">
                <span class="belief-topic">${escapeHtml(b.topic)}</span>
                <button class="btn-icon belief-delete" onclick="deleteCoreBelief('${escapeAttr(memberName)}', '${escapeAttr(b.topic)}')" title="Delete belief">
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
        // F-075: Compute age for freshness indicator
        const ageMs = e.timestamp ? (Date.now() - new Date(e.timestamp).getTime()) : 0;
        const ageDays = Math.floor(ageMs / 86400000);
        const freshnessClass = ageDays > 60 ? 'freshness-old' : ageDays > 14 ? 'freshness-moderate' : 'freshness-recent';
        const freshnessLabel = ageDays > 0 ? `${ageDays}d ago` : 'today';
        return `
        <div class="event-item ${freshnessClass}">
            <div class="event-header">
                <span class="badge badge-${typeBadge}">${typeBadge}</span>
                <span class="event-session">${escapeHtml(e.session_id || '')}</span>
                <span class="event-timestamp">${formatDate(e.timestamp)}</span>
                <span class="freshness-indicator">${freshnessLabel}</span>
            </div>
            <div class="event-content">${escapeHtml(e.content)}</div>
            ${e.source ? `<div class="event-source">— ${escapeHtml(e.source)}</div>` : ''}
        </div>`;
    }).join('') : '<div class="empty-state"><div class="empty-icon">📝</div><p>No session events recorded yet.</p></div>';

    // F-075: Summarize button
    const summarizeBtn = (data.session_count || 0) >= 6
        ? `<button class="btn btn-sm summarize-btn" onclick="triggerSummarize('${escapeAttr(memberName)}')" id="summarize-btn">📋 Summarize Old Sessions</button>`
        : '';

    // F-075: Contested section (lazy loaded)
    const contestedSection = data.contested_count > 0
        ? `<div class="memory-panel contested-panel">
                <div class="memory-panel-header">
                    <h3>🔀 Contested Memories</h3>
                    <span class="memory-panel-count">${data.contested_count}</span>
                </div>
                <div id="contested-list" class="contested-list">
                    <button class="btn btn-sm" onclick="loadContestedMemories('${escapeAttr(memberName)}')">Load Contested Memories</button>
                </div>
            </div>`
        : '';

    // F-075: Summarized section (lazy loaded)
    const summarizedSection = data.summarized_count > 0
        ? `<div class="memory-panel summarized-panel">
                <div class="memory-panel-header">
                    <h3>📋 Summarized Sessions</h3>
                    <span class="memory-panel-count">${data.summarized_count}</span>
                </div>
                <div id="summarized-list" class="summarized-list">
                    <button class="btn btn-sm" onclick="loadSummarizedMemories('${escapeAttr(memberName)}')">Load Summarized Entries</button>
                </div>
            </div>`
        : '';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('memories')">← Back to Memories</button>
            <div class="page-header">
                <h2>🧠 ${escapeHtml(data.name)}'s Memory ${typeBadge}</h2>
                <p>${statsLine.join(' · ')}</p>
                ${summarizeBtn}
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

                ${contestedSection}
                ${summarizedSection}
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

// ─── F-075: Contested, Summarized, and Summarize Actions ──────

async function loadContestedMemories(memberName) {
    const container = document.getElementById('contested-list');
    if (!container) return;
    container.innerHTML = '<div class="loading-indicator">Loading…</div>';
    try {
        const data = await api(`/api/memories/${encodeURIComponent(memberName)}/contested`);
        if (!data.contested || data.contested.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No contested memories.</p></div>';
            return;
        }
        container.innerHTML = data.contested.map(c => `
            <div class="contested-item">
                <div class="contested-header">
                    <span class="badge badge-contested">contested</span>
                    <span class="contested-agent">${escapeHtml(c.member_name || '')}</span>
                    <span class="event-timestamp">${c.timestamp ? formatDate(c.timestamp) : ''}</span>
                </div>
                <div class="contested-original">
                    <strong>Original:</strong> ${escapeHtml(c.original_content || '')}
                </div>
                <div class="contested-divergent">
                    <strong>Divergent:</strong> ${escapeHtml(c.content || '')}
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Failed to load: ${escapeHtml(err.message)}</p></div>`;
    }
}

async function loadSummarizedMemories(memberName) {
    const container = document.getElementById('summarized-list');
    if (!container) return;
    container.innerHTML = '<div class="loading-indicator">Loading…</div>';
    try {
        const data = await api(`/api/memories/${encodeURIComponent(memberName)}/summarized`);
        if (!data.summarized || data.summarized.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No summarized entries.</p></div>';
            return;
        }
        container.innerHTML = data.summarized.map(s => `
            <div class="event-item summarized-item">
                <div class="event-header">
                    <span class="badge badge-summary">summary</span>
                    <span class="summarized-badge">📋 Summarized</span>
                    <span class="event-timestamp">${s.timestamp ? formatDate(s.timestamp) : ''}</span>
                </div>
                <div class="event-content">${escapeHtml(s.content || '')}</div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Failed to load: ${escapeHtml(err.message)}</p></div>`;
    }
}

async function triggerSummarize(memberName) {
    const btn = document.getElementById('summarize-btn');
    if (!btn) return;
    if (!confirm(`Run LLM summarization on old sessions for ${memberName}? This will call the summarization API.`)) return;

    btn.disabled = true;
    btn.textContent = '⏳ Summarizing…';
    try {
        const resp = await fetch(`/api/memories/${encodeURIComponent(memberName)}/summarize`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Summarization failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Created ${data.summaries_created} summary entries ✅`);
        await renderMemoryDetail(memberName);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        btn.disabled = false;
        btn.textContent = '📋 Summarize Old Sessions';
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
