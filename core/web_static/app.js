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

// ─── Loading / Error ──────────────────────────────────────────

function showLoading() {
    $main().innerHTML = `<div class="loading"><div class="loading-spinner"></div><span>Loading…</span></div>`;
}

function showError(msg) {
    $main().innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${msg}</p></div>`;
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
                ${memberAvatar(m.name, i)}
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

    let personalityHtml = '';
    if (data.personality && Object.keys(data.personality).length) {
        personalityHtml = `
            <div class="detail-section">
                <h4>Personality</h4>
                <div class="personality-grid">
                    ${Object.entries(data.personality).map(([k, v]) => `
                        <div class="personality-item">
                            <span class="key">${k}:</span>
                            <span class="value">${Array.isArray(v) ? v.join(', ') : v}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('council')">← Back to Council</button>
            <div class="detail-panel">
                <div class="detail-header">
                    ${memberAvatar(data.name, idx >= 0 ? idx : 0, 'lg')}
                    <div>
                        <div style="font-size:1.4rem;font-weight:700">${data.name}</div>
                        <div style="color:var(--text-secondary);margin-top:2px">${data.role}</div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                            ${badge(data.api_provider)}
                            <span style="font-size:0.78rem;color:var(--text-muted)">
                                ${data.model} · Weight: ${data.vote_weight}
                            </span>
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('council')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${data.description}</p>
                </div>

                ${personalityHtml}

                <div class="detail-section">
                    <h4>Specialties</h4>
                    <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">
                        ${data.specialties.map(s => `<span class="specialty-tag">${s}</span>`).join('')}
                    </div>
                </div>

                <div class="detail-section">
                    <h4>System Prompt</h4>
                    <pre>${data.system_prompt}</pre>
                </div>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Proposals View
// ═══════════════════════════════════════════════════════════════

async function renderProposals() {
    showLoading();
    const data = await api('/api/proposals');
    state.proposalsData = data;

    const statuses = ['', ...new Set(data.map(p => p.status))];
    const categories = ['', ...new Set(data.map(p => p.category))];

    if (!data.length) {
        $main().innerHTML = `
            <div class="page-header"><h2>Proposals</h2></div>
            <div class="empty-state"><div class="empty-icon">📜</div><p>No proposals found.</p></div>`;
        return;
    }

    const rows = data.map(p => `
        <tr onclick="navigateTo('proposals','${p.id}')">
            <td class="col-id">${p.id}</td>
            <td class="col-title">${truncate(p.title, 50)}</td>
            <td>${p.author}</td>
            <td>${badge(p.category)}</td>
            <td>${badge(p.status)}</td>
            <td>${p.reviews ? p.reviews.length : 0}</td>
            <td>${formatDate(p.created_at)}</td>
        </tr>`).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Proposals</h2>
                <p>${data.length} governance proposals</p>
            </div>
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
            </div>
        </div>`;
}

async function renderProposalDetail(id) {
    showLoading();
    const data = await api(`/api/proposals/${encodeURIComponent(id)}`);

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
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${data.title}</div>
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

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${data.description}</p>
                </div>

                ${data.body ? `<div class="detail-section"><h4>Body</h4><pre>${data.body}</pre></div>` : ''}

                ${reviewsHtml}
            </div>
        </div>`;
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
