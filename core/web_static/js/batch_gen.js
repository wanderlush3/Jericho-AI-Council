async function openBatchGenerateModal(entityType) {
    let entities = [];
    try {
        if (entityType === 'character') entities = await api('/api/characters');
        else if (entityType === 'location') entities = await api('/api/locations');
        else if (entityType === 'item') entities = await api('/api/items');
        else if (entityType === 'store') entities = await api('/api/stores');
    } catch { /* no entities */ }

    if (!entities.length) {
        showToast(`No ${entityType}s found.`, true);
        return;
    }

    let templates = [];
    let presets = [];
    try { templates = await api('/api/settings/comfyui/templates'); } catch {}
    try { presets = await api('/api/settings/comfyui/style-presets'); } catch {}

    if (!templates.length) {
        showToast('No ComfyUI workflow templates found. Add one in Settings → ComfyUI first.', true);
        return;
    }

    const templateOptions = templates.map(t =>
        `<option value="${escapeAttr(t.id)}">${escapeHtml(t.name || t.id)}</option>`
    ).join('');

    const presetOptions = ['<option value="">None (default)</option>'].concat(
        presets.map(p => `<option value="${escapeAttr(p.key)}">${escapeHtml(p.name || p.key)}</option>`)
    ).join('');

    const entityIdKey = entityType === 'council_member' ? 'name' : 'id';
    const entityCheckboxes = entities.slice(0, 20).map(e => `
        <label class="gen-participant-label">
            <input type="checkbox" class="batch-entity-cb" value="${escapeAttr(e[entityIdKey])}" />
            ${escapeHtml(e.name || e[entityIdKey])}
        </label>
    `).join('');

    const modal = document.createElement('div');
    modal.className = 'gen-modal-overlay';
    modal.id = 'batch-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:600px">
            <div class="gen-modal-header">
                <h3>🎨 Batch Generate — ${escapeHtml(entityType)}s</h3>
                <button class="detail-close" onclick="closeBatchModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="filter-group">
                    <label>Select Entities <span style="color:var(--text-muted);font-size:0.72rem">(max 10)</span></label>
                    <div class="gen-participants-grid" id="batch-entities">
                        ${entityCheckboxes}
                    </div>
                </div>
                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="batch-template">Workflow Template</label>
                        <select id="batch-template" class="settings-input">${templateOptions}</select>
                    </div>
                    <div class="filter-group">
                        <label for="batch-style">Style Preset</label>
                        <select id="batch-style" class="settings-input">${presetOptions}</select>
                    </div>
                </div>
                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="batch-width">Width</label>
                        <input id="batch-width" class="settings-input" type="number" value="1024" min="64" max="4096" step="64" />
                    </div>
                    <div class="filter-group">
                        <label for="batch-height">Height</label>
                        <input id="batch-height" class="settings-input" type="number" value="1024" min="64" max="4096" step="64" />
                    </div>
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeBatchModal()">Cancel</button>
                <button class="btn btn-primary" id="batch-submit-btn" onclick="submitBatchGeneration('${escapeAttr(entityType)}')">
                    🎨 Generate Batch
                </button>
            </div>
        </div>`;
    modal.addEventListener('click', (e) => { if (e.target === modal) closeBatchModal(); });
    document.body.appendChild(modal);
}

function closeBatchModal() {
    const m = document.getElementById('batch-modal-overlay');
    if (m) m.remove();
}

async function submitBatchGeneration(entityType) {
    const selected = Array.from(document.querySelectorAll('.batch-entity-cb:checked')).map(cb => cb.value);

    if (!selected.length) {
        showToast('Select at least one entity.', true);
        return;
    }
    if (selected.length > 10) {
        showToast('Maximum 10 entities per batch.', true);
        return;
    }

    const btn = document.getElementById('batch-submit-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Queuing…'; }

    const body = {
        entity_type: entityType,
        entity_ids: selected,
        template_id: document.getElementById('batch-template')?.value || '',
        prompt_mode: 'system',
        style_preset_key: document.getElementById('batch-style')?.value || '',
        width: parseInt(document.getElementById('batch-width')?.value || '1024'),
        height: parseInt(document.getElementById('batch-height')?.value || '1024'),
        seed: 0,
    };

    try {
        const resp = await fetch('/api/generate/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Batch failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Queued ${data.count} generation job(s) 🎨`);
        closeBatchModal();
        navigateTo('generation-queue');
    } catch (err) {
        showToast(`Batch error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '🎨 Generate Batch'; }
    }
}


// ═══════════════════════════════════════════════════════════════
// Generation Completion Toast Poller (F-037g)
// ═══════════════════════════════════════════════════════════════

let _genToastPollTimer = null;
let _genToastKnownJobs = new Set();

function startGenToastPoller() {
    if (_genToastPollTimer) return;
    _genToastPollTimer = setInterval(async () => {
        try {
            const jobs = await api('/api/generate/jobs');
            for (const job of jobs) {
                if (_genToastKnownJobs.has(job.job_id)) continue;
                if (job.stage === 'completed') {
                    _genToastKnownJobs.add(job.job_id);
                    showToast(`🎨 Image generated for ${job.entity_type}/${job.entity_id}!`);
                } else if (job.stage === 'failed') {
                    _genToastKnownJobs.add(job.job_id);
                    showToast(`❌ Generation failed for ${job.entity_type}/${job.entity_id}`, true);
                } else if (['cancelled', 'queued', 'prompt_generating', 'template_filling', 'running', 'downloading', 'saving'].includes(job.stage)) {
                    // Track active jobs so we can detect transitions
                }
            }
        } catch { /* ignore */ }
    }, 5000);
}

// ═══════════════════════════════════════════════════════════════
// Stories View (F-041)
// ═══════════════════════════════════════════════════════════════

const STORY_STATUS_COLORS = {
    draft: 'amber', active: 'emerald', completed: 'blue', archived: 'text-muted',
};

const MOOD_OPTIONS = [
    'tense', 'joyful', 'melancholic', 'mysterious', 'peaceful', 'dramatic',
    'ominous', 'hopeful', 'chaotic', 'romantic', 'eerie', 'triumphant',
];

