async function renderStores() {
    showLoading();
    const data = await api('/api/stores');
    state.storesData = data;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div><h2>🏪 Stores</h2><p>Create and manage world stores where items can be purchased</p></div>
                    <div style="display:flex;gap:var(--space-sm)">
                        <button class="btn btn-secondary" onclick="openLocationStoreModal()" id="btn-add-loc-store">📍 Add Location as Store</button>
                        <button class="btn btn-primary" onclick="document.getElementById('store-create-form').style.display='block'" id="btn-create-store">➕ Create Store</button>
                    </div>
                </div>
                ${_storeCreateForm()}
                <div class="empty-state">
                    <div class="empty-icon">🏪</div>
                    <p>No stores yet. Click <strong>Create Store</strong> or <strong>Add Location as Store</strong> to add one.</p>
                </div>
            </div>`;
        return;
    }

    const filterStatus = state.storeFilterStatus || '';
    const filtered = filterStatus ? data.filter(s => s.status === filterStatus) : data;
    const statusCounts = {};
    data.forEach(s => statusCounts[s.status] = (statusCounts[s.status] || 0) + 1);

    const filters = `
        <div class="filter-group">
            <button class="btn btn-sm ${!filterStatus ? 'btn-primary' : 'btn-secondary'}" onclick="state.storeFilterStatus='';renderStores()">All (${data.length})</button>
            ${Object.entries(statusCounts).map(([st, cnt]) =>
                `<button class="btn btn-sm ${filterStatus === st ? 'btn-primary' : 'btn-secondary'}" onclick="state.storeFilterStatus='${st}';renderStores()">${st} (${cnt})</button>`
            ).join('')}
        </div>`;

    const cards = filtered.map(store => {
        const icon = STORE_TYPE_ICONS[store.store_type] || '🏪';
        const invCount = (store.inventory || []).length;
        const tagsHtml = (store.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');
        const avatarHtml = store.primary_image_url
            ? `<div class="store-avatar" style="background-image:url('${store.primary_image_url}')"></div>`
            : `<div class="store-avatar store-avatar-placeholder"><span>?</span></div>`;
        return `
        <div class="card card-clickable store-card" onclick="navigateTo('stores','${store.id}')">
            <div class="store-card-header">
                ${avatarHtml}
                <div class="store-card-icon">${icon}</div>
                <div style="flex:1">
                    <div class="store-card-name">${escapeHtml(store.name)}</div>
                    <div class="store-card-author">by ${escapeHtml(store.author)} · ${badge(store.status)} · ${badge(store.store_type)}</div>
                </div>
                <div class="store-card-stats">
                    <span class="store-stat">📦 ${invCount} item${invCount !== 1 ? 's' : ''}</span>
                    ${store.owner ? `<span class="store-stat">👤 ${escapeHtml(store.owner)}</span>` : ''}
                </div>
            </div>
            <div class="store-card-desc">${truncate(store.description, 140)}</div>
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🏪 Stores</h2><p>${data.length} store${data.length !== 1 ? 's' : ''}</p></div>
                <div style="display:flex;gap:var(--space-sm)">
                    <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('store')" title="Generate images for multiple stores">🎨 Batch Generate</button>
                    <button class="btn btn-secondary" onclick="openLocationStoreModal()" id="btn-add-loc-store">📍 Add Location as Store</button>
                    <button class="btn btn-primary" onclick="document.getElementById('store-create-form').style.display='block'" id="btn-create-store">➕ Create Store</button>
                </div>
            </div>
            ${_storeCreateForm()}
            ${filters}
            <div class="store-grid">${cards}</div>
        </div>`;
}

function _storeCreateForm() {
    const typeOptions = ['general','blacksmith','alchemist','enchanter','tavern','custom']
        .map(t => `<option value="${t}">${STORE_TYPE_ICONS[t] || ''} ${t}</option>`).join('');
    return `
    <div class="card store-form-card" id="store-create-form" style="display:none;margin-bottom:var(--space-xl)">
        <h3 class="store-form-title">✨ Create New Store</h3>
        <div class="store-form-grid">
            <div class="store-form-field">
                <label class="store-form-label">Store Name</label>
                <input type="text" id="store-new-name" class="store-form-input" placeholder="e.g. Ironhaven Smithy">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Author</label>
                <input type="text" id="store-new-author" class="store-form-input" placeholder="e.g. Council">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Store Type</label>
                <select id="store-new-type" class="store-form-input">${typeOptions}</select>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Owner <span class="store-form-hint">(character or member)</span></label>
                <input type="text" id="store-new-owner" class="store-form-input" placeholder="e.g. Sage">
            </div>
            <div class="store-form-field store-form-full">
                <label class="store-form-label">Description</label>
                <textarea id="store-new-desc" class="store-form-textarea" rows="3" placeholder="A master forge run by the finest artisans…"></textarea>
            </div>
            <div class="store-form-field store-form-full">
                <label class="store-form-label">Lore <span class="store-form-hint">(optional)</span></label>
                <textarea id="store-new-lore" class="store-form-textarea" rows="2" placeholder="Long ago, the first hammer struck…"></textarea>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Location ID <span class="store-form-hint">(optional)</span></label>
                <input type="text" id="store-new-location" class="store-form-input" placeholder="e.g. LOC-0001">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Tags <span class="store-form-hint">(comma-separated)</span></label>
                <input type="text" id="store-new-tags" class="store-form-input" placeholder="weapons, armor">
            </div>
        </div>
        <div class="store-form-actions">
            <button class="btn btn-primary" onclick="submitNewStore()" id="btn-submit-store">🏪 Create Store</button>
            <button class="btn btn-secondary" onclick="document.getElementById('store-create-form').style.display='none'">Cancel</button>
        </div>
    </div>`;
}

// ── Add Location as Store modal ──────────────────────────────

async function openLocationStoreModal() {
    let locations = [];
    try {
        locations = await api('/api/locations?status=active');
    } catch (err) {
        showToast('Failed to load locations: ' + err.message, true);
        return;
    }

    if (!locations.length) {
        showToast('No active locations found. Activate a location first.', true);
        return;
    }

    const typeOptions = ['general','blacksmith','alchemist','enchanter','tavern','custom']
        .map(t => `<option value="${t}">${STORE_TYPE_ICONS[t] || ''} ${t}</option>`).join('');

    const locOptions = locations.map(l =>
        `<option value="${l.id}" data-name="${escapeAttr(l.name)}" data-desc="${escapeAttr(l.description)}">${l.id} — ${escapeHtml(l.name)}</option>`
    ).join('');

    // Build modal
    const overlay = document.createElement('div');
    overlay.className = 'promote-modal-overlay';
    overlay.id = 'loc-store-modal';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    overlay.innerHTML = `
        <div class="store-form-card" style="width:620px;max-width:90vw">
            <h3 class="store-form-title">📍 Add Location as Store</h3>
            <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:var(--space-lg)">
                Create a new store based on an existing active location. The location's name and description will be used.
            </p>
            <div class="store-form-grid">
                <div class="store-form-field store-form-full">
                    <label class="store-form-label">Select Location</label>
                    <select id="loc-store-select" class="store-form-input" onchange="prefillLocationStore()">${locOptions}</select>
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Store Name</label>
                    <input type="text" id="loc-store-name" class="store-form-input" value="${escapeAttr(locations[0].name)}">
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Author</label>
                    <input type="text" id="loc-store-author" class="store-form-input" placeholder="e.g. Council">
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Store Type</label>
                    <select id="loc-store-type" class="store-form-input">${typeOptions}</select>
                </div>
                <div class="store-form-field">
                    <label class="store-form-label">Owner <span class="store-form-hint">(optional)</span></label>
                    <input type="text" id="loc-store-owner" class="store-form-input" placeholder="e.g. Sage">
                </div>
                <div class="store-form-field store-form-full">
                    <label class="store-form-label">Description</label>
                    <textarea id="loc-store-desc" class="store-form-textarea" rows="3">${escapeHtml(locations[0].description)}</textarea>
                </div>
            </div>
            <div class="store-form-actions">
                <button class="btn btn-primary" onclick="submitLocationStore()" id="btn-loc-store-submit">🏪 Create Store from Location</button>
                <button class="btn btn-secondary" onclick="document.getElementById('loc-store-modal').remove()">Cancel</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
}

function prefillLocationStore() {
    const sel = document.getElementById('loc-store-select');
    const opt = sel.options[sel.selectedIndex];
    document.getElementById('loc-store-name').value = opt.dataset.name || '';
    document.getElementById('loc-store-desc').value = opt.dataset.desc || '';
}

async function submitLocationStore() {
    const location_id = document.getElementById('loc-store-select').value;
    const name = document.getElementById('loc-store-name').value.trim();
    const author = document.getElementById('loc-store-author').value.trim();
    const description = document.getElementById('loc-store-desc').value.trim();
    const store_type = document.getElementById('loc-store-type').value;
    const owner = document.getElementById('loc-store-owner').value.trim();

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        return;
    }

    const btn = document.getElementById('btn-loc-store-submit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    try {
        const resp = await fetch('/api/stores', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, store_type, owner, location_id }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Store "${result.name}" created from location ✅`);
        const modal = document.getElementById('loc-store-modal');
        if (modal) modal.remove();
        navigateTo('stores', result.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🏪 Create Store from Location'; }
    }
}

async function submitNewStore() {
    const name = document.getElementById('store-new-name').value.trim();
    const description = document.getElementById('store-new-desc').value.trim();
    const author = document.getElementById('store-new-author').value.trim();
    const store_type = document.getElementById('store-new-type').value;
    const owner = document.getElementById('store-new-owner').value.trim();
    const lore = document.getElementById('store-new-lore').value.trim();
    const location_id = document.getElementById('store-new-location').value.trim();
    const rawTags = document.getElementById('store-new-tags').value.trim();
    const tags = rawTags ? rawTags.split(',').map(t => t.trim()).filter(Boolean) : [];

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        return;
    }

    const btn = document.getElementById('btn-submit-store');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating…'; }

    try {
        const resp = await fetch('/api/stores', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, store_type, owner, lore, location_id, tags }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Store "${result.name}" created ✅`);
        navigateTo('stores', result.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🏪 Create Store'; }
    }
}

async function renderStoreDetail(storeId) {
    showLoading();
    let data;
    let activeItems = [];
    try {
        data = await api(`/api/stores/${encodeURIComponent(storeId)}`);
    } catch (err) {
        showError(err.message);
        return;
    }
    try {
        activeItems = await api('/api/items?status=active');
    } catch { /* items may not exist yet */ }

    const icon = STORE_TYPE_ICONS[data.store_type] || '🏪';
    const inv = data.inventory || [];

    // Status transition buttons
    const transitions = { draft: ['active'], active: ['draft', 'archived'], archived: [] };
    const allowed = transitions[data.status] || [];
    const statusBtns = allowed.map(s =>
        `<button class="btn btn-sm ${s === 'draft' ? 'btn-secondary' : 'btn-primary'}" onclick="setStoreStatus('${storeId}','${s}')" id="btn-store-status-${s}">→ ${s}</button>`
    ).join('');

    // Inventory table
    let invHtml = '';
    if (inv.length) {
        const rows = inv.map(si => {
            const priceDisplay = [
                si.price_gold ? `${si.price_gold}G` : '',
                si.price_silver ? `${si.price_silver}S` : '',
                si.price_bronze ? `${si.price_bronze}B` : '',
            ].filter(Boolean).join(' ') || '—';
            const qtyDisplay = si.quantity === -1 ? '∞' : si.quantity;
            return `
            <tr>
                <td style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:var(--accent-cyan)">${si.item_id}${(() => { const m = activeItems.find(it => it.id === si.item_id); return m ? ` <span style="font-family:inherit;color:var(--text-secondary)">— ${escapeHtml(m.name)}</span>` : ''; })()}</td>
                <td class="store-price-cell">🪙 ${priceDisplay}</td>
                <td style="text-align:center">${qtyDisplay}</td>
                <td style="font-size:0.78rem;color:var(--text-muted)">${formatDate(si.added_at)}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="removeStoreInventory('${storeId}','${si.item_id}')" title="Remove">🗑️</button>
                </td>
            </tr>`;
        }).join('');
        invHtml = `
        <table class="store-inv-table">
            <thead><tr><th>Item ID</th><th>Price</th><th>Qty</th><th>Added</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } else {
        invHtml = '<p style="color:var(--text-muted)">No items in inventory yet.</p>';
    }

    // Build active-items dropdown options (exclude items already in inventory)
    const existingItemIds = new Set(inv.map(si => si.item_id));
    const availableItems = activeItems.filter(it => !existingItemIds.has(it.id));
    const itemOptions = availableItems.length
        ? availableItems.map(it => `<option value="${it.id}">${it.id} — ${escapeHtml(it.name)}</option>`).join('')
        : '<option value="" disabled>No active items available</option>';

    // Add inventory form
    const addInvForm = `
    <div class="card store-form-card" id="store-add-inv-form" style="display:none;margin-top:var(--space-md)">
        <h4 class="store-form-title" style="font-size:1rem">📦 Add Inventory Item</h4>
        <div class="store-form-grid">
            <div class="store-form-field">
                <label class="store-form-label">Select Item</label>
                <select id="sinv-item-id" class="store-form-input">${itemOptions}</select>
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Gold Price</label>
                <input type="number" id="sinv-gold" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Silver Price</label>
                <input type="number" id="sinv-silver" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Bronze Price</label>
                <input type="number" id="sinv-bronze" class="store-form-input" value="0" min="0">
            </div>
            <div class="store-form-field">
                <label class="store-form-label">Quantity <span class="store-form-hint">(-1 = unlimited)</span></label>
                <input type="number" id="sinv-qty" class="store-form-input" value="-1" min="-1">
            </div>
        </div>
        <div class="store-form-actions">
            <button class="btn btn-primary btn-sm" onclick="addStoreInventory('${storeId}')" id="btn-add-inv">➕ Add Item</button>
            <button class="btn btn-secondary btn-sm" onclick="document.getElementById('store-add-inv-form').style.display='none'">Cancel</button>
        </div>
    </div>`;

    // Edit form fields
    const tagsStr = (data.tags || []).join(', ');


    const galleryHtml = await renderImageGallery('store', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('stores')">← Back to Stores</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${icon} ${escapeHtml(data.name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm);align-items:center">
                            ${badge(data.status)} ${badge(data.store_type)}
                            ${data.owner ? `<span style="color:var(--text-secondary);font-size:0.82rem">👤 ${escapeHtml(data.owner)}</span>` : ''}
                            ${data.location_id ? `<span style="color:var(--text-secondary);font-size:0.82rem">📍 ${escapeHtml(data.location_id)}</span>` : ''}
                            <span class="store-stat">📦 ${inv.length} item${inv.length !== 1 ? 's' : ''}</span>
                            ${statusBtns}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('stores')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.lore ? `<div class="detail-section"><h4>📜 Lore</h4><p style="white-space:pre-line">${escapeHtml(data.lore)}</p></div>` : ''}

                <div class="detail-section">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <h4>🛒 Inventory (${inv.length})</h4>
                        <button class="btn btn-sm btn-primary" onclick="document.getElementById('store-add-inv-form').style.display='block'">➕ Add Item</button>
                    </div>
                    ${invHtml}
                    ${addInvForm}
                </div>

                ${data.status === 'active' && inv.length ? `
                <div class="detail-section">
                    <h4>💰 Purchase an Item</h4>
                    <div class="store-form-grid">
                        <div class="store-form-field">
                            <label class="store-form-label">Select Item</label>
                            <select id="purchase-item-id" class="store-form-input">
                                ${inv.map(si => {
                                    const matchedItem = activeItems.find(it => it.id === si.item_id);
                                    const label = matchedItem ? `${si.item_id} — ${escapeHtml(matchedItem.name)}` : si.item_id;
                                    const qtyLabel = si.quantity === -1 ? '∞' : si.quantity;
                                    const priceLabel = [si.price_gold ? si.price_gold + 'G' : '', si.price_silver ? si.price_silver + 'S' : '', si.price_bronze ? si.price_bronze + 'B' : ''].filter(Boolean).join(' ') || 'Free';
                                    return `<option value="${si.item_id}">${label} · ${priceLabel} · Qty: ${qtyLabel}</option>`;
                                }).join('')}
                            </select>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Buyer Account ID</label>
                            <input type="text" id="purchase-buyer" class="store-form-input" placeholder="ACCT-user-human">
                        </div>
                    </div>
                    <div class="store-form-actions">
                        <button class="btn btn-primary" onclick="purchaseFromStore('${storeId}')" id="btn-purchase">💰 Purchase</button>
                    </div>
                </div>` : ''}

                ${galleryHtml}

                <div class="detail-section">
                    <h4>✏️ Edit Store</h4>
                    <div class="store-form-grid">
                        <div class="store-form-field">
                            <label class="store-form-label">Name</label>
                            <input type="text" id="store-edit-name" class="store-form-input" value="${escapeAttr(data.name)}">
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Owner</label>
                            <input type="text" id="store-edit-owner" class="store-form-input" value="${escapeAttr(data.owner || '')}">
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Store Type</label>
                            <select id="store-edit-type" class="store-form-input">
                                ${['general','blacksmith','alchemist','enchanter','tavern','custom']
                                    .map(t => `<option value="${t}" ${t===data.store_type?'selected':''}>${STORE_TYPE_ICONS[t]||''} ${t}</option>`).join('')}
                            </select>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Location ID</label>
                            <input type="text" id="store-edit-location" class="store-form-input" value="${escapeAttr(data.location_id || '')}">
                        </div>
                        <div class="store-form-field store-form-full">
                            <label class="store-form-label">Description</label>
                            <textarea id="store-edit-desc" class="store-form-textarea" rows="3">${escapeHtml(data.description)}</textarea>
                        </div>
                        <div class="store-form-field store-form-full">
                            <label class="store-form-label">Lore</label>
                            <textarea id="store-edit-lore" class="store-form-textarea" rows="2">${escapeHtml(data.lore || '')}</textarea>
                        </div>
                        <div class="store-form-field">
                            <label class="store-form-label">Tags</label>
                            <input type="text" id="store-edit-tags" class="store-form-input" value="${escapeAttr(tagsStr)}">
                        </div>
                    </div>
                    <div class="store-form-actions">
                        <button class="btn btn-primary" onclick="updateStore('${storeId}')" id="btn-update-store">💾 Save Changes</button>
                    </div>
                </div>

                <div class="detail-section" style="font-size:0.82rem;color:var(--text-muted)">
                    Created: ${formatDate(data.created_at)} · Updated: ${formatDate(data.updated_at)} · Version: ${data.version}
                </div>
            </div>
        </div>`;
}

async function setStoreStatus(storeId, newStatus) {
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Status change failed' }));
            throw new Error(err.detail);
        }
        showToast(`Store status → ${newStatus} ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function addStoreInventory(storeId) {
    const item_id = document.getElementById('sinv-item-id').value.trim();
    const price_gold = parseInt(document.getElementById('sinv-gold').value, 10) || 0;
    const price_silver = parseInt(document.getElementById('sinv-silver').value, 10) || 0;
    const price_bronze = parseInt(document.getElementById('sinv-bronze').value, 10) || 0;
    const quantity = parseInt(document.getElementById('sinv-qty').value, 10);

    if (!item_id) { showToast('Item ID is required.', true); return; }

    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/inventory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id, price_gold, price_silver, price_bronze, quantity }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Add failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item ${item_id} added to inventory ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeStoreInventory(storeId, itemId) {
    if (!confirm(`Remove ${itemId} from inventory?`)) return;
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/inventory/${encodeURIComponent(itemId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Remove failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item ${itemId} removed ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function updateStore(storeId) {
    const body = {
        name: document.getElementById('store-edit-name').value.trim(),
        description: document.getElementById('store-edit-desc').value.trim(),
        lore: document.getElementById('store-edit-lore').value.trim(),
        owner: document.getElementById('store-edit-owner').value.trim(),
        store_type: document.getElementById('store-edit-type').value,
        location_id: document.getElementById('store-edit-location').value.trim(),
        tags: document.getElementById('store-edit-tags').value.split(',').map(t => t.trim()).filter(Boolean),
    };
    const btn = document.getElementById('btn-update-store');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }
    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Update failed' }));
            throw new Error(err.detail);
        }
        showToast('Store updated ✅');
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
    }
}

async function purchaseFromStore(storeId) {
    const item_id = document.getElementById('purchase-item-id').value.trim();
    const buyer_account_id = document.getElementById('purchase-buyer').value.trim();

    if (!item_id || !buyer_account_id) {
        showToast('Item ID and Buyer Account ID are required.', true);
        return;
    }

    const btn = document.getElementById('btn-purchase');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Processing…'; }

    try {
        const resp = await fetch(`/api/stores/${encodeURIComponent(storeId)}/purchase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id, buyer_account_id }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Purchase failed' }));
            throw new Error(err.detail);
        }
        const result = await resp.json();
        showToast(`Purchased ${result.item.item_id} successfully! ✅`);
        await renderStoreDetail(storeId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💰 Purchase'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Analytics View
// ═══════════════════════════════════════════════════════════════

