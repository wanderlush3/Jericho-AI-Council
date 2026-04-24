async function renderTasks() {
    showLoading();

    const [tasks, council, characters, items] = await Promise.all([
        api('/api/tasks'),
        api('/api/council'),
        api('/api/characters?status=active'),
        api('/api/items').catch(() => []),
    ]);

    // Filter to active items with at least one owner (for gift tasks)
    const giftableItems = (items || []).filter(
        i => i.status === 'active' && (i.owned_by || []).length > 0
    );
    state._taskGiftableItems = giftableItems;
    state._taskRecipients = _buildTaskRecipientOptions(council, characters);

    // Fetch active stores with inventory (for purchase tasks)
    let activeStores = [];
    try {
        const allStores = await api('/api/stores?status=active');
        activeStores = (allStores || []).filter(s => (s.inventory || []).length > 0);
    } catch (e) { /* stores unavailable */ }
    state._taskActiveStores = activeStores;

    // Fetch treasury accounts (for purchase tasks — buyer picker)
    let treasuryAccounts = [];
    try {
        treasuryAccounts = await api('/api/treasury');
    } catch (e) { /* treasury unavailable */ }
    state._taskTreasuryAccounts = treasuryAccounts || [];

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

    // Build gift item options
    const giftItemOpts = giftableItems.map(i => {
        const owners = (i.owned_by || []).map(o =>
            `${o.type === 'council_member' ? '👑' : o.type === 'character' ? '🎭' : '👤'} ${escapeHtml(o.name)}`
        ).join(', ');
        return `<option value="${i.id}" data-owners='${escapeAttr(JSON.stringify(i.owned_by || []))}' data-name="${escapeAttr(i.name)}">${escapeHtml(i.name)} — owned by ${owners}</option>`;
    }).join('');

    const recipientDatalist = state._taskRecipients.map(r =>
        `<option value="${escapeAttr(r.name)}" data-type="${r.type}" label="${r.label}">`
    ).join('');

    const createForm = `
        <div class="card character-create-form">
            <h3>📋 New Task</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Create a task and assign it to council members and characters. Active tasks are executed via "Do Tasks".
            </p>

            <div style="margin-bottom:var(--space-md)">
                <label style="font-size:0.8rem;font-weight:500;color:var(--text-secondary);margin-bottom:6px;display:block">Task Type</label>
                <div class="task-type-toggle">
                    <button class="task-type-btn active standard" data-type="standard" onclick="_setTaskType('standard')">📋 Standard</button>
                    <button class="task-type-btn" data-type="gift" onclick="_setTaskType('gift')">🎁 Gift Task</button>
                    <button class="task-type-btn" data-type="purchase" onclick="_setTaskType('purchase')">🛒 Purchase Task</button>
                </div>
                <input type="hidden" id="task-type-input" value="standard" />
            </div>

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

            <!-- Gift Task Config (hidden by default) -->
            <div id="gift-task-config" class="gift-task-config" style="display:none">
                <div class="gift-config-header">
                    <span class="icon">🎁</span> Gift Configuration
                </div>
                <div class="proposal-form-grid">
                    <div class="filter-group" style="flex:3">
                        <label for="task-gift-item">Item to Gift</label>
                        <select id="task-gift-item" class="settings-input" onchange="_onTaskGiftItemChange()">
                            <option value="">-- Select an item --</option>
                            ${giftItemOpts}
                        </select>
                    </div>
                </div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group" style="flex:2">
                        <label for="task-gift-from">From (Giver)</label>
                        <select id="task-gift-from" class="settings-input" disabled>
                            <option value="">-- Select item first --</option>
                        </select>
                    </div>
                </div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group" style="flex:2">
                        <label for="task-gift-to-name">To (Recipient)</label>
                        <input id="task-gift-to-name" class="settings-input" list="task-gift-recipient-list"
                            placeholder="Type a name…" oninput="_onTaskGiftRecipientChange()" />
                        <datalist id="task-gift-recipient-list">
                            ${recipientDatalist}
                        </datalist>
                    </div>
                    <div class="filter-group">
                        <label for="task-gift-to-type">Recipient Type</label>
                        <select id="task-gift-to-type" class="settings-input">
                            <option value="user">👤 User</option>
                            <option value="character">🎭 Character</option>
                            <option value="council_member">👑 Council Member</option>
                        </select>
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-xs)">
                    <label for="task-gift-message">Gift Message <span style="color:var(--text-muted);font-size:0.75rem">(optional)</span></label>
                    <input id="task-gift-message" class="settings-input" placeholder="e.g. Here's that record I promised…" />
                </div>
                <div class="gift-rep-preview" style="margin-top:var(--space-sm)">
                    <span style="color:var(--text-secondary);font-size:0.82rem">⭐ Reputation on completion:</span>
                    <span class="gift-rep-chip giver">+5 🎁 Giver</span>
                    <span class="gift-rep-chip receiver">+1 📦 Receiver</span>
                </div>
            </div>

            <!-- Purchase Task Config (hidden by default) -->
            <div id="purchase-task-config" class="purchase-task-config" style="display:none">
                <div class="purchase-config-header">
                    <span class="icon">🛒</span> Purchase Configuration
                </div>
                <div class="proposal-form-grid">
                    <div class="filter-group" style="flex:3">
                        <label for="task-purchase-store">Store</label>
                        <select id="task-purchase-store" class="settings-input" onchange="_onTaskPurchaseStoreChange()">
                            <option value="">-- Select a store --</option>
                            ${activeStores.map(s =>
                                `<option value="${s.id}" data-inventory='${escapeAttr(JSON.stringify(s.inventory || []))}' data-name="${escapeAttr(s.name)}">${escapeHtml(s.name)} (${(s.inventory || []).length} items)</option>`
                            ).join('')}
                        </select>
                    </div>
                </div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group" style="flex:3">
                        <label for="task-purchase-item">Item</label>
                        <select id="task-purchase-item" class="settings-input" disabled onchange="_onTaskPurchaseItemChange()">
                            <option value="">-- Select store first --</option>
                        </select>
                    </div>
                </div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group" style="flex:2">
                        <label for="task-purchase-buyer">Buyer Account</label>
                        <select id="task-purchase-buyer" class="settings-input">
                            <option value="">-- Select buyer --</option>
                            ${(treasuryAccounts || []).map(a =>
                                `<option value="${escapeAttr(a.account_id)}" data-name="${escapeAttr(a.owner_name)}" data-type="${escapeAttr(a.account_type)}">${escapeHtml(a.owner_name)} (${a.account_type.replace('_', ' ')}) — ${a.balance?.gold || 0}g</option>`
                            ).join('')}
                        </select>
                    </div>
                </div>
                <div id="task-purchase-price-preview" class="purchase-price-preview" style="display:none">
                    <span>💰 Price:</span>
                    <span id="task-purchase-price-display" class="price-tag"></span>
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
        const giftBadge = t.task_type === 'gift' ? ' <span class="gift-task-badge">🎁 Gift</span>' : '';
        const purchaseBadge = t.task_type === 'purchase' ? ' <span class="purchase-task-badge">🛒 Purchase</span>' : '';
        return `
        <tr class="proposal-row" onclick="navigateTo('tasks','${t.id}')">
            <td><strong>${escapeHtml(t.name)}</strong>${giftBadge}${purchaseBadge}</td>
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

    const taskType = (document.getElementById('task-type-input')?.value || 'standard');

    if (!name || !description || !reason || assignees.length === 0) {
        showToast('Please fill in all fields and select at least one assignee.', true);
        if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
        return;
    }

    // Build gift config if gift task
    let giftConfig = null;
    if (taskType === 'gift') {
        const itemId = document.getElementById('task-gift-item')?.value;
        const fromIdx = parseInt(document.getElementById('task-gift-from')?.value || '0', 10);
        const toName = document.getElementById('task-gift-to-name')?.value?.trim();
        const toType = document.getElementById('task-gift-to-type')?.value || 'user';
        const giftMsg = document.getElementById('task-gift-message')?.value?.trim() || '';

        if (!itemId) {
            showToast('Gift task requires selecting an item to gift.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }
        if (!toName) {
            showToast('Gift task requires a recipient name.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }

        // Find the from_owner from state
        const selItem = (state._taskGiftableItems || []).find(i => i.id === itemId);
        const fromOwner = selItem ? (selItem.owned_by || [])[fromIdx] : null;
        if (!fromOwner) {
            showToast('Cannot identify the giver. Please re-select the item.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }

        giftConfig = {
            item_id: itemId,
            from_owner: fromOwner,
            to_owner: { name: toName, type: toType },
            message: giftMsg,
        };
    }

    // Build purchase config if purchase task
    let purchaseConfig = null;
    if (taskType === 'purchase') {
        const storeId = document.getElementById('task-purchase-store')?.value;
        const itemId = document.getElementById('task-purchase-item')?.value;
        const buyerSel = document.getElementById('task-purchase-buyer');
        const buyerAccountId = buyerSel?.value;

        if (!storeId) {
            showToast('Purchase task requires selecting a store.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }
        if (!itemId) {
            showToast('Purchase task requires selecting an item.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }
        if (!buyerAccountId) {
            showToast('Purchase task requires selecting a buyer.', true);
            if (btn) { btn.disabled = false; btn.textContent = '📋 Create Task'; }
            return;
        }

        const buyerOpt = buyerSel.options[buyerSel.selectedIndex];
        const buyerName = buyerOpt?.dataset?.name || '';
        const buyerType = buyerOpt?.dataset?.type || 'user';

        // Map account type to entity ID prefix
        const entityPrefixMap = { council_member: 'member', character: 'character', user: 'member' };
        const entityPrefix = entityPrefixMap[buyerType] || 'member';
        const buyerEntityId = `${entityPrefix}:${buyerName}`;

        purchaseConfig = {
            store_id: storeId,
            item_id: itemId,
            buyer_account_id: buyerAccountId,
            buyer_entity_id: buyerEntityId,
            buyer_name: buyerName,
            buyer_type: buyerType,
        };
    }

    try {
        const body = { name, description, reason, assignees, task_type: taskType };
        if (giftConfig) body.gift_config = giftConfig;
        if (purchaseConfig) body.purchase_config = purchaseConfig;

        const resp = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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
                        } else if (data.type === 'gift_complete') {
                            msgEl.innerHTML += '<div class="gift-complete-card">' +
                                '<div class="gift-complete-header">' +
                                    '<span class="gift-complete-icon">🎁</span>' +
                                    '<span class="gift-complete-title">Gift Delivered!</span>' +
                                '</div>' +
                                '<div class="gift-complete-body">' +
                                    '<span class="gift-complete-item">"' + escapeHtml(data.item_name || '') + '"</span>' +
                                    '<span>' + escapeHtml(data.from_name || '') + '</span>' +
                                    '<span class="arrow">→</span>' +
                                    '<span>' + escapeHtml(data.to_name || '') + '</span>' +
                                '</div>' +
                                '<div class="gift-complete-rep">' +
                                    '<span class="gift-rep-chip giver">+5 🎁 Giver</span>' +
                                    '<span class="gift-rep-chip receiver">+1 📦 Receiver</span>' +
                                '</div>' +
                            '</div>';
                        } else if (data.type === 'gift_error') {
                            msgEl.innerHTML += '<div class="task-feed-msg task-feed-error">' +
                                '<strong>⚠️ Gift Error:</strong> ' + escapeHtml(data.detail || '') + '</div>';
                        } else if (data.type === 'purchase_complete') {
                            var adj = data.adjusted_price || {};
                            var priceChips = '';
                            if (adj.gold) priceChips += '<span class="purchase-price-chip gold">' + adj.gold + 'g</span>';
                            if (adj.silver) priceChips += '<span class="purchase-price-chip silver">' + adj.silver + 's</span>';
                            if (adj.bronze) priceChips += '<span class="purchase-price-chip bronze">' + adj.bronze + 'b</span>';
                            if (data.price_modifier && data.price_modifier !== 1.0) {
                                priceChips += '<span class="purchase-price-chip rep-modifier">×' + data.price_modifier + ' rep</span>';
                            }
                            msgEl.innerHTML += '<div class="purchase-complete-card">' +
                                '<div class="purchase-complete-header">' +
                                    '<span class="purchase-complete-icon">🛒</span>' +
                                    '<span class="purchase-complete-title">Purchase Complete!</span>' +
                                '</div>' +
                                '<div class="purchase-complete-body">' +
                                    '<span class="purchase-complete-item">"' + escapeHtml(data.item_name || '') + '"</span>' +
                                    '<span>from</span>' +
                                    '<span>' + escapeHtml(data.store_name || '') + '</span>' +
                                    '<span class="arrow">→</span>' +
                                    '<span>' + escapeHtml(data.buyer_name || '') + '</span>' +
                                '</div>' +
                                '<div class="purchase-complete-price">' + priceChips + '</div>' +
                            '</div>';
                        } else if (data.type === 'purchase_error') {
                            msgEl.innerHTML += '<div class="task-feed-msg task-feed-error">' +
                                '<strong>⚠️ Purchase Error:</strong> ' + escapeHtml(data.detail || '') + '</div>';
                        } else if (data.type === 'task_done') {
                            var doneExtra = '';
                            if (data.task_type === 'gift' && data.gift_result) {
                                doneExtra = ' · <span class="gift-task-badge">🎁 Gift Delivered</span>';
                            }
                            if (data.task_type === 'purchase' && data.purchase_result) {
                                doneExtra = ' · <span class="purchase-task-badge">🛒 Purchase Complete</span>';
                            }
                            msgEl.innerHTML += '<div class="task-feed-event task-feed-done">' +
                                '<strong>\u2705 Completed:</strong> ' + escapeHtml(data.task_name) +
                                ' (' + data.total_messages + ' messages)' + doneExtra + '</div>';
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

    // Gift delivered banner (for completed gift tasks)
    let giftDeliveredBanner = '';
    if (task.task_type === 'gift' && task.status === 'completed' && task.gift_result && task.gift_result.item_name) {
        const gr = task.gift_result;
        giftDeliveredBanner = `
            <div class="gift-delivered-banner">
                <div class="gift-delivered-icon">🎁</div>
                <div class="gift-delivered-content">
                    <div class="gift-delivered-title">Gift Delivered!</div>
                    <div class="gift-delivered-detail">
                        <strong>${escapeHtml(gr.item_name)}</strong>
                        <span>${escapeHtml(gr.from_name || '')}</span>
                        <span class="arrow">→</span>
                        <span>${escapeHtml(gr.to_name || '')}</span>
                    </div>
                    <div class="gift-delivered-rep">
                        <span class="gift-rep-chip giver">+5 🎁 Giver</span>
                        <span class="gift-rep-chip receiver">+1 📦 Receiver</span>
                    </div>
                </div>
            </div>`;
    }

    // Purchase delivered banner (for completed purchase tasks)
    let purchaseDeliveredBanner = '';
    if (task.task_type === 'purchase' && task.status === 'completed' && task.purchase_result && task.purchase_result.item_name) {
        const pr = task.purchase_result;
        const adj = pr.adjusted_price || {};
        let priceHtml = '';
        if (adj.gold) priceHtml += `<span class="purchase-price-chip gold">${adj.gold}g</span>`;
        if (adj.silver) priceHtml += `<span class="purchase-price-chip silver">${adj.silver}s</span>`;
        if (adj.bronze) priceHtml += `<span class="purchase-price-chip bronze">${adj.bronze}b</span>`;
        if (pr.price_modifier && pr.price_modifier !== 1.0) {
            priceHtml += `<span class="purchase-price-chip rep-modifier">×${pr.price_modifier} rep</span>`;
        }
        purchaseDeliveredBanner = `
            <div class="purchase-delivered-banner">
                <div class="purchase-delivered-icon">🛒</div>
                <div class="purchase-delivered-content">
                    <div class="purchase-delivered-title">Purchase Complete!</div>
                    <div class="purchase-delivered-detail">
                        <strong>${escapeHtml(pr.item_name)}</strong>
                        <span>from ${escapeHtml(pr.store_name || '')}</span>
                        <span class="arrow">→</span>
                        <span>${escapeHtml(pr.buyer_name || '')}</span>
                    </div>
                    <div class="purchase-delivered-price">${priceHtml}</div>
                </div>
            </div>`;
    }

    // Gift config info section (for gift tasks)
    let giftInfoHtml = '';
    if (task.task_type === 'gift' && task.gift_config) {
        const gc = task.gift_config;
        const fromName = (gc.from_owner || {}).name || 'Unknown';
        const fromType = (gc.from_owner || {}).type || 'user';
        const toName = (gc.to_owner || {}).name || 'Unknown';
        const toType = (gc.to_owner || {}).type || 'user';
        giftInfoHtml = `
            <div class="gift-info-section">
                <h4>🎁 Gift Configuration</h4>
                <div class="gift-info-row">
                    <span class="gift-info-label">Item</span>
                    <span class="gift-info-value">${escapeHtml(gc.item_id || '')}${gc.item_id ? ` <a href="#items/${gc.item_id}" style="color:var(--accent-cyan);font-size:0.78rem">View →</a>` : ''}</span>
                </div>
                <div class="gift-info-row">
                    <span class="gift-info-label">From</span>
                    <span class="gift-info-value">${escapeHtml(fromName)} <span style="font-size:0.72rem;color:var(--text-muted)">(${fromType.replace('_', ' ')})</span></span>
                </div>
                <div class="gift-info-row">
                    <span class="gift-info-label">To</span>
                    <span class="gift-info-value">${escapeHtml(toName)} <span style="font-size:0.72rem;color:var(--text-muted)">(${toType.replace('_', ' ')})</span></span>
                </div>
                ${gc.message ? `<div class="gift-info-row"><span class="gift-info-label">Message</span><span class="gift-info-value">"${escapeHtml(gc.message)}"</span></div>` : ''}
            </div>`;
    }

    // Purchase config info section (for purchase tasks)
    let purchaseInfoHtml = '';
    if (task.task_type === 'purchase' && task.purchase_config) {
        const pc = task.purchase_config;
        purchaseInfoHtml = `
            <div class="purchase-info-section">
                <h4>🛒 Purchase Configuration</h4>
                <div class="gift-info-row">
                    <span class="gift-info-label">Store</span>
                    <span class="gift-info-value">${escapeHtml(pc.store_id || '')}</span>
                </div>
                <div class="gift-info-row">
                    <span class="gift-info-label">Item</span>
                    <span class="gift-info-value">${escapeHtml(pc.item_id || '')}${pc.item_id ? ` <a href="#items/${pc.item_id}" style="color:var(--accent-cyan);font-size:0.78rem">View →</a>` : ''}</span>
                </div>
                <div class="gift-info-row">
                    <span class="gift-info-label">Buyer</span>
                    <span class="gift-info-value">${escapeHtml(pc.buyer_name || pc.buyer_account_id || '')} <span style="font-size:0.72rem;color:var(--text-muted)">(${(pc.buyer_type || 'user').replace('_', ' ')})</span></span>
                </div>
                <div class="gift-info-row">
                    <span class="gift-info-label">Account</span>
                    <span class="gift-info-value" style="font-family:'JetBrains Mono',monospace;font-size:0.78rem">${escapeHtml(pc.buyer_account_id || '')}</span>
                </div>
            </div>`;
    }

    const typeBadge = task.task_type === 'gift' ? ' <span class="gift-task-badge">🎁 Gift Task</span>'
        : task.task_type === 'purchase' ? ' <span class="purchase-task-badge">🛒 Purchase Task</span>'
        : '';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('tasks')">\u2190 Back to Tasks</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${task.id}${typeBadge}</div>
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

                ${giftDeliveredBanner}
                ${purchaseDeliveredBanner}

                <div class="detail-section">
                    <h4>\ud83d\udcc4 Description</h4>
                    <p>${escapeHtml(task.description)}</p>
                </div>

                <div class="detail-section">
                    <h4>\ud83d\udca1 Reason</h4>
                    <p>${escapeHtml(task.reason)}</p>
                </div>

                ${giftInfoHtml}
                ${purchaseInfoHtml}

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
// Gift Task Helpers (F-073)
// ═══════════════════════════════════════════════════════════════

function _setTaskType(type) {
    const btns = document.querySelectorAll('.task-type-btn');
    btns.forEach(b => {
        b.classList.toggle('active', b.dataset.type === type);
        if (b.dataset.type === 'standard') b.classList.toggle('standard', b.dataset.type === type);
        if (b.dataset.type === 'purchase') b.classList.toggle('purchase', b.dataset.type === type);
    });
    const input = document.getElementById('task-type-input');
    if (input) input.value = type;

    const giftPanel = document.getElementById('gift-task-config');
    if (giftPanel) giftPanel.style.display = type === 'gift' ? 'block' : 'none';

    const purchasePanel = document.getElementById('purchase-task-config');
    if (purchasePanel) purchasePanel.style.display = type === 'purchase' ? 'block' : 'none';

    // Update create button text
    const createBtn = document.getElementById('task-create-btn');
    if (createBtn) {
        if (type === 'gift') createBtn.textContent = '🎁 Create Gift Task';
        else if (type === 'purchase') createBtn.textContent = '🛒 Create Purchase Task';
        else createBtn.textContent = '📋 Create Task';
    }
}

function _onTaskGiftItemChange() {
    const select = document.getElementById('task-gift-item');
    const fromSelect = document.getElementById('task-gift-from');
    if (!select || !fromSelect) return;

    if (!select.value) {
        fromSelect.innerHTML = '<option value="">-- Select item first --</option>';
        fromSelect.disabled = true;
        return;
    }

    const selectedOption = select.options[select.selectedIndex];
    let owners = [];
    try {
        owners = JSON.parse(selectedOption.dataset.owners || '[]');
    } catch { owners = []; }

    fromSelect.innerHTML = owners.map((o, i) =>
        `<option value="${i}">${o.type === 'council_member' ? '👑' : o.type === 'character' ? '🎭' : '👤'} ${escapeHtml(o.name)} (${o.type.replace('_', ' ')})</option>`
    ).join('');
    fromSelect.disabled = false;
}

function _onTaskGiftRecipientChange() {
    const input = document.getElementById('task-gift-to-name');
    const typeSelect = document.getElementById('task-gift-to-type');
    if (!input || !typeSelect || !state._taskRecipients) return;

    const typed = input.value.trim().toLowerCase();
    const match = state._taskRecipients.find(r => r.name.toLowerCase() === typed);
    if (match) typeSelect.value = match.type;
}

function _buildTaskRecipientOptions(council, characters) {
    const options = [];
    if (Array.isArray(council)) {
        council.forEach(m => {
            const name = m.name || m;
            options.push({
                name: typeof name === 'string' ? name : String(name),
                type: 'council_member',
                label: `👑 ${name} (Council)`,
            });
        });
    }
    if (Array.isArray(characters)) {
        characters.forEach(c => {
            options.push({
                name: c.name,
                type: 'character',
                label: `🎭 ${c.name} (Character)`,
            });
        });
    }
    return options;
}

// ═══════════════════════════════════════════════════════════════
// Purchase Task Helpers (F-074)
// ═══════════════════════════════════════════════════════════════

function _onTaskPurchaseStoreChange() {
    const storeSelect = document.getElementById('task-purchase-store');
    const itemSelect = document.getElementById('task-purchase-item');
    const pricePreview = document.getElementById('task-purchase-price-preview');
    if (!storeSelect || !itemSelect) return;

    if (pricePreview) pricePreview.style.display = 'none';

    if (!storeSelect.value) {
        itemSelect.innerHTML = '<option value="">-- Select store first --</option>';
        itemSelect.disabled = true;
        return;
    }

    const selectedOption = storeSelect.options[storeSelect.selectedIndex];
    let inventory = [];
    try {
        inventory = JSON.parse(selectedOption.dataset.inventory || '[]');
    } catch { inventory = []; }

    if (inventory.length === 0) {
        itemSelect.innerHTML = '<option value="">No items in stock</option>';
        itemSelect.disabled = true;
        return;
    }

    itemSelect.innerHTML = '<option value="">-- Select an item --</option>' +
        inventory.map(si => {
            const priceParts = [];
            if (si.price_gold) priceParts.push(si.price_gold + 'g');
            if (si.price_silver) priceParts.push(si.price_silver + 's');
            if (si.price_bronze) priceParts.push(si.price_bronze + 'b');
            const priceStr = priceParts.join(' ') || 'Free';
            const qtyStr = si.quantity === -1 ? '∞' : si.quantity;
            return `<option value="${escapeAttr(si.item_id)}" data-gold="${si.price_gold || 0}" data-silver="${si.price_silver || 0}" data-bronze="${si.price_bronze || 0}">${escapeHtml(si.item_id)} — ${priceStr} (qty: ${qtyStr})</option>`;
        }).join('');
    itemSelect.disabled = false;
}

function _onTaskPurchaseItemChange() {
    const itemSelect = document.getElementById('task-purchase-item');
    const pricePreview = document.getElementById('task-purchase-price-preview');
    const priceDisplay = document.getElementById('task-purchase-price-display');
    if (!itemSelect || !pricePreview || !priceDisplay) return;

    if (!itemSelect.value) {
        pricePreview.style.display = 'none';
        return;
    }

    const opt = itemSelect.options[itemSelect.selectedIndex];
    const gold = parseInt(opt.dataset.gold || '0', 10);
    const silver = parseInt(opt.dataset.silver || '0', 10);
    const bronze = parseInt(opt.dataset.bronze || '0', 10);

    const parts = [];
    if (gold) parts.push(gold + ' Gold');
    if (silver) parts.push(silver + ' Silver');
    if (bronze) parts.push(bronze + ' Bronze');

    priceDisplay.textContent = parts.join(', ') || 'Free';
    pricePreview.style.display = 'flex';
}

// ═══════════════════════════════════════════════════════════════
// Generation Queue Dashboard (F-037g)
// ═══════════════════════════════════════════════════════════════

let _queuePollTimer = null;

