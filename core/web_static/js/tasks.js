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

