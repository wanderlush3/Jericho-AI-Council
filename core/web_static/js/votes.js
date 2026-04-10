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
