async function renderSettings() {
    const currentSkin = state.activeSkin || 'default';

    // Build skin cards
    const skinCards = Object.entries(SKINS).map(([key, skin]) => {
        const isActive = key === currentSkin;
        const swatches = (skin.swatches || []).map(c =>
            `<div class="swatch" style="background:${c}"></div>`
        ).join('');
        return `
            <div class="skin-card ${isActive ? 'active' : ''}" onclick="selectSkin('${key}')" id="skin-card-${key}">
                <div class="skin-card-preview">${swatches}</div>
                <div class="skin-card-body">
                    <div class="skin-card-icon">${skin.icon}</div>
                    <div class="skin-card-label">${skin.label}</div>
                    <div class="skin-card-desc">${skin.desc || ''}</div>
                </div>
            </div>`;
    }).join('');

    // Fetch all settings data in parallel
    let keysData = [], modelsData = [], mancerModels = [], openrouterModels = [], lmstudioModels = [];
    let userDesc = '';
    let userName = '';
    try {
        const [keys, models, mm, orm, lmsm, ud, un] = await Promise.all([
            api('/api/settings/keys'),
            api('/api/settings/models'),
            api('/api/settings/mancer-models'),
            api('/api/settings/openrouter-models'),
            api('/api/settings/lmstudio-models').catch(() => []),
            api('/api/settings/user-description'),
            api('/api/settings/user-name').catch(() => ({ name: '' })),
        ]);
        keysData = keys;
        modelsData = models;
        mancerModels = mm;
        openrouterModels = orm;
        lmstudioModels = lmsm;
        userDesc = ud.description || '';
        userName = (un && un.name) || '';
    } catch { /* endpoints may not be available */ }

    // Build provider sections (OpenRouter + Mancer)
    const providers = [
        { id: 'openrouter', label: 'OpenRouter', icon: '🌐', models: openrouterModels },
        { id: 'mancer', label: 'Mancer', icon: '⚡', models: mancerModels },
        { id: 'lmstudio', label: 'LM Studio', icon: '🖥️', models: lmstudioModels },
    ];

    const providerSections = providers.map(prov => {
        const keyInfo = keysData.find(k => k.provider === prov.id) || {};
        const modelInfo = modelsData.find(m => m.provider === prov.id) || {};
        const hasKey = keyInfo.configured || false;
        const maskedKey = keyInfo.masked || '';
        const currentModel = modelInfo.model || modelInfo.default_model || '';

        const modelOptions = prov.models.map(m =>
            `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${m}</option>`
        ).join('');

        return `
            <div class="settings-provider-card">
                <div class="settings-provider-header">
                    <span class="settings-provider-icon">${prov.icon}</span>
                    <span class="settings-provider-name">${prov.label}</span>
                    <span class="badge ${hasKey ? 'badge-active' : 'badge-draft'}">${hasKey ? 'CONFIGURED' : 'NOT SET'}</span>
                </div>

                <div class="settings-field-group">
                    <label>API Key</label>
                    <div class="settings-key-row">
                        <input type="password" id="settings-key-${prov.id}" class="settings-input"
                               placeholder="${hasKey ? maskedKey : 'Enter API key…'}"
                               autocomplete="off" />
                        <button class="btn btn-primary btn-sm" onclick="saveSettingsKey('${prov.id}')">Save</button>
                        ${hasKey ? `<button class="btn btn-sm" onclick="deleteSettingsKey('${prov.id}')" title="Remove key">🗑️</button>` : ''}
                    </div>
                </div>

                <div class="settings-field-group">
                    <label>Default Model</label>
                    <div class="settings-key-row">
                        <select id="settings-model-${prov.id}" class="settings-input">
                            ${modelOptions}
                        </select>
                        <button class="btn btn-primary btn-sm" onclick="saveSettingsModel('${prov.id}')">Save</button>
                    </div>
                    <span class="settings-field-hint">Members set to "Default" will use this model</span>
                </div>
            </div>`;
    }).join('');

    // SilentPass toggle
    const silentpassOn = state.silentpassaEnabled;

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>Settings</h2>
                <p>Configure your profile, API providers, models, appearance, and preferences</p>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">👤 About You</div>
                <div class="settings-provider-card">
                    <div class="settings-field-group">
                        <label>Your Name</label>
                        <div class="settings-key-row">
                            <input type="text" id="settings-user-name" class="settings-input"
                                   maxlength="100"
                                   placeholder="Enter your name…"
                                   value="${escapeHtml(userName)}" />
                            <button class="btn btn-primary btn-sm" onclick="saveSettingsUserName()">💾 Save</button>
                        </div>
                        <span class="settings-field-hint">How the council members and characters will address you</span>
                    </div>
                    <div class="settings-field-group">
                        <label>User Description</label>
                        <textarea id="settings-user-desc" class="settings-input settings-textarea"
                                  rows="4" maxlength="700"
                                  placeholder="Tell the AI council about yourself — this context is shared in chats…">${escapeHtml(userDesc)}</textarea>
                        <div class="settings-key-row" style="margin-top:var(--space-sm)">
                            <span class="settings-field-hint" id="settings-desc-count">${userDesc.length}/700</span>
                            <button class="btn btn-primary btn-sm" onclick="saveSettingsUserDesc()">💾 Save</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🔑 API Providers & Models</div>
                <div class="settings-providers-grid">${providerSections}</div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🎨 Appearance — Skin</div>
                <div class="settings-skin-grid">${skinCards}</div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">💬 Chat Features</div>
                <div class="settings-info-grid">
                    <div class="settings-info-card settings-toggle-card" onclick="toggleSilentPassSettings()" style="cursor:pointer">
                        <div class="settings-info-label">SilentPass</div>
                        <div class="settings-info-value">
                            <span class="badge ${silentpassOn ? 'badge-active' : 'badge-draft'}">${silentpassOn ? 'ON' : 'OFF'}</span>
                        </div>
                        <div class="settings-info-hint">Presence/Silence output wrappers</div>
                    </div>
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">🎨 ComfyUI — Image Generation</div>
                <div id="comfyui-settings-container"></div>
            </div>
        </div>`;

    // Wire up character counter
    const descEl = document.getElementById('settings-user-desc');
    if (descEl) {
        descEl.addEventListener('input', () => {
            const cnt = document.getElementById('settings-desc-count');
            if (cnt) cnt.textContent = `${descEl.value.length}/700`;
        });
    }

    // Lazy-load ComfyUI settings section
    loadComfyUISettings();
}

function selectSkin(name) {
    applySkin(name);
    renderSettings();
}

function toggleSilentPassSettings() {
    state.silentpassaEnabled = !state.silentpassaEnabled;
    localStorage.setItem('silentpassa', state.silentpassaEnabled ? 'on' : 'off');
    renderSettings();
}

async function saveSettingsKey(provider) {
    const input = document.getElementById(`settings-key-${provider}`);
    const key = input?.value?.trim();
    if (!key) return;
    try {
        await fetch('/api/settings/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: key }),
        });
        input.value = '';
        renderSettings();
    } catch (err) {
        alert('Failed to save key: ' + err.message);
    }
}

async function deleteSettingsKey(provider) {
    if (!confirm(`Remove ${provider} API key?`)) return;
    try {
        await fetch(`/api/settings/keys/${provider}`, { method: 'DELETE' });
        renderSettings();
    } catch (err) {
        alert('Failed to remove key: ' + err.message);
    }
}

async function saveSettingsModel(provider) {
    const select = document.getElementById(`settings-model-${provider}`);
    const model = select?.value;
    if (!model) return;
    try {
        await fetch('/api/settings/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, model }),
        });
        renderSettings();
    } catch (err) {
        alert('Failed to save model: ' + err.message);
    }
}

async function saveSettingsUserDesc() {
    const el = document.getElementById('settings-user-desc');
    const description = el?.value || '';
    try {
        await fetch('/api/settings/user-description', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description }),
        });
        renderSettings();
    } catch (err) {
        alert('Failed to save: ' + err.message);
    }
}

async function saveSettingsUserName() {
    const el = document.getElementById('settings-user-name');
    const name = el?.value?.trim() || '';
    try {
        const resp = await fetch('/api/settings/user-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        renderSettings();
    } catch (err) {
        alert('Failed to save name: ' + err.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// ComfyUI Settings Helpers (F-037d)
// ═══════════════════════════════════════════════════════════════

let _comfyuiPendingWorkflowJson = null;
let _comfyuiPendingFilename = '';
let _comfyuiExpandedTemplate = null;

async function loadComfyUISettings() {
    const container = document.getElementById('comfyui-settings-container');
    if (!container) return;

    let configData = { host: '127.0.0.1', port: 8007 };
    let templates = [];
    let presets = [];
    let defaultStyle = '';
    let templateAssignments = { character: '', location: '', item: '', store: '', story: '', explore: '' };

    try {
        const [cfg, tpls, prsts, ds, assigns] = await Promise.all([
            api('/api/settings/comfyui').catch(() => ({ host: '127.0.0.1', port: 8007 })),
            api('/api/settings/comfyui/templates').catch(() => []),
            api('/api/settings/comfyui/style-presets').catch(() => []),
            api('/api/settings/comfyui/default-style').catch(() => ({ style_key: '' })),
            api('/api/settings/comfyui/template-assignments').catch(() => ({ character: '', location: '', item: '', store: '' })),
        ]);
        configData = cfg;
        templates = tpls;
        presets = prsts;
        defaultStyle = ds.style_key || '';
        templateAssignments = assigns;
    } catch { /* endpoints may not be available */ }

    // ── Connection Config ─────────────
    const presetOptions = presets.map(p =>
        `<option value="${escapeAttr(p.name)}" ${p.name === defaultStyle || p.name.toLowerCase().replace(/ /g, '_') === defaultStyle ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
    ).join('');

    // ── Template List ─────────────────
    let templateListHtml;
    if (templates.length === 0) {
        templateListHtml = `
            <div class="comfyui-empty">
                <div class="comfyui-empty-icon">📄</div>
                <p>No workflow templates uploaded yet.</p>
            </div>`;
    } else {
        templateListHtml = templates.map(t => {
            const placeholderTags = (t.placeholders || []).map(p =>
                `<span class="comfyui-placeholder-tag">${escapeHtml(p)}</span>`
            ).join(' ');
            const entityBadge = t.entity_type
                ? `<span class="badge badge-active" style="font-size:0.68rem">${escapeHtml(t.entity_type)}</span>`
                : '';
            const isExpanded = _comfyuiExpandedTemplate === t.id;
            return `
                <div class="comfyui-template-card" onclick="toggleComfyUITemplateDetail('${t.id}')">
                    <span class="comfyui-template-id">${t.id}</span>
                    <div class="comfyui-template-info">
                        <div class="comfyui-template-name">${escapeHtml(t.name)}</div>
                        <div class="comfyui-template-meta">
                            ${entityBadge}
                            ${placeholderTags || '<span style="color:var(--text-muted)">no placeholders</span>'}
                            ${t.author ? `<span>by ${escapeHtml(t.author)}</span>` : ''}
                        </div>
                    </div>
                    <div class="comfyui-template-actions">
                        <button class="btn btn-sm" onclick="event.stopPropagation(); deleteComfyUITemplate('${t.id}', '${escapeAttr(t.name)}')" title="Delete template">🗑️</button>
                    </div>
                </div>
                ${isExpanded ? `<div class="comfyui-template-detail" id="comfyui-detail-${t.id}"><em>Loading…</em></div>` : ''}`;
        }).join('');
    }

    container.innerHTML = `
        <div class="settings-provider-card">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">🖥️</span>
                <span class="settings-provider-name">Connection</span>
            </div>
            <div class="comfyui-config-row">
                <div class="settings-field-group">
                    <label>Host</label>
                    <input type="text" id="comfyui-host" class="settings-input" value="${escapeAttr(configData.host)}" placeholder="127.0.0.1" />
                </div>
                <div class="settings-field-group">
                    <label>Port</label>
                    <input type="number" id="comfyui-port" class="settings-input" value="${configData.port}" min="1" max="65535" />
                </div>
                <div class="settings-field-group" style="flex:0;min-width:auto">
                    <label>&nbsp;</label>
                    <div style="display:flex;gap:var(--space-xs)">
                        <button class="btn btn-primary btn-sm" onclick="saveComfyUIConfig()" id="comfyui-save-btn">💾 Save</button>
                        <button class="btn btn-sm" onclick="testComfyUIConnection()" id="comfyui-test-btn">🔌 Test</button>
                    </div>
                </div>
            </div>
            <div id="comfyui-status"></div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">📄</span>
                <span class="settings-provider-name">Workflow Templates</span>
                <span class="badge badge-draft" style="font-size:0.72rem">${templates.length} template${templates.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="comfyui-drop-zone" id="comfyui-drop-zone"
                 onclick="document.getElementById('comfyui-file-input').click()">
                <input type="file" id="comfyui-file-input" accept=".json,application/json" style="display:none" onchange="handleComfyUIFile(event)" />
                <div class="comfyui-drop-zone-icon">📁</div>
                <div class="comfyui-drop-zone-text">Click to select or drag & drop a workflow JSON file</div>
                <div class="comfyui-drop-zone-hint">ComfyUI API format (.json)</div>
                <div class="comfyui-drop-zone-filename" id="comfyui-filename"></div>
            </div>
            <div class="comfyui-upload-form" id="comfyui-upload-form" style="${_comfyuiPendingWorkflowJson ? '' : 'display:none'}">
                <div class="settings-field-group">
                    <label>Template Name *</label>
                    <input type="text" id="comfyui-tpl-name" class="settings-input" placeholder="e.g. SDXL Character Portrait" />
                </div>
                <div class="settings-field-group">
                    <label>Entity Type</label>
                    <select id="comfyui-tpl-entity" class="settings-input">
                        <option value="">General (any)</option>
                        <option value="character">Character</option>
                        <option value="location">Location</option>
                        <option value="item">Item</option>
                        <option value="store">Store</option>
                        <option value="story">Story</option>
                        <option value="explore">Explore</option>
                        <option value="council_member">Council Member</option>
                    </select>
                </div>
                <div class="settings-field-group">
                    <label>Description</label>
                    <input type="text" id="comfyui-tpl-desc" class="settings-input" placeholder="Optional description…" />
                </div>
                <div class="settings-field-group">
                    <label>Author</label>
                    <input type="text" id="comfyui-tpl-author" class="settings-input" placeholder="Optional author name" />
                </div>
                <div class="settings-field-group" style="grid-column: 1 / -1">
                    <button class="btn btn-primary" onclick="uploadComfyUITemplate()" id="comfyui-upload-btn">📤 Upload Template</button>
                </div>
            </div>
            <div class="comfyui-template-list">
                ${templateListHtml}
            </div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">✨</span>
                <span class="settings-provider-name">Default Style Preset</span>
            </div>
            <div class="settings-field-group">
                <label>Preset</label>
                <div class="settings-key-row">
                    <select id="comfyui-style-preset" class="settings-input" onchange="previewComfyUIPreset()">
                        <option value="">None (no style applied)</option>
                        ${presetOptions}
                    </select>
                    <button class="btn btn-primary btn-sm" onclick="saveComfyUIDefaultStyle()">💾 Save</button>
                </div>
                <span class="settings-field-hint">Applied automatically when generating prompts without an explicit style</span>
            </div>
        <div id="comfyui-preset-preview"></div>
        </div>

        <div class="settings-provider-card" style="margin-top:var(--space-lg)">
            <div class="settings-provider-header">
                <span class="settings-provider-icon">📌</span>
                <span class="settings-provider-name">Default Templates per Entity Type</span>
                <span class="badge badge-draft" style="font-size:0.72rem">F-039</span>
            </div>
            <div class="settings-field-hint" style="margin-bottom:var(--space-sm)">
                Assign a default workflow template for each entity type. When generating images, the assigned template will be pre-selected automatically.
            </div>
            <div class="tpl-assign-grid" id="tpl-assign-grid">
                ${_renderAssignmentCards(templates, templateAssignments)}
            </div>
            <div style="margin-top:var(--space-sm);display:flex;gap:var(--space-sm)">
                <button class="btn btn-primary btn-sm" onclick="saveTemplateAssignments()" id="tpl-assign-save-btn">💾 Save Assignments</button>
                <span id="tpl-assign-status" style="font-size:0.78rem;color:var(--text-muted)"></span>
            </div>
        </div>

        <div id="comfyui-preset-editor-container"></div>`;

    // Wire up drag-and-drop
    const dropZone = document.getElementById('comfyui-drop-zone');
    if (dropZone) {
        dropZone.addEventListener('dragover', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) processComfyUIFile(file);
        });
    }

    // Load expanded template detail if any
    if (_comfyuiExpandedTemplate) {
        loadComfyUITemplateDetail(_comfyuiExpandedTemplate);
    }

    // Show preset preview for current selection
    previewComfyUIPreset();

    // Lazy-load the preset editor
    try {
        const editorHtml = await renderPresetEditor();
        const editorContainer = document.getElementById('comfyui-preset-editor-container');
        if (editorContainer) editorContainer.innerHTML = editorHtml;
    } catch { /* preset editor optional */ }
}

/**
 * Render the template assignment cards for each entity type.
 */
function _renderAssignmentCards(templates, assignments) {
    const entityTypes = [
        { key: 'character', label: 'Character', icon: '🎭' },
        { key: 'location', label: 'Location', icon: '🏰' },
        { key: 'item', label: 'Item', icon: '⚔️' },
        { key: 'store', label: 'Store', icon: '🏪' },
        { key: 'story', label: 'Story', icon: '📖' },
        { key: 'explore', label: 'Explore', icon: '🧭' },
    ];

    return entityTypes.map(et => {
        const assigned = assignments[et.key] || '';
        const tplOptions = ['<option value="">None (auto-select)</option>'].concat(
            templates.map(t => {
                const sel = t.id === assigned ? 'selected' : '';
                const etBadge = t.entity_type ? ` [${t.entity_type}]` : '';
                return `<option value="${escapeAttr(t.id)}" ${sel}>${escapeHtml(t.name || t.id)}${etBadge}</option>`;
            })
        ).join('');

        const assignedTpl = assigned ? templates.find(t => t.id === assigned) : null;
        const statusHtml = assigned
            ? `<span class="tpl-assign-status-set">📌 ${escapeHtml(assignedTpl?.name || assigned)}</span>`
            : '<span class="tpl-assign-status-auto">⚡ Auto</span>';

        return `
            <div class="tpl-assign-card ${assigned ? 'tpl-assign-active' : ''}">
                <div class="tpl-assign-header">
                    <span class="tpl-assign-icon">${et.icon}</span>
                    <span class="tpl-assign-label">${et.label}</span>
                    ${statusHtml}
                </div>
                <select class="settings-input tpl-assign-select" data-entity-type="${et.key}">
                    ${tplOptions}
                </select>
            </div>`;
    }).join('');
}

/**
 * Save all template assignments from the UI dropdowns.
 */
async function saveTemplateAssignments() {
    const btn = document.getElementById('tpl-assign-save-btn');
    const status = document.getElementById('tpl-assign-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    const selects = document.querySelectorAll('.tpl-assign-select');
    const assignments = {};
    selects.forEach(sel => {
        const et = sel.getAttribute('data-entity-type');
        if (et) assignments[et] = sel.value;
    });

    try {
        await fetch('/api/settings/comfyui/template-assignments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(assignments),
        }).then(r => { if (!r.ok) throw new Error('Save failed'); return r.json(); });
        showToast('Template assignments saved 📌');
        if (status) status.textContent = '✅ Saved';
        setTimeout(() => { if (status) status.textContent = ''; }, 2000);
        // Refresh to update status badges
        loadComfyUISettings();
    } catch (err) {
        showToast(`Save error: ${err.message}`, true);
        if (status) status.textContent = '❌ Error';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Assignments'; }
    }
}

function handleComfyUIFile(event) {
    const file = event.target.files[0];
    if (file) processComfyUIFile(file);
}

function processComfyUIFile(file) {
    if (!file.name.endsWith('.json')) {
        showToast('Please select a JSON file', true);
        return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const json = JSON.parse(e.target.result);
            if (typeof json !== 'object' || Array.isArray(json)) {
                showToast('Invalid workflow JSON: must be an object', true);
                return;
            }
            _comfyuiPendingWorkflowJson = json;
            _comfyuiPendingFilename = file.name;
            const filenameEl = document.getElementById('comfyui-filename');
            if (filenameEl) filenameEl.textContent = `✅ ${file.name}`;
            const form = document.getElementById('comfyui-upload-form');
            if (form) form.style.display = '';
            // Auto-fill name from filename
            const nameInput = document.getElementById('comfyui-tpl-name');
            if (nameInput && !nameInput.value) {
                nameInput.value = file.name.replace(/\.json$/i, '').replace(/[_-]/g, ' ');
            }
            showToast(`Loaded ${file.name} ✅`);
        } catch (err) {
            showToast('Failed to parse JSON: ' + err.message, true);
        }
    };
    reader.readAsText(file);
}

async function saveComfyUIConfig() {
    const host = document.getElementById('comfyui-host')?.value?.trim();
    const port = parseInt(document.getElementById('comfyui-port')?.value, 10);
    if (!host) return;
    const btn = document.getElementById('comfyui-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
    try {
        const resp = await fetch('/api/settings/comfyui', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host, port }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('ComfyUI config saved ✅');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save'; }
    }
}

async function testComfyUIConnection() {
    const btn = document.getElementById('comfyui-test-btn');
    const statusEl = document.getElementById('comfyui-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Testing…'; }
    if (statusEl) statusEl.innerHTML = '';

    try {
        const resp = await fetch('/api/settings/comfyui/test', { method: 'POST' });
        const data = await resp.json();
        if (data.connected) {
            const stats = data.system_stats || {};
            const gpuInfo = stats.system?.gpus?.[0] || {};
            statusEl.innerHTML = `
                <div class="comfyui-status-result comfyui-status-success">
                    ✅ <strong>Connected</strong> to ComfyUI at ${escapeHtml(data.host)}:${data.port}
                    ${gpuInfo.name ? `<br>GPU: ${escapeHtml(gpuInfo.name)} (${Math.round((gpuInfo.vram_total || 0) / 1073741824)}GB VRAM)` : ''}
                </div>`;
            showToast('ComfyUI connection successful ✅');
        } else {
            statusEl.innerHTML = `
                <div class="comfyui-status-result comfyui-status-error">
                    ❌ <strong>Cannot connect</strong> to ${escapeHtml(data.host)}:${data.port}
                    <br><span style="font-size:0.78rem">${escapeHtml(data.error || 'Unknown error')}</span>
                </div>`;
            showToast('ComfyUI connection failed', true);
        }
    } catch (err) {
        if (statusEl) statusEl.innerHTML = `
            <div class="comfyui-status-result comfyui-status-error">
                ❌ <strong>Request failed</strong>: ${escapeHtml(err.message)}
            </div>`;
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🔌 Test'; }
    }
}

async function uploadComfyUITemplate() {
    if (!_comfyuiPendingWorkflowJson) {
        showToast('Please load a workflow JSON file first', true);
        return;
    }
    const name = document.getElementById('comfyui-tpl-name')?.value?.trim();
    if (!name) {
        document.getElementById('comfyui-tpl-name')?.focus();
        showToast('Template name is required', true);
        return;
    }
    const btn = document.getElementById('comfyui-upload-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading…'; }

    try {
        const resp = await fetch('/api/settings/comfyui/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                workflow_json: _comfyuiPendingWorkflowJson,
                description: document.getElementById('comfyui-tpl-desc')?.value?.trim() || '',
                entity_type: document.getElementById('comfyui-tpl-entity')?.value || '',
                author: document.getElementById('comfyui-tpl-author')?.value?.trim() || '',
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        _comfyuiPendingWorkflowJson = null;
        _comfyuiPendingFilename = '';
        showToast(`Template ${data.id} created ✅`);
        loadComfyUISettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📤 Upload Template'; }
    }
}

async function deleteComfyUITemplate(templateId, templateName) {
    if (!confirm(`Delete template "${templateName}"?`)) return;
    try {
        const resp = await fetch(`/api/settings/comfyui/templates/${encodeURIComponent(templateId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast(`Template ${templateId} deleted ✅`);
        if (_comfyuiExpandedTemplate === templateId) _comfyuiExpandedTemplate = null;
        loadComfyUISettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function toggleComfyUITemplateDetail(templateId) {
    if (_comfyuiExpandedTemplate === templateId) {
        _comfyuiExpandedTemplate = null;
        loadComfyUISettings();
        return;
    }
    _comfyuiExpandedTemplate = templateId;
    loadComfyUISettings();
}

async function loadComfyUITemplateDetail(templateId) {
    const container = document.getElementById(`comfyui-detail-${templateId}`);
    if (!container) return;
    try {
        const data = await api(`/api/settings/comfyui/templates/${encodeURIComponent(templateId)}`);
        const placeholderTags = (data.placeholders || []).map(p =>
            `<span class="comfyui-placeholder-tag">${escapeHtml(p)}</span>`
        ).join(' ');
        const jsonStr = JSON.stringify(data.workflow_json, null, 2);
        const truncJson = jsonStr.length > 5000 ? jsonStr.slice(0, 5000) + '\n… (truncated)' : jsonStr;

        container.innerHTML = `
            <div style="margin-bottom:var(--space-sm)">
                ${data.description ? `<p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:var(--space-sm)">${escapeHtml(data.description)}</p>` : ''}
                <div style="font-size:0.78rem;color:var(--text-muted)">Created: ${formatDate(data.created_at)}</div>
            </div>
            <div style="margin-bottom:var(--space-sm)">
                <strong style="font-size:0.78rem;color:var(--text-secondary)">Placeholders (${data.placeholders.length}):</strong><br>
                ${placeholderTags || '<span style="color:var(--text-muted);font-size:0.78rem">None detected</span>'}
            </div>
            <div>
                <strong style="font-size:0.78rem;color:var(--text-secondary)">Workflow JSON:</strong>
                <div class="comfyui-json-preview"><pre>${escapeHtml(truncJson)}</pre></div>
            </div>`;
    } catch (err) {
        container.innerHTML = `<p style="color:var(--accent-rose)">Failed to load: ${escapeHtml(err.message)}</p>`;
    }
}

function previewComfyUIPreset() {
    const select = document.getElementById('comfyui-style-preset');
    const container = document.getElementById('comfyui-preset-preview');
    if (!select || !container) return;
    const key = select.value;
    if (!key) {
        container.innerHTML = '';
        return;
    }
    // Find preset in the select's options
    const name = select.options[select.selectedIndex]?.text || key;
    // Fetch presets to get details (they should be cached, small list)
    api('/api/settings/comfyui/style-presets').then(presets => {
        const preset = presets.find(p => p.name === key || p.name === name);
        if (!preset) { container.innerHTML = ''; return; }
        container.innerHTML = `
            <div class="comfyui-preset-preview">
                <div style="margin-bottom:var(--space-sm);font-size:0.85rem;font-weight:600">${escapeHtml(preset.name)}</div>
                ${preset.description ? `<p style="color:var(--text-secondary);font-size:0.8rem;margin-bottom:var(--space-sm)">${escapeHtml(preset.description)}</p>` : ''}
                <div class="comfyui-preset-label">Positive suffix</div>
                <div class="comfyui-preset-value">${escapeHtml(preset.positive_suffix || '(none)')}</div>
                <div class="comfyui-preset-label" style="margin-top:var(--space-sm)">Negative prefix</div>
                <div class="comfyui-preset-value">${escapeHtml(preset.negative_prefix || '(none)')}</div>
            </div>`;
    }).catch(() => { container.innerHTML = ''; });
}

async function saveComfyUIDefaultStyle() {
    const select = document.getElementById('comfyui-style-preset');
    const key = select?.value || '';
    try {
        // Use the name as the key since presets are looked up by name
        const resp = await fetch('/api/settings/comfyui/default-style', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ style_key: key }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Default style preset saved ✅');
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ─── Character Form Model Helpers ─────────────────────────────

/** Swap model field in character creation form when provider changes. */
function updateCharCreateModelField() {
    const provider = document.getElementById('char-provider-input').value;
    const container = document.getElementById('char-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('char-model-input', provider, '', true);
}

/** Swap model field in character detail edit form when provider changes. */
function updateCharEditModelField() {
    const provider = document.getElementById('char-edit-provider').value;
    const container = document.getElementById('char-edit-model-container');
    if (!container) return;
    container.innerHTML = renderModelField('char-edit-model', provider, '', true);
}


// ═══════════════════════════════════════════════════════════════
// Tasks View
// ═══════════════════════════════════════════════════════════════

