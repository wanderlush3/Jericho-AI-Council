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

    const it = data.items || {};
    let itemChips = '';
    if (it.by_status) {
        itemChips = Object.entries(it.by_status)
            .map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`)
            .join('');
    }

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
                <div class="stat-card" style="border-image:linear-gradient(135deg, #FFD700, #C0C0C0, #CD7F32) 1">
                    <div class="stat-icon">🪙</div>
                    <div class="stat-value">${(data.treasury || {}).total_accounts || 0}</div>
                    <div class="stat-label">Treasury Accounts</div>
                    ${(data.treasury && data.treasury.government_balance) ? `<div class="stat-breakdown"><span class="stat-chip badge badge-government">Gov: ${data.treasury.government_balance.gold}G</span></div>` : ''}
                </div>
                <div class="stat-card" style="border-image:linear-gradient(135deg, hsl(30,70%,50%), hsl(40,80%,55%)) 1">
                    <div class="stat-icon">📦</div>
                    <div class="stat-value">${it.count || 0}</div>
                    <div class="stat-label">Items</div>
                    ${itemChips ? `<div class="stat-breakdown">${itemChips}</div>` : ''}
                </div>
                <div class="stat-card" style="border-image:linear-gradient(135deg, hsl(220,60%,50%), hsl(200,55%,45%)) 1">
                    <div class="stat-icon">⚖️</div>
                    <div class="stat-value">${(data.laws || {}).count || 0}</div>
                    <div class="stat-label">Laws</div>
                    ${(data.laws && data.laws.by_status) ? Object.entries(data.laws.by_status).map(([k, cnt]) => `<span class="stat-chip badge badge-${k}">${k}: ${cnt}</span>`).join('') : ''}
                </div>
            </div>
        </div>`;

    // -- Narrative Banner: fetch and cycle bulletins --
    _initNarrativeBanner();
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

