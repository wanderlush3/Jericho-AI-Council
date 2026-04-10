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

