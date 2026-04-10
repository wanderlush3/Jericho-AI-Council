async function renderGenerationQueue() {
    showLoading();

    let jobs = [];
    try {
        jobs = await api('/api/generate/jobs');
    } catch { /* pipeline not initialized yet */ }

    // Sort: active first, then by newest
    const stageOrder = { 'queued': 0, 'prompt_generating': 1, 'template_filling': 2, 'running': 3, 'downloading': 4, 'saving': 5, 'completed': 6, 'failed': 7, 'cancelled': 8 };
    jobs.sort((a, b) => {
        const aActive = !['completed', 'failed', 'cancelled'].includes(a.stage);
        const bActive = !['completed', 'failed', 'cancelled'].includes(b.stage);
        if (aActive !== bActive) return bActive ? 1 : -1;
        return (stageOrder[a.stage] || 99) - (stageOrder[b.stage] || 99);
    });

    const stageLabels = {
        'queued': '📤 Queued',
        'prompt_generating': '🧠 Generating Prompt',
        'template_filling': '📋 Preparing Workflow',
        'running': '⚡ Generating',
        'downloading': '📥 Downloading',
        'saving': '💾 Saving',
        'completed': '✅ Completed',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    const jobCards = jobs.length ? jobs.map(job => {
        const isActive = !['completed', 'failed', 'cancelled'].includes(job.stage);
        const stageClass = isActive ? 'queue-card-active' : job.stage === 'completed' ? 'queue-card-done' : 'queue-card-error';
        const pct = job.progress_pct || 0;

        return `
            <div class="queue-card ${stageClass}" id="queue-card-${escapeAttr(job.job_id)}">
                <div class="queue-card-header">
                    <div class="queue-card-id">${escapeHtml(job.job_id)}</div>
                    <div class="queue-card-stage">${stageLabels[job.stage] || job.stage}</div>
                </div>
                <div class="queue-card-entity">
                    ${escapeHtml(job.entity_type || '')} / ${escapeHtml(job.entity_id || '')}
                </div>
                ${job.prompt_mode ? `<div class="queue-card-mode">Mode: ${escapeHtml(job.prompt_mode)}</div>` : ''}
                ${isActive ? `
                    <div class="queue-card-progress">
                        <div class="gen-progress-bar-bg">
                            <div class="gen-progress-bar-fill" style="width:${pct}%"></div>
                        </div>
                        <span class="queue-card-pct">${pct}%</span>
                    </div>
                ` : ''}
                ${job.prompt_positive ? `<div class="queue-card-prompt" title="${escapeAttr(job.prompt_positive)}">${escapeHtml(job.prompt_positive.substring(0, 120))}${job.prompt_positive.length > 120 ? '…' : ''}</div>` : ''}
                ${job.image_id && job.stage === 'completed' ? `<img class="queue-card-thumb" src="/api/images/file/${escapeAttr(job.image_id)}" loading="lazy" />` : ''}
                ${job.error ? `<div class="queue-card-error-msg">${escapeHtml(job.error)}</div>` : ''}
                <div class="queue-card-actions">
                    ${isActive ? `<button class="btn btn-secondary btn-sm" onclick="cancelQueueJob('${escapeAttr(job.job_id)}')">Cancel</button>` : ''}
                    ${job.stage === 'failed' ? `<button class="btn btn-primary btn-sm" onclick="retryQueueJob('${escapeAttr(job.job_id)}', '${escapeAttr(job.entity_type)}', '${escapeAttr(job.entity_id)}')">🔄 Retry</button>` : ''}
                    ${job.stage === 'completed' && job.entity_type && job.entity_id ? `<button class="btn btn-secondary btn-sm" onclick="navigateTo('${escapeAttr(job.entity_type === 'council_member' ? 'council' : job.entity_type + 's')}', '${escapeAttr(job.entity_id)}')">View Entity</button>` : ''}
                </div>
            </div>`;
    }).join('') : '<p style="color:var(--text-muted);text-align:center;padding:var(--space-xl)">No generation jobs yet. Generate an image from any entity\'s detail page.</p>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🎨 Generation Queue</h2>
                <p>Monitor and manage image generation jobs</p>
            </div>
            <div class="queue-grid" id="queue-grid">
                ${jobCards}
            </div>
        </div>`;

    // Start polling if there are active jobs
    startQueuePolling();
}

function startQueuePolling() {
    stopQueuePolling();
    _queuePollTimer = setInterval(async () => {
        // Only poll if we're on the queue view
        if (state.currentView !== 'generation-queue') {
            stopQueuePolling();
            return;
        }
        try {
            const jobs = await api('/api/generate/jobs');
            const hasActive = jobs.some(j => !['completed', 'failed', 'cancelled'].includes(j.stage));
            if (!hasActive) {
                stopQueuePolling();
            }
            // Re-render the queue with fresh data
            await renderGenerationQueue();
        } catch { /* ignore */ }
    }, 3000);
}

function stopQueuePolling() {
    if (_queuePollTimer) {
        clearInterval(_queuePollTimer);
        _queuePollTimer = null;
    }
}

async function cancelQueueJob(jobId) {
    try {
        await fetch(`/api/generate/cancel/${encodeURIComponent(jobId)}`, { method: 'POST' });
        showToast('Job cancelled.');
        await renderGenerationQueue();
    } catch (err) {
        showToast(`Cancel error: ${err.message}`, true);
    }
}

function retryQueueJob(jobId, entityType, entityId) {
    if (entityType && entityId) {
        openGenerateModal(entityType, entityId);
    }
}


// ═══════════════════════════════════════════════════════════════
// Custom Style Preset Editor (F-037g)
// ═══════════════════════════════════════════════════════════════

