async function openGenerateModal(entityType, entityId) {
    _generateEntityType = entityType;
    _generateEntityId = entityId;

    // Fetch available templates, style presets, and recommended template
    let templates = [];
    let presets = [];
    let members = [];
    let recommendedTemplateId = '';
    let recommendedSource = '';
    try {
        const [tpls, prsts, council, recommended] = await Promise.all([
            api('/api/settings/comfyui/templates').catch(() => []),
            api('/api/settings/comfyui/style-presets').catch(() => []),
            api('/api/council').catch(() => []),
            api(`/api/settings/comfyui/recommended-template/${encodeURIComponent(entityType)}`).catch(() => ({})),
        ]);
        templates = tpls;
        presets = prsts;
        members = council.map ? council.map(m => m.name) : [];
        _generateMembers = members;
        recommendedTemplateId = recommended.template_id || '';
        recommendedSource = recommended.source || '';
    } catch { /* endpoints may not be available */ }

    if (!templates.length) {
        showToast('No ComfyUI workflow templates found. Add one in Settings → ComfyUI first.', true);
        return;
    }

    // Build template options with recommended badge
    const templateOptions = templates.map(t => {
        const isRecommended = t.id === recommendedTemplateId;
        const sel = isRecommended ? 'selected' : '';
        const badge = isRecommended ? ' 📌 Default' : '';
        return `<option value="${escapeAttr(t.id)}" ${sel}>${escapeHtml(t.name || t.id)}${badge}</option>`;
    }).join('');

    const presetOptions = ['<option value="">None (default)</option>'].concat(
        presets.map(p => `<option value="${escapeAttr(p.key)}">${escapeHtml(p.name || p.key)}</option>`)
    ).join('');

    const memberOptions = members.map(m =>
        `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
    ).join('');

    const memberCheckboxes = members.map(m =>
        `<label class="gen-participant-label">
            <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
            ${escapeHtml(m)}
        </label>`
    ).join('');

    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'gen-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal">
            <div class="gen-modal-header">
                <h3>🎨 Generate Image — ${escapeHtml(entityType)}/${escapeHtml(entityId)}</h3>
                <button class="detail-close" onclick="closeGenerateModal()">✕</button>
            </div>

            <div class="gen-modal-body" id="gen-modal-body">
                <div class="gen-form-grid">
                    <div class="filter-group">
                        <label for="gen-template">Workflow Template</label>
                        <select id="gen-template" class="settings-input">${templateOptions}</select>
                    </div>
                    <div class="filter-group">
                        <label for="gen-style">Style Preset</label>
                        <select id="gen-style" class="settings-input">${presetOptions}</select>
                    </div>
                </div>

                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="gen-mode">Prompt Mode</label>
                    <select id="gen-mode" class="settings-input" onchange="updateGenModeFields()">
                        <option value="system">System — AI generates from entity context</option>
                        <option value="character">Character — A council member describes</option>
                        <option value="raw_user">Raw User — Your own prompt text</option>
                        <option value="user_refined">User Refined — Your prompt, refined by a member</option>
                        <option value="council_vote">Council Vote — Multiple members propose prompts</option>
                    </select>
                </div>

                <!-- Dynamic mode fields -->
                <div id="gen-mode-fields"></div>

                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="gen-width">Width</label>
                        <input id="gen-width" class="settings-input" type="number" value="1024" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="gen-height">Height</label>
                        <input id="gen-height" class="settings-input" type="number" value="1024" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="gen-seed">Seed <span style="color:var(--text-muted);font-size:0.72rem">(0 = random)</span></label>
                        <input id="gen-seed" class="settings-input" type="number" value="0" min="0" />
                    </div>
                </div>

                <!-- Council vote prompts preview area -->
                <div id="gen-prompts-preview" style="display:none"></div>

                <!-- Progress area (shown during generation) -->
                <div id="gen-progress-area" style="display:none">
                    <div class="gen-progress-container">
                        <div class="gen-progress-stage" id="gen-progress-stage">Initializing...</div>
                        <div class="gen-progress-bar-bg">
                            <div class="gen-progress-bar-fill" id="gen-progress-bar"></div>
                        </div>
                        <div class="gen-progress-pct" id="gen-progress-pct">0%</div>
                    </div>
                    <div id="gen-progress-prompts" class="gen-progress-prompts"></div>
                </div>
            </div>

            <div class="gen-modal-footer" id="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeGenerateModal()">Cancel</button>
                <button class="btn btn-primary" id="gen-submit-btn" onclick="submitGeneration()">
                    🎨 Generate
                </button>
            </div>
        </div>`;

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeGenerateModal();
    });
    document.body.appendChild(modal);
    updateGenModeFields();
}

function closeGenerateModal() {
    // Cancel any active SSE connection
    if (_generateEventSource) {
        _generateEventSource.close();
        _generateEventSource = null;
    }
    const m = document.getElementById('gen-modal-overlay');
    if (m) m.remove();
}

/**
 * Update dynamic fields based on selected prompt mode.
 */
function updateGenModeFields() {
    const mode = document.getElementById('gen-mode')?.value || 'system';
    const container = document.getElementById('gen-mode-fields');
    if (!container) return;

    let html = '';

    if (mode === 'character') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-member">Council Member</label>
                <select id="gen-member" class="settings-input">
                    ${_getGenMemberOptions()}
                </select>
            </div>`;
    } else if (mode === 'raw_user') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-user-prompt">Your Prompt</label>
                <textarea id="gen-user-prompt" class="settings-input proposal-textarea" rows="3"
                    placeholder="Describe the image you want to generate..."></textarea>
            </div>`;
    } else if (mode === 'user_refined') {
        html = `
            <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                <div class="filter-group" style="flex:1">
                    <label for="gen-member">Refining Member</label>
                    <select id="gen-member" class="settings-input">
                        ${_getGenMemberOptions()}
                    </select>
                </div>
            </div>
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label for="gen-user-prompt">Your Base Prompt</label>
                <textarea id="gen-user-prompt" class="settings-input proposal-textarea" rows="3"
                    placeholder="Your prompt text to be refined by the member..."></textarea>
            </div>`;
    } else if (mode === 'council_vote') {
        html = `
            <div class="filter-group" style="margin-top:var(--space-sm)">
                <label>Voting Participants <span style="color:var(--text-muted);font-size:0.72rem">(min 2)</span></label>
                <div class="gen-participants-grid" id="gen-participants">
                    ${_getGenParticipantCheckboxes()}
                </div>
            </div>
            <div style="margin-top:var(--space-sm)">
                <button class="btn btn-secondary btn-sm" onclick="previewCouncilPrompts()" id="gen-preview-btn">
                    👁 Preview Prompts
                </button>
            </div>`;
    }
    // system mode has no extra fields

    container.innerHTML = html;
}

function _getGenMemberOptions() {
    if (!_generateMembers.length) return '<option value="">No members found</option>';
    return _generateMembers.map(m =>
        `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
    ).join('');
}

function _getGenParticipantCheckboxes() {
    if (!_generateMembers.length) return '<span style="color:var(--text-muted)">No members found</span>';
    return _generateMembers.map(m =>
        `<label class="gen-participant-label">
            <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
            ${escapeHtml(m)}
        </label>`
    ).join('');
}

// On modal open, populate member dropdowns asynchronously
async function _populateGenMembers() {
    try {
        const council = await api('/api/council');
        const members = council.map(m => m.name);

        // Populate member select dropdowns
        const memberSelect = document.getElementById('gen-member');
        if (memberSelect) {
            memberSelect.innerHTML = members.map(m =>
                `<option value="${escapeAttr(m)}">${escapeHtml(m)}</option>`
            ).join('');
        }

        // Populate participant checkboxes
        const participantsDiv = document.getElementById('gen-participants');
        if (participantsDiv) {
            participantsDiv.innerHTML = members.map(m =>
                `<label class="gen-participant-label">
                    <input type="checkbox" class="gen-participant-cb" value="${escapeAttr(m)}" checked />
                    ${escapeHtml(m)}
                </label>`
            ).join('');
        }
    } catch { /* ignore */ }
}

/**
 * Preview prompts for council_vote mode.
 * Shows all generated prompts and lets the user pick one.
 */
async function previewCouncilPrompts() {
    const previewBtn = document.getElementById('gen-preview-btn');
    if (previewBtn) { previewBtn.disabled = true; previewBtn.textContent = '⏳ Generating prompts...'; }

    const participants = Array.from(document.querySelectorAll('.gen-participant-cb:checked'))
        .map(cb => cb.value);

    if (participants.length < 2) {
        showToast('Select at least 2 participants for council vote.', true);
        if (previewBtn) { previewBtn.disabled = false; previewBtn.textContent = '👁 Preview Prompts'; }
        return;
    }

    try {
        const body = {
            entity_type: _generateEntityType,
            entity_id: _generateEntityId,
            prompt_mode: 'council_vote',
            participants: participants,
            style_preset_key: document.getElementById('gen-style')?.value || '',
        };

        const result = await fetch('/api/generate/prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!result.ok) {
            const err = await result.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }

        const data = await result.json();
        const prompts = data.prompts || [];

        const previewArea = document.getElementById('gen-prompts-preview');
        if (previewArea && prompts.length) {
            previewArea.style.display = 'block';
            previewArea.innerHTML = `
                <div class="gen-prompts-list">
                    <h4>Select a Prompt</h4>
                    ${prompts.map((p, idx) => `
                        <label class="gen-prompt-option ${idx === 0 ? 'gen-prompt-selected' : ''}" onclick="selectGenPrompt(${idx})">
                            <input type="radio" name="gen-prompt-choice" value="${idx}" ${idx === 0 ? 'checked' : ''} />
                            <div class="gen-prompt-content">
                                <div class="gen-prompt-member">${escapeHtml(p.member_name || p.mode || 'Prompt ' + (idx+1))}</div>
                                <div class="gen-prompt-text">${escapeHtml(p.positive)}</div>
                                ${p.negative ? `<div class="gen-prompt-neg">Negative: ${escapeHtml(p.negative)}</div>` : ''}
                            </div>
                        </label>
                    `).join('')}
                </div>`;
        }
    } catch (err) {
        showToast(`Prompt preview failed: ${err.message}`, true);
    } finally {
        if (previewBtn) { previewBtn.disabled = false; previewBtn.textContent = '👁 Preview Prompts'; }
    }
}

function selectGenPrompt(index) {
    document.querySelectorAll('.gen-prompt-option').forEach((el, i) => {
        el.classList.toggle('gen-prompt-selected', i === index);
    });
}

/**
 * Submit the generation request and connect to SSE progress stream.
 */
async function submitGeneration() {
    const mode = document.getElementById('gen-mode')?.value || 'system';
    const templateId = document.getElementById('gen-template')?.value;
    const stylePreset = document.getElementById('gen-style')?.value || '';
    const width = parseInt(document.getElementById('gen-width')?.value || '1024');
    const height = parseInt(document.getElementById('gen-height')?.value || '1024');
    const seed = parseInt(document.getElementById('gen-seed')?.value || '0');
    const memberName = document.getElementById('gen-member')?.value || '';
    const userPrompt = document.getElementById('gen-user-prompt')?.value || '';

    // For council_vote, get selected prompt index
    let selectedPromptIndex = 0;
    if (mode === 'council_vote') {
        const checked = document.querySelector('input[name="gen-prompt-choice"]:checked');
        if (checked) selectedPromptIndex = parseInt(checked.value);
    }

    // Get participants for council_vote
    let participants = [];
    if (mode === 'council_vote') {
        participants = Array.from(document.querySelectorAll('.gen-participant-cb:checked'))
            .map(cb => cb.value);
        if (participants.length < 2) {
            showToast('Select at least 2 participants.', true);
            return;
        }
    }

    const body = {
        template_id: templateId,
        prompt_mode: mode,
        member_name: memberName,
        user_prompt: userPrompt,
        style_preset_key: stylePreset,
        participants: participants,
        selected_prompt_index: selectedPromptIndex,
        width: width,
        height: height,
        seed: seed,
    };

    const submitBtn = document.getElementById('gen-submit-btn');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '⏳ Starting...'; }

    try {
        const resp = await fetch(`/api/generate/${_generateEntityType}/${encodeURIComponent(_generateEntityId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Generation failed' }));
            throw new Error(err.detail);
        }

        const data = await resp.json();
        _generateActiveJobId = data.job_id;

        // Switch to progress view
        showGenerateProgress();

        // Connect to SSE stream
        connectGenerateSSE(data.job_id);

    } catch (err) {
        showToast(`Generation error: ${err.message}`, true);
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '🎨 Generate'; }
    }
}

/**
 * Switch modal to progress view.
 */
function showGenerateProgress() {
    const body = document.getElementById('gen-modal-body');
    const formElements = body?.querySelectorAll('.gen-form-grid, .filter-group, #gen-mode-fields, #gen-prompts-preview');
    if (formElements) formElements.forEach(el => el.style.display = 'none');

    const progressArea = document.getElementById('gen-progress-area');
    if (progressArea) progressArea.style.display = 'block';

    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-secondary" onclick="cancelGeneration()" id="gen-cancel-btn">Cancel Generation</button>
        `;
    }
}

/**
 * Connect to the SSE progress stream for a generation job.
 */
function connectGenerateSSE(jobId) {
    if (_generateEventSource) {
        _generateEventSource.close();
    }

    const es = new EventSource(`/api/generate/stream/${encodeURIComponent(jobId)}`);
    _generateEventSource = es;

    es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateGenerateProgress(data);
    });

    es.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
        updateGenerateProgress(data);
        es.close();
        _generateEventSource = null;
        onGenerationComplete(data);
    });

    es.addEventListener('error', (e) => {
        try {
            const data = JSON.parse(e.data);
            updateGenerateProgress(data);
        } catch {
            // SSE connection error
        }
        es.close();
        _generateEventSource = null;
        onGenerationError();
    });
}

/**
 * Update progress UI from SSE event data.
 */
function updateGenerateProgress(data) {
    const stageEl = document.getElementById('gen-progress-stage');
    const barEl = document.getElementById('gen-progress-bar');
    const pctEl = document.getElementById('gen-progress-pct');
    const promptsEl = document.getElementById('gen-progress-prompts');

    const stageLabels = {
        'prompt_generating': '🧠 Generating prompt...',
        'template_filling': '📋 Preparing workflow...',
        'queued': '📤 Submitting to ComfyUI...',
        'running': '⚡ ComfyUI is generating...',
        'downloading': '📥 Downloading image...',
        'saving': '💾 Saving image...',
        'completed': '✅ Complete!',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    if (stageEl) stageEl.textContent = stageLabels[data.stage] || data.stage;
    if (barEl) barEl.style.width = `${data.progress_pct || 0}%`;
    if (pctEl) pctEl.textContent = `${data.progress_pct || 0}%`;

    // Show prompts once available
    if (promptsEl && data.prompt_positive && data.stage !== 'prompt_generating') {
        promptsEl.innerHTML = `
            <div class="gen-progress-prompt-text">
                <strong>Prompt:</strong> ${escapeHtml(data.prompt_positive)}
            </div>
            ${data.prompt_negative ? `<div class="gen-progress-prompt-neg">
                <strong>Negative:</strong> ${escapeHtml(data.prompt_negative)}
            </div>` : ''}`;
    }

    if (data.error) {
        if (stageEl) stageEl.textContent = `❌ ${data.error}`;
    }
}

/**
 * Handle successful generation completion.
 */
function onGenerationComplete(data) {
    showToast('Image generated successfully! 🎨');

    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-primary" onclick="closeGenerateModal(); refreshGallery();">Close & View Gallery</button>
        `;
    }

    // Auto-refresh gallery in the background
    refreshGallery();
}

/**
 * Handle generation error.
 */
function onGenerationError() {
    const footer = document.getElementById('gen-modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn btn-secondary" onclick="closeGenerateModal()">Close</button>
            <button class="btn btn-primary" onclick="retryGeneration()">🔄 Retry</button>
        `;
    }
}

/**
 * Cancel an active generation job.
 */
async function cancelGeneration() {
    if (!_generateActiveJobId) return;
    const btn = document.getElementById('gen-cancel-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Cancelling...'; }

    try {
        await fetch(`/api/generate/cancel/${encodeURIComponent(_generateActiveJobId)}`, {
            method: 'POST',
        });
        showToast('Generation cancelled.');
    } catch (err) {
        showToast(`Cancel error: ${err.message}`, true);
    }
}

/**
 * Retry generation by reopening the modal.
 */
function retryGeneration() {
    closeGenerateModal();
    openGenerateModal(_generateEntityType, _generateEntityId);
}


// ═══════════════════════════════════════════════════════════════
// Exploration View (F-040)
// ═══════════════════════════════════════════════════════════════

