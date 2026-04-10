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
                + Add Participant
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

