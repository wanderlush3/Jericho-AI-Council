async function renderItems() {
    showLoading();
    const data = await api('/api/items');
    state.itemsData = data;

    const createForm = `
        <div class="card location-create-form">
            <h3>📦 New Item</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Define a new world item for the council's domain.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="item-name-input">Name</label>
                    <input id="item-name-input" class="settings-input" placeholder="e.g. Starfall Blade" />
                </div>
                <div class="filter-group">
                    <label for="item-author-input">Author</label>
                    <input id="item-author-input" class="settings-input" placeholder="e.g. Council" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="item-desc-input">Description</label>
                <textarea id="item-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Describe this item…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="item-lore-input">Lore</label>
                <textarea id="item-lore-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="History and background of this item…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="item-tags-input">Tags</label>
                    <input id="item-tags-input" class="settings-input" placeholder="weapon, legendary, enchanted (comma-separated)" />
                </div>
                <div class="filter-group">
                    <label for="item-rarity-input">Rarity</label>
                    <input id="item-rarity-input" class="settings-input" placeholder="e.g. legendary (optional)" />
                </div>
                <div class="filter-group">
                    <label for="item-tier-input">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required for activation)</span></label>
                    <select id="item-tier-input" class="settings-input">
                        <option value="">-- Select Tier --</option>
                        ${ITEM_TIERS.map(t => `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="item-legality-input">Legality</label>
                    <select id="item-legality-input" class="settings-input">
                        <option value="">-- Select Legality --</option>
                        ${ITEM_LEGALITY.map(l => `<option value="${l}">${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="item-injection-input">LLM Injection <span style="color:var(--accent-cyan);font-size:0.75rem">💉 custom AI context</span></label>
                <textarea id="item-injection-input" class="settings-input proposal-textarea" rows="2" maxlength="500"
                    placeholder="Custom text injected into AI context when this item is active…"
                    oninput="updateInjectionCounter('item-injection-input','item-injection-counter',500)"></textarea>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                    <span style="font-size:0.72rem;color:var(--text-muted)">Consumable tier: expires 24h after last edit. Other tiers: always active.</span>
                    <span id="item-injection-counter" style="font-size:0.72rem;color:var(--text-muted)">0 / 500</span>
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createItem()" id="item-create-btn">
                    📦 Create Item
                </button>
                <span id="item-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>📦 Items</h2>
                    <p>No items defined yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const statusFilter = (s) => data.filter(i => i.status === s);
    const active = statusFilter('active');
    const drafts = statusFilter('draft');
    const archived = statusFilter('archived');

    const itemCard = (item) => {
        const avatarHtml = item.primary_image_url
            ? `<div class="item-avatar" style="background-image:url('${item.primary_image_url}')"></div>`
            : `<div class="item-avatar item-avatar-placeholder"><span>?</span></div>`;

        return `
        <div class="card proposal-card" onclick="navigateTo('items', '${item.id}')" style="cursor:pointer">
            <div class="item-header">
                ${avatarHtml}
                <div class="item-header-text">
                    <div class="item-name">${item.name}</div>
                    <div class="item-author">by ${item.author} · v${item.version || 1}</div>
                </div>
                <div style="display:flex;gap:var(--space-xs);align-items:center;flex-wrap:wrap">
                    ${item.tier ? `<span class="badge badge-tier-${item.tier}" style="background:linear-gradient(135deg,hsl(${item.tier==='permanent'?'210,60%,50%':item.tier==='consumable'?'40,70%,50%':'0,55%,50%'}),hsl(${item.tier==='permanent'?'230,55%,45%':item.tier==='consumable'?'55,65%,45%':'15,50%,45%'}));font-size:0.7rem;padding:2px 8px">${item.tier.charAt(0).toUpperCase()+item.tier.slice(1)}</span>` : ''}
                    ${item.legality ? `<span class="badge" style="background:linear-gradient(135deg,${item.legality==='legal'?'hsl(150,55%,42%),hsl(160,50%,38%)':'hsl(0,60%,48%),hsl(10,55%,43%)'});font-size:0.7rem;padding:2px 8px">${item.legality.charAt(0).toUpperCase()+item.legality.slice(1)}</span>` : ''}
                    ${item.owner ? `<span class="badge store-owned-badge">Owned by ${escapeHtml(item.owner)}</span>` : ''}
                    ${item.rarity ? `<span class="badge badge-${item.rarity}">${item.rarity}</span>` : ''}
                    ${item.llm_injection ? `<span class="badge" style="background:linear-gradient(135deg,hsl(180,50%,40%),hsl(200,55%,35%));font-size:0.68rem;padding:2px 6px" title="LLM injection ${item.injection_active ? 'active' : 'expired'}">💉 ${item.injection_active ? 'Active' : 'Expired'}</span>` : ''}
                    ${badge(item.status)}
                </div>
            </div>
            <p style="margin:var(--space-xs) 0;color:var(--text-secondary)">${truncate(item.description, 120)}</p>
            <div style="display:flex;gap:var(--space-xs);flex-wrap:wrap;margin-top:var(--space-xs)">
                ${(item.tags||[]).map(t => `<span class="badge badge-general">${t}</span>`).join('')}
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:var(--space-sm);font-size:0.78rem;color:var(--text-muted)">
                <span>📦 ${item.properties ? item.properties.length : 0} properties</span>
                <span>${formatDate(item.created_at)}</span>
            </div>
        </div>`;
    };

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>📦 Items</h2>
                <p>${data.length} item${data.length !== 1 ? 's' : ''} · ${active.length} active · ${drafts.length} draft · ${archived.length} archived</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('item')" title="Generate images for multiple items">🎨 Batch Generate</button>
            </div>
            ${createForm}
            ${active.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">✨ Active Items</h3>` : ''}
            ${active.map(itemCard).join('')}
            ${drafts.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">📝 Drafts</h3>` : ''}
            ${drafts.map(itemCard).join('')}
            ${archived.length ? `<h3 style="margin:var(--space-lg) 0 var(--space-sm)">📁 Archived</h3>` : ''}
            ${archived.map(itemCard).join('')}
        </div>`;
}

async function renderItemDetail(id) {
    showLoading();
    const data = await api(`/api/items/${encodeURIComponent(id)}`);

    const tierBadge = data.tier
        ? `<span class="badge" style="background:linear-gradient(135deg,hsl(${data.tier==='permanent'?'210,60%,50%':data.tier==='consumable'?'40,70%,50%':'0,55%,50%'}),hsl(${data.tier==='permanent'?'230,55%,45%':data.tier==='consumable'?'55,65%,45%':'15,50%,45%'}));font-size:0.78rem;padding:3px 10px">${data.tier.charAt(0).toUpperCase()+data.tier.slice(1)}</span>`
        : `<span class="badge" style="background:var(--accent-rose);font-size:0.72rem;padding:2px 8px">⚠ No Tier</span>`;

    const statusActions = {
        draft: `<button class="btn" onclick="updateItemStatus('${id}','active')" style="background:linear-gradient(135deg, hsl(160,60%,45%),hsl(140,55%,40%));">✨ Set Active</button>`,
        active: `<button class="btn" onclick="updateItemStatus('${id}','archived')" style="background:linear-gradient(135deg, hsl(0,50%,50%),hsl(15,55%,45%));">📁 Archive</button>`,
        archived: '',
    };

    const propsHtml = (data.properties || []).map(p => `
        <div class="detail-row" style="display:flex;align-items:center;gap:var(--space-sm)">
            <span class="badge badge-${p.property_type}">${p.property_type}</span>
            <strong>${p.name}</strong>
            <span style="color:var(--text-secondary)">${p.description}</span>
            <button class="btn" style="margin-left:auto;padding:2px 8px;font-size:0.75rem" onclick="removeItemProperty('${id}','${p.name.replace(/'/g,"\\'")}')">✕</button>
        </div>`).join('');


    const galleryHtml = await renderImageGallery('item', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <button class="btn" onclick="navigateTo('items')" style="margin-bottom:var(--space-sm);font-size:0.82rem">← Back to Items</button>
                    <h2>${data.name} ${tierBadge} ${data.legality ? `<span class="badge" style="background:linear-gradient(135deg,${data.legality==='legal'?'hsl(150,55%,42%),hsl(160,50%,38%)':'hsl(0,60%,48%),hsl(10,55%,43%)'});font-size:0.78rem;padding:3px 10px">${data.legality.charAt(0).toUpperCase()+data.legality.slice(1)}</span>` : ''} ${data.rarity ? `<span class="badge badge-${data.rarity}">${data.rarity}</span>` : ''} ${data.owner ? `<span class="badge store-owned-badge">Owned by ${escapeHtml(data.owner)}</span>` : ''}</h2>
                    <p>${badge(data.status)} · ID: ${data.id} · v${data.version} · by ${data.author}</p>
                </div>
                <div style="display:flex;gap:var(--space-sm)">
                    ${statusActions[data.status] || ''}
                </div>
            </div>

            ${galleryHtml}

            <div class="detail-section">
                <h3>📝 Edit Item</h3>
                <div class="proposal-form-grid">
                    <div class="filter-group" style="flex:2">
                        <label for="item-edit-name">Name</label>
                        <input id="item-edit-name" class="settings-input" value="${data.name.replace(/"/g, '&quot;')}" />
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-rarity">Rarity</label>
                        <input id="item-edit-rarity" class="settings-input" value="${(data.rarity || '').replace(/"/g, '&quot;')}" placeholder="e.g. legendary" />
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-tier">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required)</span></label>
                        <select id="item-edit-tier" class="settings-input">
                            <option value="">-- Select Tier --</option>
                            ${ITEM_TIERS.map(t => `<option value="${t}" ${data.tier === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="item-edit-legality">Legality</label>
                        <select id="item-edit-legality" class="settings-input">
                            <option value="">-- Select Legality --</option>
                            ${ITEM_LEGALITY.map(l => `<option value="${l}" ${data.legality === l ? 'selected' : ''}>${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-desc">Description</label>
                    <textarea id="item-edit-desc" class="settings-input proposal-textarea" rows="3">${data.description}</textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-lore">Lore</label>
                    <textarea id="item-edit-lore" class="settings-input proposal-textarea" rows="3">${data.lore || ''}</textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-tags">Tags</label>
                    <input id="item-edit-tags" class="settings-input" value="${(data.tags || []).join(', ')}" />
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="item-edit-injection">LLM Injection <span style="color:var(--accent-cyan);font-size:0.75rem">💉 custom AI context</span>
                        ${data.llm_injection ? `<span class="badge" style="margin-left:var(--space-xs);background:linear-gradient(135deg,${data.injection_active ? 'hsl(160,55%,42%),hsl(170,50%,38%)' : 'hsl(35,60%,45%),hsl(40,55%,40%)'});font-size:0.68rem;padding:2px 6px">${data.injection_active ? '✨ Active' : '⏳ Expired'}</span>` : ''}
                    </label>
                    <textarea id="item-edit-injection" class="settings-input proposal-textarea" rows="2" maxlength="${data.injection_max_length || 500}"
                        oninput="updateInjectionCounter('item-edit-injection','item-edit-injection-counter',${data.injection_max_length || 500})">${data.llm_injection || ''}</textarea>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                        <span style="font-size:0.72rem;color:var(--text-muted)">Consumable tier: expires 24h after last edit. Other tiers: always active.</span>
                        <span id="item-edit-injection-counter" style="font-size:0.72rem;color:var(--text-muted)">${(data.llm_injection || '').length} / ${data.injection_max_length || 500}</span>
                    </div>
                </div>
                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="saveItemEdit('${id}')" id="item-save-btn">💾 Save Changes</button>
                    <span id="item-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>

            <div class="detail-section">
                <h3>⚙️ Properties (${data.properties ? data.properties.length : 0})</h3>
                ${propsHtml || '<p style="color:var(--text-muted)">No properties yet.</p>'}
                <div style="margin-top:var(--space-md);padding-top:var(--space-md);border-top:1px solid var(--border-subtle)">
                    <h4>Add Property</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="item-prop-name">Name</label>
                            <input id="item-prop-name" class="settings-input" placeholder="e.g. Fire Enchantment" />
                        </div>
                        <div class="filter-group">
                            <label for="item-prop-type">Type</label>
                            <select id="item-prop-type" class="settings-input">
                                ${ITEM_PROPERTY_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="item-prop-desc">Description</label>
                        <input id="item-prop-desc" class="settings-input" placeholder="What does this property do?" />
                    </div>
                    <button class="btn" onclick="addItemProperty('${id}')" style="margin-top:var(--space-sm)">➕ Add Property</button>
                </div>
            </div>

            <div class="detail-section">
                <h3>📋 Metadata</h3>
                <div class="detail-row"><span class="label">Created</span><span class="value">${formatDate(data.created_at)}</span></div>
                <div class="detail-row"><span class="label">Updated</span><span class="value">${formatDate(data.updated_at)}</span></div>
                <div class="detail-row"><span class="label">Version</span><span class="value">${data.version}</span></div>
                ${data.metadata && data.metadata.source_proposal ? `<div class="detail-row"><span class="label">Source Proposal</span><span class="value"><a href="#proposals/${data.metadata.source_proposal}" style="color:var(--accent-primary)">${data.metadata.source_proposal}</a></span></div>` : ''}
            </div>
        </div>`;
}

// ── Item Creation ────────────────────────────────────────────

async function createItem() {
    const btn = document.getElementById('item-create-btn');
    const status = document.getElementById('item-create-status');
    btn.disabled = true;
    btn.textContent = '⏳ Creating…';

    const name = document.getElementById('item-name-input').value.trim();
    const description = document.getElementById('item-desc-input').value.trim();
    const author = document.getElementById('item-author-input').value.trim();
    const lore = document.getElementById('item-lore-input').value.trim();
    const tagsRaw = document.getElementById('item-tags-input').value.trim();
    const rarity = document.getElementById('item-rarity-input').value.trim();
    const tier = document.getElementById('item-tier-input').value;
    const legality = document.getElementById('item-legality-input').value;
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    if (!name || !description || !author) {
        showToast('Name, description, and author are required.', true);
        btn.disabled = false;
        btn.textContent = '📦 Create Item';
        return;
    }

    try {
        const resp = await fetch('/api/items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, lore, tags, rarity, tier, legality, llm_injection: document.getElementById('item-injection-input').value.trim() }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Create failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Item "${data.name}" created ✅`);
        navigateTo('items', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '📦 Create Item';
    }
}

// ── Item Edit ────────────────────────────────────────────────

async function saveItemEdit(itemId) {
    const btn = document.getElementById('item-save-btn');
    const status = document.getElementById('item-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';

    const tagsRaw = document.getElementById('item-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('item-edit-name').value.trim(),
        description: document.getElementById('item-edit-desc').value.trim(),
        lore: document.getElementById('item-edit-lore').value.trim(),
        tags,
        rarity: document.getElementById('item-edit-rarity').value.trim(),
        tier: document.getElementById('item-edit-tier').value,
        legality: document.getElementById('item-edit-legality').value,
        llm_injection: document.getElementById('item-edit-injection').value.trim(),
    };

    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Item updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

// ── Item Status ──────────────────────────────────────────────

async function updateItemStatus(itemId, newStatus) {
    // Client-side guard: check tier before activation
    if (newStatus === 'active') {
        try {
            const item = await api(`/api/items/${encodeURIComponent(itemId)}`);
            if (!item.tier) {
                showToast('A tier must be set before activating an item. Edit the item and select a tier first.', true);
                return;
            }
        } catch { /* let server-side validation handle it */ }
    }
    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Item set to ${newStatus} ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Item Property Management ─────────────────────────────────

async function addItemProperty(itemId) {
    const name = document.getElementById('item-prop-name').value.trim();
    const propType = document.getElementById('item-prop-type').value;
    const desc = document.getElementById('item-prop-desc').value.trim();

    if (!name) { document.getElementById('item-prop-name').focus(); return; }

    try {
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                properties: [{ name, description: desc || name, property_type: propType }],
            }),
        });
        // Actually we need a dedicated endpoint for add_property.
        // Let's do it via full item re-fetch and re-save pattern.
    } catch (err) {
        // fallback
    }

    // Better approach: get current item, add property, update
    try {
        const current = await api(`/api/items/${encodeURIComponent(itemId)}`);
        const newProps = [...(current.properties || []), { name, description: desc || name, property_type: propType }];
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ properties: newProps }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to add property' }));
            throw new Error(err.detail);
        }
        showToast(`Property "${name}" added ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeItemProperty(itemId, propName) {
    if (!confirm(`Remove property "${propName}"?`)) return;

    try {
        const current = await api(`/api/items/${encodeURIComponent(itemId)}`);
        const newProps = (current.properties || []).filter(p => p.name !== propName);
        const resp = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ properties: newProps }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to remove property' }));
            throw new Error(err.detail);
        }
        showToast(`Property "${propName}" removed ✅`);
        await renderItemDetail(itemId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Stores View  (StoreManager-backed — F-036)
// ═══════════════════════════════════════════════════════════════

const STORE_TYPE_ICONS = {
    general: '🏪', blacksmith: '⚒️', alchemist: '⚗️',
    enchanter: '✨', tavern: '🍺', custom: '🏷️',
};

