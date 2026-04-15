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
    chat: 'world', explore: 'world', stories: 'world', locations: 'world', items: 'world', stores: 'world',
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

function updateInjectionCounter(textareaId, counterId, maxLen) {
    const ta = document.getElementById(textareaId);
    const counter = document.getElementById(counterId);
    if (!ta || !counter) return;
    const len = ta.value.length;
    counter.textContent = `${len} / ${maxLen}`;
    const threshold = maxLen * 0.9;
    counter.style.color = len >= maxLen ? 'var(--accent-rose)' : len >= threshold ? 'var(--accent-amber)' : 'var(--text-muted)';
}

// ─── Render Router ────────────────────────────────────────────

