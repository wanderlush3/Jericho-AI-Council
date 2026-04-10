async function renderPresetEditor() {
    let builtins = [];
    let customs = [];
    try {
        const all = await api('/api/settings/comfyui/style-presets');
        builtins = all.filter(p => p.is_builtin);
        customs = all.filter(p => !p.is_builtin);
    } catch { /* no presets */ }

    const builtinCards = builtins.map(p => `
        <div class="preset-card preset-card-builtin">
            <div class="preset-card-header">
                <strong>${escapeHtml(p.name)}</strong>
                <span class="preset-badge preset-badge-builtin">Built-in</span>
            </div>
            <div class="preset-card-desc">${escapeHtml(p.description || 'No description')}</div>
            <div class="preset-card-detail"><strong>Positive:</strong> ${escapeHtml(p.positive_suffix || '—')}</div>
            <div class="preset-card-detail"><strong>Negative:</strong> ${escapeHtml(p.negative_prefix || '—')}</div>
            <div class="preset-card-key">Key: <code>${escapeHtml(p.key)}</code></div>
        </div>
    `).join('');

    const customCards = customs.length ? customs.map(p => `
        <div class="preset-card preset-card-custom">
            <div class="preset-card-header">
                <strong>${escapeHtml(p.name)}</strong>
                <span class="preset-badge preset-badge-custom">Custom</span>
            </div>
            <div class="preset-card-desc">${escapeHtml(p.description || 'No description')}</div>
            <div class="preset-card-detail"><strong>Positive:</strong> ${escapeHtml(p.positive_suffix || '—')}</div>
            <div class="preset-card-detail"><strong>Negative:</strong> ${escapeHtml(p.negative_prefix || '—')}</div>
            <div class="preset-card-key">Key: <code>${escapeHtml(p.key)}</code> | ID: <code>${escapeHtml(p.id)}</code></div>
            <div class="preset-card-actions">
                <button class="btn btn-secondary btn-sm" onclick="editCustomPreset('${escapeAttr(p.id)}')">✏️ Edit</button>
                <button class="btn btn-secondary btn-sm" onclick="deleteCustomPreset('${escapeAttr(p.id)}', '${escapeAttr(p.name)}')">🗑️ Delete</button>
            </div>
        </div>
    `).join('') : '<p style="color:var(--text-muted)">No custom presets yet.</p>';

    return `
        <div class="card" style="margin-top:var(--space-lg)">
            <h3>🎨 Style Preset Editor</h3>
            <p style="color:var(--text-muted);margin-bottom:var(--space-md)">
                Create custom style presets that modify how AI generates image prompts.
            </p>

            <div class="preset-editor-actions" style="display:flex;gap:var(--space-sm);margin-bottom:var(--space-md);flex-wrap:wrap">
                <button class="btn btn-primary btn-sm" onclick="openCreatePresetModal()">➕ Create Preset</button>
                <button class="btn btn-secondary btn-sm" onclick="exportPresets()">📤 Export All</button>
                <button class="btn btn-secondary btn-sm" onclick="importPresetsDialog()">📥 Import</button>
            </div>

            <h4 style="margin-bottom:var(--space-sm)">Custom Presets</h4>
            <div class="preset-grid" id="custom-presets-grid">
                ${customCards}
            </div>

            <h4 style="margin-top:var(--space-lg);margin-bottom:var(--space-sm)">Built-in Presets <span style="color:var(--text-muted);font-size:0.78rem">(read-only)</span></h4>
            <div class="preset-grid" id="builtin-presets-grid">
                ${builtinCards}
            </div>
        </div>`;
}

function openCreatePresetModal() {
    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'preset-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:560px">
            <div class="gen-modal-header">
                <h3>➕ Create Custom Preset</h3>
                <button class="detail-close" onclick="closePresetModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="gen-form-grid">
                    <div class="filter-group">
                        <label for="preset-key">Key <span style="color:var(--text-muted);font-size:0.72rem">(unique, lowercase)</span></label>
                        <input id="preset-key" class="settings-input" placeholder="e.g. cyberpunk" oninput="updatePresetPreview()" />
                    </div>
                    <div class="filter-group">
                        <label for="preset-name">Display Name</label>
                        <input id="preset-name" class="settings-input" placeholder="e.g. Cyberpunk" oninput="updatePresetPreview()" />
                    </div>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-desc">Description</label>
                    <input id="preset-desc" class="settings-input" placeholder="Brief description of the style" />
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-positive">Positive Suffix <span style="color:var(--text-muted);font-size:0.72rem">(appended to positive prompts)</span></label>
                    <textarea id="preset-positive" class="settings-input proposal-textarea" rows="2" placeholder="e.g. cyberpunk, neon lights, rain, futuristic" oninput="updatePresetPreview()"></textarea>
                </div>
                <div class="filter-group" style="margin-top:var(--space-sm)">
                    <label for="preset-negative">Negative Prefix <span style="color:var(--text-muted);font-size:0.72rem">(prepended to negative prompts)</span></label>
                    <textarea id="preset-negative" class="settings-input proposal-textarea" rows="2" placeholder="e.g. nature, medieval, fantasy, bright daylight" oninput="updatePresetPreview()"></textarea>
                </div>

                <div class="preset-preview" id="preset-preview" style="margin-top:var(--space-md)">
                    <h4>Live Preview</h4>
                    <div class="preset-preview-box">
                        <div id="preset-preview-positive"><strong>Positive:</strong> <em style="color:var(--text-muted)">Enter suffix above…</em></div>
                        <div id="preset-preview-negative"><strong>Negative:</strong> <em style="color:var(--text-muted)">Enter prefix above…</em></div>
                    </div>
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closePresetModal()">Cancel</button>
                <button class="btn btn-primary" id="preset-save-btn" onclick="saveCustomPreset()">💾 Save Preset</button>
            </div>
        </div>`;
    modal.addEventListener('click', (e) => { if (e.target === modal) closePresetModal(); });
    document.body.appendChild(modal);
}

function closePresetModal() {
    const m = document.getElementById('preset-modal-overlay');
    if (m) m.remove();
}

function updatePresetPreview() {
    const positive = document.getElementById('preset-positive')?.value || '';
    const negative = document.getElementById('preset-negative')?.value || '';

    const samplePrompt = 'a noble knight standing in a castle courtyard';
    const previewPos = positive ? `${samplePrompt}, <strong style="color:var(--accent)">${escapeHtml(positive)}</strong>` : `${samplePrompt}`;
    const previewNeg = negative ? `<strong style="color:var(--accent)">${escapeHtml(negative)}</strong>, blurry, low quality` : 'blurry, low quality';

    const posEl = document.getElementById('preset-preview-positive');
    const negEl = document.getElementById('preset-preview-negative');
    if (posEl) posEl.innerHTML = `<strong>Positive:</strong> ${previewPos}`;
    if (negEl) negEl.innerHTML = `<strong>Negative:</strong> ${previewNeg}`;
}

async function saveCustomPreset(presetId) {
    const key = document.getElementById('preset-key')?.value || '';
    const name = document.getElementById('preset-name')?.value || '';
    const description = document.getElementById('preset-desc')?.value || '';
    const positive_suffix = document.getElementById('preset-positive')?.value || '';
    const negative_prefix = document.getElementById('preset-negative')?.value || '';

    if (!key.trim() || !name.trim()) {
        showToast('Key and name are required.', true);
        return;
    }

    const btn = document.getElementById('preset-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Saving…'; }

    try {
        const url = presetId
            ? `/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`
            : '/api/settings/comfyui/presets';
        const method = presetId ? 'PUT' : 'POST';

        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, name, description, positive_suffix, negative_prefix }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Save failed' }));
            throw new Error(err.detail);
        }
        showToast(`Preset "${name}" saved ✅`);
        closePresetModal();
        // Refresh the settings page to show the new preset
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💾 Save Preset'; }
    }
}

async function editCustomPreset(presetId) {
    let preset;
    try {
        preset = await api(`/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`);
    } catch {
        showToast('Failed to load preset.', true);
        return;
    }

    openCreatePresetModal();
    // Wait for DOM then populate
    setTimeout(() => {
        const keyEl = document.getElementById('preset-key');
        const nameEl = document.getElementById('preset-name');
        const descEl = document.getElementById('preset-desc');
        const posEl = document.getElementById('preset-positive');
        const negEl = document.getElementById('preset-negative');
        const saveBtn = document.getElementById('preset-save-btn');
        const header = document.querySelector('#preset-modal-overlay .gen-modal-header h3');

        if (keyEl) { keyEl.value = preset.key || ''; keyEl.disabled = true; }
        if (nameEl) nameEl.value = preset.name || '';
        if (descEl) descEl.value = preset.description || '';
        if (posEl) posEl.value = preset.positive_suffix || '';
        if (negEl) negEl.value = preset.negative_prefix || '';
        if (header) header.textContent = `✏️ Edit Preset — ${preset.name}`;
        if (saveBtn) {
            saveBtn.onclick = () => saveCustomPreset(presetId);
            saveBtn.textContent = '💾 Update Preset';
        }
        updatePresetPreview();
    }, 50);
}

async function deleteCustomPreset(presetId, presetName) {
    if (!confirm(`Delete custom preset "${presetName}"?`)) return;
    try {
        const resp = await fetch(`/api/settings/comfyui/presets/${encodeURIComponent(presetId)}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('Delete failed');
        showToast(`Preset "${presetName}" deleted 🗑️`);
        await renderSettings();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function exportPresets() {
    try {
        const data = await api('/api/settings/comfyui/presets/export');
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'jericho_style_presets.json';
        a.click();
        URL.revokeObjectURL(url);
        showToast('Presets exported 📤');
    } catch (err) {
        showToast(`Export error: ${err.message}`, true);
    }
}

function importPresetsDialog() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const text = await file.text();
            const presetsData = JSON.parse(text);
            const payload = Array.isArray(presetsData) ? presetsData : [presetsData];
            const resp = await fetch('/api/settings/comfyui/presets/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ presets: payload }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Import failed' }));
                throw new Error(err.detail);
            }
            const result = await resp.json();
            showToast(`Imported ${result.imported_count} preset(s) 📥`);
            await renderSettings();
        } catch (err) {
            showToast(`Import error: ${err.message}`, true);
        }
    };
    input.click();
}


// ═══════════════════════════════════════════════════════════════
// Batch Generation Modal (F-037g)
// ═══════════════════════════════════════════════════════════════

