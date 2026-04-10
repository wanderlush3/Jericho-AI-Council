async function renderProposals() {
    showLoading();
    const data = await api('/api/proposals');
    state.proposalsData = data;

    // Fetch council members for the author selector
    let members = [];
    try { members = await api('/api/council'); } catch { /* empty */ }

    // Fetch the user's display name so they can author proposals too
    let userName = '';
    try {
        const userResp = await api('/api/settings/user-name');
        userName = (userResp.name || '').trim();
    } catch { /* empty */ }

    const userOption = userName
        ? `<option value="${userName}">${userName} — You</option>
           <option disabled>──────────</option>`
        : '';

    const memberOptions = userOption + members.map(m =>
        `<option value="${m.name}">${m.name} — ${m.role}</option>`
    ).join('');

    const categoryOptions = ['character', 'governance', 'ethics', 'expansion', 'general', 'evolution', 'location', 'item', 'law']
        .map(c => `<option value="${c}">${c.charAt(0).toUpperCase() + c.slice(1)}</option>`)
        .join('');

    const rows = data.map(p => {
        const statusClass = p.status === 'decided' ? 'badge-active'
            : p.status === 'withdrawn' ? 'badge-rejected'
            : p.status === 'open' ? 'badge-open'
            : `badge-${p.status}`;
        return `
        <tr class="proposal-row" onclick="navigateTo('proposals','${p.id}')">
            <td class="col-id">${p.id}</td>
            <td class="col-title">${truncate(p.title, 50)}</td>
            <td>${p.author}</td>
            <td>${badge(p.category)}</td>
            <td>${badge(p.status)}</td>
            <td>${p.reviews ? p.reviews.length : 0}</td>
            <td>${formatDate(p.created_at)}</td>
        </tr>`;
    }).join('');

    const tableHtml = data.length ? `
        <div class="table-wrapper">
            <table class="data-table" id="proposals-table">
                <thead>
                    <tr>
                        <th>ID</th><th>Title</th><th>Author</th>
                        <th>Category</th><th>Status</th><th>Reviews</th><th>Created</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>` : '<div class="empty-state"><div class="empty-icon">📜</div><p>No proposals yet. Create one below!</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>📜 Proposals</h2>
                <p>${data.length} governance proposal${data.length !== 1 ? 's' : ''}</p>
            </div>

            <div class="proposal-form card">
                <h3>📝 New Proposal</h3>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                    Select a council member to author and present a proposal to the full council for discussion and vote.
                </p>
                <div class="proposal-form-grid">
                    <div class="filter-group">
                        <label for="proposal-author-select">Author (Council Member)</label>
                        <select id="proposal-author-select" class="settings-input">
                            <option value="">Select author…</option>
                            ${memberOptions}
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="proposal-category-select">Category</label>
                        <select id="proposal-category-select" class="settings-input" onchange="toggleProposalCategoryFields()">
                            ${categoryOptions}
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <label for="proposal-title-input">Title</label>
                        <input id="proposal-title-input" class="settings-input" placeholder="e.g. Expand Ethical Constraints" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="proposal-desc-input">Description <span id="proposal-desc-hint" style="font-weight:400;font-size:0.78rem;color:var(--accent-cyan)"></span></label>
                    <textarea id="proposal-desc-input" class="settings-input proposal-textarea" rows="3"
                        placeholder="Describe the proposal and its goals…"></textarea>
                </div>

                <!-- Character-specific fields (shown when category=character) -->
                <div id="proposal-char-fields" class="character-fields-panel" style="display:none">
                    <div class="char-fields-header">🎭 Character Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-char-name">Character Name</label>
                            <input id="proposal-char-name" class="settings-input" placeholder="e.g. Atlas" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-provider">API Provider</label>
                            <select id="proposal-char-provider" class="settings-input" onchange="updateProposalCharModelField()">
                                <option value="openrouter">OpenRouter</option>
                                <option value="mancer">Mancer</option>
                                <option value="lmstudio">LM Studio</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-model">Model</label>
                            <div id="proposal-char-model-container">
                                ${renderModelField('proposal-char-model', 'openrouter', '', true)}
                            </div>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-backstory">Backstory</label>
                        <textarea id="proposal-char-backstory" class="settings-input proposal-textarea" rows="3"
                            placeholder="Character history and background — the lion's share of the character's story…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-prompt">System Prompt</label>
                        <textarea id="proposal-char-prompt" class="settings-input proposal-textarea" rows="3"
                            placeholder="You are {{char}}, an adventurous AI who…"></textarea>
                    </div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-char-greeting">Greeting</label>
                            <input id="proposal-char-greeting" class="settings-input" placeholder="First message the character says…" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-char-tags">Tags</label>
                            <input id="proposal-char-tags" class="settings-input" placeholder="explorer, brave (comma-separated)" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-char-examples">Example Messages</label>
                        <textarea id="proposal-char-examples" class="settings-input proposal-textarea" rows="2"
                            placeholder="One message per line…"></textarea>
                    </div>

                    <div class="char-trait-editor" style="margin-top:var(--space-md)">
                        <label>Traits</label>
                        <div id="proposal-char-trait-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group">
                                <input id="proposal-char-trait-name" class="settings-input" placeholder="Trait name (e.g. Curious)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-char-trait-type" class="settings-input">
                                    <option value="personality">Personality</option>
                                    <option value="values">Values</option>
                                    <option value="flaws">Flaws</option>
                                    <option value="custom">Custom</option>
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-char-trait-desc" class="settings-input" placeholder="Trait description…" />
                            </div>
                            <div class="filter-group" style="flex:0.5">
                                <input id="proposal-char-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5"
                                    class="avatar-zoom-slider" oninput="document.getElementById('proposal-char-trait-intensity-val').textContent = this.value" />
                                <span id="proposal-char-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalCharTrait()">
                            ➕ Add Trait
                        </button>
                    </div>
                </div>

                <!-- Location-specific fields (shown when category=location) -->
                <div id="proposal-loc-fields" class="location-fields-panel" style="display:none">
                    <div class="loc-fields-header">🌍 Location Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-loc-name">Location Name</label>
                            <input id="proposal-loc-name" class="settings-input" placeholder="e.g. Ironhaven" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-loc-coords">Coordinates</label>
                            <input id="proposal-loc-coords" class="settings-input" placeholder="e.g. 42.3N, 71.1W (optional)" />
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-loc-lore">Lore</label>
                        <textarea id="proposal-loc-lore" class="settings-input proposal-textarea" rows="3"
                            placeholder="History and background of this place…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-loc-tags">Tags</label>
                        <input id="proposal-loc-tags" class="settings-input" placeholder="port, fortress, capital (comma-separated)" />
                    </div>
                    <div class="loc-feature-editor" style="margin-top:var(--space-md)">
                        <label>Features</label>
                        <div id="proposal-loc-feature-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-loc-feature-name" class="settings-input" placeholder="Feature name (e.g. Great Hall)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-loc-feature-type" class="settings-input">
                                    ${LOCATION_FEATURE_TYPES.map(ft => `<option value="${ft}">${ft.charAt(0).toUpperCase() + ft.slice(1)}</option>`).join('')}
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-loc-feature-desc" class="settings-input" placeholder="Feature description…" />
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalLocFeature()">
                            ➕ Add Feature
                        </button>
                    </div>
                </div>

                <!-- Item-specific fields (shown when category=item) -->
                <div id="proposal-item-fields" class="location-fields-panel" style="display:none">
                    <div class="loc-fields-header">📦 Item Details</div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group" style="flex:2">
                            <label for="proposal-item-name">Item Name</label>
                            <input id="proposal-item-name" class="settings-input" placeholder="e.g. Starfall Blade" />
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-rarity">Rarity</label>
                            <select id="proposal-item-rarity" class="settings-input">
                                <option value="common">Common</option>
                                <option value="uncommon">Uncommon</option>
                                <option value="rare">Rare</option>
                                <option value="epic">Epic</option>
                                <option value="legendary">Legendary</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-tier">Tier <span style="color:var(--accent-rose);font-size:0.75rem">(required)</span></label>
                            <select id="proposal-item-tier" class="settings-input">
                                <option value="">-- Select Tier --</option>
                                ${ITEM_TIERS.map(t => `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
                        </select>
                        </div>
                        <div class="filter-group">
                            <label for="proposal-item-legality">Legality</label>
                            <select id="proposal-item-legality" class="settings-input">
                                <option value="">-- Select Legality --</option>
                                ${ITEM_LEGALITY.map(l => `<option value="${l}">${l.charAt(0).toUpperCase() + l.slice(1)}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-item-lore">Lore</label>
                        <textarea id="proposal-item-lore" class="settings-input proposal-textarea" rows="3"
                            placeholder="History and origin of this item…"></textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="proposal-item-tags">Tags</label>
                        <input id="proposal-item-tags" class="settings-input" placeholder="weapon, legendary, enchanted (comma-separated)" />
                    </div>
                    <div class="loc-feature-editor" style="margin-top:var(--space-md)">
                        <label>Properties</label>
                        <div id="proposal-item-property-list"></div>
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-item-property-name" class="settings-input" placeholder="Property name (e.g. Fire Enchantment)" />
                            </div>
                            <div class="filter-group">
                                <select id="proposal-item-property-type" class="settings-input">
                                    ${ITEM_PROPERTY_TYPES.map(pt => `<option value="${pt}">${pt.charAt(0).toUpperCase() + pt.slice(1)}</option>`).join('')}
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="proposal-item-property-desc" class="settings-input" placeholder="Property description…" />
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addProposalItemProperty()">
                            ➕ Add Property
                        </button>
                    </div>
                </div>

                <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                    <button class="btn btn-primary" onclick="createNewProposal()" id="proposal-create-btn">
                        🚀 Submit Proposal
                    </button>
                    <span id="proposal-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                </div>
            </div>

            ${tableHtml}
        </div>`;
}

// ── Category Fields Toggle & Traits/Features for Proposal ────

let proposalCharTraits = [];
let proposalLocFeatures = [];
let proposalItemProperties = [];

function toggleProposalCategoryFields() {
    const cat = document.getElementById('proposal-category-select').value;
    const charPanel = document.getElementById('proposal-char-fields');
    const locPanel = document.getElementById('proposal-loc-fields');
    const itemPanel = document.getElementById('proposal-item-fields');
    const hint = document.getElementById('proposal-desc-hint');
    const descEl = document.getElementById('proposal-desc-input');

    // Hide all category panels first
    if (charPanel) charPanel.style.display = 'none';
    if (locPanel) locPanel.style.display = 'none';
    if (itemPanel) itemPanel.style.display = 'none';
    if (hint) hint.textContent = '';
    if (descEl) descEl.placeholder = 'Describe the proposal and its goals…';

    if (cat === 'character') {
        if (charPanel) charPanel.style.display = 'block';
        if (hint) hint.textContent = '(character description / background)';
        if (descEl) descEl.placeholder = 'Describe the character — this becomes the character description…';
    } else if (cat === 'location') {
        if (locPanel) locPanel.style.display = 'block';
        if (hint) hint.textContent = '(location description)';
        if (descEl) descEl.placeholder = 'Describe the location — this becomes the location description…';
    } else if (cat === 'item') {
        if (itemPanel) itemPanel.style.display = 'block';
        if (hint) hint.textContent = '(item description)';
        if (descEl) descEl.placeholder = 'Describe the item — this becomes the item description…';
    }
}

// Keep old name as alias for backward compatibility
function toggleProposalCharFields() { toggleProposalCategoryFields(); }

// ── Location Feature Editor for Proposal ─────────────────────

function addProposalLocFeature() {
    const nameEl = document.getElementById('proposal-loc-feature-name');
    const name = nameEl.value.trim();
    const featureType = document.getElementById('proposal-loc-feature-type').value;
    const desc = document.getElementById('proposal-loc-feature-desc').value.trim();
    if (!name) { nameEl.focus(); return; }
    if (proposalLocFeatures.some(f => f.name.toLowerCase() === name.toLowerCase())) {
        showToast('Feature with that name already added', true);
        return;
    }
    proposalLocFeatures.push({ name, description: desc || name, feature_type: featureType });
    nameEl.value = '';
    document.getElementById('proposal-loc-feature-desc').value = '';
    renderProposalLocFeatures();
}

function removeProposalLocFeature(index) {
    proposalLocFeatures.splice(index, 1);
    renderProposalLocFeatures();
}

function renderProposalLocFeatures() {
    const container = document.getElementById('proposal-loc-feature-list');
    if (!container) return;
    if (!proposalLocFeatures.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalLocFeatures.map((f, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(f.name)}</span>
            <span class="specialty-tag">${f.feature_type}</span>
            <span class="trait-desc-small">${escapeHtml(f.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalLocFeature(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

// ── Item Property Editor for Proposal ────────────────────────

function addProposalItemProperty() {
    const nameEl = document.getElementById('proposal-item-property-name');
    const name = nameEl.value.trim();
    const propertyType = document.getElementById('proposal-item-property-type').value;
    const desc = document.getElementById('proposal-item-property-desc').value.trim();
    if (!name) { nameEl.focus(); return; }
    if (proposalItemProperties.some(p => p.name.toLowerCase() === name.toLowerCase())) {
        showToast('Property with that name already added', true);
        return;
    }
    proposalItemProperties.push({ name, description: desc || name, property_type: propertyType });
    nameEl.value = '';
    document.getElementById('proposal-item-property-desc').value = '';
    renderProposalItemProperties();
}

function removeProposalItemProperty(index) {
    proposalItemProperties.splice(index, 1);
    renderProposalItemProperties();
}

function renderProposalItemProperties() {
    const container = document.getElementById('proposal-item-property-list');
    if (!container) return;
    if (!proposalItemProperties.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalItemProperties.map((p, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(p.name)}</span>
            <span class="specialty-tag">${p.property_type}</span>
            <span class="trait-desc-small">${escapeHtml(p.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalItemProperty(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

function updateProposalCharModelField() {
    const provider = document.getElementById('proposal-char-provider').value;
    const container = document.getElementById('proposal-char-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('proposal-char-model', provider, '', true);
}

function addProposalCharTrait() {
    const nameEl = document.getElementById('proposal-char-trait-name');
    const name = nameEl.value.trim();
    const traitType = document.getElementById('proposal-char-trait-type').value;
    const desc = document.getElementById('proposal-char-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('proposal-char-trait-intensity').value);
    if (!name) { nameEl.focus(); return; }
    if (proposalCharTraits.some(t => t.name.toLowerCase() === name.toLowerCase())) {
        showToast('Trait with that name already added', true);
        return;
    }
    proposalCharTraits.push({ trait_type: traitType, name, description: desc || name, intensity });
    nameEl.value = '';
    document.getElementById('proposal-char-trait-desc').value = '';
    document.getElementById('proposal-char-trait-intensity').value = '0.5';
    document.getElementById('proposal-char-trait-intensity-val').textContent = '0.5';
    renderProposalCharTraits();
}

function removeProposalCharTrait(index) {
    proposalCharTraits.splice(index, 1);
    renderProposalCharTraits();
}

function renderProposalCharTraits() {
    const container = document.getElementById('proposal-char-trait-list');
    if (!container) return;
    if (!proposalCharTraits.length) { container.innerHTML = ''; return; }
    container.innerHTML = proposalCharTraits.map((t, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <span class="trait-intensity">${Math.round(t.intensity * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeProposalCharTrait(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

async function createNewProposal() {
    const author = document.getElementById('proposal-author-select').value;
    const title = document.getElementById('proposal-title-input').value.trim();
    const description = document.getElementById('proposal-desc-input').value.trim();
    const category = document.getElementById('proposal-category-select').value;
    const btn = document.getElementById('proposal-create-btn');
    const status = document.getElementById('proposal-create-status');

    if (!author) { document.getElementById('proposal-author-select').focus(); return; }
    if (!title) { document.getElementById('proposal-title-input').focus(); return; }
    if (!description) { document.getElementById('proposal-desc-input').focus(); return; }

    // Build character_data if category is character
    let character_data = null;
    if (category === 'character') {
        const charName = (document.getElementById('proposal-char-name').value || '').trim();
        const backstory = (document.getElementById('proposal-char-backstory').value || '').trim();
        const systemPrompt = (document.getElementById('proposal-char-prompt').value || '').trim();
        const greeting = (document.getElementById('proposal-char-greeting').value || '').trim();
        const tagsRaw = (document.getElementById('proposal-char-tags').value || '').trim();
        const examplesRaw = (document.getElementById('proposal-char-examples').value || '').trim();
        const provider = document.getElementById('proposal-char-provider').value;
        const model = document.getElementById('proposal-char-model').value;

        // Collect any unsaved trait from inputs
        const traitName = (document.getElementById('proposal-char-trait-name').value || '').trim();
        const traits = [...proposalCharTraits];
        if (traitName) {
            traits.push({
                trait_type: document.getElementById('proposal-char-trait-type').value,
                name: traitName,
                description: (document.getElementById('proposal-char-trait-desc').value || '').trim() || traitName,
                intensity: parseFloat(document.getElementById('proposal-char-trait-intensity').value),
            });
        }

        if (!charName) {
            document.getElementById('proposal-char-name').focus();
            status.textContent = 'Character name is required for character proposals';
            return;
        }
        if (!traits.length) {
            document.getElementById('proposal-char-trait-name').focus();
            status.textContent = 'At least one trait is required for character proposals';
            return;
        }

        character_data = {
            name: charName,
            backstory,
            system_prompt: systemPrompt,
            greeting,
            tags: tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            example_messages: examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [],
            traits,
            api_provider: provider,
            model,
        };
    }

    // Build location_data if category is location
    let location_data = null;
    if (category === 'location') {
        const locName = (document.getElementById('proposal-loc-name').value || '').trim();
        const lore = (document.getElementById('proposal-loc-lore').value || '').trim();
        const locTagsRaw = (document.getElementById('proposal-loc-tags').value || '').trim();
        const coordinates = (document.getElementById('proposal-loc-coords').value || '').trim();

        // Collect any unsaved feature from inputs
        const featName = (document.getElementById('proposal-loc-feature-name').value || '').trim();
        const features = [...proposalLocFeatures];
        if (featName) {
            features.push({
                name: featName,
                description: (document.getElementById('proposal-loc-feature-desc').value || '').trim() || featName,
                feature_type: document.getElementById('proposal-loc-feature-type').value,
            });
        }

        if (!locName) {
            document.getElementById('proposal-loc-name').focus();
            status.textContent = 'Location name is required for location proposals';
            return;
        }

        location_data = {
            name: locName,
            description: description,
            lore,
            tags: locTagsRaw ? locTagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            coordinates,
            features,
        };
    }

    // Build item_data if category is item
    let item_data = null;
    if (category === 'item') {
        const itemName = (document.getElementById('proposal-item-name').value || '').trim();
        const lore = (document.getElementById('proposal-item-lore').value || '').trim();
        const itemTagsRaw = (document.getElementById('proposal-item-tags').value || '').trim();
        const rarity = document.getElementById('proposal-item-rarity').value;
        const tier = document.getElementById('proposal-item-tier').value;
        const legality = document.getElementById('proposal-item-legality').value;

        // Collect any unsaved property from inputs
        const propName = (document.getElementById('proposal-item-property-name').value || '').trim();
        const properties = [...proposalItemProperties];
        if (propName) {
            properties.push({
                name: propName,
                description: (document.getElementById('proposal-item-property-desc').value || '').trim() || propName,
                property_type: document.getElementById('proposal-item-property-type').value,
            });
        }

        if (!itemName) {
            document.getElementById('proposal-item-name').focus();
            status.textContent = 'Item name is required for item proposals';
            return;
        }

        if (!tier) {
            document.getElementById('proposal-item-tier').focus();
            status.textContent = 'Tier is required for item proposals';
            return;
        }

        item_data = {
            name: itemName,
            description: description,
            lore,
            tags: itemTagsRaw ? itemTagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [],
            rarity,
            tier,
            legality,
            properties,
        };
    }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = 'Creating proposal and opening discussion…';

    try {
        const payload = { author, title, description, category };
        if (character_data) payload.character_data = character_data;
        if (location_data) payload.location_data = location_data;
        if (item_data) payload.item_data = item_data;

        const resp = await fetch('/api/proposals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create proposal' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        proposalCharTraits = [];  // Reset
        proposalLocFeatures = [];  // Reset
        proposalItemProperties = [];  // Reset
        showToast(`Proposal ${data.id} created by ${author} ✅`);
        navigateTo('proposals', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Submit Proposal';
    }
}

async function renderProposalDetail(id) {
    showLoading();
    const data = await api(`/api/proposals/${encodeURIComponent(id)}`);

    // Try to load discussion data
    let discussion = null;
    try { discussion = await api(`/api/proposals/${encodeURIComponent(id)}/discussion`); } catch { /* no discussion */ }

    // Try to load vote data
    let voteData = null;
    try { voteData = await api(`/api/votes/${encodeURIComponent(id)}`); } catch { /* no vote */ }

    // Fetch council members for avatar URLs
    let proposalMembers = [];
    try { proposalMembers = await api('/api/council'); } catch { /* empty */ }
    const proposalAvatarMap = {};
    proposalMembers.forEach(m => { if (m.avatar_url) proposalAvatarMap[m.name.toLowerCase()] = m.avatar_url; });
    state.proposalAvatarMap = proposalAvatarMap;  // Store for SSE handlers

    const isTerminal = data.status === 'decided' || data.status === 'withdrawn';
    const hasDiscussion = !!discussion;
    const discussionOpen = hasDiscussion && discussion.status === 'open';
    const hasVote = !!voteData;
    const isReviewing = data.status === 'open_to_review';

    // Lifecycle progress bar
    const stages = ['draft', 'open', 'open_to_review', 'under_review', 'decided'];
    const currentIdx = stages.indexOf(data.status);
    const isWithdrawn = data.status === 'withdrawn';
    const lifecycleHtml = `
        <div class="proposal-lifecycle">
            ${stages.map((s, i) => {
                let cls = 'lifecycle-step';
                if (isWithdrawn) {
                    cls += i === 0 ? ' lifecycle-done' : '';
                } else if (i < currentIdx) {
                    cls += ' lifecycle-done';
                } else if (i === currentIdx) {
                    cls += ' lifecycle-active';
                }
                const labels = { draft: 'Draft', open: 'Open', open_to_review: 'Reviewing', under_review: 'Review', decided: 'Decided' };
                return `<div class="${cls}"><span class="lifecycle-dot"></span><span class="lifecycle-label">${labels[s]}</span></div>`;
            }).join('<div class="lifecycle-connector"></div>')}
            ${isWithdrawn ? '<div class="lifecycle-connector"></div><div class="lifecycle-step lifecycle-active lifecycle-withdrawn"><span class="lifecycle-dot"></span><span class="lifecycle-label">Withdrawn</span></div>' : ''}
        </div>`;

    // Discussion feed
    let discussionFeedHtml = '';
    if (hasDiscussion && discussion.contributions && discussion.contributions.length) {
        const contribs = discussion.contributions.map(c => {
            const memberIdx = (discussion.participants || []).indexOf(c.speaker);
            const renderedContent = renderMarkdown(c.content);
            const displayContent = state.silentpassaEnabled ? wrapPresenceContent(renderedContent, c.speaker) : renderedContent;
            return `
            <div class="discussion-message">
                <div class="discussion-message-header">
                    ${memberAvatarWithImage(c.speaker, memberIdx >= 0 ? memberIdx : 0, null, state.proposalAvatarMap && state.proposalAvatarMap[c.speaker.toLowerCase()])}
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
                <h4>💬 Council Discussion (${discussion.contributions.length} contributions, Round ${discussion.current_round}/${discussion.round_count})</h4>
                <div class="discussion-feed" id="discussion-feed">${contribs}</div>
            </div>`;
    } else if (hasDiscussion) {
        discussionFeedHtml = `
            <div class="detail-section">
                <h4>💬 Council Discussion</h4>
                <div class="discussion-feed" id="discussion-feed">
                    <div class="empty-state" style="padding:var(--space-lg)"><div class="empty-icon">💬</div><p>No contributions yet. Start a discussion round!</p></div>
                </div>
            </div>`;
    }

    // Discussion summary (when closed)
    let summaryHtml = '';
    if (hasDiscussion && discussion.status === 'closed' && discussion.summary) {
        summaryHtml = `
            <div class="detail-section">
                <h4>📋 Discussion Summary</h4>
                <p style="color:var(--text-secondary)">${renderMarkdown(discussion.summary)}</p>
            </div>`;
    }

    // Action buttons
    let actionsHtml = '';
    if (!isTerminal) {
        const buttons = [];
        if (discussionOpen && discussion.current_round < discussion.round_count) {
            buttons.push(`<button class="btn btn-primary" onclick="runDiscussionRound('${id}')" id="discuss-btn">▶️ Continue Discussion</button>`);
        }
        if (discussionOpen) {
            buttons.push(`<button class="btn btn-secondary" onclick="pauseDiscussion('${id}')" id="pause-btn">⏸ Pause Discussion</button>`);
        }
        if (discussionOpen && data.status === 'open') {
            buttons.push(`<button class="btn" onclick="sendToReview('${id}')" id="send-review-btn" style="background:linear-gradient(135deg, hsl(45,80%,50%), hsl(35,70%,45%));color:#fff">📝 Send to Review</button>`);
        }
        if (!hasVote && (data.status === 'open' || data.status === 'under_review' || data.status === 'open_to_review')) {
            buttons.push(`<button class="btn btn-accent" onclick="callProposalVote('${id}')" id="vote-btn">🗳️ Call Vote</button>`);
        }
        if (data.status !== 'decided') {
            buttons.push(`<button class="btn btn-danger-outline" onclick="withdrawProposal('${id}','${escapeAttr(data.author)}')" id="withdraw-btn">↩️ Withdraw</button>`);
        }
        if (buttons.length) {
            actionsHtml = `<div class="proposal-actions">${buttons.join('')}</div>`;
        }
    }

    // Scheduled message section (only when discussion is open)
    let scheduledMsgHtml = '';
    if (discussionOpen) {
        let existingMsg = '';
        try {
            const smResp = await api(`/api/proposals/${encodeURIComponent(id)}/scheduled-message`);
            if (smResp && smResp.message) existingMsg = smResp.message;
        } catch { /* no scheduled message */ }

        scheduledMsgHtml = `
            <div class="detail-section scheduled-message-section">
                <h4>📨 Schedule Message for Next Round</h4>
                <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-sm)">
                    This message will be injected into the discussion at the start of the next round, before the council members speak.
                </p>
                <textarea id="scheduled-msg-input" class="settings-input scheduled-message-textarea"
                    rows="3" placeholder="Type your message for the council to consider…">${existingMsg ? escapeHtml(existingMsg) : ''}</textarea>
                <div style="display:flex;gap:var(--space-sm);align-items:center;margin-top:var(--space-sm)">
                    <button class="btn btn-primary btn-sm" onclick="scheduleDiscussionMessage('${id}')" id="schedule-msg-btn">
                        📨 Schedule Message
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="clearScheduledMessage('${id}')" id="clear-msg-btn">
                        🗑️ Clear
                    </button>
                    <span id="scheduled-msg-status" style="font-size:0.78rem;color:var(--text-muted)">
                        ${existingMsg ? '✅ Message scheduled' : ''}
                    </span>
                </div>
            </div>`;
    }

    // Vote results
    let voteResultsHtml = '';
    if (hasVote) {
        const t = voteData.tally || {};
        const votesHtml = (voteData.votes || []).map(v => `
            <div class="vote-item">
                <span class="vote-voter">${v.voter}</span>
                ${badge(v.choice)}
                <span class="vote-reason">${renderMarkdown(v.reason) || '—'}</span>
            </div>`).join('');

        voteResultsHtml = `
            <div class="detail-section vote-results-panel">
                <h4>🗳️ Vote Results</h4>
                <div class="vote-summary-grid">
                    <div class="vote-summary-item vote-for">
                        <div class="vote-summary-count">${t.votes_for || 0}</div>
                        <div class="vote-summary-label">For</div>
                    </div>
                    <div class="vote-summary-item vote-against">
                        <div class="vote-summary-count">${t.votes_against || 0}</div>
                        <div class="vote-summary-label">Against</div>
                    </div>
                    <div class="vote-summary-item vote-abstain">
                        <div class="vote-summary-count">${t.votes_abstain || 0}</div>
                        <div class="vote-summary-label">Abstain</div>
                    </div>
                </div>
                <div style="margin:var(--space-md) 0;max-width:400px">
                    ${approvalBar(t.approval_rate)}
                </div>
                <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:var(--space-md)">
                    Quorum: ${t.quorum_met ? '✅ Met' : '❌ Not met'}
                    · Threshold: ${t.threshold_met ? '✅ Met' : '❌ Not met'}
                    · Result: <strong>${t.approved ? '✅ Approved' : '❌ Not approved'}</strong>
                    ${t.vetoed ? ' · 🚫 VETOED' : ''}
                </div>
                <div class="proposal-actions" style="margin-bottom:var(--space-md)">
                    ${voteData.vetoed
                        ? `<button class="btn btn-primary" onclick="liftVetoProposal('${id}')" id="lift-veto-btn">✅ Lift Veto</button>
                           <span style="font-size:0.82rem;color:var(--text-muted)">Reason: ${escapeHtml(voteData.veto_reason) || '—'}</span>`
                        : `<button class="btn btn-danger-outline" onclick="vetoProposal('${id}')" id="veto-btn">🚫 Veto</button>`
                    }
                </div>
                <h4 style="margin-top:var(--space-md)">Individual Votes (${(voteData.votes || []).length})</h4>
                <div class="votes-breakdown">${votesHtml || '<p style="color:var(--text-muted)">No votes cast.</p>'}</div>
            </div>`;
    }

    // Reviews section (from proposal reviews, not discussion)
    let reviewsHtml = '';
    if (data.reviews && data.reviews.length) {
        reviewsHtml = `
            <div class="detail-section">
                <h4>Reviews (${data.reviews.length})</h4>
                <div class="votes-breakdown">
                    ${data.reviews.map(r => `
                        <div class="vote-item">
                            <span class="vote-voter">${r.reviewer}</span>
                            ${badge(r.stance)}
                            <span class="vote-reason">${renderMarkdown(r.comment) || '—'}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('proposals')">← Back to Proposals</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${escapeHtml(data.title)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            by <strong>${data.author}</strong> · ${formatDate(data.created_at)}
                        </div>
                        <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                            ${badge(data.status)}
                            ${badge(data.category)}
                        </div>
                    </div>
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-sm silentpassa-toggle ${state.silentpassaEnabled ? 'silentpassa-on' : 'silentpassa-off'}" onclick="toggleSilentPass('proposals','${id}')" title="Toggle [PRESENT]/[SILENCE] wrappers">
                            ${state.silentpassaEnabled ? '🔔 SilentPass' : '🔕 SilentPass'}
                        </button>
                        <button class="detail-close" onclick="navigateTo('proposals')">✕</button>
                    </div>
                </div>

                ${lifecycleHtml}
                ${actionsHtml}
                ${scheduledMsgHtml}

                ${isReviewing ? _buildFinalProposalForm(data) : ''}

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${renderMarkdown(data.description)}</p>
                </div>

                ${data.body ? `<div class="detail-section"><h4>Body</h4><div style="white-space:pre-wrap">${renderMarkdown(data.body)}</div></div>` : ''}

                ${discussionFeedHtml}
                ${summaryHtml}
                ${voteResultsHtml}
                ${(data.category === 'evolution' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section evolution-handoff-banner">
                        <h4>🧬 Evolution Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This evolution proposal has been <strong>approved</strong> by the council. You can auto-create an evolution from this proposal or navigate to the Evolution section.</p>
                        <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">
                            <button class="btn btn-primary" onclick="createEvolutionFromProposal('${data.id}')" style="background:linear-gradient(135deg, hsl(275,60%,55%), hsl(300,50%,45%))">
                                🧬 Auto-Create Evolution
                            </button>
                            <button class="btn btn-secondary" onclick="navigateTo('evolution')">
                                📋 Go to Evolution Section
                            </button>
                        </div>
                    </div>` : ''}
                ${(data.category === 'character' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section character-handoff-banner">
                        <h4>🎭 Character Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This character proposal has been <strong>approved</strong> by the council. Create a draft character from the proposal data to continue development in the Characters section.</p>
                        <button class="btn btn-primary" onclick="handoffCharacterProposal('${data.id}')" id="char-handoff-btn" style="background:linear-gradient(135deg, hsl(200,70%,50%), hsl(170,60%,45%))">
                            🎭 Create Draft Character
                        </button>
                    </div>` : ''}
                ${(data.category === 'location' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section location-handoff-banner">
                        <h4>🌍 Location Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This location proposal has been <strong>approved</strong> by the council. Create a draft location from the proposal data to continue development in the Locations section.</p>
                        <button class="btn btn-primary" onclick="handoffLocationProposal('${data.id}')" id="loc-handoff-btn" style="background:linear-gradient(135deg, hsl(160,60%,45%), hsl(140,55%,40%))">
                            🌍 Create Draft Location
                        </button>
                    </div>` : ''}
                ${(data.category === 'item' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section item-handoff-banner">
                        <h4>📦 Item Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This item proposal has been <strong>approved</strong> by the council. Create a draft item from the proposal data to continue development in the Items section.</p>
                        <button class="btn btn-primary" onclick="handoffItemProposal('${data.id}')" id="item-handoff-btn" style="background:linear-gradient(135deg, hsl(30,70%,50%), hsl(40,80%,55%))">
                            📦 Create Draft Item
                        </button>
                    </div>` : ''}
                ${(data.category === 'law' && data.status === 'decided' && hasVote && voteData.tally && voteData.tally.approved)
                    ? `<div class="detail-section law-handoff-banner">
                        <h4>⚖️ Law Handoff</h4>
                        <p style="color:var(--text-secondary);margin-bottom:var(--space-md)">This law proposal has been <strong>approved</strong> by the council. Create a draft law from the proposal data to continue development in the Laws section.</p>
                        <button class="btn btn-primary" onclick="handoffLawProposal('${data.id}')" id="law-handoff-btn" style="background:linear-gradient(135deg, hsl(220,60%,50%), hsl(200,55%,45%))">
                            ⚖️ Create Draft Law
                        </button>
                    </div>` : ''}
                ${reviewsHtml}
            </div>
        </div>`;
}

// ── Proposal Actions ─────────────────────────────────────────

async function runDiscussionRound(proposalId) {
    const btn = document.getElementById('discuss-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Council is discussing…'; }

    const feed = document.getElementById('discussion-feed');
    if (feed) {
        // Clear empty state if present
        const emptyState = feed.querySelector('.empty-state');
        if (emptyState) emptyState.remove();
    }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-stream`, {
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
                                        : memberAvatarWithImage(data.speaker, 0, null, state.proposalAvatarMap && state.proposalAvatarMap[data.speaker.toLowerCase()])}
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
                                const statusEl = document.getElementById('scheduled-msg-status');
                                if (statusEl) statusEl.textContent = '✅ Delivered this round';
                                const inputEl = document.getElementById('scheduled-msg-input');
                                if (inputEl) inputEl.value = '';
                            }
                        } else if (eventType === 'error') {
                            showToast(data.detail || 'Discussion error', true);
                        }
                    } catch { /* invalid JSON line */ }
                    eventType = 'message';
                }
            }
        }

        showToast('Discussion round complete ✅');
        // Refresh the full view to update state
        setTimeout(() => renderProposalDetail(proposalId), 500);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '▶️ Continue Discussion'; }
    }
}

async function scheduleDiscussionMessage(proposalId) {
    const input = document.getElementById('scheduled-msg-input');
    const message = (input && input.value || '').trim();
    if (!message) { if (input) input.focus(); return; }

    const btn = document.getElementById('schedule-msg-btn');
    const status = document.getElementById('scheduled-msg-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/scheduled-message`, {
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

async function clearScheduledMessage(proposalId) {
    const btn = document.getElementById('clear-msg-btn');
    const status = document.getElementById('scheduled-msg-status');
    const input = document.getElementById('scheduled-msg-input');
    if (btn) { btn.disabled = true; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/scheduled-message`, {
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

async function pauseDiscussion(proposalId) {
    const btn = document.getElementById('pause-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Pausing…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-pause`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to pause' }));
            throw new Error(err.detail);
        }
        showToast('Discussion paused ⏸');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⏸ Pause Discussion'; }
    }
}

// ── Send to Review ──────────────────────────────────────────

async function sendToReview(proposalId) {
    const btn = document.getElementById('send-review-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Sending to review…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/send-to-review`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to send to review' }));
            throw new Error(err.detail);
        }
        showToast('Proposal sent to review — prepare the final version 📝');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📝 Send to Review'; }
    }
}

// ── Final Proposal Form Builder ─────────────────────────────

let _finalProposalTraits = [];
let _finalProposalFeatures = [];
let _finalProposalProperties = [];

function _buildFinalProposalForm(data) {
    const meta = data.metadata || {};
    const cat = data.category;

    // Character-specific
    let charFieldsHtml = '';
    if (cat === 'character') {
        const cd = meta.character_data || {};
        _finalProposalTraits = cd.traits || [];
        charFieldsHtml = `
            <div class="char-fields-header" style="margin-top:var(--space-md)">🎭 Character Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-char-name">Character Name</label>
                    <input id="fp-char-name" class="settings-input" value="${escapeAttr(cd.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-char-provider">API Provider</label>
                    <select id="fp-char-provider" class="settings-input">
                        <option value="openrouter" ${(cd.api_provider || '') === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                        <option value="mancer" ${(cd.api_provider || '') === 'mancer' ? 'selected' : ''}>Mancer</option>
                        <option value="lmstudio" ${(cd.api_provider || '') === 'lmstudio' ? 'selected' : ''}>LM Studio</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-char-model">Model</label>
                    <input id="fp-char-model" class="settings-input" value="${escapeAttr(cd.model || 'Default')}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-backstory">Backstory</label>
                <textarea id="fp-char-backstory" class="settings-input proposal-textarea" rows="3">${escapeHtml(cd.backstory || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-prompt">System Prompt</label>
                <textarea id="fp-char-prompt" class="settings-input proposal-textarea" rows="3">${escapeHtml(cd.system_prompt || '')}</textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-char-greeting">Greeting</label>
                    <input id="fp-char-greeting" class="settings-input" value="${escapeAttr(cd.greeting || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-char-tags">Tags</label>
                    <input id="fp-char-tags" class="settings-input" value="${escapeAttr((cd.tags || []).join(', '))}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-char-examples">Example Messages</label>
                <textarea id="fp-char-examples" class="settings-input proposal-textarea" rows="2">${escapeHtml((cd.example_messages || []).join('\n'))}</textarea>
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Traits</label>
                <div id="fp-char-trait-list">
                    ${_finalProposalTraits.map((t, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(t.name)}</span>
                            <span class="specialty-tag">${t.trait_type || 'personality'}</span>
                            <span class="trait-intensity">${Math.round((t.intensity || 0.5) * 100)}%</span>
                            <span class="trait-desc-small">${escapeHtml(t.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    // Location-specific
    let locFieldsHtml = '';
    if (cat === 'location') {
        const ld = meta.location_data || {};
        _finalProposalFeatures = ld.features || [];
        locFieldsHtml = `
            <div class="loc-fields-header" style="margin-top:var(--space-md)">🌍 Location Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-loc-name">Location Name</label>
                    <input id="fp-loc-name" class="settings-input" value="${escapeAttr(ld.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-loc-coords">Coordinates</label>
                    <input id="fp-loc-coords" class="settings-input" value="${escapeAttr(ld.coordinates || '')}" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-loc-lore">Lore</label>
                <textarea id="fp-loc-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(ld.lore || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-loc-tags">Tags</label>
                <input id="fp-loc-tags" class="settings-input" value="${escapeAttr((ld.tags || []).join(', '))}" />
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Features</label>
                <div id="fp-loc-feature-list">
                    ${_finalProposalFeatures.map((f, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(f.name)}</span>
                            <span class="specialty-tag">${f.feature_type || 'custom'}</span>
                            <span class="trait-desc-small">${escapeHtml(f.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    // Item-specific
    let itemFieldsHtml = '';
    if (cat === 'item') {
        const id = meta.item_data || {};
        _finalProposalProperties = id.properties || [];
        itemFieldsHtml = `
            <div class="loc-fields-header" style="margin-top:var(--space-md)">📦 Item Details</div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="fp-item-name">Item Name</label>
                    <input id="fp-item-name" class="settings-input" value="${escapeAttr(id.name || '')}" />
                </div>
                <div class="filter-group">
                    <label for="fp-item-rarity">Rarity</label>
                    <select id="fp-item-rarity" class="settings-input">
                        ${['common','uncommon','rare','epic','legendary'].map(r =>
                            `<option value="${r}" ${(id.rarity || '') === r ? 'selected' : ''}>${r.charAt(0).toUpperCase() + r.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-item-tier">Tier</label>
                    <select id="fp-item-tier" class="settings-input">
                        ${['permanent','consumable','degradable'].map(t =>
                            `<option value="${t}" ${(id.tier || '') === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="fp-item-legality">Legality</label>
                    <select id="fp-item-legality" class="settings-input">
                        ${['contraband','legal'].map(l =>
                            `<option value="${l}" ${(id.legality || '') === l ? 'selected' : ''}>${l.charAt(0).toUpperCase() + l.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-item-lore">Lore</label>
                <textarea id="fp-item-lore" class="settings-input proposal-textarea" rows="3">${escapeHtml(id.lore || '')}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-item-tags">Tags</label>
                <input id="fp-item-tags" class="settings-input" value="${escapeAttr((id.tags || []).join(', '))}" />
            </div>
            <div style="margin-top:var(--space-sm)">
                <label>Properties</label>
                <div id="fp-item-property-list">
                    ${_finalProposalProperties.map((p, i) => `
                        <div class="trait-item" style="margin-bottom:var(--space-xs)">
                            <span class="trait-name">${escapeHtml(p.name)}</span>
                            <span class="specialty-tag">${p.property_type || 'custom'}</span>
                            <span class="trait-desc-small">${escapeHtml(p.description || '')}</span>
                        </div>`).join('')}
                </div>
            </div>`;
    }

    return `
        <div class="detail-section" style="border:2px solid var(--accent-amber);border-radius:var(--radius-lg);padding:var(--space-lg);background:rgba(245,158,11,0.05)">
            <h4 style="margin-bottom:var(--space-xs)">📝 Final Proposal</h4>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Review the discussion and edit the proposal to reflect the council's consensus before calling a vote.
                This is the version the council will vote on.
            </p>
            <div class="filter-group">
                <label for="fp-title">Title</label>
                <input id="fp-title" class="settings-input" value="${escapeAttr(data.title)}" />
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-description">Description</label>
                <textarea id="fp-description" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.description)}</textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="fp-body">Body</label>
                <textarea id="fp-body" class="settings-input proposal-textarea" rows="4">${escapeHtml(data.body || '')}</textarea>
            </div>

            ${charFieldsHtml}
            ${locFieldsHtml}
            ${itemFieldsHtml}

            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="saveFinalProposal('${data.id}')" id="fp-save-btn">
                    💾 Save Final Proposal
                </button>
                <span id="fp-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;
}

// ── Save Final Proposal ─────────────────────────────────────

async function saveFinalProposal(proposalId) {
    const btn = document.getElementById('fp-save-btn');
    const status = document.getElementById('fp-save-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const title = (document.getElementById('fp-title')?.value || '').trim();
        const description = (document.getElementById('fp-description')?.value || '').trim();
        const body = (document.getElementById('fp-body')?.value || '').trim();

        if (!title) { document.getElementById('fp-title')?.focus(); throw new Error('Title is required'); }
        if (!description) { document.getElementById('fp-description')?.focus(); throw new Error('Description is required'); }

        // Build updated metadata from category-specific fields
        let metadata = null;

        // Character
        const charNameEl = document.getElementById('fp-char-name');
        if (charNameEl) {
            metadata = { character_data: {
                name: charNameEl.value.trim(),
                api_provider: document.getElementById('fp-char-provider')?.value || 'openrouter',
                model: (document.getElementById('fp-char-model')?.value || 'Default').trim(),
                backstory: (document.getElementById('fp-char-backstory')?.value || '').trim(),
                system_prompt: (document.getElementById('fp-char-prompt')?.value || '').trim(),
                greeting: (document.getElementById('fp-char-greeting')?.value || '').trim(),
                tags: (document.getElementById('fp-char-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                example_messages: (document.getElementById('fp-char-examples')?.value || '').split('\n').map(l => l.trim()).filter(Boolean),
                traits: _finalProposalTraits,
            }};
        }

        // Location
        const locNameEl = document.getElementById('fp-loc-name');
        if (locNameEl) {
            metadata = { location_data: {
                name: locNameEl.value.trim(),
                description: description,
                lore: (document.getElementById('fp-loc-lore')?.value || '').trim(),
                tags: (document.getElementById('fp-loc-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                coordinates: (document.getElementById('fp-loc-coords')?.value || '').trim(),
                features: _finalProposalFeatures,
            }};
        }

        // Item
        const itemNameEl = document.getElementById('fp-item-name');
        if (itemNameEl) {
            metadata = { item_data: {
                name: itemNameEl.value.trim(),
                description: description,
                lore: (document.getElementById('fp-item-lore')?.value || '').trim(),
                tags: (document.getElementById('fp-item-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                rarity: document.getElementById('fp-item-rarity')?.value || '',
                tier: document.getElementById('fp-item-tier')?.value || '',
                legality: document.getElementById('fp-item-legality')?.value || '',
                properties: _finalProposalProperties,
            }};
        }

        const payload = { title, description, body };
        if (metadata) payload.metadata = metadata;

        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/final-proposal`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to save' }));
            throw new Error(err.detail);
        }
        showToast('Final proposal saved 💾');
        if (status) status.textContent = '✅ Saved';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (status) status.textContent = '';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Final Proposal'; }
    }
}

async function callProposalVote(proposalId) {
    const btn = document.getElementById('vote-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Council is voting…'; }

    // If discussion is still open, pause it first
    try {
        await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/discuss-pause`, {
            method: 'POST',
        });
    } catch { /* may already be closed */ }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/vote`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Vote failed' }));
            throw new Error(err.detail);
        }
        const results = await resp.json();
        const t = results.tally || {};
        const resultText = t.approved ? 'APPROVED ✅' : 'NOT APPROVED ❌';
        showToast(`Vote complete — ${resultText}`);
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🗳️ Call Vote'; }
    }
}

async function withdrawProposal(proposalId, author) {
    if (!confirm(`Withdraw this proposal? This cannot be undone.`)) return;
    const btn = document.getElementById('withdraw-btn');
    if (btn) { btn.disabled = true; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/withdraw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Withdraw failed' }));
            throw new Error(err.detail);
        }
        showToast('Proposal withdrawn ↩️');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; }
    }
}

async function vetoProposal(proposalId) {
    const reason = prompt('Veto reason (optional):') ?? '';
    if (reason === null) return;  // user cancelled
    const btn = document.getElementById('veto-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Vetoing…'; }

    try {
        const resp = await fetch(`/api/votes/${encodeURIComponent(proposalId)}/veto`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Veto failed' }));
            throw new Error(err.detail);
        }
        showToast('Proposal vetoed 🚫');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🚫 Veto'; }
    }
}

async function liftVetoProposal(proposalId) {
    if (!confirm('Remove the veto from this proposal?')) return;
    const btn = document.getElementById('lift-veto-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Lifting veto…'; }

    try {
        const resp = await fetch(`/api/votes/${encodeURIComponent(proposalId)}/lift-veto`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Lift veto failed' }));
            throw new Error(err.detail);
        }
        showToast('Veto lifted ✅');
        await renderProposalDetail(proposalId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '✅ Lift Veto'; }
    }
}

async function handoffCharacterProposal(proposalId) {
    const btn = document.getElementById('char-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating character…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-character`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft character "${data.name}" created ✅`);
        navigateTo('characters', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🎭 Create Draft Character'; }
    }
}

async function handoffLocationProposal(proposalId) {
    const btn = document.getElementById('loc-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating location…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-location`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft location "${data.name}" created ✅`);
        navigateTo('locations', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🌍 Create Draft Location'; }
    }
}

async function handoffItemProposal(proposalId) {
    const btn = document.getElementById('item-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating item…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-item`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft item "${data.name}" created ✅`);
        navigateTo('items', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📦 Create Draft Item'; }
    }
}

async function handoffLawProposal(proposalId) {
    const btn = document.getElementById('law-handoff-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating law…'; }

    try {
        const resp = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/handoff-law`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Handoff failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Draft law "${data.title}" created ✅`);
        navigateTo('laws', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⚖️ Create Draft Law'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Votes View
// ═══════════════════════════════════════════════════════════════

