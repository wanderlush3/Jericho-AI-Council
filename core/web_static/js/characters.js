async function renderCharacters() {
    showLoading();
    const data = await api('/api/characters');
    state.charactersData = data;

    const createForm = `
        <div class="card character-create-form">
            <h3>🎭 New Character</h3>
            <p style="color:var(--text-muted);font-size:0.82rem;margin-bottom:var(--space-md)">
                Create a new character template with traits, backstory, and system prompt.
            </p>
            <div class="proposal-form-grid">
                <div class="filter-group" style="flex:2">
                    <label for="char-name-input">Name</label>
                    <input id="char-name-input" class="settings-input" placeholder="e.g. Atlas" />
                </div>
                <div class="filter-group">
                    <label for="char-author-input">Author</label>
                    <input id="char-author-input" class="settings-input" placeholder="e.g. Forge" />
                </div>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group">
                    <label for="char-provider-input">API Provider</label>
                    <select id="char-provider-input" class="settings-input" onchange="updateCharCreateModelField()">
                        <option value="openrouter">OpenRouter</option>
                        <option value="mancer">Mancer</option>
                        <option value="lmstudio">LM Studio</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="char-model-input">Model</label>
                    <div id="char-model-container">
                        ${renderModelField('char-model-input', 'openrouter', '', true)}
                    </div>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-desc-input">Description</label>
                <textarea id="char-desc-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="A short summary of this character…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-backstory-input">Backstory</label>
                <textarea id="char-backstory-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="Character history and background…"></textarea>
            </div>
            <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:2">
                    <label for="char-greeting-input">Greeting</label>
                    <input id="char-greeting-input" class="settings-input" placeholder="First message the character says…" />
                </div>
                <div class="filter-group">
                    <label for="char-tags-input">Tags</label>
                    <input id="char-tags-input" class="settings-input" placeholder="explorer, brave (comma-separated)" />
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-prompt-input">System Prompt</label>
                <textarea id="char-prompt-input" class="settings-input proposal-textarea" rows="3"
                    placeholder="You are {{char}}, an adventurous AI who…"></textarea>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="char-examples-input">Example Messages</label>
                <textarea id="char-examples-input" class="settings-input proposal-textarea" rows="2"
                    placeholder="One message per line…"></textarea>
            </div>

            <div class="char-trait-editor" style="margin-top:var(--space-md)">
                <label>Traits</label>
                <div id="char-trait-list"></div>
                <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                    <div class="filter-group">
                        <input id="char-trait-name" class="settings-input" placeholder="Trait name (e.g. Curious)" />
                    </div>
                    <div class="filter-group">
                        <select id="char-trait-type" class="settings-input">
                            <option value="personality">Personality</option>
                            <option value="values">Values</option>
                            <option value="flaws">Flaws</option>
                            <option value="custom">Custom</option>
                        </select>
                    </div>
                    <div class="filter-group" style="flex:2">
                        <input id="char-trait-desc" class="settings-input" placeholder="Trait description…" />
                    </div>
                    <div class="filter-group" style="flex:0.5">
                        <input id="char-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5"
                            class="avatar-zoom-slider" oninput="document.getElementById('char-trait-intensity-val').textContent = this.value" />
                        <span id="char-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                    </div>
                </div>
                <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addPendingTrait()">
                    ➕ Add Trait
                </button>
            </div>

            <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                <button class="btn btn-primary" onclick="createCharacter()" id="char-create-btn">
                    🎭 Create Character
                </button>
                <span id="char-create-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
            </div>
        </div>`;

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🎭 Characters</h2>
                    <p>No characters yet. Create one below!</p>
                </div>
                ${createForm}
            </div>`;
        return;
    }

    const cards = data.map(c => {
        const traitsHtml = (c.traits || []).slice(0, 4).map(t => `
            <div class="trait-item">
                <span class="trait-name">${escapeHtml(t.name)}</span>
                <div class="trait-bar-bg">
                    <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
                </div>
                <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
            </div>`).join('');

        const tagsHtml = (c.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

        const avatarHtml = c.avatar_url
            ? `<div class="char-card-avatar" style="background:url('${c.avatar_url}') center/cover no-repeat"></div>`
            : '';

        return `
        <div class="card card-clickable character-card" onclick="navigateTo('characters','${c.id}')">
            <div class="char-header">
                ${avatarHtml}
                <div style="flex:1">
                    <div class="char-name">${escapeHtml(c.name)}</div>
                    <div class="char-author">by ${escapeHtml(c.author)} · v${c.version || 1} · <span style="color:var(--accent-cyan)">${escapeHtml(c.api_provider || 'openrouter')}</span> · ${escapeHtml(c.model || 'Default')}</div>
                </div>
                ${badge(c.status)}
            </div>
            <div class="char-desc">${truncate(c.description, 120)}</div>
            ${traitsHtml ? `<div class="traits-list">${traitsHtml}</div>` : ''}
            ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div><h2>🎭 Characters</h2>
                <p>${data.length} AI character template${data.length !== 1 ? 's' : ''}</p></div>
                <button class="btn btn-secondary btn-sm" onclick="openBatchGenerateModal('character')" title="Generate images for multiple characters">🎨 Batch Generate</button>
            </div>
            ${createForm}
            <div class="character-grid">${cards}</div>
        </div>`;
}

async function renderCharacterDetail(id) {
    showLoading();
    const data = await api(`/api/characters/${encodeURIComponent(id)}`);

    const traitsHtml = (data.traits || []).map(t => `
        <div class="trait-item">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <div class="trait-bar-bg" style="max-width:150px">
                <div class="trait-bar-fill" style="width:${(t.intensity || 0) * 100}%"></div>
            </div>
            <span class="trait-intensity">${Math.round((t.intensity || 0) * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removeCharTrait('${data.id}', '${escapeAttr(t.name)}')" title="Delete trait">🗑️</button>
        </div>`).join('');

    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

    // Avatar section
    const avatarHtml = data.avatar_url
        ? `<div class="char-detail-avatar" onclick="openCharAvatarEditor('${data.id}')" title="Click to change avatar"
                style="background: url('${data.avatar_url}') center/cover no-repeat; cursor: pointer;">
             <div class="avatar-overlay">📷</div>
           </div>`
        : `<div class="char-detail-avatar char-avatar-placeholder" onclick="openCharAvatarEditor('${data.id}')" title="Click to upload avatar"
                style="cursor: pointer;">
             🎭
             <div class="avatar-overlay">📷</div>
           </div>`;

    // Status action buttons
    let statusActions = '';
    if (data.status === 'draft') {
        statusActions = `<button class="btn btn-primary btn-sm" onclick="updateCharacterStatus('${data.id}', 'active')">✅ Activate</button>`;
    } else if (data.status === 'active') {
        statusActions = `
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'archived')">📦 Archive</button>
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'draft')">📝 Revert to Draft</button>`;
    } else if (data.status === 'archived') {
        statusActions = `
            <button class="btn btn-primary btn-sm" onclick="updateCharacterStatus('${data.id}', 'active')">✅ Reactivate</button>
            <button class="btn btn-secondary btn-sm" onclick="updateCharacterStatus('${data.id}', 'draft')">📝 Revert to Draft</button>`;
    }

    const galleryHtml = await renderImageGallery('character', data.id);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('characters')">← Back to Characters</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-xl)">
                    <div style="display:flex;gap:var(--space-lg);align-items:flex-start">
                        ${avatarHtml}
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
                    </div>
                    <div style="display:flex;gap:var(--space-sm);align-items:flex-start">
                        <button class="btn btn-secondary btn-sm" onclick="exportCharacterPng('${data.id}')" title="Download as TavernCard v2 PNG">
                            📥 Export PNG
                        </button>
                        <button class="detail-close" onclick="navigateTo('characters')">✕</button>
                    </div>
                </div>

                <div class="detail-section" style="margin-top:var(--space-md)">
                    <div class="analytics-row"><span class="label">🔌 Provider</span><span class="value">${escapeHtml(data.api_provider || 'openrouter')}</span></div>
                    <div class="analytics-row"><span class="label">🤖 Model</span><span class="value">${escapeHtml(data.model || 'Default')}</span></div>
                </div>

                <div class="detail-section">
                    <h4>Description</h4>
                    <p>${escapeHtml(data.description)}</p>
                </div>

                ${data.backstory ? `<div class="detail-section"><h4>📖 Backstory</h4><p style="white-space:pre-line">${escapeHtml(data.backstory)}</p></div>` : ''}

                ${traitsHtml ? `<div class="detail-section"><h4>🧬 Traits (${data.traits.length})</h4><div class="traits-list">${traitsHtml}</div>
                    <div style="margin-top:var(--space-md);padding:var(--space-sm);border:1px dashed var(--border-subtle);border-radius:var(--radius-md)">
                        <div class="proposal-form-grid" style="margin-top:var(--space-xs)">
                            <div class="filter-group">
                                <input id="detail-trait-name" class="settings-input" placeholder="Trait name" />
                            </div>
                            <div class="filter-group">
                                <select id="detail-trait-type" class="settings-input">
                                    <option value="personality">Personality</option>
                                    <option value="values">Values</option>
                                    <option value="flaws">Flaws</option>
                                    <option value="custom">Custom</option>
                                </select>
                            </div>
                            <div class="filter-group" style="flex:2">
                                <input id="detail-trait-desc" class="settings-input" placeholder="Trait description…" />
                            </div>
                            <div class="filter-group" style="flex:0.5">
                                <input id="detail-trait-intensity" type="range" min="0" max="1" step="0.1" value="0.5" class="avatar-zoom-slider"
                                    oninput="document.getElementById('detail-trait-intensity-val').textContent = this.value" />
                                <span id="detail-trait-intensity-val" style="font-size:0.78rem;color:var(--text-muted)">0.5</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-sm)" onclick="addCharTrait('${data.id}')">➕ Add Trait</button>
                    </div>
                </div>` : ''}

                ${tagsHtml ? `<div class="detail-section"><h4>Tags</h4><div class="tag-list">${tagsHtml}</div></div>` : ''}

                ${data.greeting ? `<div class="detail-section"><h4>👋 Greeting</h4><p style="font-style:italic;color:var(--accent-cyan)">"${escapeHtml(data.greeting)}"</p></div>` : ''}

                ${data.system_prompt ? `<div class="detail-section"><h4>💻 System Prompt</h4><pre>${escapeHtml(data.system_prompt)}</pre></div>` : ''}

                ${data.example_messages && data.example_messages.length ? `
                    <div class="detail-section">
                        <h4>💬 Example Messages</h4>
                        ${data.example_messages.map(m => `<p style="color:var(--text-secondary);margin-bottom:var(--space-xs)">💬 ${escapeHtml(m)}</p>`).join('')}
                    </div>` : ''}

                ${galleryHtml}

                <div class="detail-section" style="margin-top:var(--space-xl);border-top:1px solid var(--border-subtle);padding-top:var(--space-lg)">
                    <h4>✏️ Edit Character</h4>
                    <div class="proposal-form-grid">
                        <div class="filter-group" style="flex:2">
                            <label for="char-edit-name">Name</label>
                            <input id="char-edit-name" class="settings-input" value="${escapeAttr(data.name)}" />
                        </div>
                        <div class="filter-group">
                            <label for="char-edit-tags">Tags</label>
                            <input id="char-edit-tags" class="settings-input" value="${escapeAttr((data.tags || []).join(', '))}" />
                        </div>
                    </div>
                    <div class="proposal-form-grid" style="margin-top:var(--space-sm)">
                        <div class="filter-group">
                            <label for="char-edit-provider">API Provider</label>
                            <select id="char-edit-provider" class="settings-input" onchange="updateCharEditModelField()">
                                <option value="openrouter" ${(data.api_provider || 'openrouter') === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                                <option value="mancer" ${data.api_provider === 'mancer' ? 'selected' : ''}>Mancer</option>
                                <option value="lmstudio" ${data.api_provider === 'lmstudio' ? 'selected' : ''}>LM Studio</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="char-edit-model">Model</label>
                            <div id="char-edit-model-container">
                                ${renderModelField('char-edit-model', data.api_provider || 'openrouter', data.model || 'Default', true)}
                            </div>
                            <span class="council-field-hint">Set to "Default" to use the model configured in Settings</span>
                        </div>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-desc">Description</label>
                        <textarea id="char-edit-desc" class="settings-input proposal-textarea" rows="2">${escapeHtml(data.description)}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-backstory">Backstory</label>
                        <textarea id="char-edit-backstory" class="settings-input proposal-textarea" rows="3">${escapeHtml(data.backstory || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-greeting">Greeting</label>
                        <input id="char-edit-greeting" class="settings-input" value="${escapeAttr(data.greeting || '')}" />
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-prompt">System Prompt</label>
                        <textarea id="char-edit-prompt" class="settings-input proposal-textarea" rows="4">${escapeHtml(data.system_prompt || '')}</textarea>
                    </div>
                    <div class="filter-group" style="margin-top:var(--space-sm)">
                        <label for="char-edit-examples">Example Messages (one per line)</label>
                        <textarea id="char-edit-examples" class="settings-input proposal-textarea" rows="2">${escapeHtml((data.example_messages || []).join('\n'))}</textarea>
                    </div>
                    <div style="margin-top:var(--space-md);display:flex;align-items:center;gap:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveCharacterEdit('${data.id}')" id="char-save-btn">
                            💾 Save Changes
                        </button>
                        <span id="char-save-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Character Avatar Modal -->
        <div class="avatar-modal" id="char-avatar-modal" style="display:none">
            <div class="avatar-modal-content">
                <div class="avatar-modal-header">
                    <h3>Upload Character Avatar</h3>
                    <button class="detail-close" onclick="closeCharAvatarEditor()">✕</button>
                </div>
                <div class="avatar-modal-body">
                    <div class="avatar-drop-zone" id="char-avatar-drop-zone">
                        <input type="file" id="char-avatar-file-input" accept="image/png,image/jpeg,image/webp" style="display:none" onchange="handleCharAvatarFile(event)" />
                        <div class="avatar-drop-label" onclick="document.getElementById('char-avatar-file-input').click()">
                            📁 Click to select image or drag & drop a PNG
                        </div>
                    </div>
                    <div class="avatar-preview-section" id="char-avatar-preview-section" style="display:none">
                        <canvas id="char-avatar-canvas" class="avatar-preview-canvas" width="200" height="200"></canvas>
                        <div class="avatar-zoom-control">
                            <span class="avatar-zoom-label">🔍 Zoom</span>
                            <input type="range" id="char-avatar-zoom" class="avatar-zoom-slider" min="0.5" max="3" step="0.05" value="1" oninput="updateCharAvatarPreview()" />
                            <span id="char-avatar-zoom-value">1.0×</span>
                        </div>
                    </div>
                </div>
                <div class="avatar-modal-footer">
                    <button class="btn btn-secondary" onclick="closeCharAvatarEditor()">Cancel</button>
                    <button class="btn btn-primary" id="char-avatar-save-btn" onclick="saveCharAvatar('${data.id}')" disabled>💾 Save Avatar</button>
                </div>
            </div>
        </div>`;
}

// ── Character Create ────────────────────────────────────────

// ── Pending Traits (for creation form) ──────────────────────

let pendingTraits = [];

function addPendingTrait() {
    const nameEl = document.getElementById('char-trait-name');
    const name = nameEl.value.trim();
    const traitType = document.getElementById('char-trait-type').value;
    const desc = document.getElementById('char-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('char-trait-intensity').value);

    if (!name) { nameEl.focus(); return; }

    // Check for duplicates
    if (pendingTraits.some(t => t.name.toLowerCase() === name.toLowerCase())) {
        showToast('Trait with that name already added', true);
        return;
    }

    pendingTraits.push({
        trait_type: traitType,
        name: name,
        description: desc || name,
        intensity: intensity,
    });

    // Clear inputs
    nameEl.value = '';
    document.getElementById('char-trait-desc').value = '';
    document.getElementById('char-trait-intensity').value = '0.5';
    document.getElementById('char-trait-intensity-val').textContent = '0.5';

    renderPendingTraits();
}

function removePendingTrait(index) {
    pendingTraits.splice(index, 1);
    renderPendingTraits();
}

function renderPendingTraits() {
    const container = document.getElementById('char-trait-list');
    if (!container) return;
    if (!pendingTraits.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = pendingTraits.map((t, i) => `
        <div class="trait-item" style="margin-bottom:var(--space-xs)">
            <span class="trait-name">${escapeHtml(t.name)}</span>
            <span class="specialty-tag">${t.trait_type}</span>
            <span class="trait-intensity">${Math.round(t.intensity * 100)}%</span>
            <span class="trait-desc-small">${escapeHtml(t.description)}</span>
            <button class="btn btn-sm btn-danger-subtle" onclick="removePendingTrait(${i})" title="Remove">🗑️</button>
        </div>`).join('');
}

async function createCharacter() {
    const name = document.getElementById('char-name-input').value.trim();
    const author = document.getElementById('char-author-input').value.trim();
    const description = document.getElementById('char-desc-input').value.trim();
    const backstory = document.getElementById('char-backstory-input').value.trim();
    const greeting = document.getElementById('char-greeting-input').value.trim();
    const systemPrompt = document.getElementById('char-prompt-input').value.trim();
    const tagsRaw = document.getElementById('char-tags-input').value.trim();
    const examplesRaw = document.getElementById('char-examples-input').value.trim();

    // Collect any trait currently in the input fields
    const traitName = document.getElementById('char-trait-name').value.trim();
    const traitType = document.getElementById('char-trait-type').value;
    const traitDesc = document.getElementById('char-trait-desc').value.trim();
    const traitIntensity = parseFloat(document.getElementById('char-trait-intensity').value);

    const btn = document.getElementById('char-create-btn');
    const status = document.getElementById('char-create-status');

    // Build final traits list from pending + any unsaved input
    const traits = [...pendingTraits];
    if (traitName) {
        traits.push({
            trait_type: traitType,
            name: traitName,
            description: traitDesc || traitName,
            intensity: traitIntensity,
        });
    }

    if (!name) { document.getElementById('char-name-input').focus(); return; }
    if (!author) { document.getElementById('char-author-input').focus(); return; }
    if (!description) { document.getElementById('char-desc-input').focus(); return; }
    if (!traits.length) { document.getElementById('char-trait-name').focus(); status.textContent = 'At least one trait is required'; return; }

    btn.disabled = true;
    btn.textContent = '⏳ Creating…';
    status.textContent = '';

    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
    const exampleMessages = examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [];

    const apiProvider = document.getElementById('char-provider-input').value;
    const model = document.getElementById('char-model-input').value.trim() || 'Default';

    try {
        const resp = await fetch('/api/characters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, description, author, backstory,
                system_prompt: systemPrompt, greeting,
                example_messages: exampleMessages, tags, traits,
                api_provider: apiProvider, model,
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to create character' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        pendingTraits = [];  // reset
        showToast(`Character ${data.id} created ✅`);
        navigateTo('characters', data.id);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '';
    } finally {
        btn.disabled = false;
        btn.textContent = '🎭 Create Character';
    }
}

// ── Character Edit Save ─────────────────────────────────────

async function saveCharacterEdit(characterId) {
    const btn = document.getElementById('char-save-btn');
    const status = document.getElementById('char-save-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const tagsRaw = document.getElementById('char-edit-tags').value.trim();
    const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
    const examplesRaw = document.getElementById('char-edit-examples').value.trim();
    const exampleMessages = examplesRaw ? examplesRaw.split('\n').map(l => l.trim()).filter(Boolean) : [];

    const body = {
        name: document.getElementById('char-edit-name').value.trim(),
        description: document.getElementById('char-edit-desc').value.trim(),
        backstory: document.getElementById('char-edit-backstory').value.trim(),
        greeting: document.getElementById('char-edit-greeting').value.trim(),
        system_prompt: document.getElementById('char-edit-prompt').value.trim(),
        example_messages: exampleMessages,
        tags,
        api_provider: document.getElementById('char-edit-provider').value,
        model: document.getElementById('char-edit-model').value.trim() || 'Default',
    };

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Character updated ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Changes';
    }
}

// ── Character Status ────────────────────────────────────────

async function updateCharacterStatus(characterId, newStatus) {
    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        showToast(`Character set to ${newStatus} ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Character PNG Export ─────────────────────────────────────

async function exportCharacterPng(characterId) {
    // Open a file picker for the user to select a base PNG
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/png';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) { document.body.removeChild(fileInput); return; }

        const reader = new FileReader();
        reader.onload = async (ev) => {
            try {
                const imageData = ev.target.result; // data:image/png;base64,...
                const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/export-png`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_data: imageData }),
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: 'Export failed' }));
                    throw new Error(err.detail);
                }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const cd = resp.headers.get('Content-Disposition') || '';
                const match = cd.match(/filename="(.+?)"/);
                a.download = match ? match[1] : `jericho_${characterId}.png`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Character exported as PNG ✅');
            } catch (err) {
                showToast(`Error: ${err.message}`, true);
            }
        };
        reader.readAsDataURL(file);
        document.body.removeChild(fileInput);
    });

    fileInput.click();
}

// ── Character Trait Management (detail view) ─────────────────

async function addCharTrait(characterId) {
    const name = document.getElementById('detail-trait-name').value.trim();
    const traitType = document.getElementById('detail-trait-type').value;
    const desc = document.getElementById('detail-trait-desc').value.trim();
    const intensity = parseFloat(document.getElementById('detail-trait-intensity').value);

    if (!name) { document.getElementById('detail-trait-name').focus(); return; }

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/traits`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trait_type: traitType, name, description: desc || name, intensity }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to add trait' }));
            throw new Error(err.detail);
        }
        showToast(`Trait "${name}" added ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function removeCharTrait(characterId, traitName) {
    if (!confirm(`Remove trait "${traitName}"?`)) return;

    try {
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/traits/${encodeURIComponent(traitName)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed to remove trait' }));
            throw new Error(err.detail);
        }
        showToast(`Trait "${traitName}" removed ✅`);
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ── Character Avatar Editor ─────────────────────────────────

let charAvatarState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };

function openCharAvatarEditor(characterId) {
    const modal = document.getElementById('char-avatar-modal');
    modal.style.display = 'flex';
    charAvatarState = { img: null, zoom: 1.0, offsetX: 0, offsetY: 0, dragging: false, lastX: 0, lastY: 0 };
    document.getElementById('char-avatar-preview-section').style.display = 'none';
    document.getElementById('char-avatar-save-btn').disabled = true;
    document.getElementById('char-avatar-file-input').value = '';

    const dropZone = document.getElementById('char-avatar-drop-zone');
    dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); };
    dropZone.ondragleave = () => { dropZone.classList.remove('drag-over'); };
    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) loadCharAvatarImage(file);
    };

    const canvas = document.getElementById('char-avatar-canvas');
    canvas.onmousedown = (e) => { charAvatarState.dragging = true; charAvatarState.lastX = e.clientX; charAvatarState.lastY = e.clientY; };
    canvas.onmousemove = (e) => {
        if (!charAvatarState.dragging) return;
        charAvatarState.offsetX += e.clientX - charAvatarState.lastX;
        charAvatarState.offsetY += e.clientY - charAvatarState.lastY;
        charAvatarState.lastX = e.clientX;
        charAvatarState.lastY = e.clientY;
        updateCharAvatarPreview();
    };
    canvas.onmouseup = () => { charAvatarState.dragging = false; };
    canvas.onmouseleave = () => { charAvatarState.dragging = false; };
}

function closeCharAvatarEditor() {
    document.getElementById('char-avatar-modal').style.display = 'none';
}

function handleCharAvatarFile(event) {
    const file = event.target.files[0];
    if (file) loadCharAvatarImage(file);
}

function loadCharAvatarImage(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            charAvatarState.img = img;
            charAvatarState.zoom = 1.0;
            charAvatarState.offsetX = 0;
            charAvatarState.offsetY = 0;
            document.getElementById('char-avatar-zoom').value = 1.0;
            document.getElementById('char-avatar-zoom-value').textContent = '1.0×';
            document.getElementById('char-avatar-preview-section').style.display = 'block';
            document.getElementById('char-avatar-save-btn').disabled = false;
            updateCharAvatarPreview();
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function updateCharAvatarPreview() {
    const canvas = document.getElementById('char-avatar-canvas');
    const ctx = canvas.getContext('2d');
    const zoom = parseFloat(document.getElementById('char-avatar-zoom').value);
    charAvatarState.zoom = zoom;
    document.getElementById('char-avatar-zoom-value').textContent = zoom.toFixed(1) + '×';

    const img = charAvatarState.img;
    if (!img) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    // Square clip (not circular — for character cards)
    ctx.beginPath();
    ctx.roundRect(0, 0, 200, 200, 12);
    ctx.clip();

    ctx.fillStyle = '#111827';
    ctx.fillRect(0, 0, 200, 200);

    const scale = zoom * Math.max(200 / img.width, 200 / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    const x = (200 - w) / 2 + charAvatarState.offsetX;
    const y = (200 - h) / 2 + charAvatarState.offsetY;
    ctx.drawImage(img, x, y, w, h);
    ctx.restore();

    // Border
    ctx.beginPath();
    ctx.roundRect(1, 1, 198, 198, 12);
    ctx.strokeStyle = 'rgba(139, 92, 246, 0.5)';
    ctx.lineWidth = 2;
    ctx.stroke();
}

async function saveCharAvatar(characterId) {
    const canvas = document.getElementById('char-avatar-canvas');
    const btn = document.getElementById('char-avatar-save-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Uploading…';

    try {
        const imageData = canvas.toDataURL('image/png');
        const resp = await fetch(`/api/characters/${encodeURIComponent(characterId)}/avatar-upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_data: imageData }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        showToast('Avatar saved ✅');
        closeCharAvatarEditor();
        await renderCharacterDetail(characterId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Avatar';
    }
}

// ═══════════════════════════════════════════════════════════════
// Locations View
// ═══════════════════════════════════════════════════════════════

const LOCATION_FEATURE_TYPES = ['landmark', 'district', 'building', 'natural', 'infrastructure', 'custom'];

