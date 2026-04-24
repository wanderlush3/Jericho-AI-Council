async function renderView(view, detail) {
    try {
        switch (view) {
            case 'dashboard': await renderDashboard(); break;
            case 'council': detail ? await renderCouncilDetail(detail) : await renderCouncil(); break;
            case 'proposals': detail ? await renderProposalDetail(detail) : await renderProposals(); break;
            case 'votes': detail ? await renderVoteDetail(detail) : await renderVotes(); break;
            case 'characters': detail ? await renderCharacterDetail(detail) : await renderCharacters(); break;
            case 'evolution': detail ? await renderEvolutionDetail(detail) : await renderEvolution(); break;
            case 'tasks': detail ? await renderTaskDetail(detail) : await renderTasks(); break;
            case 'explore': detail ? await renderExploreLocation(detail) : await renderExplore(); break;
            case 'stories': detail ? await renderStoryDetail(detail) : await renderStories(); break;
            case 'locations': detail ? await renderLocationDetail(detail) : await renderLocations(); break;
            case 'laws': detail ? await renderLawDetail(detail) : await renderLaws(); break;
            case 'items': detail ? await renderItemDetail(detail) : await renderItems(); break;
            case 'gifts': await renderGifts(); break;
            case 'stores': detail ? await renderStoreDetail(detail) : await renderStores(); break;
            case 'analytics': await renderAnalytics(); break;
            case 'chat': detail ? await renderChatDetail(detail) : await renderChat(); break;
            case 'memories': detail === 'shared' ? await renderSharedMemory() : detail === 'law_shared' ? await renderLawSharedMemory() : detail ? await renderMemoryDetail(detail) : await renderMemories(); break;
            case 'sessions': detail ? await renderCouncilSessionDetail(detail) : await renderCouncilSessions(); break;
            case 'treasury': detail ? await renderTreasuryDetail(detail) : await renderTreasury(); break;
            case 'taxation': await renderTaxation(); break;
            case 'generation-queue': await renderGenerationQueue(); break;
            case 'reputation': detail ? await renderReputationDetail(detail) : await renderReputation(); break;
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

    // Parallel fetch: status, activity feed, system health
    const [data, activityEvents, healthData] = await Promise.all([
        api('/api/status'),
        api('/api/activity-feed').catch(() => []),
        api('/api/system-health').catch(() => ({})),
    ]);
    state.statusData = data;
    updateNavCounts(data);

    const m = data.members || {};
    const p = data.proposals || {};
    const v = data.votes || {};
    const c = data.characters || {};
    const l = data.locations || {};
    const ev = data.evolutions || {};
    const it = data.items || {};

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Dashboard</h2>
                <p>Jericho AI Council — collaborative AI character design through democratic governance</p>
            </div>

            <div class="narrative-banner" id="narrative-banner">
                <div class="narrative-banner-header">
                    <span class="narrative-banner-title">📰 Jericho Times</span>
                    <span class="narrative-banner-controls">
                        <button class="narrative-btn" id="narrative-prev" title="Previous">◀</button>
                        <span class="narrative-counter" id="narrative-counter"></span>
                        <button class="narrative-btn" id="narrative-next" title="Next">▶</button>
                    </span>
                </div>
                <div class="narrative-ticker" id="narrative-ticker">
                    <div class="narrative-loading">Loading bulletins...</div>
                </div>
            </div>

            ${_buildQuickActions()}

            <div class="dashboard-layout">
                <div class="dashboard-col-left">
                    ${_buildActivityTimeline(activityEvents)}
                </div>
                <div class="dashboard-col-right">
                    ${_buildSystemHealth(healthData)}
                    ${_buildStatSummary(m, p, v, c, l, ev, it, data)}
                </div>
            </div>
        </div>`;

    // -- Narrative Banner: fetch and cycle bulletins --
    _initNarrativeBanner();
}

/** Build the quick-action button bar. */
function _buildQuickActions() {
    return `
        <div class="quick-actions">
            <button class="quick-action-btn" onclick="navigate('chat')" title="Start a conversation">
                <span class="qa-icon">💬</span> Start Chat
            </button>
            <button class="quick-action-btn" onclick="navigate('proposals')" title="Create a new proposal">
                <span class="qa-icon">📜</span> Create Proposal
            </button>
            <button class="quick-action-btn" onclick="navigate('tasks')" title="Run a task">
                <span class="qa-icon">⚡</span> Run Task
            </button>
            <button class="quick-action-btn" onclick="navigate('gifts')" title="Send a gift">
                <span class="qa-icon">🎁</span> Give Gift
            </button>
        </div>`;
}

/** Build the scrollable activity timeline from events. */
function _buildActivityTimeline(events) {
    if (!events || events.length === 0) {
        return `
            <div class="activity-timeline">
                <div class="activity-timeline-header">
                    <h3>⏱️ Activity Timeline</h3>
                </div>
                <div class="activity-empty">
                    <span class="empty-icon">📭</span>
                    No recent activity. Create a proposal or start a chat to get things moving!
                </div>
            </div>`;
    }

    const items = events.map(ev => {
        const timeStr = _formatRelativeTime(ev.timestamp);
        return `
            <div class="activity-event" onclick="navigate('${_escHtml(ev.nav_target || '')}')">
                <div class="activity-event-icon">${ev.icon || '📋'}</div>
                <div class="activity-event-body">
                    <div class="activity-event-title">${_escHtml(ev.title || '')}</div>
                    <div class="activity-event-desc">${_escHtml(ev.description || '')}</div>
                </div>
                <div class="activity-event-time">${_escHtml(timeStr)}</div>
            </div>`;
    }).join('');

    return `
        <div class="activity-timeline">
            <div class="activity-timeline-header">
                <h3>⏱️ Activity Timeline</h3>
                <span class="event-count">${events.length} event${events.length !== 1 ? 's' : ''}</span>
            </div>
            ${items}
        </div>`;
}

/** Build the system health panel. */
function _buildSystemHealth(health) {
    if (!health || Object.keys(health).length === 0) {
        return '';
    }

    let rows = '';

    // Provider status
    const providers = health.providers || [];
    for (const prov of providers) {
        const dot = prov.configured ? 'green' : 'red';
        const label = prov.provider.charAt(0).toUpperCase() + prov.provider.slice(1);
        const val = prov.configured ? 'Configured' : 'Not set';
        rows += `
            <div class="health-item">
                <span class="health-dot ${dot}"></span>
                <span class="health-label">${_escHtml(label)}</span>
                <span class="health-value">${_escHtml(val)}</span>
            </div>`;
    }

    // Embedding status
    const emb = health.embedding || {};
    if (emb.model) {
        const dot = emb.available ? 'green' : 'amber';
        const val = emb.available ? emb.model : 'Not installed';
        rows += `
            <div class="health-item">
                <span class="health-dot ${dot}"></span>
                <span class="health-label">Embeddings</span>
                <span class="health-value">${_escHtml(val)}</span>
            </div>`;
        rows += `
            <div class="health-item">
                <span class="health-dot green"></span>
                <span class="health-label">Scoring Mode</span>
                <span class="health-value">${_escHtml(emb.mode || 'hybrid')}</span>
            </div>`;
    }

    return `
        <div class="system-health">
            <h3>🩺 System Health</h3>
            <div class="health-grid">
                ${rows}
            </div>
        </div>`;
}

/** Build the compact stat summary cards. */
function _buildStatSummary(m, p, v, c, l, ev, it, data) {
    function _chips(byStatus) {
        if (!byStatus) return '';
        return Object.entries(byStatus)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

    function _card(icon, value, label, nav, chips) {
        return `
            <div class="stat-summary-card" onclick="navigate('${nav}')">
                <div class="stat-summary-icon">${icon}</div>
                <div class="stat-summary-value">${value}</div>
                <div class="stat-summary-label">${label}</div>
                ${chips ? `<div class="stat-summary-chips">${chips}</div>` : ''}
            </div>`;
    }

    return `
        <div class="stat-summary-grid">
            ${_card('👥', m.count || 0, 'Members', 'council', _chips(m.providers))}
            ${_card('📜', p.count || 0, 'Proposals', 'proposals', _chips(p.by_status))}
            ${_card('🗳️', v.count || 0, 'Votes', 'votes', _chips(v.by_status))}
            ${_card('🎭', c.count || 0, 'Characters', 'characters', _chips(c.by_status))}
            ${_card('🗺️', l.count || 0, 'Locations', 'locations', _chips(l.by_status))}
            ${_card('🧬', ev.count || 0, 'Evolutions', 'evolution', _chips(ev.by_status))}
            ${_card('📦', it.count || 0, 'Items', 'items', _chips(it.by_status))}
            ${_card('🪙', (data.treasury || {}).total_accounts || 0, 'Treasury', 'treasury', '')}
            ${_card('⚖️', (data.laws || {}).count || 0, 'Laws', 'laws', _chips((data.laws || {}).by_status))}
        </div>`;
}

/** Format ISO timestamp as relative time (e.g. "2h ago", "3d ago"). */
function _formatRelativeTime(isoStr) {
    if (!isoStr) return '';
    try {
        const dt = new Date(isoStr);
        const now = new Date();
        const diffMs = now - dt;
        const diffSec = Math.floor(diffMs / 1000);
        if (diffSec < 60) return 'just now';
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return diffMin + 'm ago';
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr < 24) return diffHr + 'h ago';
        const diffDay = Math.floor(diffHr / 24);
        if (diffDay < 30) return diffDay + 'd ago';
        const diffMonth = Math.floor(diffDay / 30);
        return diffMonth + 'mo ago';
    } catch (_) {
        return '';
    }
}

/** Fetch bulletins and start the auto-cycling ticker. */
async function _initNarrativeBanner() {
    const ticker = document.getElementById('narrative-ticker');
    const counter = document.getElementById('narrative-counter');
    const prevBtn = document.getElementById('narrative-prev');
    const nextBtn = document.getElementById('narrative-next');
    const banner = document.getElementById('narrative-banner');
    if (!ticker) return;

    let bulletins = [];
    try {
        bulletins = await api('/api/narrative-bulletins');
    } catch (_) {
        bulletins = [];
    }

    if (!bulletins || bulletins.length === 0) {
        ticker.innerHTML = '<div class="narrative-empty">No recent news. The council chambers are quiet.</div>';
        if (counter) counter.textContent = '';
        return;
    }

    let currentIdx = 0;
    let cycleTimer = null;

    const SOURCE_NAV = {
        proposal: 'proposals',
        vote: 'votes',
        character: 'characters',
        item: 'items',
        location: 'locations',
        treasury: 'treasury',
        session: 'sessions',
    };

    function renderBulletin(idx) {
        const b = bulletins[idx];
        const navView = SOURCE_NAV[b.source_type] || '';
        const clickAttr = navView ? `onclick="navigate('${navView}')" style="cursor:pointer;" title="Go to ${navView}"` : '';
        ticker.classList.remove('narrative-fade-in');
        // Force reflow for animation restart
        void ticker.offsetWidth;
        ticker.classList.add('narrative-fade-in');
        ticker.innerHTML = `
            <div class="narrative-item" ${clickAttr}>
                <span class="narrative-icon">${b.icon}</span>
                <div class="narrative-content">
                    <div class="narrative-headline">${_escHtml(b.headline)}</div>
                    <div class="narrative-body">${_escHtml(_truncateToSentence(b.body, 2000))}</div>
                </div>
            </div>`;
        if (counter) counter.textContent = (idx + 1) + ' / ' + bulletins.length;
    }

    function advance(dir) {
        currentIdx = (currentIdx + dir + bulletins.length) % bulletins.length;
        renderBulletin(currentIdx);
        resetTimer();
    }

    function resetTimer() {
        if (cycleTimer) clearInterval(cycleTimer);
        cycleTimer = setInterval(() => advance(1), 8000);
    }

    if (prevBtn) prevBtn.addEventListener('click', (e) => { e.stopPropagation(); advance(-1); });
    if (nextBtn) nextBtn.addEventListener('click', (e) => { e.stopPropagation(); advance(1); });

    renderBulletin(0);
    resetTimer();
}

/**
 * Truncate text to a maximum character limit, ending at the last
 * sentence boundary (. ! ?) before the limit. If no sentence boundary
 * is found in the first 500 characters, falls back to the last space.
 */
function _truncateToSentence(text, maxLen) {
    if (!text || text.length <= maxLen) return text;
    // Search for the last sentence-ending punctuation within the limit
    const slice = text.slice(0, maxLen);
    // Find last '. ' or '! ' or '? ' or sentence-ender at end of slice
    let lastSentenceEnd = -1;
    for (let i = slice.length - 1; i >= 0; i--) {
        const ch = slice[i];
        if (ch === '.' || ch === '!' || ch === '?') {
            // Accept if it's followed by a space, end of slice, or a quote
            const next = slice[i + 1];
            if (!next || next === ' ' || next === '"' || next === "'" || next === '\n') {
                lastSentenceEnd = i + 1;
                break;
            }
        }
    }
    if (lastSentenceEnd > 500) {
        return slice.slice(0, lastSentenceEnd).trimEnd();
    }
    // Fallback: break at last space to avoid cutting a word
    const lastSpace = slice.lastIndexOf(' ');
    if (lastSpace > 500) {
        return slice.slice(0, lastSpace).trimEnd() + '…';
    }
    // Final fallback: hard cut with ellipsis
    return slice.trimEnd() + '…';
}

/** Minimal HTML escaper for bulletin text. */
function _escHtml(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

