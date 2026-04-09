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
    activeSkin: localStorage.getItem('jericho-skin') || 'default',
};

const $main = () => document.getElementById('main-content');

function escapeHtml(str) {
    const el = document.createElement('div');
    el.textContent = str || '';
    return el.innerHTML;
}

function escapeAttr(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ─── Skin / Theme System ──────────────────────────────────────

const SKINS = {
    default: {
        label: 'Default',
        icon: '🌑',
        desc: 'Dark premium dashboard',
        swatches: ['#0a0e17', '#111827', '#3b82f6', '#06b6d4', '#8b5cf6'],
        vars: {},
    },
    frutiger_aero: {
        label: 'Frutiger Aero',
        icon: '🫧',
        desc: 'Glossy Y2K optimism',
        swatches: ['#e8f4fd', '#f0fdf4', '#ffffff', '#38bdf8', '#f97316'],
        vars: {
            /* Background palette — light, airy, sky-inspired */
            '--bg-primary': '#e4f0fb',
            '--bg-secondary': '#f0f7ff',
            '--bg-card': 'rgba(255, 255, 255, 0.65)',
            '--bg-card-hover': 'rgba(255, 255, 255, 0.85)',
            '--bg-input': 'rgba(255, 255, 255, 0.7)',
            '--bg-sidebar': 'rgba(224, 242, 254, 0.92)',

            /* Text palette — dark on light */
            '--text-primary': '#1e293b',
            '--text-secondary': '#475569',
            '--text-muted': '#64748b',
            '--text-accent': '#0284c7',

            /* Accent colors — vibrant, warm, nature-inspired */
            '--accent-blue': '#0ea5e9',
            '--accent-cyan': '#06b6d4',
            '--accent-emerald': '#10b981',
            '--accent-amber': '#f59e0b',
            '--accent-rose': '#f43f5e',
            '--accent-violet': '#8b5cf6',
            '--accent-indigo': '#6366f1',

            /* Borders — glossy, translucent white */
            '--border-subtle': 'rgba(148, 163, 184, 0.25)',
            '--border-medium': 'rgba(148, 163, 184, 0.35)',
            '--border-glow': 'rgba(14, 165, 233, 0.4)',

            /* Shadows — soft, light-mode glow */
            '--shadow-sm': '0 1px 3px rgba(0, 0, 0, 0.08)',
            '--shadow-md': '0 4px 14px rgba(0, 0, 0, 0.1)',
            '--shadow-lg': '0 8px 30px rgba(0, 0, 0, 0.12)',
            '--shadow-glow': '0 0 20px rgba(14, 165, 233, 0.15)',
        },
    },
    vaporwave: {
        label: 'Vaporwave',
        icon: '🌴',
        desc: 'Retro-futuristic neon glow',
        swatches: ['#1a0a2e', '#16213e', '#ff71ce', '#01cdfe', '#b967ff'],
        vars: {
            /* Background palette — deep purple-navy */
            '--bg-primary': '#0d0221',
            '--bg-secondary': '#150535',
            '--bg-card': 'rgba(26, 10, 46, 0.75)',
            '--bg-card-hover': 'rgba(36, 15, 62, 0.85)',
            '--bg-input': 'rgba(22, 8, 42, 0.8)',
            '--bg-sidebar': 'rgba(13, 2, 33, 0.95)',

            /* Text palette — soft pastels on dark */
            '--text-primary': '#e8d5f5',
            '--text-secondary': '#b8a0cc',
            '--text-muted': '#8a6faa',
            '--text-accent': '#ff71ce',

            /* Accent colors — neon retro palette */
            '--accent-blue': '#01cdfe',
            '--accent-cyan': '#05ffa1',
            '--accent-emerald': '#05ffa1',
            '--accent-amber': '#fffb96',
            '--accent-rose': '#ff71ce',
            '--accent-violet': '#b967ff',
            '--accent-indigo': '#7b5ea7',

            /* Borders — neon-tinged */
            '--border-subtle': 'rgba(185, 103, 255, 0.15)',
            '--border-medium': 'rgba(185, 103, 255, 0.3)',
            '--border-glow': 'rgba(255, 113, 206, 0.4)',

            /* Shadows — neon glow */
            '--shadow-sm': '0 1px 4px rgba(185, 103, 255, 0.1)',
            '--shadow-md': '0 4px 16px rgba(185, 103, 255, 0.12)',
            '--shadow-lg': '0 8px 32px rgba(185, 103, 255, 0.15)',
            '--shadow-glow': '0 0 24px rgba(255, 113, 206, 0.2)',
        },
    },
};

/** Track which CSS variables were last set so we can clear them. */
let _lastSkinVarKeys = [];

function applySkin(name) {
    const skin = SKINS[name];
    if (!skin) return;

    const root = document.documentElement;

    // Enable transition
    root.setAttribute('data-skin-transitioning', '');

    // Clear previous overrides
    _lastSkinVarKeys.forEach(k => root.style.removeProperty(k));
    _lastSkinVarKeys = [];

    // Apply new overrides
    if (skin.vars) {
        Object.entries(skin.vars).forEach(([k, v]) => {
            root.style.setProperty(k, v);
            _lastSkinVarKeys.push(k);
        });
    }

    root.setAttribute('data-skin', name);
    state.activeSkin = name;
    localStorage.setItem('jericho-skin', name);

    // Remove transition attribute after animation completes
    setTimeout(() => root.removeAttribute('data-skin-transitioning'), 500);
}

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

// Maps each view name to its parent accordion section
const VIEW_TO_SECTION = {
    dashboard: 'overview', analytics: 'overview',
    council: 'governance', proposals: 'governance', votes: 'governance',
    sessions: 'governance', laws: 'governance',
    characters: 'characters', memories: 'characters', evolution: 'characters',
    tasks: 'characters',
    chat: 'world', explore: 'world', locations: 'world', items: 'world', stores: 'world',
    treasury: 'world', taxation: 'world',
    settings: 'config',
};

/** Toggle a sidebar accordion section open/closed. */
function toggleNavSection(sectionName) {
    const section = document.querySelector(`.nav-section[data-section="${sectionName}"]`);
    if (!section) return;
    section.classList.toggle('open');
    _saveAccordionState();
}

/** Ensure the section for the given view is open (without closing others). */
function _expandSectionForView(view) {
    const sectionName = VIEW_TO_SECTION[view];
    if (!sectionName) return;
    const section = document.querySelector(`.nav-section[data-section="${sectionName}"]`);
    if (section && !section.classList.contains('open')) {
        section.classList.add('open');
        _saveAccordionState();
    }
}

/** Save which sections are open to localStorage. */
function _saveAccordionState() {
    const openSections = [];
    document.querySelectorAll('.nav-section.open').forEach(s => {
        const name = s.dataset.section;
        if (name) openSections.push(name);
    });
    localStorage.setItem('jericho-nav-accordion', JSON.stringify(openSections));
}

/** Restore accordion state from localStorage, or default to opening the active section. */
function _restoreAccordionState(activeView) {
    const saved = localStorage.getItem('jericho-nav-accordion');
    let openSections;
    if (saved) {
        try { openSections = JSON.parse(saved); } catch { openSections = null; }
    }
    if (!openSections) {
        // Default: open only the section containing the active view
        const activeSec = VIEW_TO_SECTION[activeView] || 'overview';
        openSections = [activeSec];
    }
    document.querySelectorAll('.nav-section[data-section]').forEach(s => {
        if (openSections.includes(s.dataset.section)) {
            s.classList.add('open');
        } else {
            s.classList.remove('open');
        }
    });
}

function navigateTo(view, detail) {
    state.currentView = view;
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    // Auto-expand the section containing the target view
    _expandSectionForView(view);
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

    // Restore accordion state after DOM is ready
    const hash = window.location.hash.slice(1) || 'dashboard';
    const activeView = hash.split('/')[0];
    _restoreAccordionState(activeView);
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
            case 'tasks': detail ? await renderTaskDetail(detail) : await renderTasks(); break;
            case 'explore': detail ? await renderExploreLocation(detail) : await renderExplore(); break;
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
                    <div class="narrative-body">${_escHtml(b.body)}</div>
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

async function renderProposals() {
    showLoading();
    const data = await api('/api/proposals');
    state.proposalsData = data;

    // Fetch council members for the author selector
    let members = [];
    try { members = await api('/api/council'); } catch { /* empty */ }

    // Fetch the user's display name so they can author proposals too
    let userName = '';
    try {
        const userResp = await api('/api/settings/user-name');
        userName = (userResp.name || '').trim();
    } catch { /* empty */ }

    const userOption = userName
        ? `<option value="${userName}">${userName} — You</option>
           <option disabled>──────────</option>`
        : '';

    const memberOptions = userOption + members.map(m =>
        `<option value="${m.name}">${m.name} — ${m.role}</option>`
    ).join('');

    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general', 'evolution', 'location', 'item', 'law']
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
                        <select id="proposal-category-select" class="settings-input" onchange="toggleProposalCategoryFields()">
                            ${categoryOptions}
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <label for="proposal-title-input">Title</label>
                        <input id="proposal-title-input" class="settings-input" placeholder="e.g. Expand Ethical Constraints" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="proposal-desc-input">Description <span id="proposal-desc-hint" style="font-weight:400;font-size:0.78rem;color:var(--accent-cyan)"></span></label>
                    <textarea id="proposal-desc-input" class="settings-input proposal-textarea" rows="3"
                        placeholder="Describe the proposal and its goals…"></textarea>
                </div>

                <!-- Character-specific fields (shown when category=character) -->
                <div id="proposal-char-fields" class="character-fields-panel" style="display:none">
                    <div class="char-fields-header">🎭 Character Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-char-name">Character Name</label>
                            <input id="proposal-char-name" class="settings-input" placeholder="e.g. Atlas" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-provider">API Provider</label>
                            <select id="proposal-char-provider" class="settings-input" onchange="updateProposalCharModelField()">
                                <option value="openrouter">OpenRouter</option>
                                <option value="mancer">Mancer</option>
                                <option value="lmstudio">LM Studio</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-model">Model</label>
                            <div id="proposal-char-model-container">
                                ${renderModelField('proposal-char-model', 'openrouter', '', true)}
                            </div>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-backstory">Backstory</label>
                        <textarea id="proposal-char-backstory" class="settings-input proposal-textarea" rows="3"
                            placeholder="Character history and background — the lion's share of the character's story…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-prompt">System Prompt</label>
                        <textarea id="proposal-char-prompt" class="settings-input proposal-textarea" rows="3"
                            placeholder="You are {{char}}, an adventurous AI who…"></textarea>
                    </div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-char-greeting">Greeting</label>
                            <input id="proposal-char-greeting" class="settings-input" placeholder="First message the character says…" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-tags">Tags</label>
                            <input id="proposal-char-tags" class="settings-input" placeholder="explorer, brave (comma-separated)" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-examples">Example Messages</label>
                        <textarea id="proposal-char-examples" class="settings-input proposal-textarea" rows="2"
                            placeholder="One message per line…"></textarea>
                    </div>

                    <div class="char-trait-editor" style="margin-top:var(--space-md)">
                        <label>Traits</label>
                        <div id="proposal-char-trait-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group">
                                <input id="proposal-char-trait-name" class="settings-input" placeholder="Trait name (e.g. Curious)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-char-trait-type" class="settings-input">
                                    <option value="personality">Personality</option>
                                    <option value="values">Values</option>
                                    <option value="flaws">Flaws</option>
                                    <option value="custom">Custom</option>
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-char-trait-desc" class="settings-input" placeholder="Trait description…" />
                            </div>
                            <div class="filter-group" style="flex:0.5">
                                <input id="proposal-char-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5"
                                    class="avatar-zoom-slider" oninput="document.getElementById('proposal-char-trait-intensity-val').textContent = this.value" />
                                <span id="proposal-char-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalCharTrait()">
                            ➕ Add Trait
                        </button>
                    </div>
                </div>

                <!-- Location-specific fields (shown when category=location) -->
                <div id="proposal-loc-fields" class="location-fields-panel" style="display:none">
                    <div class="loc-fields-header">🌍 Location Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-loc-name">Location Name</label>
                            <input id="proposal-loc-name" class="settings-input" placeholder="e.g. Ironhaven" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-loc-coords">Coordinates</label>
                            <input id="proposal-loc-coords" class="settings-input" placeholder="e.g. 42.3N, 71.1W (optional)" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-loc-lore">Lore</label>
                        <textarea id="proposal-loc-lore" class="settings-input proposal-textarea" rows="3"
                            placeholder="History and background of this place…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-loc-tags">Tags</label>
                        <input id="proposal-loc-tags" class="settings-input" placeholder="port, fortress, capital (comma-separated)" />
                    </div>
                    <div class="loc-feature-editor" style="margin-top:var(--space-md)">
                        <label>Features</label>
                        <div id="proposal-loc-feature-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-loc-feature-name" class="settings-input" placeholder="Feature name (e.g. Great Hall)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-loc-feature-type" class="settings-input">
                                    ${LOCATION_FEATURE_TYPES.map(ft => `<option value="${ft}">${ft.charAt(0).toUpperCase() + ft.slice(1)}</option>`).join('')}
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-loc-feature-desc" class="settings-input" placeholder="Feature description…" />
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalLocFeature()">
                            ➕ Add Feature
                        </button>
                    </div>
                </div>

                <!-- Item-specific fields (shown when category=item) -->
                <div id="proposal-item-fields" class="location-fields-panel" style="display:none">
                    <div class="loc-fields-header">📦 Item Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-item-name">Item Name</label>
                            <input id="proposal-item-name" class="settings-input" placeholder="e.g. Starfall Blade" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-rarity">Rarity</label>
                            <select id="proposal-item-rarity" class="settings-input">
                                <option value="common">Common</option>
                                <option value="uncommon">Uncommon</option>
                                <option value="rare">Rare</option>
                                <option value="epic">Epic</option>
                                <option value="legendary">Legendary</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-tier">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required)</span></label>
                            <select id="proposal-item-tier" class="settings-input">
                                <option value="">-- Select Tier --</option>
                                ${ITEM_TIERS.map(t => `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                        </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-legality">Legality</label>
                            <select id="proposal-item-legality" class="settings-input">
                                <option value="">-- Select Legality --</option>
                                ${ITEM_LEGALITY.map(l => `<option value="${l}">${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-item-lore">Lore</label>
                        <textarea id="proposal-item-lore" class="settings-input proposal-textarea" rows="3"
                            placeholder="History and origin of this item…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-item-tags">Tags</label>
                        <input id="proposal-item-tags" class="settings-input" placeholder="weapon, legendary, enchanted (comma-separated)" />
                    </div>
                    <div class="loc-feature-editor" style="margin-top:var(--space-md)">
                        <label>Properties</label>
                        <div id="proposal-item-property-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-item-property-name" class="settings-input" placeholder="Property name (e.g. Fire Enchantment)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-item-property-type" class="settings-input">
                                    ${ITEM_PROPERTY_TYPES.map(pt => `<option value="${pt}">${pt.charAt(0).toUpperCase() + pt.slice(1)}</option>`).join('')}
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-item-property-desc" class="settings-input" placeholder="Property description…" />
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalItemProperty()">
                            ➕ Add Property
                        </button>
                    </div>
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

// ── Category Fields Toggle & Traits/Features for Proposal ────

let proposalCharTraits = [];
let proposalLocFeatures = [];
let proposalItemProperties = [];

function toggleProposalCategoryFields() {
    const cat = document.getElementById('proposal-category-select').value;
    const charPanel = document.getElementById('proposal-char-fields');
    const locPanel = document.getElementById('proposal-loc-fields');
    const itemPanel = document.getElementById('proposal-item-fields');
    const hint = document.getElementById('proposal-desc-hint');
    const descEl = document.getElementById('proposal-desc-input');

    // Hide all category panels first
    if (charPanel) charPanel.style.display = 'none';
    if (locPanel) locPanel.style.display = 'none';
    if (itemPanel) itemPanel.style.display = 'none';
    if (hint) hint.textContent = '';
    if (descEl) descEl.placeholder = 'Describe the proposal and its goals…';

    if (cat === 'character') {
        if (charPanel) charPanel.style.display = 'block';
        if (hint) hint.textContent = '(character description / background)';
        if (descEl) descEl.placeholder = 'Describe the character — this becomes the character description…';
    } else if (cat === 'location') {
        if (locPanel) locPanel.style.display = 'block';
        if (hint) hint.textContent = '(location description)';
        if (descEl) descEl.placeholder = 'Describe the location — this becomes the location description…';
    } else if (cat === 'item') {
        if (itemPanel) itemPanel.style.display = 'block';
        if (hint) hint.textContent = '(item description)';
        if (descEl) descEl.placeholder = 'Describe the item — this becomes the item description…';
    }
}

// Keep old name as alias for backward compatibility
function toggleProposalCharFields() { toggleProposalCategoryFields(); }

// ── Location Feature Editor for Proposal ─────────────────────

function addProposalLocFeature() {
    const nameEl = document.getElementById('proposal-loc-feature-name');
    const name = nameEl.value.trim();
    const featureType = document.getElementById('proposal-loc-feature-type').value;
    const desc = document.getElementById('proposal-loc-feature-desc').value.trim();
    if (!name) { nameEl.focus(); return; }
    if (proposalLocFeatures.some(f => f.name.toLowerCase() === name.toLowerCase())) {
        showToast('Feature with that name already added', true);
        return;
    }
    proposalLocFeatures.push({ name, description: desc || name, feature_type: featureType });
    nameEl.value = '';
    document.getElementById('proposal-loc-feature-desc').value = '';
    renderProposalLocFeatures();
}

function removeProposalLocFeature(index) {
    proposalLocFeatures.splice(index, 1);
    renderProposalLocFeatures();
}

function renderProposalLocFeatures() {
    const container = document.getElementById('proposal-loc-feature-list');
    if (!container) return;
    if (!proposalLocFeatures.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalLocFeatures.map((f, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(f.name)}</span>
            <span class="specialty-tag">${f.feature_type}</span>
            <span class="trait-desc-small">${escapeHtml(f.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalLocFeature(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

// ── Item Property Editor for Proposal ────────────────────────

function addProposalItemProperty() {
    const nameEl = document.getElementById('proposal-item-property-name');
    const name = nameEl.value.trim();
    const propertyType = document.getElementById('proposal-item-property-type').value;
    const desc = document.getElementById('proposal-item-property-desc').value.trim();
    if (!name) { nameEl.focus(); return; }
    if (proposalItemProperties.some(p => p.name.toLowerCase() === name.toLowerCase())) {
        showToast('Property with that name already added', true);
        return;
    }
    proposalItemProperties.push({ name, description: desc || name, property_type: propertyType });
    nameEl.value = '';
    document.getElementById('proposal-item-property-desc').value = '';
    renderProposalItemProperties();
}

function removeProposalItemProperty(index) {
    proposalItemProperties.splice(index, 1);
    renderProposalItemProperties();
}

function renderProposalItemProperties() {
    const container = document.getElementById('proposal-item-property-list');
    if (!container) return;
    if (!proposalItemProperties.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalItemProperties.map((p, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(p.name)}</span>
            <span class="specialty-tag">${p.property_type}</span>
            <span class="trait-desc-small">${escapeHtml(p.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalItemProperty(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

function updateProposalCharModelField() {
    const provider = document.getElementById('proposal-char-provider').value;
    const container = document.getElementById('proposal-char-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('proposal-char-model', provider, '', true);
}

function addProposalCharTrait() {
    const nameEl = document.getElementById('proposal-char-trait-name');
    const name = nameEl.value.trim();
    const traitType = document.getElementById('proposal-char-trait-type').value;
    const desc = document.getElementById('proposal-char-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('proposal-char-trait-intensity').value);
    if (!name) { nameEl.focus(); return; }
    if (proposalCharTraits.some(t => t.name.toLowerCase() === name.toLowerCase())) {
        showToast('Trait with that name already added', true);
        return;
    }
    proposalCharTraits.push({ trait_type: traitType, name, description: desc || name, intensity });
    nameEl.value = '';
    document.getElementById('proposal-char-trait-desc').value = '';
    document.getElementById('proposal-char-trait-intensity').value = '0.5';
    document.getElementById('proposal-char-trait-intensity-val').textContent = '0.5';
    renderProposalCharTraits();
}

function removeProposalCharTrait(index) {
    proposalCharTraits.splice(index, 1);
    renderProposalCharTraits();
}

function renderProposalCharTraits() {
    const container = document.getElementById('proposal-char-trait-list');
    if (!container) return;
    if (!proposalCharTraits.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalCharTraits.map((t, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <span class="trait-intensity">${Math.round(t.intensity * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalCharTrait(${i})" title="Remove">🗑️</button>
        </div>`).join('');
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

    // Build character_data if category is character
    let character_data = null;
    if (category === 'character') {
        const charName = (document.getElementById('proposal-char-name').value || '').trim();
        const backstory = (document.getElementById('proposal-char-backstory').value || '').trim();
        const systemPrompt = (document.getElementById('proposal-char-prompt').value || '').trim();
        const greeting = (document.getElementById('proposal-char-greeting').value || '').trim();
        const tagsRaw = (document.getElementById('proposal-char-tags').value || '').trim();
        const examplesRaw = (document.getElementById('proposal-char-examples').value || '').trim();
        const provider = document.getElementById('proposal-char-provider').value;
        const model = document.getElementById('proposal-char-model').value;

        // Collect any unsaved trait from inputs
        const traitName = (document.getElementById('proposal-char-trait-name').value || '').trim();
        const traits = [...proposalCharTraits];
        if (traitName) {
            traits.push({
                trait_type: document.getElementById('proposal-char-trait-type').value,
                name: traitName,
                description: (document.getElementById('proposal-char-trait-desc').value || '').trim() || traitName,
                intensity: parseFloat(document.getElementById('proposal-char-trait-intensity').value),
            });
        }

        if (!charName) {
            document.getElementById('proposal-char-name').focus();
            status.textContent = 'Character name is required for character proposals';
            return;
        }
        if (!traits.length) {
            document.getElementById('proposal-char-trait-name').focus();
            status.textContent = 'At least one trait is required for character proposals';
            return;
        }

        character_data = {
            name: charName,
            backstory,
            system_prompt: systemPrompt,
            greeting,
            tags: tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            example_messages: examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [],
            traits,
            api_provider: provider,
            model,
        };
    }

    // Build location_data if category is location
    let location_data = null;
    if (category === 'location') {
        const locName = (document.getElementById('proposal-loc-name').value || '').trim();
        const lore = (document.getElementById('proposal-loc-lore').value || '').trim();
        const locTagsRaw = (document.getElementById('proposal-loc-tags').value || '').trim();
        const coordinates = (document.getElementById('proposal-loc-coords').value || '').trim();

        // Collect any unsaved feature from inputs
        const featName = (document.getElementById('proposal-loc-feature-name').value || '').trim();
        const features = [...proposalLocFeatures];
        if (featName) {
            features.push({
                name: featName,
                description: (document.getElementById('proposal-loc-feature-desc').value || '').trim() || featName,
                feature_type: document.getElementById('proposal-loc-feature-type').value,
            });
        }

        if (!locName) {
            document.getElementById('proposal-loc-name').focus();
            status.textContent = 'Location name is required for location proposals';
            return;
        }

        location_data = {
            name: locName,
            description: description,
            lore,
            tags: locTagsRaw ? locTagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            coordinates,
            features,
        };
    }

    // Build item_data if category is item
    let item_data = null;
    if (category === 'item') {
        const itemName = (document.getElementById('proposal-item-name').value || '').trim();
        const lore = (document.getElementById('proposal-item-lore').value || '').trim();
        const itemTagsRaw = (document.getElementById('proposal-item-tags').value || '').trim();
        const rarity = document.getElementById('proposal-item-rarity').value;
        const tier = document.getElementById('proposal-item-tier').value;
        const legality = document.getElementById('proposal-item-legality').value;

        // Collect any unsaved property from inputs
        const propName = (document.getElementById('proposal-item-property-name').value || '').trim();
        const properties = [...proposalItemProperties];
        if (propName) {
            properties.push({
                name: propName,
                description: (document.getElementById('proposal-item-property-desc').value || '').trim() || propName,
                property_type: document.getElementById('proposal-item-property-type').value,
            });
        }

        if (!itemName) {
            document.getElementById('proposal-item-name').focus();
            status.textContent = 'Item name is required for item proposals';
            return;
        }

        if (!tier) {
            document.getElementById('proposal-item-tier').focus();
            status.textContent = 'Tier is required for item proposals';
            return;
        }

        item_data = {
            name: itemName,
            description: description,
            lore,
            tags: itemTagsRaw ? itemTagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            rarity,
            tier,
            legality,
            properties,
        };
    }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = 'Creating proposal and opening discussion…';

    try {
        const payload = { author, title, description, category };
        if (character_data) payload.character_data = character_data;
        if (location_data) payload.location_data = location_data;
        if (item_data) payload.item_data = item_data;

        const resp = await fetch('/api/proposals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create proposal' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        proposalCharTraits = [];  // Reset
        proposalLocFeatures = [];  // Reset
        proposalItemProperties = [];  // Reset
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
    const isReviewing = data.status === 'open_to_review';

    // Lifecycle progress bar
    const stages = ['draft', 'open', 'open_to_review', 'under_review', 'decided'];
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
                const labels = { draft: 'Draft', open: 'Open', open_to_review: 'Reviewing', under_review: 'Review', decided: 'Decided' };
                return `<div class="${cls}"><span class="lifecycle-dot"></span><span class="lifecycle-label">${labels[s]}</span></div>`;
            }).join('<div class="lifecycle-connector"></div>')}
            ${isWithdrawn ? '<div class="lifecycle-connector"></div><div class="lifecycle-step lifecycle-active lifecycle-withdrawn"><span class="lifecycle-dot"></span><span class="lifecycle-label">Withdrawn</span></div>' : ''}
        </div>`;

    // Discussion feed
    let discussionFeedHtml = '';
    if (hasDiscussion && discussion.contributions && discussion.contributions.length) {
        const contribs = discussion.contributions.map(c => {
            const memberIdx = (discussion.participants || []).indexOf(c.speaker);
            const renderedContent = renderMarkdown(c.content);
            const displayContent = state.silentpassaEnabled ? wrapPresenceContent(renderedContent, c.speaker) : renderedContent;
            return `
            <div class="discussion-message">
                <div class="discussion-message-header">
                    ${memberAvatarWithImage(c.speaker, memberIdx >= 0 ? memberIdx : 0, null, state.proposalAvatarMap && state.proposalAvatarMap[c.speaker.toLowerCase()])}
                    <div>
                        <span class="discussion-speaker">${c.speaker}</span>
                        <span class="discussion-round">Round ${c.round_number}</span>
                    </div>
                </div>
                <div class="discussion-content">${displayContent}</div>
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
        if (discussionOpen && data.status === 'open') {
            buttons.push(`<button class="btn" onclick="sendToReview('${id}')" id="send-review-btn" style="background:linear-gradient(135deg, hsl(45,80%,50%), hsl(35,70%,45%));color:#fff">📝 Send to Review</button>`);
        }
        if (!hasVote && (data.status === 'open' || data.status === 'under_review' || data.status === 'open_to_review')) {
            buttons.push(`<button class="btn btn-accent" onclick="callProposalVote('${id}')" id="vote-btn">🗳️ Call Vote</button>`);
        }
        if (data.status !== 'decided') {
            buttons.push(`<button class="btn btn-danger-outline" onclick="withdrawProposal('${id}','${escapeAttr(data.author)}')" id="withdraw-btn">↩️ Withdraw</button>`);
        }
        if (buttons.length) {
            actionsHtml = `<div class="proposal-actions">${buttons.join('')}</div>`;
        }
    }

    // Scheduled message section (only when discussion is open)
    let scheduledMsgHtml = '';
    if (discussionOpen) {
        let existingMsg = '';
        try {
            const smResp = await api(`/api/proposals/${encodeURIComponent(id)}/scheduled-message`);
            if (smResp && smResp.message) existingMsg = smResp.message;
        } catch { /* no scheduled message */ }

        scheduledMsgHtml = `
            <div class="detail-section scheduled-message-section">
                <h4>📨 Schedule Message for Next Round</h4>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-sm)">
                    This message will be injected into the discussion at the start of the next round, before the council members speak.
                </p>
                <textarea id="scheduled-msg-input" class="settings-input scheduled-message-textarea"
                    rows="3" placeholder="Type your message for the council to consider…">${existingMsg ? escapeHtml(existingMsg) : ''}</textarea>
                <div style="display:flex;gap:var(--space-sm);align-items:center;margin-top:var(--space-sm)">
                    <button class="btn btn-primary btn-sm" onclick="scheduleDiscussionMessage('${id}')" id="schedule-msg-btn">
                        📨 Schedule Message
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="clearScheduledMessage('${id}')" id="clear-msg-btn">
                        🗑️ Clear
                    </button>
                    <span id="scheduled-msg-status" style="font-size:0.78rem;color:var(--text-muted)">
                        ${existingMsg ? '✅ Message scheduled' : ''}
                    </span>
                </div>
            </div>`;
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
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPass('proposals','${id}')" title="Toggle [PRESENT]/[SILENCE] wrappers">
                            ${state.silentpassaEnabled ? '🔔 SilentPass' : '🔕 SilentPass'}
                        </button>
                        <button class="detail-close" onclick="navigateTo('proposals')">✕</button>
                    </div>
                </div>

                ${lifecycleHtml}
                ${actionsHtml}
                ${scheduledMsgHtml}

                ${isReviewing ? _buildFinalProposalForm(data) : ''}

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
                ${(data.category === 'character' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section character-handoff-banner">
                        <h4>🎭 Character Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This character proposal has been <strong>approved</strong> by the council. Create a draft character from the proposal data to continue development in the Characters section.</p>
                        <button class="btn btn-primary" onclick="handoffCharacterProposal('${data.id}')" id="char-handoff-btn" style="background:linear-gradient(135deg, hsl(200,70%,50%), hsl(170,60%,45%))">
                            🎭 Create Draft Character
                        </button>
                    </div>` : ''}
                ${(data.category === 'location' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section location-handoff-banner">
                        <h4>🌍 Location Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This location proposal has been <strong>approved</strong> by the council. Create a draft location from the proposal data to continue development in the Locations section.</p>
                        <button class="btn btn-primary" onclick="handoffLocationProposal('${data.id}')" id="loc-handoff-btn" style="background:linear-gradient(135deg, hsl(160,60%,45%), hsl(140,55%,40%))">
                            🌍 Create Draft Location
                        </button>
                    </div>` : ''}
                ${(data.category === 'item' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section item-handoff-banner">
                        <h4>📦 Item Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This item proposal has been <strong>approved</strong> by the council. Create a draft item from the proposal data to continue development in the Items section.</p>
                        <button class="btn btn-primary" onclick="handoffItemProposal('${data.id}')" id="item-handoff-btn" style="background:linear-gradient(135deg, hsl(30,70%,50%), hsl(40,80%,55%))">
                            📦 Create Draft Item
                        </button>
                    </div>` : ''}
                ${(data.category === 'law' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section law-handoff-banner">
                        <h4>⚖️ Law Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This law proposal has been <strong>approved</strong> by the council. Create a draft law from the proposal data to continue development in the Laws section.</p>
                        <button class="btn btn-primary" onclick="handoffLawProposal('${data.id}')" id="law-handoff-btn" style="background:linear-gradient(135deg, hsl(220,60%,50%), hsl(200,55%,45%))">
                            ⚖️ Create Draft Law
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
                            const isUser = data.speaker === 'User';
                            const msgDiv = document.createElement('div');
                            msgDiv.className = `discussion-message discussion-message-enter${isUser ? ' discussion-message-user' : ''}`;
                            msgDiv.innerHTML = `
                                <div class="discussion-message-header">
                                    ${isUser
                                        ? `<div class="member-avatar" style="background:linear-gradient(135deg, hsl(45,80%,55%), hsl(35,90%,50%))">👤</div>`
                                        : memberAvatarWithImage(data.speaker, 0, null, state.proposalAvatarMap && state.proposalAvatarMap[data.speaker.toLowerCase()])}
                                    <div>
                                        <span class="discussion-speaker">${data.speaker}</span>
                                        <span class="discussion-round">Round ${data.round}</span>
                                    </div>
                                </div>
                                <div class="discussion-content">${state.silentpassaEnabled ? wrapPresenceContent(renderMarkdown(data.content), data.speaker) : renderMarkdown(data.content)}</div>`;
                            feed.appendChild(msgDiv);
                            feed.scrollTop = feed.scrollHeight;

                            // Clear scheduled message status after it's been consumed
                            if (isUser) {
                                const statusEl = document.getElementById('scheduled-msg-status');
                                if (statusEl) statusEl.textContent = '✅ Delivered this round';
                                const inputEl = document.getElementById('scheduled-msg-input');
                                if (inputEl) inputEl.value = '';
                            }
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

async function scheduleDiscussionMessage(proposalId) {
    const input = document.getElementById('scheduled-msg-input');
    const message = (input && input.value || '').trim();
    if (!message) { if (input) input.focus(); return; }

    const btn = document.getElementById('schedule-msg-btn');
    const status = document.getElementById('scheduled-msg-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/scheduled-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to schedule' }));
            throw new Error(err.detail);
        }
        showToast('Message scheduled for next round 📨');
        if (status) status.textContent = '✅ Message scheduled';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📨 Schedule Message'; }
    }
}

async function clearScheduledMessage(proposalId) {
    const btn = document.getElementById('clear-msg-btn');
    const status = document.getElementById('scheduled-msg-status');
    const input = document.getElementById('scheduled-msg-input');
    if (btn) { btn.disabled = true; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/scheduled-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '' }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to clear' }));
            throw new Error(err.detail);
        }
        if (input) input.value = '';
        if (status) status.textContent = '';
        showToast('Scheduled message cleared 🗑️');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; }
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

// ── Send to Review ──────────────────────────────────────────

async function sendToReview(proposalId) {
    const btn = document.getElementById('send-review-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Sending to review…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/send-to-review`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to send to review' }));
            throw new Error(err.detail);
        }
        showToast('Proposal sent to review — prepare the final version 📝');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📝 Send to Review'; }
    }
}

// ── Final Proposal Form Builder ─────────────────────────────

let _finalProposalTraits = [];
let _finalProposalFeatures = [];
let _finalProposalProperties = [];

function _buildFinalProposalForm(data) {
    const meta = data.metadata || {};
    const cat = data.category;

    // Character-specific
    let charFieldsHtml = '';
    if (cat === 'character') {
        const cd = meta.character_data || {};
        _finalProposalTraits = cd.traits || [];
        charFieldsHtml = `
            <div class="char-fields-header" style="margin-top:var(--space-md)">🎭 Character Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-char-name">Character Name</label>
                    <input id="fp-char-name" class="settings-input" value="${escapeAttr(cd.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-char-provider">API Provider</label>
                    <select id="fp-char-provider" class="settings-input">
                        <option value="openrouter" ${(cd.api_provider || '') === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                        <option value="mancer" ${(cd.api_provider || '') === 'mancer' ? 'selected' : ''}>Mancer</option>
                        <option value="lmstudio" ${(cd.api_provider || '') === 'lmstudio' ? 'selected' : ''}>LM Studio</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-char-model">Model</label>
                    <input id="fp-char-model" class="settings-input" value="${escapeAttr(cd.model || 'Default')}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-backstory">Backstory</label>
                <textarea id="fp-char-backstory" class="settings-input proposal-textarea" rows="3">${escapeHtml(cd.backstory || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-prompt">System Prompt</label>
                <textarea id="fp-char-prompt" class="settings-input proposal-textarea" rows="3">${escapeHtml(cd.system_prompt || '')}</textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-char-greeting">Greeting</label>
                    <input id="fp-char-greeting" class="settings-input" value="${escapeAttr(cd.greeting || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-char-tags">Tags</label>
                    <input id="fp-char-tags" class="settings-input" value="${escapeAttr((cd.tags || []).join(', '))}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-examples">Example Messages</label>
                <textarea id="fp-char-examples" class="settings-input proposal-textarea" rows="2">${escapeHtml((cd.example_messages || []).join('\n'))}</textarea>
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Traits</label>
                <div id="fp-char-trait-list">
                    ${_finalProposalTraits.map((t, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(t.name)}</span>
                            <span class="specialty-tag">${t.trait_type || 'personality'}</span>
                            <span class="trait-intensity">${Math.round((t.intensity || 0.5) * 100)}%</span>
                            <span class="trait-desc-small">${escapeHtml(t.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    // Location-specific
    let locFieldsHtml = '';
    if (cat === 'location') {
        const ld = meta.location_data || {};
        _finalProposalFeatures = ld.features || [];
        locFieldsHtml = `
            <div class="loc-fields-header" style="margin-top:var(--space-md)">🌍 Location Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-loc-name">Location Name</label>
                    <input id="fp-loc-name" class="settings-input" value="${escapeAttr(ld.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-loc-coords">Coordinates</label>
                    <input id="fp-loc-coords" class="settings-input" value="${escapeAttr(ld.coordinates || '')}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-loc-lore">Lore</label>
                <textarea id="fp-loc-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(ld.lore || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-loc-tags">Tags</label>
                <input id="fp-loc-tags" class="settings-input" value="${escapeAttr((ld.tags || []).join(', '))}" />
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Features</label>
                <div id="fp-loc-feature-list">
                    ${_finalProposalFeatures.map((f, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(f.name)}</span>
                            <span class="specialty-tag">${f.feature_type || 'custom'}</span>
                            <span class="trait-desc-small">${escapeHtml(f.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    // Item-specific
    let itemFieldsHtml = '';
    if (cat === 'item') {
        const id = meta.item_data || {};
        _finalProposalProperties = id.properties || [];
        itemFieldsHtml = `
            <div class="loc-fields-header" style="margin-top:var(--space-md)">📦 Item Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-item-name">Item Name</label>
                    <input id="fp-item-name" class="settings-input" value="${escapeAttr(id.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-item-rarity">Rarity</label>
                    <select id="fp-item-rarity" class="settings-input">
                        ${['common','uncommon','rare','epic','legendary'].map(r =>
                            `<option value="${r}" ${(id.rarity || '') === r ? 'selected' : ''}>${r.charAt(0).toUpperCase() + r.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-item-tier">Tier</label>
                    <select id="fp-item-tier" class="settings-input">
                        ${['permanent','consumable','degradable'].map(t =>
                            `<option value="${t}" ${(id.tier || '') === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-item-legality">Legality</label>
                    <select id="fp-item-legality" class="settings-input">
                        ${['contraband','legal'].map(l =>
                            `<option value="${l}" ${(id.legality || '') === l ? 'selected' : ''}>${l.charAt(0).toUpperCase() + l.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-item-lore">Lore</label>
                <textarea id="fp-item-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(id.lore || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-item-tags">Tags</label>
                <input id="fp-item-tags" class="settings-input" value="${escapeAttr((id.tags || []).join(', '))}" />
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Properties</label>
                <div id="fp-item-property-list">
                    ${_finalProposalProperties.map((p, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(p.name)}</span>
                            <span class="specialty-tag">${p.property_type || 'custom'}</span>
                            <span class="trait-desc-small">${escapeHtml(p.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    return `
        <div class="detail-section" style="border:2px solid var(--accent-amber);border-radius:var(--radius-lg);padding:var(--space-lg);background:rgba(245,158,11,0.05)">
            <h4 style="margin-bottom:var(--space-xs)">📝 Final Proposal</h4>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Review the discussion and edit the proposal to reflect the council's consensus before calling a vote.
                This is the version the council will vote on.
            </p>
            <div class="filter-group">
                <label for="fp-title">Title</label>
                <input id="fp-title" class="settings-input" value="${escapeAttr(data.title)}" />
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-description">Description</label>
                <textarea id="fp-description" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.description)}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-body">Body</label>
                <textarea id="fp-body" class="settings-input proposal-textarea" rows="4">${escapeHtml(data.body || '')}</textarea>
            </div>

            ${charFieldsHtml}
            ${locFieldsHtml}
            ${itemFieldsHtml}

            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="saveFinalProposal('${data.id}')" id="fp-save-btn">
                    💾 Save Final Proposal
                </button>
                <span id="fp-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;
}

// ── Save Final Proposal ─────────────────────────────────────

async function saveFinalProposal(proposalId) {
    const btn = document.getElementById('fp-save-btn');
    const status = document.getElementById('fp-save-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const title = (document.getElementById('fp-title')?.value || '').trim();
        const description = (document.getElementById('fp-description')?.value || '').trim();
        const body = (document.getElementById('fp-body')?.value || '').trim();

        if (!title) { document.getElementById('fp-title')?.focus(); throw new Error('Title is required'); }
        if (!description) { document.getElementById('fp-description')?.focus(); throw new Error('Description is required'); }

        // Build updated metadata from category-specific fields
        let metadata = null;

        // Character
        const charNameEl = document.getElementById('fp-char-name');
        if (charNameEl) {
            metadata = { character_data: {
                name: charNameEl.value.trim(),
                api_provider: document.getElementById('fp-char-provider')?.value || 'openrouter',
                model: (document.getElementById('fp-char-model')?.value || 'Default').trim(),
                backstory: (document.getElementById('fp-char-backstory')?.value || '').trim(),
                system_prompt: (document.getElementById('fp-char-prompt')?.value || '').trim(),
                greeting: (document.getElementById('fp-char-greeting')?.value || '').trim(),
                tags: (document.getElementById('fp-char-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                example_messages: (document.getElementById('fp-char-examples')?.value || '').split('\n').map(l => l.trim()).filter(Boolean),
                traits: _finalProposalTraits,
            }};
        }

        // Location
        const locNameEl = document.getElementById('fp-loc-name');
        if (locNameEl) {
            metadata = { location_data: {
                name: locNameEl.value.trim(),
                description: description,
                lore: (document.getElementById('fp-loc-lore')?.value || '').trim(),
                tags: (document.getElementById('fp-loc-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                coordinates: (document.getElementById('fp-loc-coords')?.value || '').trim(),
                features: _finalProposalFeatures,
            }};
        }

        // Item
        const itemNameEl = document.getElementById('fp-item-name');
        if (itemNameEl) {
            metadata = { item_data: {
                name: itemNameEl.value.trim(),
                description: description,
                lore: (document.getElementById('fp-item-lore')?.value || '').trim(),
                tags: (document.getElementById('fp-item-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                rarity: document.getElementById('fp-item-rarity')?.value || '',
                tier: document.getElementById('fp-item-tier')?.value || '',
                legality: document.getElementById('fp-item-legality')?.value || '',
                properties: _finalProposalProperties,
            }};
        }

        const payload = { title, description, body };
        if (metadata) payload.metadata = metadata;

        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/final-proposal`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to save' }));
            throw new Error(err.detail);
        }
        showToast('Final proposal saved 💾');
        if (status) status.textContent = '✅ Saved';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (status) status.textContent = '';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Final Proposal'; }
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

async function handoffCharacterProposal(proposalId) {
    const btn = document.getElementById('char-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating character…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-character`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft character "${data.name}" created ✅`);
        navigateTo('characters', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🎭 Create Draft Character'; }
    }
}

async function handoffLocationProposal(proposalId) {
    const btn = document.getElementById('loc-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating location…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-location`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft location "${data.name}" created ✅`);
        navigateTo('locations', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🌍 Create Draft Location'; }
    }
}

async function handoffItemProposal(proposalId) {
    const btn = document.getElementById('item-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating item…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-item`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft item "${data.name}" created ✅`);
        navigateTo('items', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📦 Create Draft Item'; }
    }
}

async function handoffLawProposal(proposalId) {
    const btn = document.getElementById('law-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating law…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-law`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft law "${data.title}" created ✅`);
        navigateTo('laws', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⚖️ Create Draft Law'; }
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

    const votesHtml = (data.votes || []).map(v => {
        const reasonText = v.reason || '—';
        const renderedReason = renderMarkdown(reasonText);
        const displayReason = state.silentpassaEnabled ? wrapPresenceContent(renderedReason, v.voter) : renderedReason;
        return `
        <div class="vote-item">
            <span class="vote-voter">${v.voter}</span>
            ${badge(v.choice)}
            <span class="vote-reason">${displayReason}</span>
            <span class="vote-weight">w:${v.weight}</span>
        </div>`;
    }).join('');

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
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPass('votes','${data.proposal_id}')" title="Toggle [PRESENT]/[SILENCE] wrappers">
                            ${state.silentpassaEnabled ? '🔔 SilentPass' : '🔕 SilentPass'}
                        </button>
                        <button class="detail-close" onclick="navigateTo('votes')">✕</button>
                    </div>
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
// Entity Image Gallery (F-037e)
// ═══════════════════════════════════════════════════════════════

let _galleryImages = [];       // Current gallery image list
let _galleryEntityType = '';
let _galleryEntityId = '';

/**
 * Render an image gallery panel for any entity type.
 * Returns an HTML string to inject into a detail page.
 */
async function renderImageGallery(entityType, entityId) {
    _galleryEntityType = entityType;
    _galleryEntityId = entityId;

    try {
        const images = await api(`/api/images/${entityType}/${encodeURIComponent(entityId)}`);
        _galleryImages = images;
    } catch {
        _galleryImages = [];
    }

    const thumbs = _galleryImages.map((img, idx) => {
        const primaryBadge = img.is_primary
            ? '<div class="gallery-primary-badge">⭐ Primary</div>'
            : '';

        const promptIndicator = img.prompt
            ? `<div class="gallery-prompt-indicator" title="View prompt info">ℹ
                 <div class="gallery-prompt-tooltip">
                     <strong>Prompt</strong>${escapeHtml(img.prompt)}
                     ${img.negative_prompt ? `<strong>Negative</strong>${escapeHtml(img.negative_prompt)}` : ''}
                     ${img.template_id ? `<strong>Template</strong>${escapeHtml(img.template_id)}` : ''}
                 </div>
               </div>`
            : '';

        const actions = `
            <div class="gallery-actions">
                ${!img.is_primary ? `<button class="gallery-action-btn gallery-action-primary" onclick="event.stopPropagation(); gallerySetPrimary('${img.id}')" title="Set as primary">⭐</button>` : ''}
                <button class="gallery-action-btn" onclick="event.stopPropagation(); galleryDownload('${img.id}')" title="Download">⬇</button>
                <button class="gallery-action-btn gallery-action-delete" onclick="event.stopPropagation(); galleryDelete('${img.id}')" title="Delete">🗑️</button>
            </div>`;

        return `
            <div class="gallery-thumb" onclick="openGalleryLightbox(${idx})">
                ${primaryBadge}
                ${promptIndicator}
                <img src="${img.url}" alt="Image ${img.id}" loading="lazy" />
                ${actions}
            </div>`;
    }).join('');

    const uploadZone = `
        <div class="gallery-upload-zone" id="gallery-upload-zone"
             onclick="openGalleryUpload('${entityType}', '${escapeAttr(entityId)}')"
             title="Upload a new image">
            <div class="gallery-upload-icon">📁</div>
            <span>Upload</span>
        </div>`;

    return `
        <div class="image-gallery detail-section" id="entity-gallery">
            <div class="gallery-header">
                <h4>🖼️ Image Gallery (${_galleryImages.length})</h4>
                <button class="btn btn-sm btn-generate" onclick="openGenerateModal('${entityType}', '${escapeAttr(entityId)}')" title="Generate a new image with AI">
                    🎨 Generate Image
                </button>
            </div>
            <div class="gallery-grid">
                ${thumbs}
                ${uploadZone}
            </div>
            <div id="generate-progress-inline"></div>
        </div>`;
}

/* ── Lightbox ────────────────────────────────────────────────── */

function openGalleryLightbox(index) {
    if (!_galleryImages.length) return;
    if (index < 0) index = _galleryImages.length - 1;
    if (index >= _galleryImages.length) index = 0;

    const img = _galleryImages[index];
    const overlay = document.createElement('div');
    overlay.className = 'gallery-lightbox';
    overlay.id = 'gallery-lightbox';
    overlay.innerHTML = `
        <div class="gallery-lb-content">
            <button class="gallery-lb-close" onclick="closeGalleryLightbox()" title="Close">✕</button>
            ${_galleryImages.length > 1
                ? `<button class="gallery-lb-nav gallery-lb-prev" onclick="navigateGalleryLb(${index - 1})">◀</button>
                   <button class="gallery-lb-nav gallery-lb-next" onclick="navigateGalleryLb(${index + 1})">▶</button>`
                : ''}
            <img src="${img.url}" alt="${img.id}" />
            <div class="gallery-lb-info">
                <span>${img.id} · ${index + 1} / ${_galleryImages.length}${img.is_primary ? ' · ⭐ Primary' : ''}</span>
                <div class="gallery-lb-actions">
                    ${!img.is_primary ? `<button class="gallery-lb-action-btn" onclick="gallerySetPrimary('${img.id}')">⭐ Set Primary</button>` : ''}
                    <button class="gallery-lb-action-btn" onclick="galleryDownload('${img.id}')">⬇ Download</button>
                    <button class="gallery-lb-action-btn" onclick="galleryDelete('${img.id}')">🗑️ Delete</button>
                </div>
            </div>
            ${img.prompt ? `<div style="color:rgba(255,255,255,0.5);font-size:0.75rem;max-width:600px;text-align:center;margin-top:var(--space-xs)">
                <strong style="color:rgba(255,255,255,0.7)">Prompt:</strong> ${escapeHtml(img.prompt)}
            </div>` : ''}
        </div>`;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeGalleryLightbox();
    });
    document.body.appendChild(overlay);

    // Keyboard navigation
    overlay._keyHandler = (e) => {
        if (e.key === 'Escape') closeGalleryLightbox();
        if (e.key === 'ArrowLeft') navigateGalleryLb(index - 1);
        if (e.key === 'ArrowRight') navigateGalleryLb(index + 1);
    };
    document.addEventListener('keydown', overlay._keyHandler);
}

function closeGalleryLightbox() {
    const lb = document.getElementById('gallery-lightbox');
    if (lb) {
        if (lb._keyHandler) document.removeEventListener('keydown', lb._keyHandler);
        lb.remove();
    }
}

function navigateGalleryLb(index) {
    closeGalleryLightbox();
    openGalleryLightbox(index);
}

/* ── Upload Modal ────────────────────────────────────────────── */

let _galleryUploadData = null;

function openGalleryUpload(entityType, entityId) {
    _galleryUploadData = null;
    const modal = document.createElement('div');
    modal.className = 'gallery-upload-modal';
    modal.id = 'gallery-upload-modal';
    modal.innerHTML = `
        <div class="gallery-upload-modal-content">
            <h3>📁 Upload Image — ${entityType}/${entityId}</h3>
            <div class="gallery-upload-drop" id="gallery-upload-drop"
                 onclick="document.getElementById('gallery-file-input').click()">
                <input type="file" id="gallery-file-input" accept="image/png,image/jpeg,image/webp"
                       style="display:none" onchange="handleGalleryFileSelect(event)" />
                <div class="gallery-upload-icon" style="font-size:2rem;margin-bottom:var(--space-sm)">📁</div>
                <div style="color:var(--text-secondary);font-size:0.85rem">Click or drag an image here</div>
                <div style="color:var(--text-muted);font-size:0.72rem;margin-top:var(--space-xs)">PNG, JPEG, or WebP</div>
                <img id="gallery-upload-preview-img" class="gallery-upload-preview" />
            </div>
            <div class="gallery-upload-footer">
                <button class="btn btn-secondary" onclick="closeGalleryUpload()">Cancel</button>
                <button class="btn btn-primary" id="gallery-upload-save-btn"
                        onclick="submitGalleryUpload('${entityType}', '${escapeAttr(entityId)}')" disabled>
                    📤 Upload
                </button>
            </div>
        </div>`;

    // Drag and drop
    setTimeout(() => {
        const drop = document.getElementById('gallery-upload-drop');
        if (drop) {
            drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('gallery-drag-over'); };
            drop.ondragleave = () => drop.classList.remove('gallery-drag-over');
            drop.ondrop = (e) => {
                e.preventDefault();
                drop.classList.remove('gallery-drag-over');
                const file = e.dataTransfer.files[0];
                if (file) loadGalleryFile(file);
            };
        }
    }, 50);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeGalleryUpload();
    });
    document.body.appendChild(modal);
}

function closeGalleryUpload() {
    const m = document.getElementById('gallery-upload-modal');
    if (m) m.remove();
    _galleryUploadData = null;
}

function handleGalleryFileSelect(event) {
    const file = event.target.files[0];
    if (file) loadGalleryFile(file);
}

function loadGalleryFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        _galleryUploadData = { dataUrl: e.target.result, filename: file.name };
        const preview = document.getElementById('gallery-upload-preview-img');
        if (preview) {
            preview.src = e.target.result;
            preview.style.display = 'block';
        }
        const btn = document.getElementById('gallery-upload-save-btn');
        if (btn) btn.disabled = false;
    };
    reader.readAsDataURL(file);
}

async function submitGalleryUpload(entityType, entityId) {
    if (!_galleryUploadData) return;
    const btn = document.getElementById('gallery-upload-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading…'; }

    try {
        const resp = await fetch(`/api/images/${entityType}/${encodeURIComponent(entityId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_data: _galleryUploadData.dataUrl,
                original_filename: _galleryUploadData.filename || '',
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        showToast('Image uploaded ✅');
        closeGalleryUpload();
        await refreshGallery();
    } catch (err) {
        showToast(`Upload error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📤 Upload'; }
    }
}

/* ── Gallery Actions ──────────────────────────────────────────── */

async function gallerySetPrimary(imageId) {
    try {
        await fetch(`/api/images/set-primary/${imageId}`, { method: 'POST' });
        showToast('Primary image updated ⭐');
        closeGalleryLightbox();
        await refreshGallery();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function galleryDelete(imageId) {
    if (!confirm('Delete this image?')) return;
    try {
        const resp = await fetch(`/api/images/delete/${imageId}`, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast('Image deleted 🗑️');
        closeGalleryLightbox();
        await refreshGallery();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

function galleryDownload(imageId) {
    const link = document.createElement('a');
    link.href = `/api/images/file/${imageId}`;
    link.download = `${imageId}.png`;
    link.click();
}

/**
 * Re-render just the gallery section without reloading the entire page.
 */
async function refreshGallery() {
    const container = document.getElementById('entity-gallery');
    if (!container || !_galleryEntityType || !_galleryEntityId) return;
    const html = await renderImageGallery(_galleryEntityType, _galleryEntityId);
    container.outerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
// Generation Pipeline & Progress UI (F-037f)
// ═══════════════════════════════════════════════════════════════

let _generateEntityType = '';
let _generateEntityId = '';
let _generateActiveJobId = null;
let _generateEventSource = null;
let _generateMembers = [];

/**
 * Open the AI image generation modal for any entity.
 */
async function openGenerateModal(entityType, entityId) {
    _generateEntityType = entityType;
    _generateEntityId = entityId;

    // Fetch available templates, style presets, and recommended template
    let templates = [];
    let presets = [];
    let members = [];
    let recommendedTemplateId = '';
    let recommendedSource = '';
    try {
        const [tpls, prsts, council, recommended] = await Promise.all([
            api('/api/settings/comfyui/templates').catch(() => []),
            api('/api/settings/comfyui/style-presets').catch(() => []),
            api('/api/council').catch(() => []),
            api(`/api/settings/comfyui/recommended-template/${encodeURIComponent(entityType)}`).catch(() => ({})),
        ]);
        templates = tpls;
        presets = prsts;
        members = council.map ? council.map(m => m.name) : [];
        _generateMembers = members;
        recommendedTemplateId = recommended.template_id || '';
        recommendedSource = recommended.source || '';
    } catch { /* endpoints may not be available */ }

    if (!templates.length) {
        showToast('No ComfyUI workflow templates found. Add one in Settings → ComfyUI first.', true);
        return;
    }

    // Build template options with recommended badge
    const templateOptions = templates.map(t => {
        const isRecommended = t.id === recommendedTemplateId;
        const sel = isRecommended ? 'selected' : '';
        const badge = isRecommended ? ' 📌 Default' : '';
        return `<option value="${escapeAttr(t.id)}" ${sel}>${escapeHtml(t.name || t.id)}${badge}</option>`;
    }).join('');

    const presetOptions = ['<option value="">None (default)</option>'].concat(
        presets.map(p => `<option value="${escapeAttr(p.key)}">${escapeHtml(p.name || p.key)}</option>`)
    ).join('');

    const memberOptions = members.map(m =>
        `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
    ).join('');

    const memberCheckboxes = members.map(m =>
        `<label class="gen-participant-label">
            <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
            ${escapeHtml(m)}
        </label>`
    ).join('');

    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'gen-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal">
            <div class="gen-modal-header">
                <h3>🎨 Generate Image — ${escapeHtml(entityType)}/${escapeHtml(entityId)}</h3>
                <button class="detail-close" onclick="closeGenerateModal()">✕</button>
            </div>

            <div class="gen-modal-body" id="gen-modal-body">
                <div class="gen-form-grid">
                    <div class="filter-group">
                        <label for="gen-template">Workflow Template</label>
                        <select id="gen-template" class="settings-input">${templateOptions}</select>
                    </div>
                    <div class="filter-group">
                        <label for="gen-style">Style Preset</label>
                        <select id="gen-style" class="settings-input">${presetOptions}</select>
                    </div>
                </div>

                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="gen-mode">Prompt Mode</label>
                    <select id="gen-mode" class="settings-input" onchange="updateGenModeFields()">
                        <option value="system">System — AI generates from entity context</option>
                        <option value="character">Character — A council member describes</option>
                        <option value="raw_user">Raw User — Your own prompt text</option>
                        <option value="user_refined">User Refined — Your prompt, refined by a member</option>
                        <option value="council_vote">Council Vote — Multiple members propose prompts</option>
                    </select>
                </div>

                <!-- Dynamic mode fields -->
                <div id="gen-mode-fields"></div>

                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="gen-width">Width</label>
                        <input id="gen-width" class="settings-input" type="number" value="512" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="gen-height">Height</label>
                        <input id="gen-height" class="settings-input" type="number" value="512" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="gen-seed">Seed <span style="color:var(--text-muted);font-size:0.72rem">(0 = random)</span></label>
                        <input id="gen-seed" class="settings-input" type="number" value="0" min="0" />
                    </div>
                </div>

                <!-- Council vote prompts preview area -->
                <div id="gen-prompts-preview" style="display:none"></div>

                <!-- Progress area (shown during generation) -->
                <div id="gen-progress-area" style="display:none">
                    <div class="gen-progress-container">
                        <div class="gen-progress-stage" id="gen-progress-stage">Initializing...</div>
                        <div class="gen-progress-bar-bg">
                            <div class="gen-progress-bar-fill" id="gen-progress-bar"></div>
                        </div>
                        <div class="gen-progress-pct" id="gen-progress-pct">0%</div>
                    </div>
                    <div id="gen-progress-prompts" class="gen-progress-prompts"></div>
                </div>
            </div>

            <div class="gen-modal-footer" id="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeGenerateModal()">Cancel</button>
                <button class="btn btn-primary" id="gen-submit-btn" onclick="submitGeneration()">
                    🎨 Generate
                </button>
            </div>
        </div>`;

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeGenerateModal();
    });
    document.body.appendChild(modal);
    updateGenModeFields();
}

function closeGenerateModal() {
    // Cancel any active SSE connection
    if (_generateEventSource) {
        _generateEventSource.close();
        _generateEventSource = null;
    }
    const m = document.getElementById('gen-modal-overlay');
    if (m) m.remove();
}

/**
 * Update dynamic fields based on selected prompt mode.
 */
function updateGenModeFields() {
    const mode = document.getElementById('gen-mode')?.value || 'system';
    const container = document.getElementById('gen-mode-fields');
    if (!container) return;

    let html = '';

    if (mode === 'character') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-member">Council Member</label>
                <select id="gen-member" class="settings-input">
                    ${_getGenMemberOptions()}
                </select>
            </div>`;
    } else if (mode === 'raw_user') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-user-prompt">Your Prompt</label>
                <textarea id="gen-user-prompt" class="settings-input proposal-textarea" rows="3"
                    placeholder="Describe the image you want to generate..."></textarea>
            </div>`;
    } else if (mode === 'user_refined') {
        html = `
            <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:1">
                    <label for="gen-member">Refining Member</label>
                    <select id="gen-member" class="settings-input">
                        ${_getGenMemberOptions()}
                    </select>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-user-prompt">Your Base Prompt</label>
                <textarea id="gen-user-prompt" class="settings-input proposal-textarea" rows="3"
                    placeholder="Your prompt text to be refined by the member..."></textarea>
            </div>`;
    } else if (mode === 'council_vote') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label>Voting Participants <span style="color:var(--text-muted);font-size:0.72rem">(min 2)</span></label>
                <div class="gen-participants-grid" id="gen-participants">
                    ${_getGenParticipantCheckboxes()}
                </div>
            </div>
            <div style="margin-top:var(--space-sm)">
                <button class="btn btn-secondary btn-sm" onclick="previewCouncilPrompts()" id="gen-preview-btn">
                    👁 Preview Prompts
                </button>
            </div>`;
    }
    // system mode has no extra fields

    container.innerHTML = html;
}

function _getGenMemberOptions() {
    if (!_generateMembers.length) return '<option value="">No members found</option>';
    return _generateMembers.map(m =>
        `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
    ).join('');
}

function _getGenParticipantCheckboxes() {
    if (!_generateMembers.length) return '<span style="color:var(--text-muted)">No members found</span>';
    return _generateMembers.map(m =>
        `<label class="gen-participant-label">
            <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
            ${escapeHtml(m)}
        </label>`
    ).join('');
}

// On modal open, populate member dropdowns asynchronously
async function _populateGenMembers() {
    try {
        const council = await api('/api/council');
        const members = council.map(m => m.name);

        // Populate member select dropdowns
        const memberSelect = document.getElementById('gen-member');
        if (memberSelect) {
            memberSelect.innerHTML = members.map(m =>
                `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
            ).join('');
        }

        // Populate participant checkboxes
        const participantsDiv = document.getElementById('gen-participants');
        if (participantsDiv) {
            participantsDiv.innerHTML = members.map(m =>
                `<label class="gen-participant-label">
                    <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
                    ${escapeHtml(m)}
                </label>`
            ).join('');
        }
    } catch { /* ignore */ }
}

/**
 * Preview prompts for council_vote mode.
 * Shows all generated prompts and lets the user pick one.
 */
async function previewCouncilPrompts() {
    const previewBtn = document.getElementById('gen-preview-btn');
    if (previewBtn) { previewBtn.disabled = true; previewBtn.textContent = '⏳ Generating prompts...'; }

    const participants = Array.from(document.querySelectorAll('.gen-participant-cb:checked'))
        .map(cb => cb.value);

    if (participants.length < 2) {
        showToast('Select at least 2 participants for council vote.', true);
        if (previewBtn) { previewBtn.disabled = false; previewBtn.textContent = '👁 Preview Prompts'; }
        return;
    }

    try {
        const body = {
            entity_type: _generateEntityType,
            entity_id: _generateEntityId,
            prompt_mode: 'council_vote',
            participants: participants,
            style_preset_key: document.getElementById('gen-style')?.value || '',
        };

        const result = await fetch('/api/generate/prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!result.ok) {
            const err = await result.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }

        const data = await result.json();
        const prompts = data.prompts || [];

        const previewArea = document.getElementById('gen-prompts-preview');
        if (previewArea && prompts.length) {
            previewArea.style.display = 'block';
            previewArea.innerHTML = `
                <div class="gen-prompts-list">
                    <h4>Select a Prompt</h4>
                    ${prompts.map((p, idx) => `
                        <label class="gen-prompt-option ${idx === 0 ? 'gen-prompt-selected' : ''}" onclick="selectGenPrompt(${idx})">
                            <input type="radio" name="gen-prompt-choice" value="${idx}" ${idx === 0 ? 'checked' : ''} />
                            <div class="gen-prompt-content">
                                <div class="gen-prompt-member">${escapeHtml(p.member_name || p.mode || 'Prompt ' + (idx+1))}</div>
                                <div class="gen-prompt-text">${escapeHtml(p.positive)}</div>
                                ${p.negative ? `<div class="gen-prompt-neg">Negative: ${escapeHtml(p.negative)}</div>` : ''}
                            </div>
                        </label>
                    `).join('')}
                </div>`;
        }
    } catch (err) {
        showToast(`Prompt preview failed: ${err.message}`, true);
    } finally {
        if (previewBtn) { previewBtn.disabled = false; previewBtn.textContent = '👁 Preview Prompts'; }
    }
}

function selectGenPrompt(index) {
    document.querySelectorAll('.gen-prompt-option').forEach((el, i) => {
        el.classList.toggle('gen-prompt-selected', i === index);
    });
}

/**
 * Submit the generation request and connect to SSE progress stream.
 */
async function submitGeneration() {
    const mode = document.getElementById('gen-mode')?.value || 'system';
    const templateId = document.getElementById('gen-template')?.value;
    const stylePreset = document.getElementById('gen-style')?.value || '';
    const width = parseInt(document.getElementById('gen-width')?.value || '512');
    const height = parseInt(document.getElementById('gen-height')?.value || '512');
    const seed = parseInt(document.getElementById('gen-seed')?.value || '0');
    const memberName = document.getElementById('gen-member')?.value || '';
    const userPrompt = document.getElementById('gen-user-prompt')?.value || '';

    // For council_vote, get selected prompt index
    let selectedPromptIndex = 0;
    if (mode === 'council_vote') {
        const checked = document.querySelector('input[name="gen-prompt-choice"]:checked');
        if (checked) selectedPromptIndex = parseInt(checked.value);
    }

    // Get participants for council_vote
    let participants = [];
    if (mode === 'council_vote') {
        participants = Array.from(document.querySelectorAll('.gen-participant-cb:checked'))
            .map(cb => cb.value);
        if (participants.length < 2) {
            showToast('Select at least 2 participants.', true);
            return;
        }
    }

    const body = {
        template_id: templateId,
        prompt_mode: mode,
        member_name: memberName,
        user_prompt: userPrompt,
        style_preset_key: stylePreset,
        participants: participants,
        selected_prompt_index: selectedPromptIndex,
        width: width,
        height: height,
        seed: seed,
    };

    const submitBtn = document.getElementById('gen-submit-btn');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '⏳ Starting...'; }

    try {
        const resp = await fetch(`/api/generate/${_generateEntityType}/${encodeURIComponent(_generateEntityId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Generation failed' }));
            throw new Error(err.detail);
        }

        const data = await resp.json();
        _generateActiveJobId = data.job_id;

        // Switch to progress view
        showGenerateProgress();

        // Connect to SSE stream
        connectGenerateSSE(data.job_id);

    } catch (err) {
        showToast(`Generation error: ${err.message}`, true);
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '🎨 Generate'; }
    }
}

/**
 * Switch modal to progress view.
 */
function showGenerateProgress() {
    const body = document.getElementById('gen-modal-body');
    const formElements = body?.querySelectorAll('.gen-form-grid, .filter-group, #gen-mode-fields, #gen-prompts-preview');
    if (formElements) formElements.forEach(el => el.style.display = 'none');

    const progressArea = document.getElementById('gen-progress-area');
    if (progressArea) progressArea.style.display = 'block';

    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-secondary" onclick="cancelGeneration()" id="gen-cancel-btn">Cancel Generation</button>
        `;
    }
}

/**
 * Connect to the SSE progress stream for a generation job.
 */
function connectGenerateSSE(jobId) {
    if (_generateEventSource) {
        _generateEventSource.close();
    }

    const es = new EventSource(`/api/generate/stream/${encodeURIComponent(jobId)}`);
    _generateEventSource = es;

    es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateGenerateProgress(data);
    });

    es.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
        updateGenerateProgress(data);
        es.close();
        _generateEventSource = null;
        onGenerationComplete(data);
    });

    es.addEventListener('error', (e) => {
        try {
            const data = JSON.parse(e.data);
            updateGenerateProgress(data);
        } catch {
            // SSE connection error
        }
        es.close();
        _generateEventSource = null;
        onGenerationError();
    });
}

/**
 * Update progress UI from SSE event data.
 */
function updateGenerateProgress(data) {
    const stageEl = document.getElementById('gen-progress-stage');
    const barEl = document.getElementById('gen-progress-bar');
    const pctEl = document.getElementById('gen-progress-pct');
    const promptsEl = document.getElementById('gen-progress-prompts');

    const stageLabels = {
        'prompt_generating': '🧠 Generating prompt...',
        'template_filling': '📋 Preparing workflow...',
        'queued': '📤 Submitting to ComfyUI...',
        'running': '⚡ ComfyUI is generating...',
        'downloading': '📥 Downloading image...',
        'saving': '💾 Saving image...',
        'completed': '✅ Complete!',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    if (stageEl) stageEl.textContent = stageLabels[data.stage] || data.stage;
    if (barEl) barEl.style.width = `${data.progress_pct || 0}%`;
    if (pctEl) pctEl.textContent = `${data.progress_pct || 0}%`;

    // Show prompts once available
    if (promptsEl && data.prompt_positive && data.stage !== 'prompt_generating') {
        promptsEl.innerHTML = `
            <div class="gen-progress-prompt-text">
                <strong>Prompt:</strong> ${escapeHtml(data.prompt_positive)}
            </div>
            ${data.prompt_negative ? `<div class="gen-progress-prompt-neg">
                <strong>Negative:</strong> ${escapeHtml(data.prompt_negative)}
            </div>` : ''}`;
    }

    if (data.error) {
        if (stageEl) stageEl.textContent = `❌ ${data.error}`;
    }
}

/**
 * Handle successful generation completion.
 */
function onGenerationComplete(data) {
    showToast('Image generated successfully! 🎨');

    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-primary" onclick="closeGenerateModal(); refreshGallery();">Close & View Gallery</button>
        `;
    }

    // Auto-refresh gallery in the background
    refreshGallery();
}

/**
 * Handle generation error.
 */
function onGenerationError() {
    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-secondary" onclick="closeGenerateModal()">Close</button>
            <button class="btn btn-primary" onclick="retryGeneration()">🔄 Retry</button>
        `;
    }
}

/**
 * Cancel an active generation job.
 */
async function cancelGeneration() {
    if (!_generateActiveJobId) return;
    const btn = document.getElementById('gen-cancel-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Cancelling...'; }

    try {
        await fetch(`/api/generate/cancel/${encodeURIComponent(_generateActiveJobId)}`, {
            method: 'POST',
        });
        showToast('Generation cancelled.');
    } catch (err) {
        showToast(`Cancel error: ${err.message}`, true);
    }
}

/**
 * Retry generation by reopening the modal.
 */
function retryGeneration() {
    closeGenerateModal();
    openGenerateModal(_generateEntityType, _generateEntityId);
}


// ═══════════════════════════════════════════════════════════════
// Exploration View (F-040)
// ═══════════════════════════════════════════════════════════════

async function renderExplore() {
    showLoading();
    let locations = [];
    try {
        locations = await api('/api/explore');
    } catch {
        locations = [];
    }

    if (!locations.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🧭 Explore</h2>
                    <p>No active locations to explore yet. Create locations in the <a href="#locations" style="color:var(--accent-cyan)">Locations</a> section and set them to active.</p>
                </div>
                <div class="empty-state">
                    <div class="empty-icon">🗺️</div>
                    <p>Your world awaits — create some locations first!</p>
                </div>
            </div>`;
        return;
    }

    const cards = locations.map(loc => {
        const imgStyle = loc.primary_image_url
            ? `background: url('${loc.primary_image_url}') center/cover no-repeat`
            : `background: linear-gradient(135deg, hsl(200,30%,20%), hsl(220,25%,15%))`;

        const scenesBadge = loc.scene_count > 0
            ? `<span class="explore-scene-badge">${loc.scene_count} scene${loc.scene_count !== 1 ? 's' : ''}</span>`
            : '';

        return `
            <div class="explore-card card-clickable" onclick="navigateTo('explore','${loc.id}')">
                <div class="explore-card-image" style="${imgStyle}">
                    ${!loc.primary_image_url ? '<div class="explore-card-placeholder">🗺️</div>' : ''}
                    ${scenesBadge}
                </div>
                <div class="explore-card-info">
                    <div class="explore-card-name">${escapeHtml(loc.name)}</div>
                    <div class="explore-card-desc">${truncate(loc.description, 80)}</div>
                    ${loc.tags && loc.tags.length ? `<div class="explore-card-tags">${loc.tags.slice(0, 3).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                </div>
            </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>🧭 Explore the World</h2>
                    <p>${locations.length} location${locations.length !== 1 ? 's' : ''} to explore</p>
                </div>
            </div>
            <div class="explore-grid">${cards}</div>
        </div>`;
}

async function renderExploreLocation(locationId) {
    showLoading();
    let data;
    try {
        data = await api(`/api/explore/${encodeURIComponent(locationId)}`);
    } catch (err) {
        showError(`Location not found: ${err.message}`);
        return;
    }

    // Hero image
    const heroImageUrl = data.primary_image_url || '';
    const heroStyle = heroImageUrl
        ? `background-image: url('${heroImageUrl}')`
        : `background: linear-gradient(135deg, hsl(220,30%,18%), hsl(250,25%,12%))`;

    // Features list
    const featuresHtml = (data.features || []).map(f => `
        <div class="explore-feature-item">
            <span class="explore-feature-icon">${f.feature_type === 'landmark' ? '🏛️' : f.feature_type === 'natural' ? '🌿' : f.feature_type === 'building' ? '🏠' : f.feature_type === 'district' ? '🏘️' : '📍'}</span>
            <div>
                <div class="explore-feature-name">${escapeHtml(f.name)}</div>
                <div class="explore-feature-desc">${escapeHtml(f.description || '')}</div>
            </div>
        </div>`).join('');

    // Scene strip
    const scenesHtml = (data.scenes || []).map((s, idx) => `
        <div class="explore-scene-thumb" onclick="openExploreSceneLightbox(${idx})">
            <img src="${s.image_url}" alt="${escapeAttr(s.description || s.scene_id)}" loading="lazy" />
            <div class="explore-scene-type">${s.scene_type}</div>
            <button class="explore-scene-delete" onclick="event.stopPropagation(); deleteExploreScene('${locationId}', '${s.scene_id}')" title="Delete scene">🗑️</button>
        </div>`).join('');

    // Navigation cards
    const navHtml = _buildExploreNavPanel(data.navigation);

    // Tags
    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('explore')">← Back to Explore</button>

            <div class="explore-hero" style="${heroStyle}">
                <div class="explore-hero-overlay">
                    <div class="explore-hero-content">
                        <h2 class="explore-hero-title">${escapeHtml(data.name)}</h2>
                        ${data.coordinates ? `<div class="explore-hero-coords">📍 ${escapeHtml(data.coordinates)}</div>` : ''}
                        <p class="explore-hero-desc">${escapeHtml(data.description || '')}</p>
                        ${tagsHtml ? `<div class="explore-hero-tags">${tagsHtml}</div>` : ''}
                    </div>
                    <div class="explore-hero-actions">
                        <button class="btn explore-look-around-btn" onclick="exploreLookAround('${locationId}')" id="explore-look-around-btn">
                            👁️ Look Around
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="navigateTo('locations', '${locationId}')" title="Open location detail page">
                            🗺️ Location Page
                        </button>
                    </div>
                </div>
            </div>

            <div id="explore-gen-progress" style="display:none">
                <div class="explore-gen-progress-bar">
                    <div class="explore-gen-progress-fill" id="explore-gen-fill"></div>
                </div>
                <div class="explore-gen-status" id="explore-gen-status">Generating scene…</div>
            </div>

            ${data.lore ? `
                <div class="explore-section">
                    <h4>📜 Lore</h4>
                    <p class="explore-lore-text">${escapeHtml(data.lore)}</p>
                </div>` : ''}

            ${featuresHtml ? `
                <div class="explore-section">
                    <h4>🏛️ Notable Features</h4>
                    <div class="explore-features-grid">${featuresHtml}</div>
                </div>` : ''}

            <div class="explore-section">
                <div class="explore-section-header">
                    <h4>🖼️ Scene Gallery (${(data.scenes || []).length})</h4>
                </div>
                ${scenesHtml
                    ? `<div class="explore-scene-strip" id="explore-scene-strip">${scenesHtml}</div>`
                    : `<div class="explore-empty-scenes">
                        <div class="empty-icon">👁️</div>
                        <p>No scenes yet. Click <strong>"Look Around"</strong> to generate your first scene!</p>
                    </div>`
                }
            </div>

            ${navHtml}
        </div>`;

    // Store scenes data for lightbox
    window._exploreScenes = data.scenes || [];
}

function _buildExploreNavPanel(nav) {
    if (!nav) return '';
    const allTargets = [];

    if (nav.parent) {
        allTargets.push({ ...nav.parent, relation: '⬆️ Parent' });
    }
    (nav.children || []).forEach(c => {
        allTargets.push({ ...c, relation: '⬇️ Child' });
    });
    (nav.siblings || []).forEach(s => {
        allTargets.push({ ...s, relation: '↔️ Sibling' });
    });

    if (!allTargets.length) return '';

    const cards = allTargets.map(t => {
        const imgStyle = t.primary_image_url
            ? `background: url('${t.primary_image_url}') center/cover no-repeat`
            : `background: linear-gradient(135deg, hsl(200,30%,20%), hsl(220,25%,15%))`;

        return `
            <div class="explore-nav-card card-clickable" onclick="navigateTo('explore','${t.id}')">
                <div class="explore-nav-card-img" style="${imgStyle}">
                    ${!t.primary_image_url ? '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:1.5rem;opacity:0.4">🗺️</div>' : ''}
                </div>
                <div class="explore-nav-card-info">
                    <span class="explore-nav-relation">${t.relation}</span>
                    <div class="explore-nav-card-name">${escapeHtml(t.name)}</div>
                    <div class="explore-nav-card-desc">${truncate(t.description, 60)}</div>
                </div>
            </div>`;
    }).join('');

    return `
        <div class="explore-section">
            <h4>🧭 Connected Locations</h4>
            <div class="explore-nav-grid">${cards}</div>
        </div>`;
}

/* ── Look Around Generation ────────────────────────────────── */

async function exploreLookAround(locationId) {
    const btn = document.getElementById('explore-look-around-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating…'; }

    const progressEl = document.getElementById('explore-gen-progress');
    const fillEl = document.getElementById('explore-gen-fill');
    const statusEl = document.getElementById('explore-gen-status');
    if (progressEl) progressEl.style.display = 'block';

    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/look-around`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Generation failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Scene generation started (${data.job_id}) 🎨`);

        // Poll for job status
        _pollExploreGeneration(data.job_id, locationId, fillEl, statusEl);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
        if (progressEl) progressEl.style.display = 'none';
    }
}

async function _pollExploreGeneration(jobId, locationId, fillEl, statusEl) {
    const stageLabels = {
        'prompt_generating': '🧠 Generating prompt…',
        'template_filling': '📋 Preparing workflow…',
        'queued': '📤 Queued…',
        'running': '⚡ Generating image…',
        'downloading': '📥 Downloading…',
        'saving': '💾 Saving…',
        'completed': '✅ Scene ready!',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    const poll = async () => {
        try {
            const data = await api(`/api/generate/job/${encodeURIComponent(jobId)}`);
            if (fillEl) fillEl.style.width = `${data.progress_pct || 0}%`;
            if (statusEl) statusEl.textContent = stageLabels[data.stage] || data.stage;

            if (data.stage === 'completed') {
                showToast('Scene generated! 🎨');

                // Auto-add the scene to this location
                if (data.image_id) {
                    try {
                        await fetch(`/api/explore/${encodeURIComponent(locationId)}/scenes`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                image_id: data.image_id,
                                scene_type: 'overview',
                                description: `Scene generated via Look Around`,
                            }),
                        });
                    } catch { /* scene add failed, image still exists */ }
                }

                // Refresh the explore page
                setTimeout(() => renderExploreLocation(locationId), 500);
                return;
            }

            if (data.stage === 'failed' || data.stage === 'cancelled') {
                showToast(`Generation ${data.stage}: ${data.error || ''}`, true);
                const btn = document.getElementById('explore-look-around-btn');
                if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
                const progressEl = document.getElementById('explore-gen-progress');
                if (progressEl) setTimeout(() => progressEl.style.display = 'none', 2000);
                return;
            }

            // Continue polling
            setTimeout(poll, 1500);
        } catch (err) {
            showToast(`Poll error: ${err.message}`, true);
            const btn = document.getElementById('explore-look-around-btn');
            if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
        }
    };

    setTimeout(poll, 2000);
}

/* ── Scene Lightbox ────────────────────────────────────────── */

function openExploreSceneLightbox(index) {
    const scenes = window._exploreScenes || [];
    if (!scenes.length) return;
    if (index < 0) index = scenes.length - 1;
    if (index >= scenes.length) index = 0;

    const scene = scenes[index];
    const overlay = document.createElement('div');
    overlay.className = 'gallery-lightbox';
    overlay.id = 'explore-scene-lightbox';
    overlay.innerHTML = `
        <div class="gallery-lb-content">
            <button class="gallery-lb-close" onclick="closeExploreSceneLightbox()" title="Close">✕</button>
            ${scenes.length > 1
                ? `<button class="gallery-lb-nav gallery-lb-prev" onclick="navigateExploreSceneLb(${index - 1})">◀</button>
                   <button class="gallery-lb-nav gallery-lb-next" onclick="navigateExploreSceneLb(${index + 1})">▶</button>`
                : ''}
            <img src="${scene.image_url}" alt="${escapeAttr(scene.description || scene.scene_id)}" />
            <div class="gallery-lb-info">
                <span>${scene.scene_id} · ${index + 1} / ${scenes.length} · ${scene.scene_type}</span>
            </div>
            ${scene.description ? `<div style="color:rgba(255,255,255,0.5);font-size:0.75rem;max-width:600px;text-align:center;margin-top:var(--space-xs)">
                ${escapeHtml(scene.description)}
            </div>` : ''}
        </div>`;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeExploreSceneLightbox();
    });
    document.body.appendChild(overlay);

    overlay._keyHandler = (e) => {
        if (e.key === 'Escape') closeExploreSceneLightbox();
        if (e.key === 'ArrowLeft') navigateExploreSceneLb(index - 1);
        if (e.key === 'ArrowRight') navigateExploreSceneLb(index + 1);
    };
    document.addEventListener('keydown', overlay._keyHandler);
}

function closeExploreSceneLightbox() {
    const lb = document.getElementById('explore-scene-lightbox');
    if (lb) {
        if (lb._keyHandler) document.removeEventListener('keydown', lb._keyHandler);
        lb.remove();
    }
}

function navigateExploreSceneLb(index) {
    closeExploreSceneLightbox();
    openExploreSceneLightbox(index);
}

/* ── Delete Scene ──────────────────────────────────────────── */

async function deleteExploreScene(locationId, sceneId) {
    if (!confirm('Delete this scene?')) return;
    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/scenes/${encodeURIComponent(sceneId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast('Scene deleted 🗑️');
        renderExploreLocation(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
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
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group">
                    <label for="char-provider-input">API Provider</label>
                    <select id="char-provider-input" class="settings-input" onchange="updateCharCreateModelField()">
                        <option value="openrouter">OpenRouter</option>
                        <option value="mancer">Mancer</option>
                        <option value="lmstudio">LM Studio</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="char-model-input">Model</label>
                    <div id="char-model-container">
                        ${renderModelField('char-model-input', 'openrouter', '', true)}
                    </div>
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
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🎭 Characters</h2>
                <p>${data.length} AI character template${data.length !== 1 ? 's' : ''}</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('character')" title="Generate images for multiple characters">🎨 Batch Generate</button>
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

    const galleryHtml = await renderImageGallery('character', data.id);

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

                ${galleryHtml}

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
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group">
                            <label for="char-edit-provider">API Provider</label>
                            <select id="char-edit-provider" class="settings-input" onchange="updateCharEditModelField()">
                                <option value="openrouter" ${(data.api_provider || 'openrouter') === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                                <option value="mancer" ${data.api_provider === 'mancer' ? 'selected' : ''}>Mancer</option>
                                <option value="lmstudio" ${data.api_provider === 'lmstudio' ? 'selected' : ''}>LM Studio</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="char-edit-model">Model</label>
                            <div id="char-edit-model-container">
                                ${renderModelField('char-edit-model', data.api_provider || 'openrouter', data.model || 'Default', true)}
                            </div>
                            <span class="council-field-hint">Set to "Default" to use the model configured in Settings</span>
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

    const apiProvider = document.getElementById('char-provider-input').value;
    const model = document.getElementById('char-model-input').value.trim() || 'Default';

    try {
        const resp = await fetch('/api/characters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, description, author, backstory,
                system_prompt: systemPrompt, greeting,
                example_messages: exampleMessages, tags, traits,
                api_provider: apiProvider, model,
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
        api_provider: document.getElementById('char-edit-provider').value,
        model: document.getElementById('char-edit-model').value.trim() || 'Default',
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
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🗺️ Locations</h2>
                <p>${data.length} world location${data.length !== 1 ? 's' : ''}</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('location')" title="Generate images for multiple locations">🎨 Batch Generate</button>
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
        statusActions = `
            <button class="btn btn-secondary btn-sm" onclick="updateLocationStatus('${data.id}', 'draft')">📝 → Draft</button>
            <button class="btn btn-secondary btn-sm" onclick="updateLocationStatus('${data.id}', 'archived')">📦 Archive</button>`;
    }


    const galleryHtml = await renderImageGallery('location', data.id);

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

                ${galleryHtml}

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
// Items View
// ═══════════════════════════════════════════════════════════════

const ITEM_PROPERTY_TYPES = ['magical', 'physical', 'consumable', 'equipment', 'material', 'custom'];
const ITEM_TIERS = ['permanent', 'consumable', 'degradable'];
const ITEM_LEGALITY = ['contraband', 'legal'];

async function renderItems() {
    showLoading();
    const data = await api('/api/items');
    state.itemsData = data;

    const createForm = `
        <div class="card location-create-form">
            <h3>📦 New Item</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Define a new world item for the council's domain.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="item-name-input">Name</label>
                    <input id="item-name-input" class="settings-input" placeholder="e.g. Starfall Blade" />
                </div>
                <div class="filter-group">
                    <label for="item-author-input">Author</label>
                    <input id="item-author-input" class="settings-input" placeholder="e.g. Council" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="item-desc-input">Description</label>
                <textarea id="item-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Describe this item…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="item-lore-input">Lore</label>
                <textarea id="item-lore-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="History and background of this item…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="item-tags-input">Tags</label>
                    <input id="item-tags-input" class="settings-input" placeholder="weapon, legendary, enchanted (comma-separated)" />
                </div>
                <div class="filter-group">
                    <label for="item-rarity-input">Rarity</label>
                    <input id="item-rarity-input" class="settings-input" placeholder="e.g. legendary (optional)" />
                </div>
                <div class="filter-group">
                    <label for="item-tier-input">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required for activation)</span></label>
                    <select id="item-tier-input" class="settings-input">
                        <option value="">-- Select Tier --</option>
                        ${ITEM_TIERS.map(t => `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="item-legality-input">Legality</label>
                    <select id="item-legality-input" class="settings-input">
                        <option value="">-- Select Legality --</option>
                        ${ITEM_LEGALITY.map(l => `<option value="${l}">${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createItem()" id="item-create-btn">
                    📦 Create Item
                </button>
                <span id="item-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>📦 Items</h2>
                    <p>No items defined yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const statusFilter = (s) => data.filter(i => i.status === s);
    const active = statusFilter('active');
    const drafts = statusFilter('draft');
    const archived = statusFilter('archived');

    const itemCard = (item) => `
        <div class="card proposal-card" onclick="navigateTo('items', '${item.id}')" style="cursor:pointer">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <h3 style="margin:0">${item.name}</h3>
                <div style="display:flex;gap:var(--space-xs);align-items:center">
                    ${item.tier ? `<span class="badge badge-tier-${item.tier}" style="background:linear-gradient(135deg,hsl(${item.tier==='permanent'?'210,60%,50%':item.tier==='consumable'?'40,70%,50%':'0,55%,50%'}),hsl(${item.tier==='permanent'?'230,55%,45%':item.tier==='consumable'?'55,65%,45%':'15,50%,45%'}));font-size:0.7rem;padding:2px 8px">${item.tier.charAt(0).toUpperCase()+item.tier.slice(1)}</span>` : ''}
                    ${item.legality ? `<span class="badge" style="background:linear-gradient(135deg,${item.legality==='legal'?'hsl(150,55%,42%),hsl(160,50%,38%)':'hsl(0,60%,48%),hsl(10,55%,43%)'});font-size:0.7rem;padding:2px 8px">${item.legality.charAt(0).toUpperCase()+item.legality.slice(1)}</span>` : ''}
                    ${item.owner ? `<span class="badge store-owned-badge">Owned by ${escapeHtml(item.owner)}</span>` : ''}
                    ${item.rarity ? `<span class="badge badge-${item.rarity}">${item.rarity}</span>` : ''}
                    ${badge(item.status)}
                </div>
            </div>
            <p style="margin:var(--space-xs) 0;color:var(--text-secondary)">${truncate(item.description, 120)}</p>
            <div style="display:flex;gap:var(--space-xs);flex-wrap:wrap;margin-top:var(--space-xs)">
                ${(item.tags||[]).map(t => `<span class="badge badge-general">${t}</span>`).join('')}
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:var(--space-sm);font-size:0.78rem;color:var(--text-muted)">
                <span>📦 ${item.properties ? item.properties.length : 0} properties</span>
                <span>by ${item.author} · ${formatDate(item.created_at)}</span>
            </div>
        </div>`;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>📦 Items</h2>
                <p>${data.length} item${data.length !== 1 ? 's' : ''} · ${active.length} active · ${drafts.length} draft · ${archived.length} archived</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('item')" title="Generate images for multiple items">🎨 Batch Generate</button>
            </div>
            ${createForm}
            ${active.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">✨ Active Items</h3>` : ''}
            ${active.map(itemCard).join('')}
            ${drafts.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">📝 Drafts</h3>` : ''}
            ${drafts.map(itemCard).join('')}
            ${archived.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">📁 Archived</h3>` : ''}
            ${archived.map(itemCard).join('')}
        </div>`;
}

async function renderItemDetail(id) {
    showLoading();
    const data = await api(`/api/items/${encodeURIComponent(id)}`);

    const tierBadge = data.tier
        ? `<span class="badge" style="background:linear-gradient(135deg,hsl(${data.tier==='permanent'?'210,60%,50%':data.tier==='consumable'?'40,70%,50%':'0,55%,50%'}),hsl(${data.tier==='permanent'?'230,55%,45%':data.tier==='consumable'?'55,65%,45%':'15,50%,45%'}));font-size:0.78rem;padding:3px 10px">${data.tier.charAt(0).toUpperCase()+data.tier.slice(1)}</span>`
        : `<span class="badge" style="background:var(--accent-rose);font-size:0.72rem;padding:2px 8px">⚠ No Tier</span>`;

    const statusActions = {
        draft: `<button class="btn" onclick="updateItemStatus('${id}','active')" style="background:linear-gradient(135deg, hsl(160,60%,45%),hsl(140,55%,40%));">✨ Set Active</button>`,
        active: `<button class="btn" onclick="updateItemStatus('${id}','archived')" style="background:linear-gradient(135deg, hsl(0,50%,50%),hsl(15,55%,45%));">📁 Archive</button>`,
        archived: '',
    };

    const propsHtml = (data.properties || []).map(p => `
        <div class="detail-row" style="display:flex;align-items:center;gap:var(--space-sm)">
            <span class="badge badge-${p.property_type}">${p.property_type}</span>
            <strong>${p.name}</strong>
            <span style="color:var(--text-secondary)">${p.description}</span>
            <button class="btn" style="margin-left:auto;padding:2px 8px;font-size:0.75rem" onclick="removeItemProperty('${id}','${p.name.replace(/'/g,"\\'")}')">✕</button>
        </div>`).join('');


    const galleryHtml = await renderImageGallery('item', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <button class="btn" onclick="navigateTo('items')" style="margin-bottom:var(--space-sm);font-size:0.82rem">← Back to Items</button>
                    <h2>${data.name} ${tierBadge} ${data.legality ? `<span class="badge" style="background:linear-gradient(135deg,${data.legality==='legal'?'hsl(150,55%,42%),hsl(160,50%,38%)':'hsl(0,60%,48%),hsl(10,55%,43%)'});font-size:0.78rem;padding:3px 10px">${data.legality.charAt(0).toUpperCase()+data.legality.slice(1)}</span>` : ''} ${data.rarity ? `<span class="badge badge-${data.rarity}">${data.rarity}</span>` : ''} ${data.owner ? `<span class="badge store-owned-badge">Owned by ${escapeHtml(data.owner)}</span>` : ''}</h2>
                    <p>${badge(data.status)} · ID: ${data.id} · v${data.version} · by ${data.author}</p>
                </div>
                <div style="display:flex;gap:var(--space-sm)">
                    ${statusActions[data.status] || ''}
                </div>
            </div>

            ${galleryHtml}

            <div class="detail-section">
                <h3>📝 Edit Item</h3>
                <div class="proposal-form-grid">
                    <div class="filter-group" style="flex:2">
                        <label for="item-edit-name">Name</label>
                        <input id="item-edit-name" class="settings-input" value="${data.name.replace(/"/g, '&quot;')}" />
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-rarity">Rarity</label>
                        <input id="item-edit-rarity" class="settings-input" value="${(data.rarity || '').replace(/"/g, '&quot;')}" placeholder="e.g. legendary" />
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-tier">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required)</span></label>
                        <select id="item-edit-tier" class="settings-input">
                            <option value="">-- Select Tier --</option>
                            ${ITEM_TIERS.map(t => `<option value="${t}" ${data.tier === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-legality">Legality</label>
                        <select id="item-edit-legality" class="settings-input">
                            <option value="">-- Select Legality --</option>
                            ${ITEM_LEGALITY.map(l => `<option value="${l}" ${data.legality === l ? 'selected' : ''}>${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-desc">Description</label>
                    <textarea id="item-edit-desc" class="settings-input proposal-textarea" rows="3">${data.description}</textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-lore">Lore</label>
                    <textarea id="item-edit-lore" class="settings-input proposal-textarea" rows="3">${data.lore || ''}</textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-tags">Tags</label>
                    <input id="item-edit-tags" class="settings-input" value="${(data.tags || []).join(', ')}" />
                </div>
                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="saveItemEdit('${id}')" id="item-save-btn">💾 Save Changes</button>
                    <span id="item-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>

            <div class="detail-section">
                <h3>⚙️ Properties (${data.properties ? data.properties.length : 0})</h3>
                ${propsHtml || '<p style="color:var(--text-muted)">No properties yet.</p>'}
                <div style="margin-top:var(--space-md);padding-top:var(--space-md);border-top:1px solid var(--border-subtle)">
                    <h4>Add Property</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="item-prop-name">Name</label>
                            <input id="item-prop-name" class="settings-input" placeholder="e.g. Fire Enchantment" />
                        </div>
                        <div class="filter-group">
                            <label for="item-prop-type">Type</label>
                            <select id="item-prop-type" class="settings-input">
                                ${ITEM_PROPERTY_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="item-prop-desc">Description</label>
                        <input id="item-prop-desc" class="settings-input" placeholder="What does this property do?" />
                    </div>
                    <button class="btn" onclick="addItemProperty('${id}')" style="margin-top:var(--space-sm)">➕ Add Property</button>
                </div>
            </div>

            <div class="detail-section">
                <h3>📋 Metadata</h3>
                <div class="detail-row"><span class="label">Created</span><span class="value">${formatDate(data.created_at)}</span></div>
                <div class="detail-row"><span class="label">Updated</span><span class="value">${formatDate(data.updated_at)}</span></div>
                <div class="detail-row"><span class="label">Version</span><span class="value">${data.version}</span></div>
                ${data.metadata && data.metadata.source_proposal ? `<div class="detail-row"><span class="label">Source Proposal</span><span class="value"><a href="#proposals/${data.metadata.source_proposal}" style="color:var(--accent-primary)">${data.metadata.source_proposal}</a></span></div>` : ''}
            </div>
        </div>`;
}

// ── Item Creation ────────────────────────────────────────────

async function createItem() {
    const btn = document.getElementById('item-create-btn');
    const status = document.getElementById('item-create-status');
    btn.disabled = true;
    btn.textContent = '⏳ Creating…';

    const name = document.getElementById('item-name-input').value.trim();
    const description = document.getElementById('item-desc-input').value.trim();
    const author = document.getElementById('item-author-input').value.trim();
    const lore = document.getElementById('item-lore-input').value.trim();
    const tagsRaw = document.getElementById('item-tags-input').value.trim();
    const rarity = document.getElementById('item-rarity-input').value.trim();
    const tier = document.getElementById('item-tier-input').value;
    const legality = document.getElementById('item-legality-input').value;
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        btn.disabled = false;
        btn.textContent = '📦 Create Item';
        return;
    }

    try {
        const resp = await fetch('/api/items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, lore, tags, rarity, tier, legality }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Item "${data.name}" created ✅`);
        navigateTo('items', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '📦 Create Item';
    }
}

// ── Item Edit ────────────────────────────────────────────────

async function saveItemEdit(itemId) {
    const btn = document.getElementById('item-save-btn');
    const status = document.getElementById('item-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';

    const tagsRaw = document.getElementById('item-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('item-edit-name').value.trim(),
        description: document.getElementById('item-edit-desc').value.trim(),
        lore: document.getElementById('item-edit-lore').value.trim(),
        tags,
        rarity: document.getElementById('item-edit-rarity').value.trim(),
        tier: document.getElementById('item-edit-tier').value,
        legality: document.getElementById('item-edit-legality').value,
    };

    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Item updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

// ── Item Status ──────────────────────────────────────────────

async function updateItemStatus(itemId, newStatus) {
    // Client-side guard: check tier before activation
    if (newStatus === 'active') {
        try {
            const item = await api(`/api/items/${encodeURIComponent(itemId)}`);
            if (!item.tier) {
                showToast('A tier must be set before activating an item. Edit the item and select a tier first.', true);
                return;
            }
        } catch { /* let server-side validation handle it */ }
    }
    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item set to ${newStatus} ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Item Property Management ─────────────────────────────────

async function addItemProperty(itemId) {
    const name = document.getElementById('item-prop-name').value.trim();
    const propType = document.getElementById('item-prop-type').value;
    const desc = document.getElementById('item-prop-desc').value.trim();

    if (!name) { document.getElementById('item-prop-name').focus(); return; }

    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                properties: [{ name, description: desc || name, property_type: propType }],
            }),
        });
        // Actually we need a dedicated endpoint for add_property.
        // Let's do it via full item re-fetch and re-save pattern.
    } catch (err) {
        // fallback
    }

    // Better approach: get current item, add property, update
    try {
        const current = await api(`/api/items/${encodeURIComponent(itemId)}`);
        const newProps = [...(current.properties || []), { name, description: desc || name, property_type: propType }];
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ properties: newProps }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to add property' }));
            throw new Error(err.detail);
        }
        showToast(`Property "${name}" added ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeItemProperty(itemId, propName) {
    if (!confirm(`Remove property "${propName}"?`)) return;

    try {
        const current = await api(`/api/items/${encodeURIComponent(itemId)}`);
        const newProps = (current.properties || []).filter(p => p.name !== propName);
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ properties: newProps }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to remove property' }));
            throw new Error(err.detail);
        }
        showToast(`Property "${propName}" removed ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Stores View  (StoreManager-backed — F-036)
// ═══════════════════════════════════════════════════════════════

const STORE_TYPE_ICONS = {
    general: '🏪', blacksmith: '⚒️', alchemist: '⚗️',
    enchanter: '✨', tavern: '🍺', custom: '🏷️',
};

async function renderStores() {
    showLoading();
    const data = await api('/api/stores');
    state.storesData = data;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div><h2>🏪 Stores</h2><p>Create and manage world stores where items can be purchased</p></div>
                    <div style="display:flex;gap:var(--space-sm)">
                        <button class="btn btn-secondary" onclick="openLocationStoreModal()" id="btn-add-loc-store">📍 Add Location as Store</button>
                        <button class="btn btn-primary" onclick="document.getElementById('store-create-form').style.display='block'" id="btn-create-store">➕ Create Store</button>
                    </div>
                </div>
                ${_storeCreateForm()}
                <div class="empty-state">
                    <div class="empty-icon">🏪</div>
                    <p>No stores yet. Click <strong>Create Store</strong> or <strong>Add Location as Store</strong> to add one.</p>
                </div>
            </div>`;
        return;
    }

    const filterStatus = state.storeFilterStatus || '';
    const filtered = filterStatus ? data.filter(s => s.status === filterStatus) : data;
    const statusCounts = {};
    data.forEach(s => statusCounts[s.status] = (statusCounts[s.status] || 0) + 1);

    const filters = `
        <div class="filter-group">
            <button class="btn btn-sm ${!filterStatus ? 'btn-primary' : 'btn-secondary'}" onclick="state.storeFilterStatus='';renderStores()">All (${data.length})</button>
            ${Object.entries(statusCounts).map(([st, cnt]) =>
                `<button class="btn btn-sm ${filterStatus === st ? 'btn-primary' : 'btn-secondary'}" onclick="state.storeFilterStatus='${st}';renderStores()">${st} (${cnt})</button>`
            ).join('')}
        </div>`;

    const cards = filtered.map(store => {
        const icon = STORE_TYPE_ICONS[store.store_type] || '🏪';
        const invCount = (store.inventory || []).length;
        const tagsHtml = (store.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');
        return `
        <div class="card card-clickable store-card" onclick="navigateTo('stores','${store.id}')">
            <div class="store-card-header">
                <div class="store-card-icon">${icon}</div>
                <div style="flex:1">
                    <div class="store-card-name">${escapeHtml(store.name)}</div>
                    <div class="store-card-author">by ${escapeHtml(store.author)} · ${badge(store.status)} · ${badge(store.store_type)}</div>
                </div>
                <div class="store-card-stats">
                    <span class="store-stat">📦 ${invCount} item${invCount !== 1 ? 's' : ''}</span>
                    ${store.owner ? `<span class="store-stat">👤 ${escapeHtml(store.owner)}</span>` : ''}
                </div>
            </div>
            <div class="store-card-desc">${truncate(store.description, 140)}</div>
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🏪 Stores</h2><p>${data.length} store${data.length !== 1 ? 's' : ''}</p></div>
                <div style="display:flex;gap:var(--space-sm)">
                    <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('store')" title="Generate images for multiple stores">🎨 Batch Generate</button>
                    <button class="btn btn-secondary" onclick="openLocationStoreModal()" id="btn-add-loc-store">📍 Add Location as Store</button>
                    <button class="btn btn-primary" onclick="document.getElementById('store-create-form').style.display='block'" id="btn-create-store">➕ Create Store</button>
                </div>
            </div>
            ${_storeCreateForm()}
            ${filters}
            <div class="store-grid">${cards}</div>
        </div>`;
}

function _storeCreateForm() {
    const typeOptions = ['general','blacksmith','alchemist','enchanter','tavern','custom']
        .map(t => `<option value="${t}">${STORE_TYPE_ICONS[t] || ''} ${t}</option>`).join('');
    return `
    <div class="card store-form-card" id="store-create-form" style="display:none;margin-bottom:var(--space-xl)">
        <h3 class="store-form-title">✨ Create New Store</h3>
        <div class="store-form-grid">
            <div class="store-form-field">
                <label class="store-form-label">Store Name</label>
                <input type="text" id="store-new-name" class="store-form-input" placeholder="e.g. Ironhaven Smithy">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Author</label>
                <input type="text" id="store-new-author" class="store-form-input" placeholder="e.g. Council">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Store Type</label>
                <select id="store-new-type" class="store-form-input">${typeOptions}</select>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Owner <span class="store-form-hint">(character or member)</span></label>
                <input type="text" id="store-new-owner" class="store-form-input" placeholder="e.g. Sage">
            </div>
            <div class="store-form-field store-form-full">
                <label class="store-form-label">Description</label>
                <textarea id="store-new-desc" class="store-form-textarea" rows="3" placeholder="A master forge run by the finest artisans…"></textarea>
            </div>
            <div class="store-form-field store-form-full">
                <label class="store-form-label">Lore <span class="store-form-hint">(optional)</span></label>
                <textarea id="store-new-lore" class="store-form-textarea" rows="2" placeholder="Long ago, the first hammer struck…"></textarea>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Location ID <span class="store-form-hint">(optional)</span></label>
                <input type="text" id="store-new-location" class="store-form-input" placeholder="e.g. LOC-0001">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Tags <span class="store-form-hint">(comma-separated)</span></label>
                <input type="text" id="store-new-tags" class="store-form-input" placeholder="weapons, armor">
            </div>
        </div>
        <div class="store-form-actions">
            <button class="btn btn-primary" onclick="submitNewStore()" id="btn-submit-store">🏪 Create Store</button>
            <button class="btn btn-secondary" onclick="document.getElementById('store-create-form').style.display='none'">Cancel</button>
        </div>
    </div>`;
}

// ── Add Location as Store modal ──────────────────────────────

async function openLocationStoreModal() {
    let locations = [];
    try {
        locations = await api('/api/locations?status=active');
    } catch (err) {
        showToast('Failed to load locations: ' + err.message, true);
        return;
    }

    if (!locations.length) {
        showToast('No active locations found. Activate a location first.', true);
        return;
    }

    const typeOptions = ['general','blacksmith','alchemist','enchanter','tavern','custom']
        .map(t => `<option value="${t}">${STORE_TYPE_ICONS[t] || ''} ${t}</option>`).join('');

    const locOptions = locations.map(l =>
        `<option value="${l.id}" data-name="${escapeAttr(l.name)}" data-desc="${escapeAttr(l.description)}">${l.id} — ${escapeHtml(l.name)}</option>`
    ).join('');

    // Build modal
    const overlay = document.createElement('div');
    overlay.className = 'promote-modal-overlay';
    overlay.id = 'loc-store-modal';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    overlay.innerHTML = `
        <div class="store-form-card" style="width:620px;max-width:90vw">
            <h3 class="store-form-title">📍 Add Location as Store</h3>
            <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:var(--space-lg)">
                Create a new store based on an existing active location. The location's name and description will be used.
            </p>
            <div class="store-form-grid">
                <div class="store-form-field store-form-full">
                    <label class="store-form-label">Select Location</label>
                    <select id="loc-store-select" class="store-form-input" onchange="prefillLocationStore()">${locOptions}</select>
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Store Name</label>
                    <input type="text" id="loc-store-name" class="store-form-input" value="${escapeAttr(locations[0].name)}">
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Author</label>
                    <input type="text" id="loc-store-author" class="store-form-input" placeholder="e.g. Council">
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Store Type</label>
                    <select id="loc-store-type" class="store-form-input">${typeOptions}</select>
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Owner <span class="store-form-hint">(optional)</span></label>
                    <input type="text" id="loc-store-owner" class="store-form-input" placeholder="e.g. Sage">
                </div>
                <div class="store-form-field store-form-full">
                    <label class="store-form-label">Description</label>
                    <textarea id="loc-store-desc" class="store-form-textarea" rows="3">${escapeHtml(locations[0].description)}</textarea>
                </div>
            </div>
            <div class="store-form-actions">
                <button class="btn btn-primary" onclick="submitLocationStore()" id="btn-loc-store-submit">🏪 Create Store from Location</button>
                <button class="btn btn-secondary" onclick="document.getElementById('loc-store-modal').remove()">Cancel</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
}

function prefillLocationStore() {
    const sel = document.getElementById('loc-store-select');
    const opt = sel.options[sel.selectedIndex];
    document.getElementById('loc-store-name').value = opt.dataset.name || '';
    document.getElementById('loc-store-desc').value = opt.dataset.desc || '';
}

async function submitLocationStore() {
    const location_id = document.getElementById('loc-store-select').value;
    const name = document.getElementById('loc-store-name').value.trim();
    const author = document.getElementById('loc-store-author').value.trim();
    const description = document.getElementById('loc-store-desc').value.trim();
    const store_type = document.getElementById('loc-store-type').value;
    const owner = document.getElementById('loc-store-owner').value.trim();

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        return;
    }

    const btn = document.getElementById('btn-loc-store-submit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    try {
        const resp = await fetch('/api/stores', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, store_type, owner, location_id }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Store "${result.name}" created from location ✅`);
        const modal = document.getElementById('loc-store-modal');
        if (modal) modal.remove();
        navigateTo('stores', result.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🏪 Create Store from Location'; }
    }
}

async function submitNewStore() {
    const name = document.getElementById('store-new-name').value.trim();
    const description = document.getElementById('store-new-desc').value.trim();
    const author = document.getElementById('store-new-author').value.trim();
    const store_type = document.getElementById('store-new-type').value;
    const owner = document.getElementById('store-new-owner').value.trim();
    const lore = document.getElementById('store-new-lore').value.trim();
    const location_id = document.getElementById('store-new-location').value.trim();
    const rawTags = document.getElementById('store-new-tags').value.trim();
    const tags = rawTags ? rawTags.split(',').map(t => t.trim()).filter(Boolean) : [];

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        return;
    }

    const btn = document.getElementById('btn-submit-store');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    try {
        const resp = await fetch('/api/stores', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, store_type, owner, lore, location_id, tags }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Store "${result.name}" created ✅`);
        navigateTo('stores', result.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🏪 Create Store'; }
    }
}

async function renderStoreDetail(storeId) {
    showLoading();
    let data;
    let activeItems = [];
    try {
        data = await api(`/api/stores/${encodeURIComponent(storeId)}`);
    } catch (err) {
        showError(err.message);
        return;
    }
    try {
        activeItems = await api('/api/items?status=active');
    } catch { /* items may not exist yet */ }

    const icon = STORE_TYPE_ICONS[data.store_type] || '🏪';
    const inv = data.inventory || [];

    // Status transition buttons
    const transitions = { draft: ['active'], active: ['draft', 'archived'], archived: [] };
    const allowed = transitions[data.status] || [];
    const statusBtns = allowed.map(s =>
        `<button class="btn btn-sm ${s === 'draft' ? 'btn-secondary' : 'btn-primary'}" onclick="setStoreStatus('${storeId}','${s}')" id="btn-store-status-${s}">→ ${s}</button>`
    ).join('');

    // Inventory table
    let invHtml = '';
    if (inv.length) {
        const rows = inv.map(si => {
            const priceDisplay = [
                si.price_gold ? `${si.price_gold}G` : '',
                si.price_silver ? `${si.price_silver}S` : '',
                si.price_bronze ? `${si.price_bronze}B` : '',
            ].filter(Boolean).join(' ') || '—';
            const qtyDisplay = si.quantity === -1 ? '∞' : si.quantity;
            return `
            <tr>
                <td style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:var(--accent-cyan)">${si.item_id}${(() => { const m = activeItems.find(it => it.id === si.item_id); return m ? ` <span style="font-family:inherit;color:var(--text-secondary)">— ${escapeHtml(m.name)}</span>` : ''; })()}</td>
                <td class="store-price-cell">🪙 ${priceDisplay}</td>
                <td style="text-align:center">${qtyDisplay}</td>
                <td style="font-size:0.78rem;color:var(--text-muted)">${formatDate(si.added_at)}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="removeStoreInventory('${storeId}','${si.item_id}')" title="Remove">🗑️</button>
                </td>
            </tr>`;
        }).join('');
        invHtml = `
        <table class="store-inv-table">
            <thead><tr><th>Item ID</th><th>Price</th><th>Qty</th><th>Added</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } else {
        invHtml = '<p style="color:var(--text-muted)">No items in inventory yet.</p>';
    }

    // Build active-items dropdown options (exclude items already in inventory)
    const existingItemIds = new Set(inv.map(si => si.item_id));
    const availableItems = activeItems.filter(it => !existingItemIds.has(it.id));
    const itemOptions = availableItems.length
        ? availableItems.map(it => `<option value="${it.id}">${it.id} — ${escapeHtml(it.name)}</option>`).join('')
        : '<option value="" disabled>No active items available</option>';

    // Add inventory form
    const addInvForm = `
    <div class="card store-form-card" id="store-add-inv-form" style="display:none;margin-top:var(--space-md)">
        <h4 class="store-form-title" style="font-size:1rem">📦 Add Inventory Item</h4>
        <div class="store-form-grid">
            <div class="store-form-field">
                <label class="store-form-label">Select Item</label>
                <select id="sinv-item-id" class="store-form-input">${itemOptions}</select>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Gold Price</label>
                <input type="number" id="sinv-gold" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Silver Price</label>
                <input type="number" id="sinv-silver" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Bronze Price</label>
                <input type="number" id="sinv-bronze" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Quantity <span class="store-form-hint">(-1 = unlimited)</span></label>
                <input type="number" id="sinv-qty" class="store-form-input" value="-1" min="-1">
            </div>
        </div>
        <div class="store-form-actions">
            <button class="btn btn-primary btn-sm" onclick="addStoreInventory('${storeId}')" id="btn-add-inv">➕ Add Item</button>
            <button class="btn btn-secondary btn-sm" onclick="document.getElementById('store-add-inv-form').style.display='none'">Cancel</button>
        </div>
    </div>`;

    // Edit form fields
    const tagsStr = (data.tags || []).join(', ');


    const galleryHtml = await renderImageGallery('store', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('stores')">← Back to Stores</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${icon} ${escapeHtml(data.name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm);align-items:center">
                            ${badge(data.status)} ${badge(data.store_type)}
                            ${data.owner ? `<span style="color:var(--text-secondary);font-size:0.82rem">👤 ${escapeHtml(data.owner)}</span>` : ''}
                            ${data.location_id ? `<span style="color:var(--text-secondary);font-size:0.82rem">📍 ${escapeHtml(data.location_id)}</span>` : ''}
                            <span class="store-stat">📦 ${inv.length} item${inv.length !== 1 ? 's' : ''}</span>
                            ${statusBtns}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('stores')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.lore ? `<div class="detail-section"><h4>📜 Lore</h4><p style="white-space:pre-line">${escapeHtml(data.lore)}</p></div>` : ''}

                <div class="detail-section">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <h4>🛒 Inventory (${inv.length})</h4>
                        <button class="btn btn-sm btn-primary" onclick="document.getElementById('store-add-inv-form').style.display='block'">➕ Add Item</button>
                    </div>
                    ${invHtml}
                    ${addInvForm}
                </div>

                ${data.status === 'active' && inv.length ? `
                <div class="detail-section">
                    <h4>💰 Purchase an Item</h4>
                    <div class="store-form-grid">
                        <div class="store-form-field">
                            <label class="store-form-label">Select Item</label>
                            <select id="purchase-item-id" class="store-form-input">
                                ${inv.map(si => {
                                    const matchedItem = activeItems.find(it => it.id === si.item_id);
                                    const label = matchedItem ? `${si.item_id} — ${escapeHtml(matchedItem.name)}` : si.item_id;
                                    const qtyLabel = si.quantity === -1 ? '∞' : si.quantity;
                                    const priceLabel = [si.price_gold ? si.price_gold + 'G' : '', si.price_silver ? si.price_silver + 'S' : '', si.price_bronze ? si.price_bronze + 'B' : ''].filter(Boolean).join(' ') || 'Free';
                                    return `<option value="${si.item_id}">${label} · ${priceLabel} · Qty: ${qtyLabel}</option>`;
                                }).join('')}
                            </select>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Buyer Account ID</label>
                            <input type="text" id="purchase-buyer" class="store-form-input" placeholder="ACCT-user-human">
                        </div>
                    </div>
                    <div class="store-form-actions">
                        <button class="btn btn-primary" onclick="purchaseFromStore('${storeId}')" id="btn-purchase">💰 Purchase</button>
                    </div>
                </div>` : ''}

                ${galleryHtml}

                <div class="detail-section">
                    <h4>✏️ Edit Store</h4>
                    <div class="store-form-grid">
                        <div class="store-form-field">
                            <label class="store-form-label">Name</label>
                            <input type="text" id="store-edit-name" class="store-form-input" value="${escapeAttr(data.name)}">
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Owner</label>
                            <input type="text" id="store-edit-owner" class="store-form-input" value="${escapeAttr(data.owner || '')}">
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Store Type</label>
                            <select id="store-edit-type" class="store-form-input">
                                ${['general','blacksmith','alchemist','enchanter','tavern','custom']
                                    .map(t => `<option value="${t}" ${t===data.store_type?'selected':''}>${STORE_TYPE_ICONS[t]||''} ${t}</option>`).join('')}
                            </select>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Location ID</label>
                            <input type="text" id="store-edit-location" class="store-form-input" value="${escapeAttr(data.location_id || '')}">
                        </div>
                        <div class="store-form-field store-form-full">
                            <label class="store-form-label">Description</label>
                            <textarea id="store-edit-desc" class="store-form-textarea" rows="3">${escapeHtml(data.description)}</textarea>
                        </div>
                        <div class="store-form-field store-form-full">
                            <label class="store-form-label">Lore</label>
                            <textarea id="store-edit-lore" class="store-form-textarea" rows="2">${escapeHtml(data.lore || '')}</textarea>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Tags</label>
                            <input type="text" id="store-edit-tags" class="store-form-input" value="${escapeAttr(tagsStr)}">
                        </div>
                    </div>
                    <div class="store-form-actions">
                        <button class="btn btn-primary" onclick="updateStore('${storeId}')" id="btn-update-store">💾 Save Changes</button>
                    </div>
                </div>

                <div class="detail-section" style="font-size:0.82rem;color:var(--text-muted)">
                    Created: ${formatDate(data.created_at)} · Updated: ${formatDate(data.updated_at)} · Version: ${data.version}
                </div>
            </div>
        </div>`;
}

async function setStoreStatus(storeId, newStatus) {
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Status change failed' }));
            throw new Error(err.detail);
        }
        showToast(`Store status → ${newStatus} ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function addStoreInventory(storeId) {
    const item_id = document.getElementById('sinv-item-id').value.trim();
    const price_gold = parseInt(document.getElementById('sinv-gold').value, 10) || 0;
    const price_silver = parseInt(document.getElementById('sinv-silver').value, 10) || 0;
    const price_bronze = parseInt(document.getElementById('sinv-bronze').value, 10) || 0;
    const quantity = parseInt(document.getElementById('sinv-qty').value, 10);

    if (!item_id) { showToast('Item ID is required.', true); return; }

    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/inventory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id, price_gold, price_silver, price_bronze, quantity }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Add failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item ${item_id} added to inventory ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeStoreInventory(storeId, itemId) {
    if (!confirm(`Remove ${itemId} from inventory?`)) return;
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/inventory/${encodeURIComponent(itemId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Remove failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item ${itemId} removed ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function updateStore(storeId) {
    const body = {
        name: document.getElementById('store-edit-name').value.trim(),
        description: document.getElementById('store-edit-desc').value.trim(),
        lore: document.getElementById('store-edit-lore').value.trim(),
        owner: document.getElementById('store-edit-owner').value.trim(),
        store_type: document.getElementById('store-edit-type').value,
        location_id: document.getElementById('store-edit-location').value.trim(),
        tags: document.getElementById('store-edit-tags').value.split(',').map(t => t.trim()).filter(Boolean),
    };
    const btn = document.getElementById('btn-update-store');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Update failed' }));
            throw new Error(err.detail);
        }
        showToast('Store updated ✅');
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
    }
}

async function purchaseFromStore(storeId) {
    const item_id = document.getElementById('purchase-item-id').value.trim();
    const buyer_account_id = document.getElementById('purchase-buyer').value.trim();

    if (!item_id || !buyer_account_id) {
        showToast('Item ID and Buyer Account ID are required.', true);
        return;
    }

    const btn = document.getElementById('btn-purchase');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Processing…'; }

    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/purchase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id, buyer_account_id }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Purchase failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Purchased ${result.item.item_id} successfully! ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💰 Purchase'; }
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
        ? [...activeChats].reverse().map((c, i) => chatCard(c, i)).join('')
        : '<div class="empty-state"><div class="empty-icon">💬</div><p>No active chats. Start a new conversation!</p></div>';

    const closedHtml = closedChats.length
        ? `<details class="chat-closed-section">
            <summary class="chat-closed-toggle">Closed Chats (${closedChats.length})</summary>
            <div class="chat-list">${[...closedChats].reverse().map((c, i) => chatCard(c, i + activeChats.length)).join('')}</div>
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
                    <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPass('chat','${chatId}')" id="silentpassa-btn" title="Toggle [PRESENT]/[SILENCE] wrappers">
                        ${state.silentpassaEnabled ? '🔔 SilentPass' : '🔕 SilentPass'}
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
 * Toggle the SilentPass feature on/off and re-render the current view.
 * @param {string} viewType - 'chat', 'proposals', 'votes', or 'sessions'
 * @param {string} viewId - The ID relevant to re-render the correct detail view
 */
async function toggleSilentPass(viewType, viewId) {
    state.silentpassaEnabled = !state.silentpassaEnabled;
    localStorage.setItem('silentpassa', state.silentpassaEnabled ? 'on' : 'off');
    if (!viewId) return;
    switch (viewType) {
        case 'chat': await renderChatDetail(viewId); break;
        case 'proposals': await renderProposalDetail(viewId); break;
        case 'votes': await renderVoteDetail(viewId); break;
        case 'sessions': await renderCouncilSessionDetail(viewId); break;
    }
}
// Legacy alias
async function toggleSilentPassa(chatId) { return toggleSilentPass('chat', chatId); }

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
    lmstudio:   { name: 'LM Studio', icon: '🖥️', url: 'https://lmstudio.ai' },
};

// Model dropdown options (fetched from API, cached here)
let MANCER_MODEL_OPTIONS = ['Default'];
let OPENROUTER_MODEL_OPTIONS = ['Default'];
let LMSTUDIO_MODEL_OPTIONS = ['Default'];
let _modelOptionsLoaded = false;

/** Eagerly fetch model option lists from the API so they're available
 *  before the user visits any form (council, character, proposal). */
async function loadModelOptions() {
    if (_modelOptionsLoaded) return;
    try {
        const [mancer, openrouter, lmstudio] = await Promise.all([
            api('/api/settings/mancer-models').catch(() => ['Default']),
            api('/api/settings/openrouter-models').catch(() => ['Default']),
            api('/api/settings/lmstudio-models').catch(() => ['Default']),
        ]);
        if (mancer && mancer.length) MANCER_MODEL_OPTIONS = mancer;
        if (openrouter && openrouter.length) OPENROUTER_MODEL_OPTIONS = openrouter;
        if (lmstudio && lmstudio.length) LMSTUDIO_MODEL_OPTIONS = lmstudio;
        _modelOptionsLoaded = true;
    } catch (_) { /* silently degrade — will try again on Settings visit */ }
}

/** Return model options array for a given provider. */
function getModelOptionsForProvider(provider) {
    if (provider === 'mancer') return MANCER_MODEL_OPTIONS;
    if (provider === 'lmstudio') return LMSTUDIO_MODEL_OPTIONS;
    return OPENROUTER_MODEL_OPTIONS;
}

/** Render a model dropdown (or LM Studio info message) for a given provider.
 *  @param {string} selectId - the id for the <select> element
 *  @param {string} provider - 'openrouter' | 'mancer' | 'lmstudio'
 *  @param {string} currentModel - the currently selected model value
 *  @param {boolean} includeDefault - whether to include 'Default' as an option
 */
function renderModelField(selectId, provider, currentModel, includeDefault) {
    if (provider === 'lmstudio') {
        return `<div class="lmstudio-model-info" style="padding:var(--space-sm);background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);color:var(--text-secondary);font-size:0.85rem">
            🖥️ Model is selected in the LM Studio application
            <input type="hidden" id="${selectId}" value="Loaded Model" />
        </div>`;
    }
    const opts = getModelOptionsForProvider(provider);
    const filteredOpts = includeDefault ? opts : opts.filter(m => m !== 'Default');
    return `<select id="${selectId}" class="settings-input">
        ${filteredOpts.map(m => `<option value="${m}" ${currentModel === m || (!currentModel && m === 'Default') ? 'selected' : ''}>${m}</option>`).join('')}
    </select>`;
}

async function renderSettings() {
    showLoading();
    const [keys, models, userDescData, userNameData, mancerModels, openrouterModels, lmstudioModels] = await Promise.all([
        api('/api/settings/keys'),
        api('/api/settings/models'),
        api('/api/settings/user-description'),
        api('/api/settings/user-name').catch(() => ({ name: '' })),
        api('/api/settings/mancer-models').catch(() => ['Default']),
        api('/api/settings/openrouter-models').catch(() => ['Default']),
        api('/api/settings/lmstudio-models').catch(() => ['Default']),
    ]);

    // Cache model options for use in council member editing
    if (mancerModels && mancerModels.length) MANCER_MODEL_OPTIONS = mancerModels;
    if (openrouterModels && openrouterModels.length) OPENROUTER_MODEL_OPTIONS = openrouterModels;
    if (lmstudioModels && lmstudioModels.length) LMSTUDIO_MODEL_OPTIONS = lmstudioModels;

    const userDesc = userDescData.description || '';
    const userName = userNameData.name || '';
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
                        : k.provider === 'lmstudio'
                        ? `<select id="model-input-${k.provider}" class="settings-input">
                               ${lmstudioModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
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
                            <div class="settings-provider-name">About You</div>
                            <span class="settings-provider-link" style="cursor:default">Tell the AI council about yourself so they know who they're speaking with</span>
                        </div>
                    </div>
                </div>
                <div class="settings-form" style="margin-top:var(--space-sm)">
                    <div class="filter-group" style="margin-bottom:var(--space-md)">
                        <label for="user-name-input" class="user-desc-label">
                            Your Name
                            <span class="user-desc-hint">How the council members and characters will address you.</span>
                        </label>
                        <div class="settings-input-row">
                            <input id="user-name-input"
                                   class="settings-input"
                                   type="text"
                                   maxlength="100"
                                   placeholder="Enter your name…"
                                   value="${escapeHtml(userName)}" />
                            <button class="btn btn-primary" onclick="saveUserName()" id="user-name-save-btn">
                                💾 Save
                            </button>
                        </div>
                        <span id="user-name-status" style="font-size:0.82rem;color:var(--text-muted);margin-top:var(--space-xs);display:block"></span>
                    </div>
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

async function saveUserName() {
    const input = document.getElementById('user-name-input');
    const btn = document.getElementById('user-name-save-btn');
    const status = document.getElementById('user-name-status');
    const name = input.value.trim();

    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    try {
        const resp = await fetch('/api/settings/user-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Name saved ✅');
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

function obeliskBadge(balance) {
    if (!balance) return '';
    const parts = [];
    if (balance.gold)   parts.push(`<span class="obelisk-coin obelisk-gold">🥇 ${balance.gold}</span>`);
    if (balance.silver) parts.push(`<span class="obelisk-coin obelisk-silver">🥈 ${balance.silver}</span>`);
    if (balance.bronze) parts.push(`<span class="obelisk-coin obelisk-bronze">🥉 ${balance.bronze}</span>`);
    if (!parts.length)  parts.push(`<span class="obelisk-coin obelisk-empty">— empty —</span>`);
    return `<div class="obelisk-balance">${parts.join('')}</div>`;
}

function obeliskTotal(balance) {
    if (!balance) return '0.00';
    const rate = 100;
    const totalBronze = (balance.gold || 0) * rate * rate + (balance.silver || 0) * rate + (balance.bronze || 0);
    return (totalBronze / (rate * rate)).toFixed(2);
}

async function renderTreasury() {
    showLoading();
    const typeFilter = state._treasuryFilter || '';
    const url = typeFilter ? `/api/treasury?type=${encodeURIComponent(typeFilter)}` : '/api/treasury';
    const data = await api(url);

    const filterOptions = ['', 'council_member', 'character', 'user', 'government']
        .map(t => `<option value="${t}" ${t === typeFilter ? 'selected' : ''}>${t ? (ACCT_TYPE_LABELS[t]?.label || t) : 'All Types'}</option>`)
        .join('');

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div>
                        <h2>🪙 Treasury — Obelisk Accounts</h2>
                        <p>No treasury accounts found. Initialize to create default accounts.</p>
                    </div>
                    <div style="display:flex;gap:var(--space-sm)">
                        <select class="settings-input" style="min-width:140px" onchange="state._treasuryFilter=this.value;renderTreasury()" id="treasury-filter">${filterOptions}</select>
                        <button class="btn btn-primary" onclick="initializeTreasury()" id="btn-treasury-init">⚡ Initialize Treasury</button>
                    </div>
                </div>
                <div class="empty-state"><div class="empty-icon">🪙</div><p>Click "Initialize Treasury" to create accounts for all council members, characters, and the government.</p></div>
            </div>`;
        return;
    }

    const cards = data.map(a => {
        const meta = ACCT_TYPE_LABELS[a.account_type] || { icon: '💰', label: a.account_type, badge: 'default' };
        const total = obeliskTotal(a.balance);
        return `
        <div class="card card-clickable treasury-card" onclick="navigateTo('treasury','${a.account_id}')">
            <div class="treasury-card-header">
                <div class="treasury-card-icon">${meta.icon}</div>
                <div class="treasury-card-info">
                    <div class="treasury-card-owner">${escapeHtml(a.owner_name)}</div>
                    <div class="treasury-card-id">${a.account_id}</div>
                </div>
                ${badge(meta.label, meta.badge)}
            </div>
            ${obeliskBadge(a.balance)}
            <div class="treasury-card-total">≈ ${total} Gold equivalent</div>
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>🪙 Treasury — Obelisk Accounts</h2>
                    <p>${data.length} account${data.length !== 1 ? 's' : ''} across the Jericho economy</p>
                </div>
                <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">
                    <select class="settings-input" style="min-width:140px" onchange="state._treasuryFilter=this.value;renderTreasury()" id="treasury-filter">${filterOptions}</select>
                    <button class="btn btn-primary" onclick="initializeTreasury()" id="btn-treasury-init">⚡ Initialize</button>
                    <button class="btn btn-secondary" onclick="openTransferModal()" id="btn-treasury-transfer">💸 Transfer</button>
                </div>
            </div>
            <div class="treasury-grid">${cards}</div>
        </div>`;
}

async function renderTreasuryDetail(accountId) {
    showLoading();
    let data;
    try {
        data = await api(`/api/treasury/${encodeURIComponent(accountId)}`);
    } catch (err) {
        showError(`Account not found: ${accountId}`);
        return;
    }
    const meta = ACCT_TYPE_LABELS[data.account_type] || { icon: '💰', label: data.account_type, badge: 'default' };
    const total = obeliskTotal(data.balance);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('treasury')">← Back to Treasury</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.account_id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${meta.icon} ${escapeHtml(data.owner_name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            ${badge(meta.label, meta.badge)}
                            · Created ${formatDate(data.created_at)}
                            ${data.updated_at ? ` · Updated ${formatDate(data.updated_at)}` : ''}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('treasury')">✕</button>
                </div>

                <!-- Balance Display -->
                <div class="detail-section treasury-balance-panel">
                    <h4>💰 Obelisk Balance</h4>
                    <div class="treasury-balance-grid">
                        <div class="treasury-tier treasury-tier-gold">
                            <div class="treasury-tier-icon">🥇</div>
                            <div class="treasury-tier-value">${data.balance.gold}</div>
                            <div class="treasury-tier-label">Gold</div>
                        </div>
                        <div class="treasury-tier treasury-tier-silver">
                            <div class="treasury-tier-icon">🥈</div>
                            <div class="treasury-tier-value">${data.balance.silver}</div>
                            <div class="treasury-tier-label">Silver</div>
                        </div>
                        <div class="treasury-tier treasury-tier-bronze">
                            <div class="treasury-tier-icon">🥉</div>
                            <div class="treasury-tier-value">${data.balance.bronze}</div>
                            <div class="treasury-tier-label">Bronze</div>
                        </div>
                    </div>
                    <div class="treasury-total-display">≈ <strong>${total}</strong> Gold equivalent</div>
                </div>

                <!-- Credit Form -->
                <div class="detail-section">
                    <h4>➕ Credit Funds</h4>
                    <div class="treasury-action-form" id="credit-form">
                        <div class="treasury-input-row">
                            <div class="treasury-input-group">
                                <label>Gold</label>
                                <input type="number" id="credit-gold" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Silver</label>
                                <input type="number" id="credit-silver" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Bronze</label>
                                <input type="number" id="credit-bronze" class="settings-input" value="0" min="0" />
                            </div>
                            <button class="btn btn-primary" onclick="treasuryCredit('${data.account_id}')" id="btn-credit">➕ Credit</button>
                        </div>
                    </div>
                </div>

                <!-- Debit Form -->
                <div class="detail-section">
                    <h4>➖ Debit Funds</h4>
                    <div class="treasury-action-form" id="debit-form">
                        <div class="treasury-input-row">
                            <div class="treasury-input-group">
                                <label>Gold</label>
                                <input type="number" id="debit-gold" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Silver</label>
                                <input type="number" id="debit-silver" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Bronze</label>
                                <input type="number" id="debit-bronze" class="settings-input" value="0" min="0" />
                            </div>
                            <button class="btn btn-secondary" onclick="treasuryDebit('${data.account_id}')" id="btn-debit" style="border-color:var(--accent-rose)">➖ Debit</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
}

async function initializeTreasury() {
    const btn = document.getElementById('btn-treasury-init');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Initializing…'; }

    try {
        const resp = await fetch('/api/treasury/initialize', { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Treasury initialized — ${data.created_count} account${data.created_count !== 1 ? 's' : ''} created ✅`);
        await renderTreasury();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Initialize Treasury'; }
    }
}

async function treasuryCredit(accountId) {
    const gold   = parseInt(document.getElementById('credit-gold').value)   || 0;
    const silver = parseInt(document.getElementById('credit-silver').value) || 0;
    const bronze = parseInt(document.getElementById('credit-bronze').value) || 0;
    if (!gold && !silver && !bronze) { showToast('Enter an amount to credit.', true); return; }

    const btn = document.getElementById('btn-credit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }

    try {
        const resp = await fetch(`/api/treasury/${encodeURIComponent(accountId)}/credit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Credit failed' }));
            throw new Error(err.detail);
        }
        showToast(`Credited ${gold}G ${silver}S ${bronze}B ✅`);
        await renderTreasuryDetail(accountId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '➕ Credit'; }
    }
}

async function treasuryDebit(accountId) {
    const gold   = parseInt(document.getElementById('debit-gold').value)   || 0;
    const silver = parseInt(document.getElementById('debit-silver').value) || 0;
    const bronze = parseInt(document.getElementById('debit-bronze').value) || 0;
    if (!gold && !silver && !bronze) { showToast('Enter an amount to debit.', true); return; }

    const btn = document.getElementById('btn-debit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }

    try {
        const resp = await fetch(`/api/treasury/${encodeURIComponent(accountId)}/debit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Debit failed' }));
            throw new Error(err.detail);
        }
        showToast(`Debited ${gold}G ${silver}S ${bronze}B ✅`);
        await renderTreasuryDetail(accountId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '➖ Debit'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Taxation View (F-034)
// ═══════════════════════════════════════════════════════════════

async function renderTaxation() {
    showLoading();
    let summary, events;
    try {
        [summary, events] = await Promise.all([
            api('/api/tax/summary'),
            api('/api/tax/events?limit=50'),
        ]);
    } catch (err) {
        showError('Failed to load taxation data: ' + err.message);
        return;
    }

    const policy = summary.policy || {};
    const total = summary.total_collected || {};
    const ratePct = Math.round((policy.rate || 0) * 100);
    const exempt = (policy.exempt_account_types || []).join(', ') || 'none';

    const eventsRows = events.length
        ? events.map(e => `
            <tr>
                <td style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:var(--accent-cyan)">${escapeHtml(e.event_id)}</td>
                <td>${escapeHtml(e.from_account)}</td>
                <td>${escapeHtml(e.to_account)}</td>
                <td>${obeliskBadge({gold: e.transaction_gold, silver: e.transaction_silver, bronze: e.transaction_bronze})}</td>
                <td>${obeliskBadge({gold: e.tax_gold, silver: e.tax_silver, bronze: e.tax_bronze})}</td>
                <td>${Math.round(e.tax_rate * 100)}%</td>
                <td style="font-size:0.8rem;color:var(--text-muted)">${formatDate(e.timestamp)}</td>
            </tr>`).join('')
        : '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:var(--space-lg)">No tax events recorded yet. Tax is collected automatically on transfers between non-exempt accounts.</td></tr>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🏛️ Taxation — Obelisk Tax System</h2>
                <p>Government tax policy and collection ledger</p>
            </div>

            <div class="tax-panels-grid">
                <!-- Policy Panel -->
                <div class="card tax-policy-panel">
                    <h3>📋 Tax Policy</h3>
                    <div class="tax-policy-fields">
                        <div class="tax-field">
                            <label>Status</label>
                            <div class="tax-toggle-row">
                                <span class="badge badge-${policy.enabled ? 'active' : 'archived'}">${policy.enabled ? 'Enabled' : 'Disabled'}</span>
                                <button class="btn btn-sm" onclick="toggleTaxEnabled(${!policy.enabled})" id="btn-tax-toggle">
                                    ${policy.enabled ? '⏸ Disable' : '▶ Enable'}
                                </button>
                            </div>
                        </div>
                        <div class="tax-field">
                            <label for="tax-rate-slider">Tax Rate: <strong id="tax-rate-display">${ratePct}%</strong></label>
                            <div class="tax-rate-slider-row">
                                <input type="range" id="tax-rate-slider" class="tax-rate-slider" min="0" max="50" value="${ratePct}"
                                    oninput="document.getElementById('tax-rate-display').textContent = this.value + '%'" />
                                <button class="btn btn-sm btn-primary" onclick="updateTaxRate()" id="btn-tax-rate">Save</button>
                            </div>
                        </div>
                        <div class="tax-field">
                            <label>Exempt Account Types</label>
                            <div class="tax-exempt-list">
                                ${(policy.exempt_account_types || ['government']).map(t => `<span class="tax-exempt-badge">${t}</span>`).join('')}
                            </div>
                        </div>
                        <div class="tax-field" style="margin-top:var(--space-xs)">
                            <span style="font-size:0.78rem;color:var(--text-muted)">Last updated: ${formatDate(policy.updated_at)}</span>
                        </div>
                    </div>
                </div>

                <!-- Revenue Summary -->
                <div class="card tax-revenue-panel">
                    <h3>💰 Revenue Summary</h3>
                    <div class="tax-revenue-stats">
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${summary.event_count || 0}</div>
                            <div class="tax-rev-label">Total Events</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.gold || 0}</div>
                            <div class="tax-rev-label">🥇 Gold Collected</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.silver || 0}</div>
                            <div class="tax-rev-label">🥈 Silver Collected</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.bronze || 0}</div>
                            <div class="tax-rev-label">🥉 Bronze Collected</div>
                        </div>
                    </div>
                    ${obeliskBadge(total)}
                    <div class="treasury-total-display" style="margin-top:var(--space-sm)">≈ <strong>${obeliskTotal(total)}</strong> Gold equivalent total tax revenue</div>
                </div>
            </div>

            <!-- Tax Events Log -->
            <div class="card" style="margin-top:var(--space-lg)">
                <h3>📜 Tax Collection Ledger</h3>
                <div class="table-container">
                    <table class="data-table tax-events-table">
                        <thead>
                            <tr>
                                <th>Event ID</th>
                                <th>From</th>
                                <th>To</th>
                                <th>Transaction</th>
                                <th>Tax Collected</th>
                                <th>Rate</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>${eventsRows}</tbody>
                    </table>
                </div>
            </div>
        </div>`;
}

async function toggleTaxEnabled(enabled) {
    const btn = document.getElementById('btn-tax-toggle');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
        await fetch('/api/tax/policy', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        showToast(enabled ? 'Tax collection enabled ✅' : 'Tax collection disabled ⏸');
        await renderTaxation();
    } catch (err) {
        showToast('Failed: ' + err.message, true);
        if (btn) { btn.disabled = false; }
    }
}

async function updateTaxRate() {
    const slider = document.getElementById('tax-rate-slider');
    const btn = document.getElementById('btn-tax-rate');
    if (!slider) return;
    const rate = parseInt(slider.value, 10) / 100;
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
        const resp = await fetch('/api/tax/policy', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rate }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({detail: 'Failed'}));
            throw new Error(err.detail);
        }
        showToast(`Tax rate updated to ${slider.value}% ✅`);
        await renderTaxation();
    } catch (err) {
        showToast('Failed: ' + err.message, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
    }
}

// ── Transfer Modal ──────────────────────────────────────────────

async function openTransferModal() {
    try {
        const accounts = await api('/api/treasury');
        if (accounts.length < 2) {
            showToast('Need at least 2 accounts for a transfer.', true);
            return;
        }

        const optionsHtml = accounts.map(a => {
            const meta = ACCT_TYPE_LABELS[a.account_type] || { label: a.account_type };
            return `<option value="${a.account_id}">${a.owner_name} (${meta.label}) — ${a.balance.gold}G ${a.balance.silver}S ${a.balance.bronze}B</option>`;
        }).join('');

        const existing = document.getElementById('transfer-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'transfer-modal';
        modal.className = 'promote-modal';
        modal.style.display = 'flex';
        modal.innerHTML = `
            <div class="promote-modal-content" style="max-width:520px">
                <div class="promote-modal-header">
                    <h3>💸 Transfer Obelisk</h3>
                    <button class="detail-close" onclick="closeTransferModal()">✕</button>
                </div>
                <div class="promote-modal-body">
                    <div class="promote-form-group">
                        <label for="xfer-from">From Account</label>
                        <select id="xfer-from" class="settings-input">${optionsHtml}</select>
                    </div>
                    <div class="promote-form-group">
                        <label for="xfer-to">To Account</label>
                        <select id="xfer-to" class="settings-input">${optionsHtml}</select>
                    </div>
                    <div class="treasury-input-row" style="margin-top:var(--space-sm)">
                        <div class="treasury-input-group">
                            <label>Gold</label>
                            <input type="number" id="xfer-gold" class="settings-input" value="0" min="0" />
                        </div>
                        <div class="treasury-input-group">
                            <label>Silver</label>
                            <input type="number" id="xfer-silver" class="settings-input" value="0" min="0" />
                        </div>
                        <div class="treasury-input-group">
                            <label>Bronze</label>
                            <input type="number" id="xfer-bronze" class="settings-input" value="0" min="0" />
                        </div>
                    </div>
                </div>
                <div class="promote-modal-footer">
                    <button class="btn" onclick="closeTransferModal()">Cancel</button>
                    <button class="btn btn-primary" onclick="executeTransfer()" id="btn-xfer-submit">💸 Transfer</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => { if (e.target === modal) closeTransferModal(); });

        // Auto-select different to-account
        if (accounts.length >= 2) {
            document.getElementById('xfer-to').selectedIndex = 1;
        }
    } catch (err) {
        showToast('Failed to load accounts: ' + err.message, true);
    }
}

function closeTransferModal() {
    const modal = document.getElementById('transfer-modal');
    if (modal) modal.remove();
}

async function executeTransfer() {
    const fromId = document.getElementById('xfer-from').value;
    const toId   = document.getElementById('xfer-to').value;
    const gold   = parseInt(document.getElementById('xfer-gold').value)   || 0;
    const silver = parseInt(document.getElementById('xfer-silver').value) || 0;
    const bronze = parseInt(document.getElementById('xfer-bronze').value) || 0;

    if (fromId === toId) { showToast('Cannot transfer to the same account.', true); return; }
    if (!gold && !silver && !bronze) { showToast('Enter an amount to transfer.', true); return; }

    const btn = document.getElementById('btn-xfer-submit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Transferring…'; }

    try {
        const resp = await fetch('/api/treasury/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from: fromId, to: toId, gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Transfer failed' }));
            throw new Error(err.detail);
        }
        showToast(`Transferred ${gold}G ${silver}S ${bronze}B ✅`);
        closeTransferModal();
        await renderTreasury();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💸 Transfer'; }
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

// ═══════════════════════════════════════════════════════════════
// Council Sessions View
// ═══════════════════════════════════════════════════════════════

async function renderCouncilSessions() {
    showLoading();
    const data = await api('/api/council-sessions');

    // Fetch council members for the author selector
    let members = [];
    try { members = await api('/api/council'); } catch { /* empty */ }

    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general', 'evolution', 'law']
        .map(c => `<option value="${c}" ${c === 'governance' ? 'selected' : ''}>${c.charAt(0).toUpperCase() + c.slice(1)}</option>`)
        .join('');

    const rows = data.map(s => {
        const statusClass = s.status === 'closed' ? 'badge-active' : 'badge-open';
        return `
        <tr class="proposal-row" onclick="navigateTo('sessions','${s.session_id}')">
            <td class="col-id">${s.session_id}</td>
            <td class="col-title">${truncate(s.title, 50)}</td>
            <td>${truncate(s.topic, 40)}</td>
            <td>${badge(s.status)}</td>
            <td>${s.current_round}/${s.round_count}</td>
            <td>${(s.contributions || []).length}</td>
            <td>${formatDate(s.created_at)}</td>
        </tr>`;
    }).join('');

    const tableHtml = data.length ? `
        <div class="table-wrapper">
            <table class="data-table" id="sessions-table">
                <thead>
                    <tr>
                        <th>ID</th><th>Title</th><th>Topic</th>
                        <th>Status</th><th>Rounds</th><th>Contributions</th><th>Created</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>` : '<div class="empty-state"><div class="empty-icon">🏛️</div><p>No council sessions yet. Start one below!</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🏛️ Council Sessions</h2>
                <p>${data.length} council session${data.length !== 1 ? 's' : ''}</p>
            </div>

            <div class="proposal-form card">
                <h3>📋 New Council Session</h3>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                    Open a new deliberation session for the full council. Sessions can later be handed off as proposals.
                </p>
                <div class="proposal-form-grid">
                    <div class="filter-group" style="flex:2">
                        <label for="session-title-input">Session Title</label>
                        <input id="session-title-input" class="settings-input" placeholder="e.g. Ethics Framework Review" />
                    </div>
                    <div class="filter-group">
                        <label for="session-category-select">Proposal Category</label>
                        <select id="session-category-select" class="settings-input">
                            ${categoryOptions}
                        </select>
                        <span style="font-size:0.72rem;color:var(--text-muted);margin-top:2px">Used if session becomes a proposal</span>
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="session-topic-input">Topic</label>
                    <textarea id="session-topic-input" class="settings-input proposal-textarea" rows="2"
                        placeholder="What should the council discuss? This will frame the deliberation…"></textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="session-agenda-input">Agenda <span style="font-weight:400;font-size:0.78rem;color:var(--text-muted)">(optional)</span></label>
                    <textarea id="session-agenda-input" class="settings-input proposal-textarea" rows="2"
                        placeholder="Key points or questions to address…"></textarea>
                </div>

                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="createNewSession()" id="session-create-btn">
                        🚀 Start Session
                    </button>
                    <span id="session-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>

            ${tableHtml}
        </div>`;
}

async function createNewSession() {
    const title = document.getElementById('session-title-input').value.trim();
    const topic = document.getElementById('session-topic-input').value.trim();
    const agenda = document.getElementById('session-agenda-input').value.trim();
    const category = document.getElementById('session-category-select').value;
    const btn = document.getElementById('session-create-btn');
    const status = document.getElementById('session-create-status');

    if (!title) { document.getElementById('session-title-input').focus(); return; }
    if (!topic) { document.getElementById('session-topic-input').focus(); return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = 'Setting up council session…';

    try {
        const resp = await fetch('/api/council-sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, topic, agenda, category }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create session' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Session ${data.session_id} created ✅`);
        navigateTo('sessions', data.session_id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Start Session';
    }
}

async function renderCouncilSessionDetail(id) {
    showLoading();
    const data = await api(`/api/council-sessions/${encodeURIComponent(id)}`);

    // Fetch council members for avatars
    let sessionMembers = [];
    try { sessionMembers = await api('/api/council'); } catch { /* empty */ }
    const sessionAvatarMap = {};
    sessionMembers.forEach(m => { if (m.avatar_url) sessionAvatarMap[m.name.toLowerCase()] = m.avatar_url; });
    state.sessionAvatarMap = sessionAvatarMap;

    const isOpen = data.status === 'open';
    const isClosed = data.status === 'closed';
    const roundsLeft = data.round_count - data.current_round;

    // Category options for the handoff form
    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general', 'evolution', 'law']
        .map(c => `<option value="${c}" ${c === data.proposed_category ? 'selected' : ''}>${c.charAt(0).toUpperCase() + c.slice(1)}</option>`)
        .join('');

    // Author options for the handoff form
    const authorOptions = sessionMembers.map(m =>
        `<option value="${m.name}" ${data.participants && data.participants[0] === m.name ? 'selected' : ''}>${m.name} — ${m.role}</option>`
    ).join('');

    // Discussion feed
    let discussionFeedHtml = '';
    if (data.contributions && data.contributions.length) {
        const contribs = data.contributions.map(c => {
            const memberIdx = (data.participants || []).indexOf(c.speaker);
            const renderedContent = renderMarkdown(c.content);
            const displayContent = state.silentpassaEnabled ? wrapPresenceContent(renderedContent, c.speaker) : renderedContent;
            return `
            <div class="discussion-message">
                <div class="discussion-message-header">
                    ${memberAvatarWithImage(c.speaker, memberIdx >= 0 ? memberIdx : 0, null, sessionAvatarMap[c.speaker.toLowerCase()])}
                    <div>
                        <span class="discussion-speaker">${c.speaker}</span>
                        <span class="discussion-round">Round ${c.round_number}</span>
                    </div>
                </div>
                <div class="discussion-content">${displayContent}</div>
            </div>`;
        }).join('');
        discussionFeedHtml = `
            <div class="detail-section">
                <h4>💬 Council Deliberation (${data.contributions.length} contributions, Round ${data.current_round}/${data.round_count})</h4>
                <div class="discussion-feed" id="session-discussion-feed">${contribs}</div>
            </div>`;
    } else {
        discussionFeedHtml = `
            <div class="detail-section">
                <h4>💬 Council Deliberation</h4>
                <div class="discussion-feed" id="session-discussion-feed">
                    <div class="empty-state" style="padding:var(--space-lg)"><div class="empty-icon">💬</div><p>No contributions yet. Start a discussion round!</p></div>
                </div>
            </div>`;
    }

    // Summary (when closed)
    let summaryHtml = '';
    if (isClosed && data.summary) {
        summaryHtml = `
            <div class="detail-section">
                <h4>📋 Session Summary</h4>
                <p style="color:var(--text-secondary)">${renderMarkdown(data.summary)}</p>
            </div>`;
    }

    // Action buttons
    let actionsHtml = '';
    if (isOpen) {
        const buttons = [];
        if (roundsLeft > 0) {
            buttons.push(`<button class="btn btn-primary" onclick="runSessionRound('${id}')" id="session-discuss-btn">▶️ Continue Discussion (${roundsLeft} left)</button>`);
        }
        buttons.push(`<button class="btn btn-secondary" onclick="closeSession('${id}')" id="session-close-btn">⏹️ Close Session</button>`);
        actionsHtml = `<div class="proposal-actions">${buttons.join('')}</div>`;
    }

    // Scheduled message section (only when session is open)
    let scheduledMsgHtml = '';
    if (isOpen) {
        let existingMsg = '';
        try {
            const smResp = await api(`/api/council-sessions/${encodeURIComponent(id)}/scheduled-message`);
            if (smResp && smResp.message) existingMsg = smResp.message;
        } catch { /* no scheduled message */ }

        scheduledMsgHtml = `
            <div class="detail-section scheduled-message-section">
                <h4>📨 Schedule Message for Next Round</h4>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-sm)">
                    This message will be injected into the session at the start of the next round, before the council members speak.
                </p>
                <textarea id="session-scheduled-msg-input" class="settings-input scheduled-message-textarea"
                    rows="3" placeholder="Type your message for the council to consider…">${existingMsg ? escapeHtml(existingMsg) : ''}</textarea>
                <div style="display:flex;gap:var(--space-sm);align-items:center;margin-top:var(--space-sm)">
                    <button class="btn btn-primary btn-sm" onclick="scheduleSessionMessage('${id}')" id="session-schedule-msg-btn">
                        📨 Schedule Message
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="clearSessionScheduledMessage('${id}')" id="session-clear-msg-btn">
                        🗑️ Clear
                    </button>
                    <span id="session-scheduled-msg-status" style="font-size:0.78rem;color:var(--text-muted)">
                        ${existingMsg ? '✅ Message scheduled' : ''}
                    </span>
                </div>
            </div>`;
    }

    // Handoff panel (shown when session is closed)
    let handoffHtml = '';
    if (isClosed) {
        handoffHtml = `
            <div class="detail-section session-handoff-panel">
                <h4>📜 Create Proposal from Session</h4>
                <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:var(--space-md)">
                    Hand off this session's deliberation into a formal proposal. Edit the fields below before creating.
                </p>
                <div class="proposal-form-grid">
                    <div class="filter-group">
                        <label for="handoff-author">Author</label>
                        <select id="handoff-author" class="settings-input">
                            ${authorOptions}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="handoff-category">Category</label>
                        <select id="handoff-category" class="settings-input">
                            ${categoryOptions}
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <label for="handoff-title">Proposal Title</label>
                        <input id="handoff-title" class="settings-input" value="${escapeAttr(data.proposed_title || data.title)}" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="handoff-desc">Proposal Description</label>
                    <textarea id="handoff-desc" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.proposed_description || data.topic)}</textarea>
                </div>
                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="handoffSessionToProposal('${id}')" id="session-handoff-btn"
                        style="background:linear-gradient(135deg, hsl(210,70%,50%), hsl(170,60%,45%))">
                        📜 Create Proposal
                    </button>
                    <span id="session-handoff-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>`;
    }

    // Participants
    const participantsHtml = (data.participants || []).map((name, i) =>
        `<span class="specialty-tag">${name}</span>`
    ).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('sessions')">← Back to Sessions</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.session_id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.title)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            ${formatDate(data.created_at)}
                            ${data.closed_at ? ` · Closed ${formatDate(data.closed_at)}` : ''}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${badge(data.proposed_category)}
                        </div>
                    </div>
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPass('sessions','${id}')" title="Toggle [PRESENT]/[SILENCE] wrappers">
                            ${state.silentpassaEnabled ? '🔔 SilentPass' : '🔕 SilentPass'}
                        </button>
                        <button class="detail-close" onclick="navigateTo('sessions')">✕</button>
                    </div>
                </div>

                ${actionsHtml}
                ${scheduledMsgHtml}

                <div class="detail-section">
                    <h4>Topic</h4>
                    <p>${renderMarkdown(data.topic)}</p>
                </div>

                ${data.agenda ? `<div class="detail-section"><h4>Agenda</h4><div style="white-space:pre-wrap">${renderMarkdown(data.agenda)}</div></div>` : ''}

                <div class="detail-section">
                    <h4>Participants (${(data.participants || []).length})</h4>
                    <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">${participantsHtml}</div>
                </div>

                ${discussionFeedHtml}
                ${summaryHtml}
                ${handoffHtml}
            </div>
        </div>`;
}

async function runSessionRound(sessionId) {
    const btn = document.getElementById('session-discuss-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Council is deliberating…'; }

    const feed = document.getElementById('session-discussion-feed');
    if (feed) {
        const emptyState = feed.querySelector('.empty-state');
        if (emptyState) emptyState.remove();
    }

    try {
        const resp = await fetch(`/api/council-sessions/${encodeURIComponent(sessionId)}/discuss-stream`, {
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
                            const isUser = data.speaker === 'User';
                            const msgDiv = document.createElement('div');
                            msgDiv.className = `discussion-message discussion-message-enter${isUser ? ' discussion-message-user' : ''}`;
                            msgDiv.innerHTML = `
                                <div class="discussion-message-header">
                                    ${isUser
                                        ? `<div class="member-avatar" style="background:linear-gradient(135deg, hsl(45,80%,55%), hsl(35,90%,50%))">👤</div>`
                                        : memberAvatarWithImage(data.speaker, 0, null, state.sessionAvatarMap && state.sessionAvatarMap[data.speaker.toLowerCase()])}
                                    <div>
                                        <span class="discussion-speaker">${data.speaker}</span>
                                        <span class="discussion-round">Round ${data.round}</span>
                                    </div>
                                </div>
                                <div class="discussion-content">${state.silentpassaEnabled ? wrapPresenceContent(renderMarkdown(data.content), data.speaker) : renderMarkdown(data.content)}</div>`;
                            feed.appendChild(msgDiv);
                            feed.scrollTop = feed.scrollHeight;

                            // Clear scheduled message status after it's been consumed
                            if (isUser) {
                                const statusEl = document.getElementById('session-scheduled-msg-status');
                                if (statusEl) statusEl.textContent = '✅ Delivered this round';
                                const inputEl = document.getElementById('session-scheduled-msg-input');
                                if (inputEl) inputEl.value = '';
                            }
                        } else if (eventType === 'error') {
                            showToast(data.detail || 'Session error', true);
                        }
                    } catch { /* invalid JSON line */ }
                    eventType = 'message';
                }
            }
        }

        showToast('Discussion round complete ✅');
        setTimeout(() => renderCouncilSessionDetail(sessionId), 500);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '▶️ Continue Discussion'; }
    }
}

async function scheduleSessionMessage(sessionId) {
    const input = document.getElementById('session-scheduled-msg-input');
    const message = (input && input.value || '').trim();
    if (!message) { if (input) input.focus(); return; }

    const btn = document.getElementById('session-schedule-msg-btn');
    const status = document.getElementById('session-scheduled-msg-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const resp = await fetch(`/api/council-sessions/${encodeURIComponent(sessionId)}/scheduled-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to schedule' }));
            throw new Error(err.detail);
        }
        showToast('Message scheduled for next round 📨');
        if (status) status.textContent = '✅ Message scheduled';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📨 Schedule Message'; }
    }
}

async function clearSessionScheduledMessage(sessionId) {
    const btn = document.getElementById('session-clear-msg-btn');
    const status = document.getElementById('session-scheduled-msg-status');
    const input = document.getElementById('session-scheduled-msg-input');
    if (btn) { btn.disabled = true; }

    try {
        const resp = await fetch(`/api/council-sessions/${encodeURIComponent(sessionId)}/scheduled-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '' }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to clear' }));
            throw new Error(err.detail);
        }
        if (input) input.value = '';
        if (status) status.textContent = '';
        showToast('Scheduled message cleared 🗑️');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; }
    }
}

async function closeSession(sessionId) {
    if (!confirm('Close this council session? You can create a proposal from it afterwards.')) return;
    const btn = document.getElementById('session-close-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Closing…'; }

    try {
        const resp = await fetch(`/api/council-sessions/${encodeURIComponent(sessionId)}/close`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to close' }));
            throw new Error(err.detail);
        }
        showToast('Session closed ⏹️');
        await renderCouncilSessionDetail(sessionId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⏹️ Close Session'; }
    }
}

async function handoffSessionToProposal(sessionId) {
    const btn = document.getElementById('session-handoff-btn');
    const statusEl = document.getElementById('session-handoff-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating proposal…'; }

    const title = (document.getElementById('handoff-title').value || '').trim();
    const description = (document.getElementById('handoff-desc').value || '').trim();
    const category = document.getElementById('handoff-category').value;
    const author = document.getElementById('handoff-author').value;

    if (!title) { document.getElementById('handoff-title').focus(); btn.disabled = false; btn.textContent = '📜 Create Proposal'; return; }
    if (!description) { document.getElementById('handoff-desc').focus(); btn.disabled = false; btn.textContent = '📜 Create Proposal'; return; }

    try {
        const resp = await fetch(`/api/council-sessions/${encodeURIComponent(sessionId)}/handoff-proposal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, category, author }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Proposal ${data.id} created from session ✅`);
        navigateTo('proposals', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (statusEl) statusEl.textContent = '';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📜 Create Proposal'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Laws View
// ═══════════════════════════════════════════════════════════════

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

async function renderSettings() {
    const currentSkin = state.activeSkin || 'default';

    // Build skin cards
    const skinCards = Object.entries(SKINS).map(([key, skin]) => {
        const isActive = key === currentSkin;
        const swatches = (skin.swatches || []).map(c =>
            `<div class="swatch" style="background:${c}"></div>`
        ).join('');
        return `
            <div class="skin-card ${isActive ? 'active' : ''}" onclick="selectSkin('${key}')" id="skin-card-${key}">
                <div class="skin-card-preview">${swatches}</div>
                <div class="skin-card-body">
                    <div class="skin-card-icon">${skin.icon}</div>
                    <div class="skin-card-label">${skin.label}</div>
                    <div class="skin-card-desc">${skin.desc || ''}</div>
                </div>
            </div>`;
    }).join('');

    // Fetch all settings data in parallel
    let keysData = [], modelsData = [], mancerModels = [], openrouterModels = [], lmstudioModels = [];
    let userDesc = '';
    let userName = '';
    try {
        const [keys, models, mm, orm, lmsm, ud, un] = await Promise.all([
            api('/api/settings/keys'),
            api('/api/settings/models'),
            api('/api/settings/mancer-models'),
            api('/api/settings/openrouter-models'),
            api('/api/settings/lmstudio-models').catch(() => []),
            api('/api/settings/user-description'),
            api('/api/settings/user-name').catch(() => ({ name: '' })),
        ]);
        keysData = keys;
        modelsData = models;
        mancerModels = mm;
        openrouterModels = orm;
        lmstudioModels = lmsm;
        userDesc = ud.description || '';
        userName = (un && un.name) || '';
    } catch { /* endpoints may not be available */ }

    // Build provider sections (OpenRouter + Mancer)
    const providers = [
        { id: 'openrouter', label: 'OpenRouter', icon: '🌐', models: openrouterModels },
        { id: 'mancer', label: 'Mancer', icon: '⚡', models: mancerModels },
        { id: 'lmstudio', label: 'LM Studio', icon: '🖥️', models: lmstudioModels },
    ];

    const providerSections = providers.map(prov => {
        const keyInfo = keysData.find(k => k.provider === prov.id) || {};
        const modelInfo = modelsData.find(m => m.provider === prov.id) || {};
        const hasKey = keyInfo.configured || false;
        const maskedKey = keyInfo.masked || '';
        const currentModel = modelInfo.model || modelInfo.default_model || '';

        const modelOptions = prov.models.map(m =>
            `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${m}</option>`
        ).join('');

        return `
            <div class="settings-provider-card">
                <div class="settings-provider-header">
                    <span class="settings-provider-icon">${prov.icon}</span>
                    <span class="settings-provider-name">${prov.label}</span>
                    <span class="badge ${hasKey ? 'badge-active' : 'badge-draft'}">${hasKey ? 'CONFIGURED' : 'NOT SET'}</span>
                </div>

                <div class="settings-field-group">
                    <label>API Key</label>
                    <div class="settings-key-row">
                        <input type="password" id="settings-key-${prov.id}" class="settings-input"
                               placeholder="${hasKey ? maskedKey : 'Enter API key…'}"
                               autocomplete="off" />
                        <button class="btn btn-primary btn-sm" onclick="saveSettingsKey('${prov.id}')">Save</button>
                        ${hasKey ? `<button class="btn btn-sm" onclick="deleteSettingsKey('${prov.id}')" title="Remove key">🗑️</button>` : ''}
                    </div>
                </div>

                <div class="settings-field-group">
                    <label>Default Model</label>
                    <div class="settings-key-row">
                        <select id="settings-model-${prov.id}" class="settings-input">
                            ${modelOptions}
                        </select>
                        <button class="btn btn-primary btn-sm" onclick="saveSettingsModel('${prov.id}')">Save</button>
                    </div>
                    <span class="settings-field-hint">Members set to "Default" will use this model</span>
                </div>
            </div>`;
    }).join('');

    // SilentPass toggle
    const silentpassOn = state.silentpassaEnabled;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Settings</h2>
                <p>Configure your profile, API providers, models, appearance, and preferences</p>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">👤 About You</div>
                <div class="settings-provider-card">
                    <div class="settings-field-group">
                        <label>Your Name</label>
                        <div class="settings-key-row">
                            <input type="text" id="settings-user-name" class="settings-input"
                                   maxlength="100"
                                   placeholder="Enter your name…"
                                   value="${escapeHtml(userName)}" />
                            <button class="btn btn-primary btn-sm" onclick="saveSettingsUserName()">💾 Save</button>
                        </div>
                        <span class="settings-field-hint">How the council members and characters will address you</span>
                    </div>
                    <div class="settings-field-group">
                        <label>User Description</label>
                        <textarea id="settings-user-desc" class="settings-input settings-textarea"
                                  rows="4" maxlength="700"
                                  placeholder="Tell the AI council about yourself — this context is shared in chats…">${escapeHtml(userDesc)}</textarea>
                        <div class="settings-key-row" style="margin-top:var(--space-sm)">
                            <span class="settings-field-hint" id="settings-desc-count">${userDesc.length}/700</span>
                            <button class="btn btn-primary btn-sm" onclick="saveSettingsUserDesc()">💾 Save</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🔑 API Providers & Models</div>
                <div class="settings-providers-grid">${providerSections}</div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🎨 Appearance — Skin</div>
                <div class="settings-skin-grid">${skinCards}</div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">💬 Chat Features</div>
                <div class="settings-info-grid">
                    <div class="settings-info-card settings-toggle-card" onclick="toggleSilentPassSettings()" style="cursor:pointer">
                        <div class="settings-info-label">SilentPass</div>
                        <div class="settings-info-value">
                            <span class="badge ${silentpassOn ? 'badge-active' : 'badge-draft'}">${silentpassOn ? 'ON' : 'OFF'}</span>
                        </div>
                        <div class="settings-info-hint">Presence/Silence output wrappers</div>
                    </div>
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🎨 ComfyUI — Image Generation</div>
                <div id="comfyui-settings-container"></div>
            </div>
        </div>`;

    // Wire up character counter
    const descEl = document.getElementById('settings-user-desc');
    if (descEl) {
        descEl.addEventListener('input', () => {
            const cnt = document.getElementById('settings-desc-count');
            if (cnt) cnt.textContent = `${descEl.value.length}/700`;
        });
    }

    // Lazy-load ComfyUI settings section
    loadComfyUISettings();
}

function selectSkin(name) {
    applySkin(name);
    renderSettings();
}

function toggleSilentPassSettings() {
    state.silentpassaEnabled = !state.silentpassaEnabled;
    localStorage.setItem('silentpassa', state.silentpassaEnabled ? 'on' : 'off');
    renderSettings();
}

async function saveSettingsKey(provider) {
    const input = document.getElementById(`settings-key-${provider}`);
    const key = input?.value?.trim();
    if (!key) return;
    try {
        await fetch('/api/settings/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: key }),
        });
        input.value = '';
        renderSettings();
    } catch (err) {
        alert('Failed to save key: ' + err.message);
    }
}

async function deleteSettingsKey(provider) {
    if (!confirm(`Remove ${provider} API key?`)) return;
    try {
        await fetch(`/api/settings/keys/${provider}`, { method: 'DELETE' });
        renderSettings();
    } catch (err) {
        alert('Failed to remove key: ' + err.message);
    }
}

async function saveSettingsModel(provider) {
    const select = document.getElementById(`settings-model-${provider}`);
    const model = select?.value;
    if (!model) return;
    try {
        await fetch('/api/settings/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, model }),
        });
        renderSettings();
    } catch (err) {
        alert('Failed to save model: ' + err.message);
    }
}

async function saveSettingsUserDesc() {
    const el = document.getElementById('settings-user-desc');
    const description = el?.value || '';
    try {
        await fetch('/api/settings/user-description', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description }),
        });
        renderSettings();
    } catch (err) {
        alert('Failed to save: ' + err.message);
    }
}

async function saveSettingsUserName() {
    const el = document.getElementById('settings-user-name');
    const name = el?.value?.trim() || '';
    try {
        const resp = await fetch('/api/settings/user-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        renderSettings();
    } catch (err) {
        alert('Failed to save name: ' + err.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// ComfyUI Settings Helpers (F-037d)
// ═══════════════════════════════════════════════════════════════

let _comfyuiPendingWorkflowJson = null;
let _comfyuiPendingFilename = '';
let _comfyuiExpandedTemplate = null;

async function loadComfyUISettings() {
    const container = document.getElementById('comfyui-settings-container');
    if (!container) return;

    let configData = { host: '127.0.0.1', port: 8188 };
    let templates = [];
    let presets = [];
    let defaultStyle = '';
    let templateAssignments = { character: '', location: '', item: '', store: '' };

    try {
        const [cfg, tpls, prsts, ds, assigns] = await Promise.all([
            api('/api/settings/comfyui').catch(() => ({ host: '127.0.0.1', port: 8188 })),
            api('/api/settings/comfyui/templates').catch(() => []),
            api('/api/settings/comfyui/style-presets').catch(() => []),
            api('/api/settings/comfyui/default-style').catch(() => ({ style_key: '' })),
            api('/api/settings/comfyui/template-assignments').catch(() => ({ character: '', location: '', item: '', store: '' })),
        ]);
        configData = cfg;
        templates = tpls;
        presets = prsts;
        defaultStyle = ds.style_key || '';
        templateAssignments = assigns;
    } catch { /* endpoints may not be available */ }

    // ── Connection Config ─────────────
    const presetOptions = presets.map(p =>
        `<option value="${escapeAttr(p.name)}" ${p.name === defaultStyle || p.name.toLowerCase().replace(/ /g, '_') === defaultStyle ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
    ).join('');

    // ── Template List ─────────────────
    let templateListHtml;
    if (templates.length === 0) {
        templateListHtml = `
            <div class="comfyui-empty">
                <div class="comfyui-empty-icon">📄</div>
                <p>No workflow templates uploaded yet.</p>
            </div>`;
    } else {
        templateListHtml = templates.map(t => {
            const placeholderTags = (t.placeholders || []).map(p =>
                `<span class="comfyui-placeholder-tag">${escapeHtml(p)}</span>`
            ).join(' ');
            const entityBadge = t.entity_type
                ? `<span class="badge badge-active" style="font-size:0.68rem">${escapeHtml(t.entity_type)}</span>`
                : '';
            const isExpanded = _comfyuiExpandedTemplate === t.id;
            return `
                <div class="comfyui-template-card" onclick="toggleComfyUITemplateDetail('${t.id}')">
                    <span class="comfyui-template-id">${t.id}</span>
                    <div class="comfyui-template-info">
                        <div class="comfyui-template-name">${escapeHtml(t.name)}</div>
                        <div class="comfyui-template-meta">
                            ${entityBadge}
                            ${placeholderTags || '<span style="color:var(--text-muted)">no placeholders</span>'}
                            ${t.author ? `<span>by ${escapeHtml(t.author)}</span>` : ''}
                        </div>
                    </div>
                    <div class="comfyui-template-actions">
                        <button class="btn btn-sm" onclick="event.stopPropagation(); deleteComfyUITemplate('${t.id}', '${escapeAttr(t.name)}')" title="Delete template">🗑️</button>
                    </div>
                </div>
                ${isExpanded ? `<div class="comfyui-template-detail" id="comfyui-detail-${t.id}"><em>Loading…</em></div>` : ''}`;
        }).join('');
    }

    container.innerHTML = `
        <div class="settings-provider-card">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">🖥️</span>
                <span class="settings-provider-name">Connection</span>
            </div>
            <div class="comfyui-config-row">
                <div class="settings-field-group">
                    <label>Host</label>
                    <input type="text" id="comfyui-host" class="settings-input" value="${escapeAttr(configData.host)}" placeholder="127.0.0.1" />
                </div>
                <div class="settings-field-group">
                    <label>Port</label>
                    <input type="number" id="comfyui-port" class="settings-input" value="${configData.port}" min="1" max="65535" />
                </div>
                <div class="settings-field-group" style="flex:0;min-width:auto">
                    <label>&nbsp;</label>
                    <div style="display:flex;gap:var(--space-xs)">
                        <button class="btn btn-primary btn-sm" onclick="saveComfyUIConfig()" id="comfyui-save-btn">💾 Save</button>
                        <button class="btn btn-sm" onclick="testComfyUIConnection()" id="comfyui-test-btn">🔌 Test</button>
                    </div>
                </div>
            </div>
            <div id="comfyui-status"></div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">📄</span>
                <span class="settings-provider-name">Workflow Templates</span>
                <span class="badge badge-draft" style="font-size:0.72rem">${templates.length} template${templates.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="comfyui-drop-zone" id="comfyui-drop-zone"
                 onclick="document.getElementById('comfyui-file-input').click()">
                <input type="file" id="comfyui-file-input" accept=".json,application/json" style="display:none" onchange="handleComfyUIFile(event)" />
                <div class="comfyui-drop-zone-icon">📁</div>
                <div class="comfyui-drop-zone-text">Click to select or drag & drop a workflow JSON file</div>
                <div class="comfyui-drop-zone-hint">ComfyUI API format (.json)</div>
                <div class="comfyui-drop-zone-filename" id="comfyui-filename"></div>
            </div>
            <div class="comfyui-upload-form" id="comfyui-upload-form" style="${_comfyuiPendingWorkflowJson ? '' : 'display:none'}">
                <div class="settings-field-group">
                    <label>Template Name *</label>
                    <input type="text" id="comfyui-tpl-name" class="settings-input" placeholder="e.g. SDXL Character Portrait" />
                </div>
                <div class="settings-field-group">
                    <label>Entity Type</label>
                    <select id="comfyui-tpl-entity" class="settings-input">
                        <option value="">General (any)</option>
                        <option value="character">Character</option>
                        <option value="location">Location</option>
                        <option value="item">Item</option>
                        <option value="store">Store</option>
                        <option value="council_member">Council Member</option>
                    </select>
                </div>
                <div class="settings-field-group">
                    <label>Description</label>
                    <input type="text" id="comfyui-tpl-desc" class="settings-input" placeholder="Optional description…" />
                </div>
                <div class="settings-field-group">
                    <label>Author</label>
                    <input type="text" id="comfyui-tpl-author" class="settings-input" placeholder="Optional author name" />
                </div>
                <div class="settings-field-group" style="grid-column: 1 / -1">
                    <button class="btn btn-primary" onclick="uploadComfyUITemplate()" id="comfyui-upload-btn">📤 Upload Template</button>
                </div>
            </div>
            <div class="comfyui-template-list">
                ${templateListHtml}
            </div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">✨</span>
                <span class="settings-provider-name">Default Style Preset</span>
            </div>
            <div class="settings-field-group">
                <label>Preset</label>
                <div class="settings-key-row">
                    <select id="comfyui-style-preset" class="settings-input" onchange="previewComfyUIPreset()">
                        <option value="">None (no style applied)</option>
                        ${presetOptions}
                    </select>
                    <button class="btn btn-primary btn-sm" onclick="saveComfyUIDefaultStyle()">💾 Save</button>
                </div>
                <span class="settings-field-hint">Applied automatically when generating prompts without an explicit style</span>
            </div>
        <div id="comfyui-preset-preview"></div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">📌</span>
                <span class="settings-provider-name">Default Templates per Entity Type</span>
                <span class="badge badge-draft" style="font-size:0.72rem">F-039</span>
            </div>
            <div class="settings-field-hint" style="margin-bottom:var(--space-sm)">
                Assign a default workflow template for each entity type. When generating images, the assigned template will be pre-selected automatically.
            </div>
            <div class="tpl-assign-grid" id="tpl-assign-grid">
                ${_renderAssignmentCards(templates, templateAssignments)}
            </div>
            <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                <button class="btn btn-primary btn-sm" onclick="saveTemplateAssignments()" id="tpl-assign-save-btn">💾 Save Assignments</button>
                <span id="tpl-assign-status" style="font-size:0.78rem;color:var(--text-muted)"></span>
            </div>
        </div>

        <div id="comfyui-preset-editor-container"></div>`;

    // Wire up drag-and-drop
    const dropZone = document.getElementById('comfyui-drop-zone');
    if (dropZone) {
        dropZone.addEventListener('dragover', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) processComfyUIFile(file);
        });
    }

    // Load expanded template detail if any
    if (_comfyuiExpandedTemplate) {
        loadComfyUITemplateDetail(_comfyuiExpandedTemplate);
    }

    // Show preset preview for current selection
    previewComfyUIPreset();

    // Lazy-load the preset editor
    try {
        const editorHtml = await renderPresetEditor();
        const editorContainer = document.getElementById('comfyui-preset-editor-container');
        if (editorContainer) editorContainer.innerHTML = editorHtml;
    } catch { /* preset editor optional */ }
}

/**
 * Render the template assignment cards for each entity type.
 */
function _renderAssignmentCards(templates, assignments) {
    const entityTypes = [
        { key: 'character', label: 'Character', icon: '🎭' },
        { key: 'location', label: 'Location', icon: '🏰' },
        { key: 'item', label: 'Item', icon: '⚔️' },
        { key: 'store', label: 'Store', icon: '🏪' },
    ];

    return entityTypes.map(et => {
        const assigned = assignments[et.key] || '';
        const tplOptions = ['<option value="">None (auto-select)</option>'].concat(
            templates.map(t => {
                const sel = t.id === assigned ? 'selected' : '';
                const etBadge = t.entity_type ? ` [${t.entity_type}]` : '';
                return `<option value="${escapeAttr(t.id)}" ${sel}>${escapeHtml(t.name || t.id)}${etBadge}</option>`;
            })
        ).join('');

        const assignedTpl = assigned ? templates.find(t => t.id === assigned) : null;
        const statusHtml = assigned
            ? `<span class="tpl-assign-status-set">📌 ${escapeHtml(assignedTpl?.name || assigned)}</span>`
            : '<span class="tpl-assign-status-auto">⚡ Auto</span>';

        return `
            <div class="tpl-assign-card ${assigned ? 'tpl-assign-active' : ''}">
                <div class="tpl-assign-header">
                    <span class="tpl-assign-icon">${et.icon}</span>
                    <span class="tpl-assign-label">${et.label}</span>
                    ${statusHtml}
                </div>
                <select class="settings-input tpl-assign-select" data-entity-type="${et.key}">
                    ${tplOptions}
                </select>
            </div>`;
    }).join('');
}

/**
 * Save all template assignments from the UI dropdowns.
 */
async function saveTemplateAssignments() {
    const btn = document.getElementById('tpl-assign-save-btn');
    const status = document.getElementById('tpl-assign-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    const selects = document.querySelectorAll('.tpl-assign-select');
    const assignments = {};
    selects.forEach(sel => {
        const et = sel.getAttribute('data-entity-type');
        if (et) assignments[et] = sel.value;
    });

    try {
        await fetch('/api/settings/comfyui/template-assignments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(assignments),
        }).then(r => { if (!r.ok) throw new Error('Save failed'); return r.json(); });
        showToast('Template assignments saved 📌');
        if (status) status.textContent = '✅ Saved';
        setTimeout(() => { if (status) status.textContent = ''; }, 2000);
        // Refresh to update status badges
        loadComfyUISettings();
    } catch (err) {
        showToast(`Save error: ${err.message}`, true);
        if (status) status.textContent = '❌ Error';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Assignments'; }
    }
}

function handleComfyUIFile(event) {
    const file = event.target.files[0];
    if (file) processComfyUIFile(file);
}

function processComfyUIFile(file) {
    if (!file.name.endsWith('.json')) {
        showToast('Please select a JSON file', true);
        return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const json = JSON.parse(e.target.result);
            if (typeof json !== 'object' || Array.isArray(json)) {
                showToast('Invalid workflow JSON: must be an object', true);
                return;
            }
            _comfyuiPendingWorkflowJson = json;
            _comfyuiPendingFilename = file.name;
            const filenameEl = document.getElementById('comfyui-filename');
            if (filenameEl) filenameEl.textContent = `✅ ${file.name}`;
            const form = document.getElementById('comfyui-upload-form');
            if (form) form.style.display = '';
            // Auto-fill name from filename
            const nameInput = document.getElementById('comfyui-tpl-name');
            if (nameInput && !nameInput.value) {
                nameInput.value = file.name.replace(/\.json$/i, '').replace(/[_-]/g, ' ');
            }
            showToast(`Loaded ${file.name} ✅`);
        } catch (err) {
            showToast('Failed to parse JSON: ' + err.message, true);
        }
    };
    reader.readAsText(file);
}

async function saveComfyUIConfig() {
    const host = document.getElementById('comfyui-host')?.value?.trim();
    const port = parseInt(document.getElementById('comfyui-port')?.value, 10);
    if (!host) return;
    const btn = document.getElementById('comfyui-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
    try {
        const resp = await fetch('/api/settings/comfyui', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host, port }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('ComfyUI config saved ✅');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save'; }
    }
}

async function testComfyUIConnection() {
    const btn = document.getElementById('comfyui-test-btn');
    const statusEl = document.getElementById('comfyui-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Testing…'; }
    if (statusEl) statusEl.innerHTML = '';

    try {
        const resp = await fetch('/api/settings/comfyui/test', { method: 'POST' });
        const data = await resp.json();
        if (data.connected) {
            const stats = data.system_stats || {};
            const gpuInfo = stats.system?.gpus?.[0] || {};
            statusEl.innerHTML = `
                <div class="comfyui-status-result comfyui-status-success">
                    ✅ <strong>Connected</strong> to ComfyUI at ${escapeHtml(data.host)}:${data.port}
                    ${gpuInfo.name ? `<br>GPU: ${escapeHtml(gpuInfo.name)} (${Math.round((gpuInfo.vram_total || 0) / 1073741824)}GB VRAM)` : ''}
                </div>`;
            showToast('ComfyUI connection successful ✅');
        } else {
            statusEl.innerHTML = `
                <div class="comfyui-status-result comfyui-status-error">
                    ❌ <strong>Cannot connect</strong> to ${escapeHtml(data.host)}:${data.port}
                    <br><span style="font-size:0.78rem">${escapeHtml(data.error || 'Unknown error')}</span>
                </div>`;
            showToast('ComfyUI connection failed', true);
        }
    } catch (err) {
        if (statusEl) statusEl.innerHTML = `
            <div class="comfyui-status-result comfyui-status-error">
                ❌ <strong>Request failed</strong>: ${escapeHtml(err.message)}
            </div>`;
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🔌 Test'; }
    }
}

async function uploadComfyUITemplate() {
    if (!_comfyuiPendingWorkflowJson) {
        showToast('Please load a workflow JSON file first', true);
        return;
    }
    const name = document.getElementById('comfyui-tpl-name')?.value?.trim();
    if (!name) {
        document.getElementById('comfyui-tpl-name')?.focus();
        showToast('Template name is required', true);
        return;
    }
    const btn = document.getElementById('comfyui-upload-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading…'; }

    try {
        const resp = await fetch('/api/settings/comfyui/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                workflow_json: _comfyuiPendingWorkflowJson,
                description: document.getElementById('comfyui-tpl-desc')?.value?.trim() || '',
                entity_type: document.getElementById('comfyui-tpl-entity')?.value || '',
                author: document.getElementById('comfyui-tpl-author')?.value?.trim() || '',
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        _comfyuiPendingWorkflowJson = null;
        _comfyuiPendingFilename = '';
        showToast(`Template ${data.id} created ✅`);
        loadComfyUISettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📤 Upload Template'; }
    }
}

async function deleteComfyUITemplate(templateId, templateName) {
    if (!confirm(`Delete template "${templateName}"?`)) return;
    try {
        const resp = await fetch(`/api/settings/comfyui/templates/${encodeURIComponent(templateId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast(`Template ${templateId} deleted ✅`);
        if (_comfyuiExpandedTemplate === templateId) _comfyuiExpandedTemplate = null;
        loadComfyUISettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function toggleComfyUITemplateDetail(templateId) {
    if (_comfyuiExpandedTemplate === templateId) {
        _comfyuiExpandedTemplate = null;
        loadComfyUISettings();
        return;
    }
    _comfyuiExpandedTemplate = templateId;
    loadComfyUISettings();
}

async function loadComfyUITemplateDetail(templateId) {
    const container = document.getElementById(`comfyui-detail-${templateId}`);
    if (!container) return;
    try {
        const data = await api(`/api/settings/comfyui/templates/${encodeURIComponent(templateId)}`);
        const placeholderTags = (data.placeholders || []).map(p =>
            `<span class="comfyui-placeholder-tag">${escapeHtml(p)}</span>`
        ).join(' ');
        const jsonStr = JSON.stringify(data.workflow_json, null, 2);
        const truncJson = jsonStr.length > 5000 ? jsonStr.slice(0, 5000) + '\n… (truncated)' : jsonStr;

        container.innerHTML = `
            <div style="margin-bottom:var(--space-sm)">
                ${data.description ? `<p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:var(--space-sm)">${escapeHtml(data.description)}</p>` : ''}
                <div style="font-size:0.78rem;color:var(--text-muted)">Created: ${formatDate(data.created_at)}</div>
            </div>
            <div style="margin-bottom:var(--space-sm)">
                <strong style="font-size:0.78rem;color:var(--text-secondary)">Placeholders (${data.placeholders.length}):</strong><br>
                ${placeholderTags || '<span style="color:var(--text-muted);font-size:0.78rem">None detected</span>'}
            </div>
            <div>
                <strong style="font-size:0.78rem;color:var(--text-secondary)">Workflow JSON:</strong>
                <div class="comfyui-json-preview"><pre>${escapeHtml(truncJson)}</pre></div>
            </div>`;
    } catch (err) {
        container.innerHTML = `<p style="color:var(--accent-rose)">Failed to load: ${escapeHtml(err.message)}</p>`;
    }
}

function previewComfyUIPreset() {
    const select = document.getElementById('comfyui-style-preset');
    const container = document.getElementById('comfyui-preset-preview');
    if (!select || !container) return;
    const key = select.value;
    if (!key) {
        container.innerHTML = '';
        return;
    }
    // Find preset in the select's options
    const name = select.options[select.selectedIndex]?.text || key;
    // Fetch presets to get details (they should be cached, small list)
    api('/api/settings/comfyui/style-presets').then(presets => {
        const preset = presets.find(p => p.name === key || p.name === name);
        if (!preset) { container.innerHTML = ''; return; }
        container.innerHTML = `
            <div class="comfyui-preset-preview">
                <div style="margin-bottom:var(--space-sm);font-size:0.85rem;font-weight:600">${escapeHtml(preset.name)}</div>
                ${preset.description ? `<p style="color:var(--text-secondary);font-size:0.8rem;margin-bottom:var(--space-sm)">${escapeHtml(preset.description)}</p>` : ''}
                <div class="comfyui-preset-label">Positive suffix</div>
                <div class="comfyui-preset-value">${escapeHtml(preset.positive_suffix || '(none)')}</div>
                <div class="comfyui-preset-label" style="margin-top:var(--space-sm)">Negative prefix</div>
                <div class="comfyui-preset-value">${escapeHtml(preset.negative_prefix || '(none)')}</div>
            </div>`;
    }).catch(() => { container.innerHTML = ''; });
}

async function saveComfyUIDefaultStyle() {
    const select = document.getElementById('comfyui-style-preset');
    const key = select?.value || '';
    try {
        // Use the name as the key since presets are looked up by name
        const resp = await fetch('/api/settings/comfyui/default-style', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ style_key: key }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Default style preset saved ✅');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ─── Character Form Model Helpers ─────────────────────────────

/** Swap model field in character creation form when provider changes. */
function updateCharCreateModelField() {
    const provider = document.getElementById('char-provider-input').value;
    const container = document.getElementById('char-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('char-model-input', provider, '', true);
}

/** Swap model field in character detail edit form when provider changes. */
function updateCharEditModelField() {
    const provider = document.getElementById('char-edit-provider').value;
    const container = document.getElementById('char-edit-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('char-edit-model', provider, '', true);
}


// ═══════════════════════════════════════════════════════════════
// Tasks View
// ═══════════════════════════════════════════════════════════════

async function renderTasks() {
    showLoading();

    const [tasks, council, characters] = await Promise.all([
        api('/api/tasks'),
        api('/api/council'),
        api('/api/characters?status=active'),
    ]);

    const statusOrder = { active: 0, draft: 1, completed: 2 };
    tasks.sort((a, b) => (statusOrder[a.status] || 9) - (statusOrder[b.status] || 9));

    const assigneeOptions = [
        ...council.map(m => m.name),
        ...characters.map(c => c.name),
    ];

    const activeTasks = tasks.filter(t => t.status === 'active');

    const assigneeChips = assigneeOptions.map(name =>
        `<label class="task-assignee-chip"><input type="checkbox" value="${escapeAttr(name)}"><span>${escapeHtml(name)}</span></label>`
    ).join('');

    const doTasksBtn = activeTasks.length > 0
        ? `<button class="btn btn-primary" id="btn-do-tasks" onclick="doTasks()">▶️ Do Tasks (${activeTasks.length} active)</button>`
        : '';

    const createForm = `
        <div class="card character-create-form">
            <h3>📋 New Task</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Create a task and assign it to council members and characters. Active tasks are executed via "Do Tasks".
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="task-name-input">Task Name</label>
                    <input id="task-name-input" class="settings-input" placeholder="e.g. Patrol the Northern Gate" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="task-desc-input">Description</label>
                <textarea id="task-desc-input" class="settings-input proposal-textarea" rows="3"
                    placeholder="What needs to be done…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="task-reason-input">Reason</label>
                <textarea id="task-reason-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Why this task is needed…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label>Assignees</label>
                <div class="task-assignee-grid" id="task-assignee-grid">
                    ${assigneeChips}
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createTask()" id="task-create-btn">
                    📋 Create Task
                </button>
                <span id="task-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    const rows = tasks.map(t => {
        const assigneeBadges = t.assignees.map(a => `<span class="badge badge-active">${escapeHtml(a)}</span>`).join(' ');
        return `
        <tr class="proposal-row" onclick="navigateTo('tasks','${t.id}')">
            <td><strong>${escapeHtml(t.name)}</strong></td>
            <td>${assigneeBadges}</td>
            <td>${badge(t.status)}</td>
            <td>${t.current_round} / 5</td>
            <td>${formatDate(t.created_at)}</td>
        </tr>`;
    }).join('');

    const tableHtml = tasks.length ? `
        <div class="table-wrapper">
            <table class="data-table" id="tasks-table">
                <thead>
                    <tr>
                        <th>Name</th><th>Assignees</th><th>Status</th>
                        <th>Round</th><th>Created</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>` : '<div class="empty-state"><div class="empty-icon">📋</div><p>No tasks yet. Create one above!</p></div>';

    const executionFeed = `
        <div id="task-execution-feed" class="card" style="display:none;margin-bottom:var(--space-xl)">
            <h3 style="display:flex;align-items:center;gap:var(--space-sm);margin-bottom:var(--space-md)">
                ⚙️ Completing Tasks
                <div class="loading-spinner" id="task-spinner" style="width:18px;height:18px;"></div>
            </h3>
            <div id="task-feed-messages" class="task-feed-messages"></div>
        </div>`;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>📋 Tasks</h2>
                <p>${tasks.length} task${tasks.length !== 1 ? 's' : ''}${activeTasks.length > 0 ? ` — <span class="badge badge-active">${activeTasks.length} active</span>` : ''}</p>
            </div>

            <div style="margin-bottom:var(--space-xl)">
                ${doTasksBtn}
            </div>

            ${executionFeed}
            ${createForm}
            ${tableHtml}
        </div>`;

    const countEl = document.getElementById('count-tasks');
    if (countEl) countEl.textContent = tasks.length;
}

async function createTask() {
    const btn = document.getElementById('task-create-btn');
    const status = document.getElementById('task-create-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    const name = (document.getElementById('task-name-input')?.value || '').trim();
    const description = (document.getElementById('task-desc-input')?.value || '').trim();
    const reason = (document.getElementById('task-reason-input')?.value || '').trim();
    const checkboxes = document.querySelectorAll('#task-assignee-grid input[type=checkbox]:checked');
    const assignees = Array.from(checkboxes).map(cb => cb.value);

    if (!name || !description || !reason || assignees.length === 0) {
        showToast('Please fill in all fields and select at least one assignee.', true);
        if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
        return;
    }

    try {
        const resp = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, reason, assignees }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Task "${data.name}" created ✅`);
        await renderTasks();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (status) status.textContent = '';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
    }
}

async function doTasks() {
    var btn = document.getElementById('btn-do-tasks');
    if (btn) { btn.disabled = true; btn.textContent = '\u23F3 Running...'; }

    var feedEl = document.getElementById('task-execution-feed');
    var msgEl = document.getElementById('task-feed-messages');
    if (feedEl) feedEl.style.display = 'block';
    if (msgEl) msgEl.innerHTML = '';

    try {
        var response = await fetch('/api/tasks/do-tasks', { method: 'POST' });
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        while (true) {
            var result = await reader.read();
            if (result.done) break;

            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.indexOf('data: ') === 0) {
                    try {
                        var data = JSON.parse(line.slice(6));
                        if (data.type === 'task_start') {
                            msgEl.innerHTML += '<div class="task-feed-event task-feed-start">' +
                                '<strong>\uD83D\uDE80 Starting task:</strong> ' + escapeHtml(data.task_name) +
                                '<span class="text-muted"> \u2014 ' + data.assignees.map(function(a){return escapeHtml(a);}).join(', ') + '</span></div>';
                        } else if (data.type === 'message') {
                            msgEl.innerHTML += '<div class="task-feed-msg">' +
                                '<div class="task-feed-msg-header">' +
                                '<span class="badge badge-active">' + escapeHtml(data.speaker) + '</span>' +
                                '<span class="text-muted">Round ' + data.round + '/5</span></div>' +
                                '<div class="task-feed-msg-body">' + escapeHtml(data.content) + '</div></div>';
                        } else if (data.type === 'error') {
                            msgEl.innerHTML += '<div class="task-feed-msg task-feed-error">' +
                                '<strong>\u26A0\uFE0F ' + escapeHtml(data.speaker || 'Error') + ':</strong> ' +
                                escapeHtml(data.detail || '') + '</div>';
                        } else if (data.type === 'task_done') {
                            msgEl.innerHTML += '<div class="task-feed-event task-feed-done">' +
                                '<strong>\u2705 Completed:</strong> ' + escapeHtml(data.task_name) +
                                ' (' + data.total_messages + ' messages)</div>';
                        } else if (data.type === 'all_done') {
                            msgEl.innerHTML += '<div class="task-feed-event task-feed-alldone">' +
                                '<strong>\uD83C\uDF89 All ' + data.tasks_completed + ' task(s) completed!</strong></div>';
                        }
                        msgEl.scrollTop = msgEl.scrollHeight;
                    } catch (e) { /* skip */ }
                }
            }
        }
    } catch (err) {
        if (msgEl) msgEl.innerHTML += '<div class="task-feed-error">\u274C Connection error: ' + escapeHtml(err.message) + '</div>';
    }

    var spinner = document.getElementById('task-spinner');
    if (spinner) spinner.style.display = 'none';
    if (btn) { btn.disabled = false; btn.textContent = '\u25B6 Do Tasks'; }

    setTimeout(function() { renderTasks(); }, 1500);
}

async function renderTaskDetail(taskId) {
    showLoading();

    let task;
    try {
        task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    } catch (err) {
        showError('Task not found: ' + taskId);
        return;
    }

    // Status action buttons
    let statusActions = '';
    if (task.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="setTaskStatus('${taskId}','active')">\u25b6\ufe0f Activate</button>`;
    } else if (task.status === 'active') {
        statusActions = `<button class="btn btn-secondary btn-sm" onclick="setTaskStatus('${taskId}','draft')">\u23f8\ufe0f Back to Draft</button>`;
    }

    // Assignees
    const assigneesHtml = task.assignees.map(a =>
        `<span class="specialty-tag">${escapeHtml(a)}</span>`
    ).join('');

    // Messages feed
    let messagesHtml = '';
    if (task.messages && task.messages.length > 0) {
        const msgs = task.messages.map(m => `
            <div class="task-feed-msg">
                <div class="task-feed-msg-header">
                    <span class="badge badge-active">${escapeHtml(m.speaker)}</span>
                    <span style="font-size:0.78rem;color:var(--text-muted)">Round ${m.round_number}/5</span>
                </div>
                <div class="task-feed-msg-body">${escapeHtml(m.content)}</div>
            </div>`).join('');

        messagesHtml = `
            <div class="detail-section">
                <h4>\ud83d\udcac Completion Narration (${task.messages.length} messages)</h4>
                <div class="task-feed-messages" style="max-height:600px;overflow-y:auto">${msgs}</div>
            </div>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('tasks')">\u2190 Back to Tasks</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${task.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(task.name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            Round ${task.current_round} / 5 \u00b7 ${formatDate(task.created_at)}
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:var(--space-sm)">
                        ${badge(task.status)}
                        ${statusActions}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>\ud83d\udcc4 Description</h4>
                    <p>${escapeHtml(task.description)}</p>
                </div>

                <div class="detail-section">
                    <h4>\ud83d\udca1 Reason</h4>
                    <p>${escapeHtml(task.reason)}</p>
                </div>

                <div class="detail-section">
                    <h4>\ud83d\udc65 Assignees (${task.assignees.length})</h4>
                    <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">${assigneesHtml}</div>
                </div>

                ${messagesHtml}

                <div class="detail-section" style="font-size:0.82rem;color:var(--text-muted)">
                    Created: ${formatDate(task.created_at)} \u00b7 Updated: ${formatDate(task.updated_at)}
                </div>
            </div>
        </div>`;
}

async function setTaskStatus(taskId, newStatus) {
    try {
        var resp = await fetch('/api/tasks/' + taskId + '/status', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            var err = await resp.json();
            throw new Error(err.detail);
        }
        await renderTaskDetail(taskId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// Generation Queue Dashboard (F-037g)
// ═══════════════════════════════════════════════════════════════

let _queuePollTimer = null;

async function renderGenerationQueue() {
    showLoading();

    let jobs = [];
    try {
        jobs = await api('/api/generate/jobs');
    } catch { /* pipeline not initialized yet */ }

    // Sort: active first, then by newest
    const stageOrder = { 'queued': 0, 'prompt_generating': 1, 'template_filling': 2, 'running': 3, 'downloading': 4, 'saving': 5, 'completed': 6, 'failed': 7, 'cancelled': 8 };
    jobs.sort((a, b) => {
        const aActive = !['completed', 'failed', 'cancelled'].includes(a.stage);
        const bActive = !['completed', 'failed', 'cancelled'].includes(b.stage);
        if (aActive !== bActive) return bActive ? 1 : -1;
        return (stageOrder[a.stage] || 99) - (stageOrder[b.stage] || 99);
    });

    const stageLabels = {
        'queued': '📤 Queued',
        'prompt_generating': '🧠 Generating Prompt',
        'template_filling': '📋 Preparing Workflow',
        'running': '⚡ Generating',
        'downloading': '📥 Downloading',
        'saving': '💾 Saving',
        'completed': '✅ Completed',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    const jobCards = jobs.length ? jobs.map(job => {
        const isActive = !['completed', 'failed', 'cancelled'].includes(job.stage);
        const stageClass = isActive ? 'queue-card-active' : job.stage === 'completed' ? 'queue-card-done' : 'queue-card-error';
        const pct = job.progress_pct || 0;

        return `
            <div class="queue-card ${stageClass}" id="queue-card-${escapeAttr(job.job_id)}">
                <div class="queue-card-header">
                    <div class="queue-card-id">${escapeHtml(job.job_id)}</div>
                    <div class="queue-card-stage">${stageLabels[job.stage] || job.stage}</div>
                </div>
                <div class="queue-card-entity">
                    ${escapeHtml(job.entity_type || '')} / ${escapeHtml(job.entity_id || '')}
                </div>
                ${job.prompt_mode ? `<div class="queue-card-mode">Mode: ${escapeHtml(job.prompt_mode)}</div>` : ''}
                ${isActive ? `
                    <div class="queue-card-progress">
                        <div class="gen-progress-bar-bg">
                            <div class="gen-progress-bar-fill" style="width:${pct}%"></div>
                        </div>
                        <span class="queue-card-pct">${pct}%</span>
                    </div>
                ` : ''}
                ${job.prompt_positive ? `<div class="queue-card-prompt" title="${escapeAttr(job.prompt_positive)}">${escapeHtml(job.prompt_positive.substring(0, 120))}${job.prompt_positive.length > 120 ? '…' : ''}</div>` : ''}
                ${job.image_id && job.stage === 'completed' ? `<img class="queue-card-thumb" src="/api/images/file/${escapeAttr(job.image_id)}" loading="lazy" />` : ''}
                ${job.error ? `<div class="queue-card-error-msg">${escapeHtml(job.error)}</div>` : ''}
                <div class="queue-card-actions">
                    ${isActive ? `<button class="btn btn-secondary btn-sm" onclick="cancelQueueJob('${escapeAttr(job.job_id)}')">Cancel</button>` : ''}
                    ${job.stage === 'failed' ? `<button class="btn btn-primary btn-sm" onclick="retryQueueJob('${escapeAttr(job.job_id)}', '${escapeAttr(job.entity_type)}', '${escapeAttr(job.entity_id)}')">🔄 Retry</button>` : ''}
                    ${job.stage === 'completed' && job.entity_type && job.entity_id ? `<button class="btn btn-secondary btn-sm" onclick="navigateTo('${escapeAttr(job.entity_type === 'council_member' ? 'council' : job.entity_type + 's')}', '${escapeAttr(job.entity_id)}')">View Entity</button>` : ''}
                </div>
            </div>`;
    }).join('') : '<p style="color:var(--text-muted);text-align:center;padding:var(--space-xl)">No generation jobs yet. Generate an image from any entity\'s detail page.</p>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🎨 Generation Queue</h2>
                <p>Monitor and manage image generation jobs</p>
            </div>
            <div class="queue-grid" id="queue-grid">
                ${jobCards}
            </div>
        </div>`;

    // Start polling if there are active jobs
    startQueuePolling();
}

function startQueuePolling() {
    stopQueuePolling();
    _queuePollTimer = setInterval(async () => {
        // Only poll if we're on the queue view
        if (state.currentView !== 'generation-queue') {
            stopQueuePolling();
            return;
        }
        try {
            const jobs = await api('/api/generate/jobs');
            const hasActive = jobs.some(j => !['completed', 'failed', 'cancelled'].includes(j.stage));
            if (!hasActive) {
                stopQueuePolling();
            }
            // Re-render the queue with fresh data
            await renderGenerationQueue();
        } catch { /* ignore */ }
    }, 3000);
}

function stopQueuePolling() {
    if (_queuePollTimer) {
        clearInterval(_queuePollTimer);
        _queuePollTimer = null;
    }
}

async function cancelQueueJob(jobId) {
    try {
        await fetch(`/api/generate/cancel/${encodeURIComponent(jobId)}`, { method: 'POST' });
        showToast('Job cancelled.');
        await renderGenerationQueue();
    } catch (err) {
        showToast(`Cancel error: ${err.message}`, true);
    }
}

function retryQueueJob(jobId, entityType, entityId) {
    if (entityType && entityId) {
        openGenerateModal(entityType, entityId);
    }
}


// ═══════════════════════════════════════════════════════════════
// Custom Style Preset Editor (F-037g)
// ═══════════════════════════════════════════════════════════════

async function renderPresetEditor() {
    let builtins = [];
    let customs = [];
    try {
        const all = await api('/api/settings/comfyui/style-presets');
        builtins = all.filter(p => p.is_builtin);
        customs = all.filter(p => !p.is_builtin);
    } catch { /* no presets */ }

    const builtinCards = builtins.map(p => `
        <div class="preset-card preset-card-builtin">
            <div class="preset-card-header">
                <strong>${escapeHtml(p.name)}</strong>
                <span class="preset-badge preset-badge-builtin">Built-in</span>
            </div>
            <div class="preset-card-desc">${escapeHtml(p.description || 'No description')}</div>
            <div class="preset-card-detail"><strong>Positive:</strong> ${escapeHtml(p.positive_suffix || '—')}</div>
            <div class="preset-card-detail"><strong>Negative:</strong> ${escapeHtml(p.negative_prefix || '—')}</div>
            <div class="preset-card-key">Key: <code>${escapeHtml(p.key)}</code></div>
        </div>
    `).join('');

    const customCards = customs.length ? customs.map(p => `
        <div class="preset-card preset-card-custom">
            <div class="preset-card-header">
                <strong>${escapeHtml(p.name)}</strong>
                <span class="preset-badge preset-badge-custom">Custom</span>
            </div>
            <div class="preset-card-desc">${escapeHtml(p.description || 'No description')}</div>
            <div class="preset-card-detail"><strong>Positive:</strong> ${escapeHtml(p.positive_suffix || '—')}</div>
            <div class="preset-card-detail"><strong>Negative:</strong> ${escapeHtml(p.negative_prefix || '—')}</div>
            <div class="preset-card-key">Key: <code>${escapeHtml(p.key)}</code> | ID: <code>${escapeHtml(p.id)}</code></div>
            <div class="preset-card-actions">
                <button class="btn btn-secondary btn-sm" onclick="editCustomPreset('${escapeAttr(p.id)}')">✏️ Edit</button>
                <button class="btn btn-secondary btn-sm" onclick="deleteCustomPreset('${escapeAttr(p.id)}', '${escapeAttr(p.name)}')">🗑️ Delete</button>
            </div>
        </div>
    `).join('') : '<p style="color:var(--text-muted)">No custom presets yet.</p>';

    return `
        <div class="card" style="margin-top:var(--space-lg)">
            <h3>🎨 Style Preset Editor</h3>
            <p style="color:var(--text-muted);margin-bottom:var(--space-md)">
                Create custom style presets that modify how AI generates image prompts.
            </p>

            <div class="preset-editor-actions" style="display:flex;gap:var(--space-sm);margin-bottom:var(--space-md);flex-wrap:wrap">
                <button class="btn btn-primary btn-sm" onclick="openCreatePresetModal()">➕ Create Preset</button>
                <button class="btn btn-secondary btn-sm" onclick="exportPresets()">📤 Export All</button>
                <button class="btn btn-secondary btn-sm" onclick="importPresetsDialog()">📥 Import</button>
            </div>

            <h4 style="margin-bottom:var(--space-sm)">Custom Presets</h4>
            <div class="preset-grid" id="custom-presets-grid">
                ${customCards}
            </div>

            <h4 style="margin-top:var(--space-lg);margin-bottom:var(--space-sm)">Built-in Presets <span style="color:var(--text-muted);font-size:0.78rem">(read-only)</span></h4>
            <div class="preset-grid" id="builtin-presets-grid">
                ${builtinCards}
            </div>
        </div>`;
}

function openCreatePresetModal() {
    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'preset-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:560px">
            <div class="gen-modal-header">
                <h3>➕ Create Custom Preset</h3>
                <button class="detail-close" onclick="closePresetModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="gen-form-grid">
                    <div class="filter-group">
                        <label for="preset-key">Key <span style="color:var(--text-muted);font-size:0.72rem">(unique, lowercase)</span></label>
                        <input id="preset-key" class="settings-input" placeholder="e.g. cyberpunk" oninput="updatePresetPreview()" />
                    </div>
                    <div class="filter-group">
                        <label for="preset-name">Display Name</label>
                        <input id="preset-name" class="settings-input" placeholder="e.g. Cyberpunk" oninput="updatePresetPreview()" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-desc">Description</label>
                    <input id="preset-desc" class="settings-input" placeholder="Brief description of the style" />
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-positive">Positive Suffix <span style="color:var(--text-muted);font-size:0.72rem">(appended to positive prompts)</span></label>
                    <textarea id="preset-positive" class="settings-input proposal-textarea" rows="2" placeholder="e.g. cyberpunk, neon lights, rain, futuristic" oninput="updatePresetPreview()"></textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-negative">Negative Prefix <span style="color:var(--text-muted);font-size:0.72rem">(prepended to negative prompts)</span></label>
                    <textarea id="preset-negative" class="settings-input proposal-textarea" rows="2" placeholder="e.g. nature, medieval, fantasy, bright daylight" oninput="updatePresetPreview()"></textarea>
                </div>

                <div class="preset-preview" id="preset-preview" style="margin-top:var(--space-md)">
                    <h4>Live Preview</h4>
                    <div class="preset-preview-box">
                        <div id="preset-preview-positive"><strong>Positive:</strong> <em style="color:var(--text-muted)">Enter suffix above…</em></div>
                        <div id="preset-preview-negative"><strong>Negative:</strong> <em style="color:var(--text-muted)">Enter prefix above…</em></div>
                    </div>
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closePresetModal()">Cancel</button>
                <button class="btn btn-primary" id="preset-save-btn" onclick="saveCustomPreset()">💾 Save Preset</button>
            </div>
        </div>`;
    modal.addEventListener('click', (e) => { if (e.target === modal) closePresetModal(); });
    document.body.appendChild(modal);
}

function closePresetModal() {
    const m = document.getElementById('preset-modal-overlay');
    if (m) m.remove();
}

function updatePresetPreview() {
    const positive = document.getElementById('preset-positive')?.value || '';
    const negative = document.getElementById('preset-negative')?.value || '';

    const samplePrompt = 'a noble knight standing in a castle courtyard';
    const previewPos = positive ? `${samplePrompt}, <strong style="color:var(--accent)">${escapeHtml(positive)}</strong>` : `${samplePrompt}`;
    const previewNeg = negative ? `<strong style="color:var(--accent)">${escapeHtml(negative)}</strong>, blurry, low quality` : 'blurry, low quality';

    const posEl = document.getElementById('preset-preview-positive');
    const negEl = document.getElementById('preset-preview-negative');
    if (posEl) posEl.innerHTML = `<strong>Positive:</strong> ${previewPos}`;
    if (negEl) negEl.innerHTML = `<strong>Negative:</strong> ${previewNeg}`;
}

async function saveCustomPreset(presetId) {
    const key = document.getElementById('preset-key')?.value || '';
    const name = document.getElementById('preset-name')?.value || '';
    const description = document.getElementById('preset-desc')?.value || '';
    const positive_suffix = document.getElementById('preset-positive')?.value || '';
    const negative_prefix = document.getElementById('preset-negative')?.value || '';

    if (!key.trim() || !name.trim()) {
        showToast('Key and name are required.', true);
        return;
    }

    const btn = document.getElementById('preset-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const url = presetId
            ? `/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`
            : '/api/settings/comfyui/presets';
        const method = presetId ? 'PUT' : 'POST';

        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, name, description, positive_suffix, negative_prefix }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast(`Preset "${name}" saved ✅`);
        closePresetModal();
        // Refresh the settings page to show the new preset
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Preset'; }
    }
}

async function editCustomPreset(presetId) {
    let preset;
    try {
        preset = await api(`/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`);
    } catch {
        showToast('Failed to load preset.', true);
        return;
    }

    openCreatePresetModal();
    // Wait for DOM then populate
    setTimeout(() => {
        const keyEl = document.getElementById('preset-key');
        const nameEl = document.getElementById('preset-name');
        const descEl = document.getElementById('preset-desc');
        const posEl = document.getElementById('preset-positive');
        const negEl = document.getElementById('preset-negative');
        const saveBtn = document.getElementById('preset-save-btn');
        const header = document.querySelector('#preset-modal-overlay .gen-modal-header h3');

        if (keyEl) { keyEl.value = preset.key || ''; keyEl.disabled = true; }
        if (nameEl) nameEl.value = preset.name || '';
        if (descEl) descEl.value = preset.description || '';
        if (posEl) posEl.value = preset.positive_suffix || '';
        if (negEl) negEl.value = preset.negative_prefix || '';
        if (header) header.textContent = `✏️ Edit Preset — ${preset.name}`;
        if (saveBtn) {
            saveBtn.onclick = () => saveCustomPreset(presetId);
            saveBtn.textContent = '💾 Update Preset';
        }
        updatePresetPreview();
    }, 50);
}

async function deleteCustomPreset(presetId, presetName) {
    if (!confirm(`Delete custom preset "${presetName}"?`)) return;
    try {
        const resp = await fetch(`/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('Delete failed');
        showToast(`Preset "${presetName}" deleted 🗑️`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function exportPresets() {
    try {
        const data = await api('/api/settings/comfyui/presets/export');
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'jericho_style_presets.json';
        a.click();
        URL.revokeObjectURL(url);
        showToast('Presets exported 📤');
    } catch (err) {
        showToast(`Export error: ${err.message}`, true);
    }
}

function importPresetsDialog() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const text = await file.text();
            const presetsData = JSON.parse(text);
            const payload = Array.isArray(presetsData) ? presetsData : [presetsData];
            const resp = await fetch('/api/settings/comfyui/presets/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ presets: payload }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Import failed' }));
                throw new Error(err.detail);
            }
            const result = await resp.json();
            showToast(`Imported ${result.imported_count} preset(s) 📥`);
            await renderSettings();
        } catch (err) {
            showToast(`Import error: ${err.message}`, true);
        }
    };
    input.click();
}


// ═══════════════════════════════════════════════════════════════
// Batch Generation Modal (F-037g)
// ═══════════════════════════════════════════════════════════════

async function openBatchGenerateModal(entityType) {
    let entities = [];
    try {
        if (entityType === 'character') entities = await api('/api/characters');
        else if (entityType === 'location') entities = await api('/api/locations');
        else if (entityType === 'item') entities = await api('/api/items');
        else if (entityType === 'store') entities = await api('/api/stores');
    } catch { /* no entities */ }

    if (!entities.length) {
        showToast(`No ${entityType}s found.`, true);
        return;
    }

    let templates = [];
    let presets = [];
    try { templates = await api('/api/settings/comfyui/templates'); } catch {}
    try { presets = await api('/api/settings/comfyui/style-presets'); } catch {}

    if (!templates.length) {
        showToast('No ComfyUI workflow templates found. Add one in Settings → ComfyUI first.', true);
        return;
    }

    const templateOptions = templates.map(t =>
        `<option value="${escapeAttr(t.id)}">${escapeHtml(t.name || t.id)}</option>`
    ).join('');

    const presetOptions = ['<option value="">None (default)</option>'].concat(
        presets.map(p => `<option value="${escapeAttr(p.key)}">${escapeHtml(p.name || p.key)}</option>`)
    ).join('');

    const entityIdKey = entityType === 'council_member' ? 'name' : 'id';
    const entityCheckboxes = entities.slice(0, 20).map(e => `
        <label class="gen-participant-label">
            <input type="checkbox" class="batch-entity-cb" value="${escapeAttr(e[entityIdKey])}" />
            ${escapeHtml(e.name || e[entityIdKey])}
        </label>
    `).join('');

    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'batch-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:600px">
            <div class="gen-modal-header">
                <h3>🎨 Batch Generate — ${escapeHtml(entityType)}s</h3>
                <button class="detail-close" onclick="closeBatchModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="filter-group">
                    <label>Select Entities <span style="color:var(--text-muted);font-size:0.72rem">(max 10)</span></label>
                    <div class="gen-participants-grid" id="batch-entities">
                        ${entityCheckboxes}
                    </div>
                </div>
                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="batch-template">Workflow Template</label>
                        <select id="batch-template" class="settings-input">${templateOptions}</select>
                    </div>
                    <div class="filter-group">
                        <label for="batch-style">Style Preset</label>
                        <select id="batch-style" class="settings-input">${presetOptions}</select>
                    </div>
                </div>
                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="batch-width">Width</label>
                        <input id="batch-width" class="settings-input" type="number" value="512" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="batch-height">Height</label>
                        <input id="batch-height" class="settings-input" type="number" value="512" min="64" max="4096" step="64" />
                    </div>
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeBatchModal()">Cancel</button>
                <button class="btn btn-primary" id="batch-submit-btn" onclick="submitBatchGeneration('${escapeAttr(entityType)}')">
                    🎨 Generate Batch
                </button>
            </div>
        </div>`;
    modal.addEventListener('click', (e) => { if (e.target === modal) closeBatchModal(); });
    document.body.appendChild(modal);
}

function closeBatchModal() {
    const m = document.getElementById('batch-modal-overlay');
    if (m) m.remove();
}

async function submitBatchGeneration(entityType) {
    const selected = Array.from(document.querySelectorAll('.batch-entity-cb:checked')).map(cb => cb.value);

    if (!selected.length) {
        showToast('Select at least one entity.', true);
        return;
    }
    if (selected.length > 10) {
        showToast('Maximum 10 entities per batch.', true);
        return;
    }

    const btn = document.getElementById('batch-submit-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Queuing…'; }

    const body = {
        entity_type: entityType,
        entity_ids: selected,
        template_id: document.getElementById('batch-template')?.value || '',
        prompt_mode: 'system',
        style_preset_key: document.getElementById('batch-style')?.value || '',
        width: parseInt(document.getElementById('batch-width')?.value || '512'),
        height: parseInt(document.getElementById('batch-height')?.value || '512'),
        seed: 0,
    };

    try {
        const resp = await fetch('/api/generate/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Batch failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Queued ${data.count} generation job(s) 🎨`);
        closeBatchModal();
        navigateTo('generation-queue');
    } catch (err) {
        showToast(`Batch error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🎨 Generate Batch'; }
    }
}


// ═══════════════════════════════════════════════════════════════
// Generation Completion Toast Poller (F-037g)
// ═══════════════════════════════════════════════════════════════

let _genToastPollTimer = null;
let _genToastKnownJobs = new Set();

function startGenToastPoller() {
    if (_genToastPollTimer) return;
    _genToastPollTimer = setInterval(async () => {
        try {
            const jobs = await api('/api/generate/jobs');
            for (const job of jobs) {
                if (_genToastKnownJobs.has(job.job_id)) continue;
                if (job.stage === 'completed') {
                    _genToastKnownJobs.add(job.job_id);
                    showToast(`🎨 Image generated for ${job.entity_type}/${job.entity_id}!`);
                } else if (job.stage === 'failed') {
                    _genToastKnownJobs.add(job.job_id);
                    showToast(`❌ Generation failed for ${job.entity_type}/${job.entity_id}`, true);
                } else if (['cancelled', 'queued', 'prompt_generating', 'template_filling', 'running', 'downloading', 'saving'].includes(job.stage)) {
                    // Track active jobs so we can detect transitions
                }
            }
        } catch { /* ignore */ }
    }, 5000);
}


// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Apply saved skin before anything renders
    applySkin(state.activeSkin);

    // Eagerly load model options so dropdowns work before Settings is visited
    loadModelOptions();

    // Start global generation toast poller (F-037g)
    startGenToastPoller();

    initNavigation();
    const hash = window.location.hash.slice(1) || 'dashboard';
    const [view, ...rest] = hash.split('/');
    navigateTo(view, rest.join('/') || null);
});
