/**
 * Jericho — Gifting Section (F-072)
 *
 * Dedicated view for gifting items between users, council members, and characters.
 * Hooks into the existing POST /api/items/{id}/gift endpoint (F-068)
 * and surfaces reputation gains from gifts (F-069/F-070).
 */

// ═══════════════════════════════════════════════════════════════
// Render Gift View
// ═══════════════════════════════════════════════════════════════

async function renderGifts() {
    showLoading();

    let items, council, characters, history;
    try {
        [items, council, characters, history] = await Promise.all([
            api('/api/items'),
            api('/api/council'),
            api('/api/characters?status=active').catch(() => []),
            api('/api/gifts/history').catch(() => []),
        ]);
    } catch (err) {
        showError('Failed to load gifting data: ' + err.message);
        return;
    }

    // Filter to active items with at least one owner
    const giftableItems = (items || []).filter(
        i => i.status === 'active' && (i.owned_by || []).length > 0
    );

    // Build recipient autocomplete list
    const recipientOptions = _buildRecipientOptions(council, characters);

    // ── Gift Form ────────────────────────────────────────────
    const itemOptions = giftableItems.map(i => {
        const owners = (i.owned_by || []).map(o =>
            `${o.type === 'council_member' ? '👑' : o.type === 'character' ? '🎭' : '👤'} ${escapeHtml(o.name)}`
        ).join(', ');
        return `<option value="${i.id}" data-owners='${escapeAttr(JSON.stringify(i.owned_by || []))}' data-name="${escapeAttr(i.name)}" data-img="${escapeAttr(i.primary_image_url || '')}">${escapeHtml(i.name)} — owned by ${owners}</option>`;
    }).join('');

    const recipientDatalist = recipientOptions.map(r =>
        `<option value="${escapeAttr(r.name)}" data-type="${r.type}" label="${r.label}">`
    ).join('');

    const giftForm = `
        <div class="gift-form-card">
            <h3>🎁 Give a Gift</h3>
            <p class="gift-form-subtitle">
                Transfer an item from one owner to another. A chat record acknowledging the gift will be created automatically.
            </p>

            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:3">
                    <label for="gift-item-select">Item to Gift</label>
                    <select id="gift-item-select" class="settings-input" onchange="_onGiftItemChange()">
                        <option value="">-- Select an item --</option>
                        ${itemOptions}
                    </select>
                </div>
            </div>

            <div id="gift-item-preview-area" style="display:none"></div>

            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="gift-from-select">From (Giver)</label>
                    <select id="gift-from-select" class="settings-input" disabled>
                        <option value="">-- Select item first --</option>
                    </select>
                </div>
            </div>

            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="gift-to-name">To (Recipient)</label>
                    <input id="gift-to-name" class="settings-input" list="gift-recipient-list"
                        placeholder="Type a name or select from the list…"
                        oninput="_onGiftRecipientChange()" />
                    <datalist id="gift-recipient-list">
                        ${recipientDatalist}
                    </datalist>
                </div>
                <div class="filter-group">
                    <label for="gift-to-type">Recipient Type</label>
                    <select id="gift-to-type" class="settings-input">
                        <option value="user">👤 User</option>
                        <option value="character">🎭 Character</option>
                        <option value="council_member">👑 Council Member</option>
                    </select>
                </div>
            </div>

            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gift-message">Gift Message <span style="color:var(--text-muted);font-size:0.75rem">(optional)</span></label>
                <input id="gift-message" class="settings-input"
                    placeholder="e.g. A token of appreciation for your service to the council…" />
            </div>

            <div class="gift-rep-preview">
                <span style="color:var(--text-secondary);font-size:0.82rem">⭐ Reputation:</span>
                <span class="gift-rep-chip giver">+5 🎁 Giver</span>
                <span class="gift-rep-chip receiver">+1 📦 Receiver</span>
            </div>

            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="_submitGift()" id="gift-submit-btn"
                    style="background:linear-gradient(135deg,hsl(330,55%,50%),hsl(350,50%,45%))">
                    🎁 Send Gift
                </button>
                <span id="gift-submit-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    // ── Gift History ──────────────────────────────────────────
    let historyHtml;
    if (!history || history.length === 0) {
        historyHtml = `
            <div class="gift-empty-state">
                <div class="gift-empty-icon">🎁</div>
                <p>No gifts have been exchanged yet. Use the form above to give your first gift!</p>
            </div>`;
    } else {
        historyHtml = `<div class="gift-history-list">` +
            history.map(g => _renderGiftHistoryItem(g)).join('') +
            `</div>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🎁 Gifting</h2>
                <p>Give items to council members, characters, or users — and earn reputation for generosity.</p>
            </div>
            ${giftForm}
            <div class="gift-history-header">
                <h3>📜 Gift History</h3>
                <span class="gift-history-count">${(history || []).length} gift${(history || []).length !== 1 ? 's' : ''} recorded</span>
            </div>
            ${historyHtml}
        </div>`;

    // Store data for form interactions
    state._giftRecipients = recipientOptions;
    state._giftableItems = giftableItems;
}


// ═══════════════════════════════════════════════════════════════
// Form Interactions
// ═══════════════════════════════════════════════════════════════

function _onGiftItemChange() {
    const select = document.getElementById('gift-item-select');
    const fromSelect = document.getElementById('gift-from-select');
    const previewArea = document.getElementById('gift-item-preview-area');

    if (!select || !fromSelect) return;

    const selectedOption = select.options[select.selectedIndex];
    if (!select.value) {
        fromSelect.innerHTML = '<option value="">-- Select item first --</option>';
        fromSelect.disabled = true;
        if (previewArea) previewArea.style.display = 'none';
        return;
    }

    // Parse owners from the selected option
    let owners = [];
    try {
        owners = JSON.parse(selectedOption.dataset.owners || '[]');
    } catch { owners = []; }

    // Populate from-owner dropdown
    fromSelect.innerHTML = owners.map((o, i) =>
        `<option value="${i}">${o.type === 'council_member' ? '👑' : o.type === 'character' ? '🎭' : '👤'} ${escapeHtml(o.name)} (${o.type.replace('_', ' ')})</option>`
    ).join('');
    fromSelect.disabled = false;

    // Show item preview
    const itemName = selectedOption.dataset.name || '';
    const imgUrl = selectedOption.dataset.img || '';

    const imgHtml = imgUrl
        ? `<div class="gift-item-preview-img" style="background-image:url('${imgUrl}')"></div>`
        : `<div class="gift-item-preview-img gift-item-preview-img-placeholder">📦</div>`;

    if (previewArea) {
        previewArea.style.display = 'block';
        previewArea.innerHTML = `
            <div class="gift-item-preview" style="margin-top:var(--space-sm)">
                ${imgHtml}
                <div class="gift-item-preview-text">
                    <div class="gift-item-preview-name">${escapeHtml(itemName)}</div>
                    <div class="gift-item-preview-meta">${owners.length} owner${owners.length !== 1 ? 's' : ''} · ID: ${select.value}</div>
                </div>
            </div>`;
    }
}

function _onGiftRecipientChange() {
    const nameInput = document.getElementById('gift-to-name');
    const typeSelect = document.getElementById('gift-to-type');
    if (!nameInput || !typeSelect || !state._giftRecipients) return;

    const typed = nameInput.value.trim().toLowerCase();
    const match = state._giftRecipients.find(
        r => r.name.toLowerCase() === typed
    );

    if (match) {
        typeSelect.value = match.type;
    }
}


// ═══════════════════════════════════════════════════════════════
// Submit Gift
// ═══════════════════════════════════════════════════════════════

async function _submitGift() {
    const btn = document.getElementById('gift-submit-btn');
    const status = document.getElementById('gift-submit-status');
    const itemSelect = document.getElementById('gift-item-select');
    const fromSelect = document.getElementById('gift-from-select');
    const toNameInput = document.getElementById('gift-to-name');
    const toTypeSelect = document.getElementById('gift-to-type');
    const messageInput = document.getElementById('gift-message');

    const itemId = itemSelect?.value;
    const fromIdx = parseInt(fromSelect?.value || '0', 10);
    const toName = toNameInput?.value?.trim();
    const toType = toTypeSelect?.value || 'user';
    const message = messageInput?.value?.trim() || '';

    if (!itemId) {
        showToast('Please select an item to gift.', true);
        itemSelect?.focus();
        return;
    }
    if (!toName) {
        showToast('Please enter a recipient name.', true);
        toNameInput?.focus();
        return;
    }

    // Get the from_owner by looking up the item
    let currentItem;
    try {
        currentItem = await api(`/api/items/${encodeURIComponent(itemId)}`);
    } catch (err) {
        showToast(`Failed to load item: ${err.message}`, true);
        return;
    }

    const fromOwner = (currentItem.owned_by || [])[fromIdx];
    if (!fromOwner) {
        showToast('Selected giver not found. Please re-select.', true);
        return;
    }

    if (!confirm(`Gift "${currentItem.name}" from ${fromOwner.name} to ${toName}?`)) return;

    btn.disabled = true;
    btn.textContent = '⏳ Sending gift…';
    if (status) status.textContent = '';

    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}/gift`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_owner: fromOwner,
                to_owner: { name: toName, type: toType },
                message: message,
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Gift failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`🎁 "${currentItem.name}" gifted to ${toName}! ⭐ +5 giver / +1 receiver reputation`);

        // Refresh the view
        await renderGifts();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (status) {
            status.textContent = '❌ Failed';
            status.style.color = 'var(--accent-rose)';
        }
    } finally {
        btn.disabled = false;
        btn.textContent = '🎁 Send Gift';
    }
}


// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function _buildRecipientOptions(council, characters) {
    const options = [];

    // Council members
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

    // Characters
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

function _renderGiftHistoryItem(gift) {
    const fromType = (gift.from_owner || {}).type || 'user';
    const fromName = (gift.from_owner || {}).name || 'Unknown';
    const toType = (gift.to_owner || {}).type || 'user';
    const toName = (gift.to_owner || {}).name || 'Unknown';
    const itemName = gift.item_name || 'Unknown Item';
    const itemId = gift.item_id || '';

    const fromIcon = fromType === 'council_member' ? '👑' : fromType === 'character' ? '🎭' : '👤';
    const toIcon = toType === 'council_member' ? '👑' : toType === 'character' ? '🎭' : '👤';

    // Extract clean message (remove the emoji prefix if present)
    let msg = gift.message || '';
    if (msg.startsWith('🎁')) {
        const newline = msg.indexOf('\n');
        msg = newline > 0 ? msg.slice(newline + 1).trim() : '';
    }

    const clickAction = itemId ? `onclick="navigateTo('items','${escapeAttr(itemId)}')"` : '';

    return `
        <div class="gift-history-item" ${clickAction}>
            <div class="gift-history-icon">🎁</div>
            <div class="gift-history-body">
                <div class="gift-history-title">${escapeHtml(itemName)}</div>
                <div class="gift-history-detail">
                    <span class="gift-owner-badge ${fromType}">${fromIcon} ${escapeHtml(fromName)}</span>
                    <span class="gift-history-arrow">→</span>
                    <span class="gift-owner-badge ${toType}">${toIcon} ${escapeHtml(toName)}</span>
                </div>
                ${msg ? `<div class="gift-history-msg">"${escapeHtml(msg)}"</div>` : ''}
            </div>
            <div class="gift-history-right">
                <span class="gift-history-date">${formatDate(gift.timestamp)}</span>
                <div class="gift-history-rep">
                    <span class="gift-rep-chip giver">+5</span>
                    <span class="gift-rep-chip receiver">+1</span>
                </div>
            </div>
        </div>`;
}
