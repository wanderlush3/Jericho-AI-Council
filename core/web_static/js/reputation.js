/**
 * Jericho — Reputation Module (F-069)
 *
 * Leaderboard view, entity detail view, and manual event recording.
 */

// ═══════════════════════════════════════════════════════════════
// Reputation Leaderboard
// ═══════════════════════════════════════════════════════════════

async function renderReputation() {
    showLoading();

    let board, stances;
    try {
        [board, stances] = await Promise.all([
            api('/api/reputation'),
            api('/api/reputation/stances'),
        ]);
    } catch (err) {
        showError('Failed to load reputation data: ' + err.message);
        return;
    }

    // Build stance chips
    let stanceHtml = '';
    if (stances && Object.keys(stances).length > 0) {
        const chips = Object.entries(stances).map(([name, tier]) => {
            const emoji = _repTierEmoji(tier);
            return `<div class="stance-chip">
                <span class="stance-name">${escapeHtml(_capitalize(name))}</span>
                <span class="reputation-tier-badge tier-${tier}">${emoji} ${_capitalize(tier)}</span>
            </div>`;
        }).join('');
        stanceHtml = `
            <div class="card" style="margin-bottom:1.5rem">
                <h3 style="margin:0 0 0.75rem">🎭 Default Perception Stances</h3>
                <p style="font-size:0.85rem;color:var(--text-secondary);margin:0 0 0.75rem">
                    How each entity perceives strangers by default (before any reputation events).
                </p>
                <div class="stances-grid">${chips}</div>
            </div>`;
    }

    // Build leaderboard rows
    let rowsHtml = '';
    if (board.length === 0) {
        rowsHtml = `<div class="empty-state">
            <div class="empty-icon">⭐</div>
            <p>No reputation events recorded yet. Use the admin form below to start awarding reputation.</p>
        </div>`;
    } else {
        rowsHtml = board.map((s, i) => {
            const rank = i + 1;
            const rankClass = rank <= 3 ? ` top-${rank}` : '';
            const scoreClass = s.decayed_score > 0 ? 'positive' : s.decayed_score < 0 ? 'negative' : 'zero';
            const displayName = _formatEntityId(s.entity_id);
            return `<div class="reputation-row" onclick="navigateTo('reputation','${escapeAttr(s.entity_id)}')">
                <div class="reputation-rank${rankClass}">#${rank}</div>
                <div class="reputation-entity-name">${escapeHtml(displayName)}</div>
                <span class="reputation-tier-badge tier-${s.tier}">${s.tier_emoji} ${_capitalize(s.tier)}</span>
                <div class="reputation-score ${scoreClass}">${_formatScore(s.decayed_score)}</div>
                <div class="reputation-event-count">${s.event_count} event${s.event_count !== 1 ? 's' : ''}</div>
            </div>`;
        }).join('');
    }

    // Admin quick-add form
    const adminForm = `
        <div class="card" style="margin-top:1.5rem">
            <h3 style="margin:0 0 0.75rem">🛠️ Award / Penalize Reputation</h3>
            <div class="reputation-admin-form">
                <div class="form-group">
                    <label>Entity ID</label>
                    <input type="text" id="rep-entity-id" placeholder="member:sage or character:CH-0001">
                </div>
                <div class="form-group">
                    <label>Event Type</label>
                    <select id="rep-event-type">
                        <option value="custom">Custom</option>
                        <option value="proposal_authored">Proposal Authored (+10)</option>
                        <option value="proposal_approved">Proposal Approved (+5)</option>
                        <option value="proposal_rejected">Proposal Rejected (-2)</option>
                        <option value="vote_cast">Vote Cast (+2)</option>
                        <option value="vote_aligned">Vote Aligned (+1)</option>
                        <option value="review_written">Review Written (+3)</option>
                        <option value="gift_given">Gift Given (+5)</option>
                        <option value="gift_received">Gift Received (+1)</option>
                        <option value="discussion_participated">Discussion (+2)</option>
                        <option value="session_participated">Session (+3)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Points (override)</label>
                    <input type="number" id="rep-points" placeholder="Leave blank for default">
                </div>
                <div class="form-group">
                    <label>Source ID (optional)</label>
                    <input type="text" id="rep-source-id" placeholder="P-0001, ITEM-0003, etc.">
                </div>
                <div class="form-group full-width">
                    <label>Reason</label>
                    <textarea id="rep-reason" placeholder="Why is this reputation change being made?"></textarea>
                </div>
                <div class="form-group full-width" style="align-items:flex-end">
                    <button class="btn btn-primary" onclick="_submitReputationEvent()">Record Event</button>
                </div>
            </div>
        </div>`;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>⭐ Reputation</h2>
                <p>Community standing of council members and characters</p>
            </div>
            ${stanceHtml}
            <div class="reputation-leaderboard">${rowsHtml}</div>
            ${adminForm}
        </div>`;
}


// ═══════════════════════════════════════════════════════════════
// Reputation Detail
// ═══════════════════════════════════════════════════════════════

async function renderReputationDetail(entityId) {
    showLoading();

    let score, events;
    try {
        [score, events] = await Promise.all([
            api(`/api/reputation/${entityId}`),
            api(`/api/reputation/${entityId}/events?limit=100`),
        ]);
    } catch (err) {
        showError('Failed to load reputation for ' + entityId + ': ' + err.message);
        return;
    }

    const scoreClass = score.decayed_score > 0 ? 'positive' : score.decayed_score < 0 ? 'negative' : 'zero';
    const displayName = _formatEntityId(entityId);

    let eventsHtml = '';
    if (events.length === 0) {
        eventsHtml = `<div class="empty-state"><div class="empty-icon">📝</div><p>No events recorded yet.</p></div>`;
    } else {
        eventsHtml = events.map(e => {
            const ptClass = e.points >= 0 ? 'positive' : 'negative';
            const ptSign = e.points >= 0 ? '+' : '';
            return `<div class="reputation-event-item">
                <span class="reputation-event-type">${escapeHtml(e.event_type)}</span>
                <span class="reputation-event-reason">${escapeHtml(e.reason || '—')}</span>
                <span class="reputation-event-points ${ptClass}">${ptSign}${e.points}</span>
                <span class="reputation-event-time">${formatDate(e.timestamp)}</span>
            </div>`;
        }).join('');
    }

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:center;gap:1rem">
                <button class="btn btn-ghost" onclick="navigateTo('reputation')">← Back</button>
                <div>
                    <h2>${escapeHtml(displayName)}</h2>
                    <p>Reputation history and score breakdown</p>
                </div>
            </div>

            <div class="reputation-detail-header">
                <div class="reputation-detail-score ${scoreClass}">
                    ${_formatScore(score.decayed_score)}
                </div>
                <div class="reputation-detail-meta">
                    <span class="entity-name">${score.tier_emoji} ${_capitalize(score.tier)}</span>
                    <span class="score-breakdown">
                        Raw: ${score.raw_score} · Decayed: ${_formatScore(score.decayed_score)} · ${score.event_count} event${score.event_count !== 1 ? 's' : ''}
                    </span>
                    ${score.last_event_at ? `<span class="score-breakdown">Last event: ${formatDate(score.last_event_at)}</span>` : ''}
                </div>
                <span class="reputation-tier-badge tier-${score.tier}" style="margin-left:auto;font-size:0.95rem;padding:0.4rem 1rem">
                    ${score.tier_emoji} ${_capitalize(score.tier)}
                </span>
            </div>

            <h3 style="margin:0 0 0.75rem">📜 Event History</h3>
            <div class="reputation-events">${eventsHtml}</div>
        </div>`;
}


// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function _formatEntityId(eid) {
    // "member:sage" → "Sage (Council Member)"
    // "character:ch-0001" → "CH-0001 (Character)"
    if (!eid) return eid;
    const parts = eid.split(':');
    if (parts.length !== 2) return eid;
    const [type, name] = parts;
    if (type === 'member') return _capitalize(name) + ' (Council)';
    if (type === 'character') return name.toUpperCase() + ' (Character)';
    return _capitalize(name);
}

function _capitalize(s) {
    if (!s) return '';
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function _formatScore(score) {
    if (score === 0) return '0';
    const sign = score > 0 ? '+' : '';
    return sign + (Number.isInteger(score) ? score : score.toFixed(1));
}

function _repTierEmoji(tier) {
    const map = {
        legendary: '\u2B50',
        distinguished: '\uD83C\uDFC6',
        respected: '\u2728',
        neutral: '\uD83D\uDC64',
        dubious: '\u26A0\uFE0F',
        disgraced: '\uD83D\uDEAB',
    };
    return map[tier] || '\uD83D\uDC64';
}

async function _submitReputationEvent() {
    const entityId = document.getElementById('rep-entity-id')?.value?.trim();
    const eventType = document.getElementById('rep-event-type')?.value;
    const pointsRaw = document.getElementById('rep-points')?.value?.trim();
    const reason = document.getElementById('rep-reason')?.value?.trim() || '';
    const sourceId = document.getElementById('rep-source-id')?.value?.trim() || '';

    if (!entityId) {
        alert('Entity ID is required (e.g. member:sage)');
        return;
    }

    const body = {
        event_type: eventType,
        reason: reason,
        source_id: sourceId,
    };
    if (pointsRaw !== '' && pointsRaw !== undefined) {
        body.points = parseInt(pointsRaw, 10);
        if (isNaN(body.points)) {
            alert('Points must be a number');
            return;
        }
    }

    try {
        const resp = await fetch(`/api/reputation/${entityId}/events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        // Refresh the leaderboard
        await renderReputation();
    } catch (err) {
        alert('Error recording event: ' + err.message);
    }
}
