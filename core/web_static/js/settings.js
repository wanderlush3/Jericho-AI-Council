/** Eagerly fetch model option lists from the API so they're available
 *  before the user visits any form (council, character, proposal). */
async function loadModelOptions() {
    if (_modelOptionsLoaded) return;
    try {
        const [mancer, openrouter, lmstudio] = await Promise.all([
            api('/api/settings/mancer-models').catch(() => ['Default']),
            api('/api/settings/openrouter-models').catch(() => ['Default']),
            api('/api/settings/lmstudio-models').catch(() => ['Default']),
        ]);
        if (mancer && mancer.length) MANCER_MODEL_OPTIONS = mancer;
        if (openrouter && openrouter.length) OPENROUTER_MODEL_OPTIONS = openrouter;
        if (lmstudio && lmstudio.length) LMSTUDIO_MODEL_OPTIONS = lmstudio;
        _modelOptionsLoaded = true;
    } catch (_) { /* silently degrade — will try again on Settings visit */ }
}

/** Return model options array for a given provider. */
function getModelOptionsForProvider(provider) {
    if (provider === 'mancer') return MANCER_MODEL_OPTIONS;
    if (provider === 'lmstudio') return LMSTUDIO_MODEL_OPTIONS;
    return OPENROUTER_MODEL_OPTIONS;
}

/** Render a model dropdown (or LM Studio info message) for a given provider.
 *  @param {string} selectId - the id for the <select> element
 *  @param {string} provider - 'openrouter' | 'mancer' | 'lmstudio'
 *  @param {string} currentModel - the currently selected model value
 *  @param {boolean} includeDefault - whether to include 'Default' as an option
 */
function renderModelField(selectId, provider, currentModel, includeDefault) {
    if (provider === 'lmstudio') {
        return `<div class="lmstudio-model-info" style="padding:var(--space-sm);background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:var(--radius-md);color:var(--text-secondary);font-size:0.85rem">
            🖥️ Model is selected in the LM Studio application
            <input type="hidden" id="${selectId}" value="Loaded Model" />
        </div>`;
    }
    const opts = getModelOptionsForProvider(provider);
    const filteredOpts = includeDefault ? opts : opts.filter(m => m !== 'Default');
    return `<select id="${selectId}" class="settings-input">
        ${filteredOpts.map(m => `<option value="${m}" ${currentModel === m || (!currentModel && m === 'Default') ? 'selected' : ''}>${m}</option>`).join('')}
    </select>`;
}

async function renderSettings() {
    showLoading();
    const [keys, models, userDescData, userNameData, mancerModels, openrouterModels, lmstudioModels, memDecayConfig, narrativeConfig, embeddingsConfig] = await Promise.all([
        api('/api/settings/keys'),
        api('/api/settings/models'),
        api('/api/settings/user-description'),
        api('/api/settings/user-name').catch(() => ({ name: '' })),
        api('/api/settings/mancer-models').catch(() => ['Default']),
        api('/api/settings/openrouter-models').catch(() => ['Default']),
        api('/api/settings/lmstudio-models').catch(() => ['Default']),
        api('/api/settings/memory-decay').catch(() => ({ decay: {}, summarization: {}, contested: {} })),
        api('/api/settings/narrative').catch(() => ({ max_bulletins: 10, max_age_days: 30 })),
        api('/api/settings/embeddings').catch(() => ({ model_name: 'all-MiniLM-L6-v2', model_options: [], mode: 'hybrid', similarity_weight: 0.7, jaccard_weight: 0.3, available: false })),
    ]);

    // Cache model options for use in council member editing
    if (mancerModels && mancerModels.length) MANCER_MODEL_OPTIONS = mancerModels;
    if (openrouterModels && openrouterModels.length) OPENROUTER_MODEL_OPTIONS = openrouterModels;
    if (lmstudioModels && lmstudioModels.length) LMSTUDIO_MODEL_OPTIONS = lmstudioModels;

    const userDesc = userDescData.description || '';
    const userName = userNameData.name || '';
    const maxLen = 700;

    // Build a map of provider -> model info
    const modelMap = {};
    models.forEach(m => { modelMap[m.provider] = m; });

    const cards = keys.map(k => {
        const info = PROVIDER_LABELS[k.provider] || { name: k.provider, icon: '🔑', url: '#' };
        const configured = k.configured;
        const statusBadge = configured
            ? `<span class="badge badge-active">✅ Configured</span>`
            : `<span class="badge badge-draft">❌ Not Set</span>`;
        const maskedDisplay = configured
            ? `<div class="key-masked"><code>${k.masked}</code></div>`
            : '';

        const modelInfo = modelMap[k.provider] || {};
        const currentModel = modelInfo.model || '';
        const isDefault = modelInfo.is_default !== false;
        const modelLabel = 'Default Model (fallback)';
        const modelBadge = isDefault
            ? `<span class="badge badge-draft" style="font-size:0.7rem">default</span>`
            : `<span class="badge badge-active" style="font-size:0.7rem">custom</span>`;

        return `
        <div class="card settings-card" id="key-card-${k.provider}">
            <div class="settings-card-header">
                <div class="settings-provider-info">
                    <span class="settings-provider-icon">${info.icon}</span>
                    <div>
                        <div class="settings-provider-name">${info.name}</div>
                        <a href="${info.url}" target="_blank" rel="noopener" class="settings-provider-link">Get API key ↗</a>
                    </div>
                </div>
                ${statusBadge}
            </div>
            ${maskedDisplay}
            <div class="settings-form">
                <div class="settings-input-row">
                    <input type="password"
                           id="key-input-${k.provider}"
                           class="settings-input"
                           placeholder="Paste your ${info.name} API key…"
                           autocomplete="off"
                           spellcheck="false" />
                    <button class="btn btn-primary" onclick="saveApiKey('${k.provider}')">
                        💾 Save
                    </button>
                    ${configured ? `<button class="btn btn-danger" onclick="deleteApiKey('${k.provider}')">🗑️ Delete</button>` : ''}
                </div>
            </div>
            <div class="settings-model-section">
                <div class="settings-model-header">
                    <span class="settings-model-label">🤖 ${modelLabel}</span>
                    ${modelBadge}
                </div>
                <p style="font-size:0.8rem;color:var(--text-muted);margin:var(--space-xs) 0">Used when a council member's model is set to "Default".</p>
                <div class="settings-input-row">
                    ${k.provider === 'mancer'
                        ? `<select id="model-input-${k.provider}" class="settings-input">
                               ${mancerModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                           </select>`
                        : k.provider === 'lmstudio'
                        ? `<select id="model-input-${k.provider}" class="settings-input">
                               ${lmstudioModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                           </select>`
                        : `<select id="model-input-${k.provider}" class="settings-input">
                               ${openrouterModels.filter(m => m !== 'Default').map(m => `<option value="${m}" ${currentModel === m ? 'selected' : ''}>${m}</option>`).join('')}
                           </select>`
                    }
                    <button class="btn btn-primary" onclick="saveModel('${k.provider}')">
                        💾 Save
                    </button>
                </div>
            </div>
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>⚙️ Settings</h2>
                <p>Configure your profile, API provider keys, and models</p>
            </div>

            <div class="card settings-card user-profile-card">
                <div class="settings-card-header">
                    <div class="settings-provider-info">
                        <span class="settings-provider-icon">👤</span>
                        <div>
                            <div class="settings-provider-name">About You</div>
                            <span class="settings-provider-link" style="cursor:default">Tell the AI council about yourself so they know who they're speaking with</span>
                        </div>
                    </div>
                </div>
                <div class="settings-form" style="margin-top:var(--space-sm)">
                    <div class="filter-group" style="margin-bottom:var(--space-md)">
                        <label for="user-name-input" class="user-desc-label">
                            Your Name
                            <span class="user-desc-hint">How the council members and characters will address you.</span>
                        </label>
                        <div class="settings-input-row">
                            <input id="user-name-input"
                                   class="settings-input"
                                   type="text"
                                   maxlength="100"
                                   placeholder="Enter your name…"
                                   value="${escapeHtml(userName)}" />
                            <button class="btn btn-primary" onclick="saveUserName()" id="user-name-save-btn">
                                💾 Save
                            </button>
                        </div>
                        <span id="user-name-status" style="font-size:0.82rem;color:var(--text-muted);margin-top:var(--space-xs);display:block"></span>
                    </div>
                    <label for="user-desc-input" class="user-desc-label">
                        About You
                        <span class="user-desc-hint">This description is shared with council members so they know who they're speaking with.</span>
                    </label>
                    <textarea id="user-desc-input"
                              class="settings-input user-desc-textarea"
                              rows="5"
                              maxlength="${maxLen}"
                              placeholder="Write a brief description about yourself — your interests, role, what you're working on…"
                              oninput="updateCharCount()">${escapeHtml(userDesc)}</textarea>
                    <div class="user-desc-footer">
                        <span class="user-desc-counter" id="user-desc-counter">
                            <span id="user-desc-count">${userDesc.length}</span> / ${maxLen}
                        </span>
                        <div style="display:flex;align-items:center;gap:var(--space-sm)">
                            <span id="user-desc-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                            <button class="btn btn-primary" onclick="saveUserDescription()" id="user-desc-save-btn">
                                💾 Save
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="settings-notice">
                <span class="settings-notice-icon">🔒</span>
                <div>
                    <strong>Your keys are safe.</strong>
                    Keys are encrypted with AES before being stored locally in <code>config/.env</code>.
                    They are never transmitted to any third party — only to the API providers you configure.
                </div>
            </div>

            <div class="settings-grid">${cards}</div>

            <div class="card settings-card memory-decay-card" id="memory-decay-card">
                <div class="settings-card-header">
                    <div class="settings-provider-info">
                        <span class="settings-provider-icon">🧠</span>
                        <div>
                            <div class="settings-provider-name">Memory & Decay</div>
                            <span class="settings-provider-link" style="cursor:default">Configure time decay, summarization, and contested memory subsystems</span>
                        </div>
                    </div>
                </div>
                <div class="settings-form memory-decay-form" style="margin-top:var(--space-sm)">
                    <div class="memory-decay-grid">
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">⏳ Time Decay</h4>
                            <p class="memory-decay-hint">Older memories gradually lose influence. Half-life controls the rate.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label">
                                    <input type="checkbox" id="decay-enabled" ${memDecayConfig.decay?.enabled !== false ? 'checked' : ''} />
                                    Enabled
                                </label>
                            </div>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="decay-half-life">Half-life (days)</label>
                                <input type="number" id="decay-half-life" class="settings-input memory-decay-input"
                                       min="1" max="365" step="1"
                                       value="${memDecayConfig.decay?.half_life_days ?? 30}" />
                            </div>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="decay-min-factor">Min factor</label>
                                <input type="number" id="decay-min-factor" class="settings-input memory-decay-input"
                                       min="0.01" max="0.99" step="0.01"
                                       value="${memDecayConfig.decay?.min_factor ?? 0.1}" />
                            </div>
                        </div>

                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">📋 Summarization</h4>
                            <p class="memory-decay-hint">Condense old sessions via LLM to keep context compact.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label">
                                    <input type="checkbox" id="summarization-enabled" ${memDecayConfig.summarization?.enabled !== false ? 'checked' : ''} />
                                    Enabled
                                </label>
                            </div>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="summarization-threshold">Session threshold</label>
                                <input type="number" id="summarization-threshold" class="settings-input memory-decay-input"
                                       min="2" max="50" step="1"
                                       value="${memDecayConfig.summarization?.session_threshold ?? 6}" />
                            </div>
                            <div class="memory-decay-row">
                                <span class="memory-decay-hint" style="font-size:0.78rem">Keep recent: ${memDecayConfig.summarization?.keep_recent ?? 3} sessions</span>
                            </div>
                        </div>

                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">🔀 Contested Memories</h4>
                            <p class="memory-decay-hint">Agents may record divergent recollections of events. Low probability preserves coherence.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label">
                                    <input type="checkbox" id="contested-enabled" ${memDecayConfig.contested?.enabled !== false ? 'checked' : ''} />
                                    Enabled
                                </label>
                            </div>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="contested-probability">Probability (%)</label>
                                <input type="number" id="contested-probability" class="settings-input memory-decay-input"
                                       min="0" max="10" step="0.5"
                                       value="${((memDecayConfig.contested?.probability ?? 0.03) * 100).toFixed(1)}" />
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:var(--space-sm);margin-top:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveMemoryDecay()" id="memory-decay-save-btn">💾 Save Memory Settings</button>
                        <span id="memory-decay-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>

            <div class="card settings-card narrative-settings-card" id="narrative-settings-card">
                <div class="settings-card-header">
                    <div class="settings-provider-info">
                        <span class="settings-provider-icon">📰</span>
                        <div>
                            <div class="settings-provider-name">Narrative Engine</div>
                            <span class="settings-provider-link" style="cursor:default">Configure the Jericho Times news ticker on the Dashboard</span>
                        </div>
                    </div>
                </div>
                <div class="settings-form" style="margin-top:var(--space-sm)">
                    <div class="memory-decay-grid" style="grid-template-columns:repeat(2, 1fr)">
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">📊 Max Bulletins</h4>
                            <p class="memory-decay-hint">Maximum number of news bulletins shown per request.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="narrative-max-bulletins">Count</label>
                                <input type="number" id="narrative-max-bulletins" class="settings-input memory-decay-input"
                                       min="1" max="50" step="1"
                                       value="${narrativeConfig.max_bulletins ?? 10}" />
                            </div>
                        </div>
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">📅 Event Window</h4>
                            <p class="memory-decay-hint">Only consider events within this many days.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="narrative-max-age">Days</label>
                                <input type="number" id="narrative-max-age" class="settings-input memory-decay-input"
                                       min="1" max="365" step="1"
                                       value="${narrativeConfig.max_age_days ?? 30}" />
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:var(--space-sm);margin-top:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveNarrativeSettings()" id="narrative-save-btn">💾 Save Narrative Settings</button>
                        <span id="narrative-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>

            <div class="card settings-card embeddings-settings-card" id="embeddings-settings-card">
                <div class="settings-card-header">
                    <div class="settings-provider-info">
                        <span class="settings-provider-icon">🧠</span>
                        <div>
                            <div class="settings-provider-name">Embeddings & Scoring</div>
                            <span class="settings-provider-link" style="cursor:default">Configure semantic memory scoring model, mode, and weights</span>
                        </div>
                    </div>
                    <span class="badge badge-${embeddingsConfig.available ? 'active' : 'draft'}" style="font-size:0.72rem">${embeddingsConfig.available ? '✅ Model Loaded' : '⚠️ Unavailable'}</span>
                </div>
                <div class="settings-form" style="margin-top:var(--space-sm)">
                    ${!embeddingsConfig.available ? `<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);border-radius:var(--radius-md);padding:var(--space-md);margin-bottom:var(--space-md);font-size:0.82rem;color:var(--text-secondary)">⚠️ sentence-transformers not installed. Scoring uses keyword-only mode.<br><code style="background:var(--bg-surface);padding:2px 6px;border-radius:4px;font-size:0.78rem">${embeddingsConfig.install_hint || 'pip install sentence-transformers'}</code></div>` : ''}
                    <div class="memory-decay-grid" style="grid-template-columns:repeat(2, 1fr)">
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">🔧 Model</h4>
                            <p class="memory-decay-hint">Sentence-transformer model for semantic similarity.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="emb-model-name">Model</label>
                                <select id="emb-model-name" class="settings-input memory-decay-input">
                                    ${(embeddingsConfig.model_options || []).map(m => `<option value="${m}" ${m === embeddingsConfig.model_name ? 'selected' : ''}>${m}</option>`).join('')}
                                </select>
                            </div>
                        </div>
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">⚙️ Scoring Mode</h4>
                            <p class="memory-decay-hint">Hybrid uses both semantic + keyword; Keyword Only skips embeddings.</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="emb-mode">Mode</label>
                                <select id="emb-mode" class="settings-input memory-decay-input">
                                    <option value="hybrid" ${embeddingsConfig.mode === 'hybrid' ? 'selected' : ''}>Hybrid (Semantic + Keyword)</option>
                                    <option value="keyword_only" ${embeddingsConfig.mode === 'keyword_only' ? 'selected' : ''}>Keyword Only</option>
                                </select>
                            </div>
                        </div>
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">📊 Semantic Weight</h4>
                            <p class="memory-decay-hint">Weight given to embedding cosine similarity (0.0–1.0).</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="emb-sim-weight">Weight</label>
                                <input type="number" id="emb-sim-weight" class="settings-input memory-decay-input"
                                       min="0" max="1" step="0.05"
                                       value="${embeddingsConfig.similarity_weight ?? 0.7}" />
                            </div>
                        </div>
                        <div class="memory-decay-section">
                            <h4 class="memory-decay-heading">🔤 Keyword Weight</h4>
                            <p class="memory-decay-hint">Weight given to Jaccard keyword overlap (0.0–1.0).</p>
                            <div class="memory-decay-row">
                                <label class="memory-decay-label" for="emb-jac-weight">Weight</label>
                                <input type="number" id="emb-jac-weight" class="settings-input memory-decay-input"
                                       min="0" max="1" step="0.05"
                                       value="${embeddingsConfig.jaccard_weight ?? 0.3}" />
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:var(--space-sm);margin-top:var(--space-md)">
                        <button class="btn btn-primary" onclick="saveEmbeddingSettings()" id="emb-save-btn">💾 Save Embedding Settings</button>
                        <span id="emb-status" style="font-size:0.82rem;color:var(--text-muted)"></span>
                    </div>
                </div>
            </div>
        </div>`;

    // Initialize character count display color
    updateCharCount();
}

async function saveApiKey(provider) {
    const input = document.getElementById(`key-input-${provider}`);
    const key = input.value.trim();
    if (!key) { input.focus(); return; }

    input.disabled = true;
    try {
        await fetch('/api/settings/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: key }),
        });
        input.value = '';
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} key saved & encrypted ✅`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        input.disabled = false;
    }
}

async function deleteApiKey(provider) {
    if (!confirm(`Remove the ${PROVIDER_LABELS[provider]?.name || provider} API key?`)) return;
    try {
        await fetch(`/api/settings/keys/${provider}`, { method: 'DELETE' });
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} key removed`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function saveModel(provider) {
    const el = document.getElementById(`model-input-${provider}`);
    const model = el.value.trim();
    if (!model) { el.focus(); return; }

    el.disabled = true;
    try {
        await fetch('/api/settings/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, model }),
        });
        showToast(`${PROVIDER_LABELS[provider]?.name || provider} default model saved ✅`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    } finally {
        el.disabled = false;
    }
}

function updateCharCount() {
    const textarea = document.getElementById('user-desc-input');
    const countEl = document.getElementById('user-desc-count');
    const counterEl = document.getElementById('user-desc-counter');
    if (!textarea || !countEl || !counterEl) return;

    const len = textarea.value.length;
    countEl.textContent = len;

    // Color feedback
    if (len >= 700) {
        counterEl.classList.add('at-limit');
        counterEl.classList.remove('near-limit');
    } else if (len >= 600) {
        counterEl.classList.add('near-limit');
        counterEl.classList.remove('at-limit');
    } else {
        counterEl.classList.remove('near-limit', 'at-limit');
    }
}

async function saveUserDescription() {
    const textarea = document.getElementById('user-desc-input');
    const btn = document.getElementById('user-desc-save-btn');
    const status = document.getElementById('user-desc-status');
    const description = textarea.value;

    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    try {
        const resp = await fetch('/api/settings/user-description', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('User description saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save';
    }
}

async function saveUserName() {
    const input = document.getElementById('user-name-input');
    const btn = document.getElementById('user-name-save-btn');
    const status = document.getElementById('user-name-status');
    const name = input.value.trim();

    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

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
        showToast('Name saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save';
    }
}

function escapeHtml(text) {
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
}

function showToast(msg, isError) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'toast-error' : 'toast-success'}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('toast-exit'); }, 2500);
    setTimeout(() => { toast.remove(); }, 3000);
}

// ═══════════════════════════════════════════════════════════════
// Memory Decay Settings (F-075)
// ═══════════════════════════════════════════════════════════════

async function saveMemoryDecay() {
    const btn = document.getElementById('memory-decay-save-btn');
    const status = document.getElementById('memory-decay-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const body = {
        decay: {
            enabled: document.getElementById('decay-enabled').checked,
            half_life_days: parseFloat(document.getElementById('decay-half-life').value) || 30,
            min_factor: parseFloat(document.getElementById('decay-min-factor').value) || 0.1,
        },
        summarization: {
            enabled: document.getElementById('summarization-enabled').checked,
            session_threshold: parseInt(document.getElementById('summarization-threshold').value, 10) || 6,
        },
        contested: {
            enabled: document.getElementById('contested-enabled').checked,
            probability: (parseFloat(document.getElementById('contested-probability').value) || 3) / 100,
        },
    };

    try {
        const resp = await fetch('/api/settings/memory-decay', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Memory settings saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Memory Settings';
    }
}

// ═══════════════════════════════════════════════════════════════
// Narrative Engine Settings (F-076)
// ═══════════════════════════════════════════════════════════════

async function saveNarrativeSettings() {
    const btn = document.getElementById('narrative-save-btn');
    const status = document.getElementById('narrative-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const body = {
        max_bulletins: parseInt(document.getElementById('narrative-max-bulletins').value, 10) || 10,
        max_age_days: parseInt(document.getElementById('narrative-max-age').value, 10) || 30,
    };

    try {
        const resp = await fetch('/api/settings/narrative', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Narrative settings saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Narrative Settings';
    }
}

// ═══════════════════════════════════════════════════════════════
// Memory Explorer Views (F-028)
// ═══════════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════════
// Embedding & Scoring Settings (F-077)
// ═══════════════════════════════════════════════════════════════

async function saveEmbeddingSettings() {
    const btn = document.getElementById('emb-save-btn');
    const status = document.getElementById('emb-status');
    btn.disabled = true;
    btn.textContent = '⏳ Saving…';
    status.textContent = '';

    const body = {
        model_name: document.getElementById('emb-model-name').value,
        mode: document.getElementById('emb-mode').value,
        similarity_weight: parseFloat(document.getElementById('emb-sim-weight').value) || 0.7,
        jaccard_weight: parseFloat(document.getElementById('emb-jac-weight').value) || 0.3,
    };

    try {
        const resp = await fetch('/api/settings/embeddings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast('Embedding settings saved ✅');
        status.textContent = '✅ Saved';
        status.style.color = 'var(--accent-emerald)';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        status.textContent = '❌ Failed';
        status.style.color = 'var(--accent-rose)';
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Embedding Settings';
    }
}
