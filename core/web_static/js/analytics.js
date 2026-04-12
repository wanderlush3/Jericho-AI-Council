async function renderAnalytics() {
    showLoading();
    const data = await api('/api/analytics');
    state.analyticsData = data;

    const ps = data.proposal_stats || {};
    const vs = data.voting_stats || {};
    const ss = data.session_stats || {};
    const top = data.top_participants || [];
    const wb = data.world_building_stats || {};
    const ec = data.economy_stats || {};
    const cs = data.content_stats || {};
    const im = data.image_stats || {};
    const mk = data.memory_knowledge_stats || {};

    // Helper: format bytes to human-readable
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        let i = 0;
        let val = bytes;
        while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
        return val.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
    }

    // Helper: render status breakdown chips
    function statusChips(byStatus) {
        if (!byStatus || Object.keys(byStatus).length === 0) return '';
        return Object.entries(byStatus).map(([k, v]) =>
            `<div class="analytics-row"><span class="label">${badge(k)}</span><span class="value">${v}</span></div>`
        ).join('');
    }

    // Top participants bar chart
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

    // Economy: format government balance
    const govBal = ec.government_balance || {};
    const govBalDisplay = (govBal.gold || govBal.silver || govBal.bronze)
        ? `${govBal.gold || 0}G / ${govBal.silver || 0}S / ${govBal.bronze || 0}B`
        : '—';

    // Content: illustration percentage
    const illustPct = cs.total_scenes > 0
        ? Math.round((cs.illustrated_scenes / cs.total_scenes) * 100)
        : 0;

    // Images: by-type chips
    const imgTypeRows = Object.entries(im.images_by_entity_type || {}).map(([k, v]) =>
        `<div class="analytics-row"><span class="label">${k}</span><span class="value">${v}</span></div>`
    ).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Analytics</h2>
                <p>Governance, world building, economy, content, and system-wide metrics</p>
            </div>

            <div class="analytics-section-label">⚖️ Governance</div>
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
                    <div class="analytics-row"><span class="label">Unanimous Votes</span><span class="value">${vs.unanimous_count || 0}</span></div>
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

            <div class="analytics-section-label">🌐 System</div>
            <div class="analytics-grid">
                <div class="card analytics-card">
                    <h3>🌍 World Building</h3>
                    <div class="analytics-row"><span class="label">Characters</span><span class="value">${wb.total_characters || 0}</span></div>
                    ${statusChips(wb.characters_by_status)}
                    <div class="analytics-row"><span class="label">Locations</span><span class="value">${wb.total_locations || 0}</span></div>
                    ${statusChips(wb.locations_by_status)}
                    <div class="analytics-row"><span class="label">Items</span><span class="value">${wb.total_items || 0}</span></div>
                    ${statusChips(wb.items_by_status)}
                    <div class="analytics-row"><span class="label">Stores</span><span class="value">${wb.total_stores || 0}</span></div>
                    <div class="analytics-row"><span class="label">Active Stores</span><span class="value">${wb.active_stores || 0}</span></div>
                    <div class="analytics-row"><span class="label">Inventory Slots</span><span class="value">${wb.total_inventory_slots || 0}</span></div>
                </div>

                <div class="card analytics-card">
                    <h3>💰 Economy & Treasury</h3>
                    <div class="analytics-row"><span class="label">Treasury Accounts</span><span class="value">${ec.total_accounts || 0}</span></div>
                    <div class="analytics-row"><span class="label">Total Circulation</span><span class="value">${ec.total_circulation_gold || '0.00'} Gold</span></div>
                    <div class="analytics-row"><span class="label">Gov Balance</span><span class="value">${govBalDisplay}</span></div>
                    <div class="analytics-row"><span class="label">Tax Events</span><span class="value">${ec.total_tax_events || 0}</span></div>
                </div>

                <div class="card analytics-card">
                    <h3>📖 Content & Stories</h3>
                    <div class="analytics-row"><span class="label">Total Stories</span><span class="value">${cs.total_stories || 0}</span></div>
                    ${statusChips(cs.stories_by_status)}
                    <div class="analytics-row"><span class="label">Total Chapters</span><span class="value">${cs.total_chapters || 0}</span></div>
                    <div class="analytics-row"><span class="label">Total Scenes</span><span class="value">${cs.total_scenes || 0}</span></div>
                    <div class="analytics-row"><span class="label">Illustrated Scenes</span><span class="value">${cs.illustrated_scenes || 0} (${illustPct}%)</span></div>
                </div>

                <div class="card analytics-card">
                    <h3>🖼️ Image Generation</h3>
                    <div class="analytics-row"><span class="label">Total Images</span><span class="value">${im.total_images || 0}</span></div>
                    ${imgTypeRows}
                    <div class="analytics-row"><span class="label">Storage Used</span><span class="value">${formatBytes(im.total_storage_bytes)}</span></div>
                    <div class="analytics-row"><span class="label">Workflow Templates</span><span class="value">${im.total_templates || 0}</span></div>
                </div>

                <div class="card analytics-card">
                    <h3>🧠 Memory & Knowledge</h3>
                    <div class="analytics-row"><span class="label">Core Beliefs</span><span class="value">${mk.total_beliefs || 0}</span></div>
                    <div class="analytics-row"><span class="label">Session Events</span><span class="value">${mk.total_session_events || 0}</span></div>
                    <div class="analytics-row"><span class="label">Shared Decisions</span><span class="value">${mk.total_shared_decisions || 0}</span></div>
                    <div class="analytics-row"><span class="label">Total Laws</span><span class="value">${mk.total_laws || 0}</span></div>
                    ${statusChips(mk.laws_by_status)}
                </div>
            </div>
        </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Chat View
// ═══════════════════════════════════════════════════════════════

