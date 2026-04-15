async function renderLocations() {
    showLoading();
    const data = await api('/api/locations');
    state.locationsData = data;

    const createForm = `
        <div class="card location-create-form">
            <h3>🌍 New Location</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Define a new world location for the council's domain.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="loc-name-input">Name</label>
                    <input id="loc-name-input" class="settings-input" placeholder="e.g. Ironhaven" />
                </div>
                <div class="filter-group">
                    <label for="loc-author-input">Author</label>
                    <input id="loc-author-input" class="settings-input" placeholder="e.g. Council" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="loc-desc-input">Description</label>
                <textarea id="loc-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Describe this location…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="loc-lore-input">Lore</label>
                <textarea id="loc-lore-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="History and background of this place…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="loc-tags-input">Tags</label>
                    <input id="loc-tags-input" class="settings-input" placeholder="port, fortress, capital (comma-separated)" />
                </div>
                <div class="filter-group">
                    <label for="loc-coords-input">Coordinates</label>
                    <input id="loc-coords-input" class="settings-input" placeholder="e.g. 42.3N, 71.1W (optional)" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="loc-injection-input">LLM Injection <span style="color:var(--accent-cyan);font-size:0.75rem">💉 custom AI context</span></label>
                <textarea id="loc-injection-input" class="settings-input proposal-textarea" rows="2" maxlength="800"
                    placeholder="Custom text always injected into AI context for this location…"
                    oninput="updateInjectionCounter('loc-injection-input','loc-injection-counter',800)"></textarea>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                    <span style="font-size:0.72rem;color:var(--text-muted)">Static: always active while this location is active.</span>
                    <span id="loc-injection-counter" style="font-size:0.72rem;color:var(--text-muted)">0 / 800</span>
                </div>
            </div>
            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createLocation()" id="loc-create-btn">
                    🌍 Create Location
                </button>
                <span id="loc-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🗺️ Locations</h2>
                    <p>No locations defined yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const cards = data.map(loc => {
        const featuresHtml = (loc.features || []).slice(0, 3).map(f =>
            `<span class="location-feature-chip">
                <span class="feature-type-dot feature-type-${f.feature_type}"></span>
                ${escapeHtml(f.name)}
            </span>`
        ).join('');

        const tagsHtml = (loc.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');
        const moreFeats = (loc.features || []).length > 3 ? `<span class="location-feature-chip">+${loc.features.length - 3} more</span>` : '';

        // Avatar: show primary image or question mark placeholder
        const avatarHtml = loc.primary_image_url
            ? `<div class="loc-avatar" style="background-image:url('${loc.primary_image_url}')"></div>`
            : `<div class="loc-avatar loc-avatar-placeholder"><span>?</span></div>`;

        return `
        <div class="card card-clickable location-card" onclick="navigateTo('locations','${loc.id}')">
            <div class="loc-header">
                ${avatarHtml}
                <div class="loc-header-text">
                    <div class="loc-name">${escapeHtml(loc.name)}</div>
                    <div class="loc-author">by ${escapeHtml(loc.author)} · v${loc.version || 1}</div>
                </div>
                <div style="display:flex;gap:var(--space-xs);align-items:center">
                    ${loc.llm_injection ? '<span class="badge" style="background:linear-gradient(135deg,hsl(180,50%,40%),hsl(200,55%,35%));font-size:0.68rem;padding:2px 6px" title="Has LLM injection">💉</span>' : ''}
                    ${badge(loc.status)}
                </div>
            </div>
            <div class="loc-desc">${truncate(loc.description, 120)}</div>
            ${featuresHtml || moreFeats ? `<div class="location-features-row">${featuresHtml}${moreFeats}</div>` : ''}
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🗺️ Locations</h2>
                <p>${data.length} world location${data.length !== 1 ? 's' : ''}</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('location')" title="Generate images for multiple locations">🎨 Batch Generate</button>
            </div>
            ${createForm}
            <div class="location-grid">${cards}</div>
        </div>`;
}

async function renderLocationDetail(id) {
    showLoading();
    const data = await api(`/api/locations/${encodeURIComponent(id)}`);

    const featuresHtml = (data.features || []).map(f => `
        <div class="location-feature-detail">
            <div class="location-feature-detail-header">
                <span class="feature-type-dot feature-type-${f.feature_type}"></span>
                <strong>${escapeHtml(f.name)}</strong>
                <span class="specialty-tag">${f.feature_type}</span>
            </div>
            <p class="location-feature-detail-desc">${escapeHtml(f.description)}</p>
        </div>`).join('');

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');

    // Load children
    let childrenHtml = '';
    try {
        const children = await api(`/api/locations?parent_location_id=${encodeURIComponent(id)}`);
        if (children.length) {
            childrenHtml = `<div class="detail-section">
                <h4>🏛️ Sub-locations (${children.length})</h4>
                <div class="location-children-list">
                    ${children.map(c => `
                        <div class="card card-clickable location-child" onclick="navigateTo('locations','${c.id}')">
                            <strong>${escapeHtml(c.name)}</strong>
                            <span style="color:var(--text-muted);font-size:0.82rem">${truncate(c.description, 60)}</span>
                            ${badge(c.status)}
                        </div>`).join('')}
                </div>
            </div>`;
        }
    } catch { /* ignore */ }

    // Status action buttons
    let statusActions = '';
    if (data.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateLocationStatus('${data.id}', 'active')">✅ Activate</button>`;
    } else if (data.status === 'active') {
        statusActions = `
            <button class="btn btn-secondary btn-sm" onclick="updateLocationStatus('${data.id}', 'draft')">📝 → Draft</button>
            <button class="btn btn-secondary btn-sm" onclick="updateLocationStatus('${data.id}', 'archived')">📦 Archive</button>`;
    }


    const galleryHtml = await renderImageGallery('location', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('locations')">← Back to Locations</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id} · v${data.version || 1}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${escapeHtml(data.author)}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;align-items:center;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${statusActions}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('locations')">✕</button>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.lore ? `<div class="detail-section"><h4>📜 Lore</h4><p style="white-space:pre-line">${escapeHtml(data.lore)}</p></div>` : ''}

                ${data.coordinates ? `<div class="detail-section"><h4>📍 Coordinates</h4><p style="font-family:'JetBrains Mono',monospace;color:var(--accent-cyan)">${escapeHtml(data.coordinates)}</p></div>` : ''}

                ${featuresHtml ? `<div class="detail-section"><h4>⭐ Features (${data.features.length})</h4><div class="location-features-list">${featuresHtml}</div></div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                ${data.parent_location_id ? `<div class="detail-section"><h4>🔗 Parent Location</h4><a class="location-parent-link" onclick="navigateTo('locations','${data.parent_location_id}')">${data.parent_location_id}</a></div>` : ''}

                ${childrenHtml}

                ${galleryHtml}

                <div class="detail-section" style="margin-top:var(--space-xl);border-top:1px solid var(--border-subtle);padding-top:var(--space-lg)">
                    <h4>✏️ Edit Location</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="loc-edit-name">Name</label>
                            <input id="loc-edit-name" class="settings-input" value="${escapeAttr(data.name)}" />
                        </div>
                        <div class="filter-group">
                            <label for="loc-edit-coords">Coordinates</label>
                            <input id="loc-edit-coords" class="settings-input" value="${escapeAttr(data.coordinates)}" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-desc">Description</label>
                        <textarea id="loc-edit-desc" class="settings-input proposal-textarea" rows="2">${escapeHtml(data.description)}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-lore">Lore</label>
                        <textarea id="loc-edit-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.lore || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-tags">Tags</label>
                        <input id="loc-edit-tags" class="settings-input" value="${escapeAttr((data.tags || []).join(', '))}" />
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="loc-edit-injection">LLM Injection <span style="color:var(--accent-cyan);font-size:0.75rem">💉 custom AI context</span>
                            ${data.llm_injection ? '<span class="badge" style="margin-left:var(--space-xs);background:linear-gradient(135deg,hsl(160,55%,42%),hsl(170,50%,38%));font-size:0.68rem;padding:2px 6px">✨ Active</span>' : ''}
                        </label>
                        <textarea id="loc-edit-injection" class="settings-input proposal-textarea" rows="2" maxlength="${data.injection_max_length || 800}"
                            oninput="updateInjectionCounter('loc-edit-injection','loc-edit-injection-counter',${data.injection_max_length || 800})">${escapeHtml(data.llm_injection || '')}</textarea>
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                            <span style="font-size:0.72rem;color:var(--text-muted)">Static: always active while this location is active.</span>
                            <span id="loc-edit-injection-counter" style="font-size:0.72rem;color:var(--text-muted)">${(data.llm_injection || '').length} / ${data.injection_max_length || 800}</span>
                        </div>
                    </div>
                    <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveLocationEdit('${data.id}')" id="loc-save-btn">
                            💾 Save Changes
                        </button>
                        <span id="loc-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>
        </div>`;
}

async function createLocation() {
    const name = document.getElementById('loc-name-input').value.trim();
    const author = document.getElementById('loc-author-input').value.trim();
    const description = document.getElementById('loc-desc-input').value.trim();
    const lore = document.getElementById('loc-lore-input').value.trim();
    const tagsRaw = document.getElementById('loc-tags-input').value.trim();
    const coordinates = document.getElementById('loc-coords-input').value.trim();
    const btn = document.getElementById('loc-create-btn');
    const status = document.getElementById('loc-create-status');

    if (!name) { document.getElementById('loc-name-input').focus(); return; }
    if (!author) { document.getElementById('loc-author-input').focus(); return; }
    if (!description) { document.getElementById('loc-desc-input').focus(); return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = '';

    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    try {
        const resp = await fetch('/api/locations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, author, lore, tags, coordinates, llm_injection: document.getElementById('loc-injection-input').value.trim() }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create location' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Location ${data.id} created ✅`);
        navigateTo('locations', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🌍 Create Location';
    }
}

async function saveLocationEdit(locationId) {
    const btn = document.getElementById('loc-save-btn');
    const status = document.getElementById('loc-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const tagsRaw = document.getElementById('loc-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('loc-edit-name').value.trim(),
        description: document.getElementById('loc-edit-desc').value.trim(),
        lore: document.getElementById('loc-edit-lore').value.trim(),
        coordinates: document.getElementById('loc-edit-coords').value.trim(),
        tags,
        llm_injection: document.getElementById('loc-edit-injection').value.trim(),
    };

    try {
        const resp = await fetch(`/api/locations/${encodeURIComponent(locationId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Location updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderLocationDetail(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

async function updateLocationStatus(locationId, newStatus) {
    try {
        const resp = await fetch(`/api/locations/${encodeURIComponent(locationId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Location set to ${newStatus} ✅`);
        await renderLocationDetail(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Items View
// ═══════════════════════════════════════════════════════════════

const ITEM_PROPERTY_TYPES = ['magical', 'physical', 'consumable', 'equipment', 'material', 'custom'];
const ITEM_TIERS = ['permanent', 'consumable', 'degradable'];
const ITEM_LEGALITY = ['contraband', 'legal'];

