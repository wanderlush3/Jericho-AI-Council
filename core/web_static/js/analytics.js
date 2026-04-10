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

