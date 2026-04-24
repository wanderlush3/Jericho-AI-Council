async function renderStories() {
    showLoading();
    let stories = [];
    try { stories = await api('/api/stories'); } catch (e) { showError(e.message); return; }

    const statusTabs = ['all', 'draft', 'active', 'completed', 'archived'];
    const tabsHtml = statusTabs.map(s => {
        const cls = s === 'all' ? 'active' : '';
        return `<button class="story-filter-tab ${cls}" data-filter="${s}" onclick="filterStories('${s}')">${s}</button>`;
    }).join('');

    const cardsHtml = stories.length ? stories.map(s => `
        <div class="card card-clickable story-card" data-status="${s.status}" onclick="navigateTo('stories','${s.story_id}')">
            <div class="story-card-header">
                <div class="story-card-title">${escapeHtml(s.title)}</div>
                <span class="badge badge-${STORY_STATUS_COLORS[s.status] || 'default'}">${s.status}</span>
            </div>
            <div class="story-card-synopsis">${escapeHtml(truncate(s.synopsis, 120))}</div>
            <div class="story-card-meta">
                ${s.author ? `<span class="story-meta-chip">✍️ ${escapeHtml(s.author)}</span>` : ''}
                <span class="story-meta-chip">📑 ${s.chapter_count} ch</span>
                <span class="story-meta-chip">🎬 ${s.scene_count} scenes</span>
                <span class="story-meta-chip">🖼️ ${s.illustration_count} illus</span>
            </div>
            <div class="story-card-date">${formatDate(s.updated_at || s.created_at)}</div>
        </div>`).join('') : '<div class="empty-state"><div class="empty-icon">📖</div><p>No stories yet. Create your first illustrated story!</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>📖 Stories</h2>
                    <p>LLM-narrated illustrated stories from your world</p>
                </div>
                <button class="btn btn-primary" onclick="openCreateStoryModal()" id="btn-create-story">✨ New Story</button>
            </div>
            <div class="story-filter-bar">${tabsHtml}</div>
            <div class="story-grid" id="story-grid">${cardsHtml}</div>
        </div>`;
}

function filterStories(status) {
    document.querySelectorAll('.story-filter-tab').forEach(t => t.classList.toggle('active', t.dataset.filter === status));
    document.querySelectorAll('.story-card').forEach(c => {
        c.style.display = (status === 'all' || c.dataset.status === status) ? '' : 'none';
    });
}

function openCreateStoryModal() {
    const existing = document.getElementById('story-modal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'story-modal';
    modal.className = 'gen-modal-overlay story-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:560px">
            <div class="gen-modal-header story-modal-header">
                <h3>✨ Create New Story</h3>
                <button class="detail-close" onclick="closeStoryModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="filter-group">
                    <label for="story-title">Title *</label>
                    <input type="text" id="story-title" class="settings-input" placeholder="The Fall of Ironhaven" />
                </div>
                <div class="filter-group">
                    <label for="story-synopsis">Synopsis</label>
                    <textarea id="story-synopsis" class="settings-input settings-textarea" rows="3"
                              placeholder="A tale of betrayal, courage, and the quest for redemption…"></textarea>
                </div>
                <div class="filter-group">
                    <label for="story-author">Author</label>
                    <input type="text" id="story-author" class="settings-input" placeholder="Your name" />
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeStoryModal()">Cancel</button>
                <button class="btn btn-primary" onclick="submitCreateStory()" id="btn-submit-story">✨ Create Story</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) closeStoryModal(); });
    document.getElementById('story-title')?.focus();
}

function closeStoryModal() {
    const m = document.getElementById('story-modal');
    if (m) m.remove();
}

async function submitCreateStory() {
    const title = (document.getElementById('story-title')?.value || '').trim();
    if (!title) { showToast('Title is required.', true); return; }
    const btn = document.getElementById('btn-submit-story');
    if (btn) { btn.disabled = true; btn.textContent = 'Creating…'; }
    try {
        const resp = await fetch('/api/stories', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title,
                synopsis: (document.getElementById('story-synopsis')?.value || '').trim(),
                author: (document.getElementById('story-author')?.value || '').trim(),
            }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        const story = await resp.json();
        showToast(`📖 Story "${story.title}" created!`);
        closeStoryModal();
        navigateTo('stories', story.story_id);
    } catch (err) {
        showToast('Error: ' + err.message, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Create Story'; }
    }
}

// ─── Story Detail ───────────────────────────────────────────

async function renderStoryDetail(storyId) {
    // Check for reader mode
    if (storyId.endsWith('/read')) {
        return renderStoryReader(storyId.replace('/read', ''));
    }
    showLoading();
    let story;
    try { story = await api(`/api/stories/${storyId}`); } catch (e) { showError(e.message); return; }

    // Restore saved participant selections from story metadata
    const savedParticipants = (story.metadata && story.metadata.participants) || [];
    window._storyParticipants = savedParticipants;

    const statusBadge = `<span class="badge badge-${STORY_STATUS_COLORS[story.status] || 'default'}">${story.status}</span>`;

    const chaptersHtml = story.chapters.length ? story.chapters.map(ch => {
        const scenesHtml = (ch.scenes || []).map(sc => {
            const hasImage = sc.image_id && sc.image_url;
            const hasText = sc.narrative_text;
            return `
            <div class="story-scene-item" id="scene-${sc.scene_id}">
                <div class="story-scene-header">
                    <span class="story-scene-num">Scene ${sc.scene_number}</span>
                    ${sc.mood ? `<span class="story-mood-badge">${sc.mood}</span>` : ''}
                    <div class="story-scene-actions">
                        <button class="btn btn-sm" onclick="narrateScene('${storyId}','${ch.chapter_id}','${sc.scene_id}')" title="Generate narration">✍️ Narrate</button>
                        <button class="btn btn-sm" onclick="illustrateScene('${storyId}','${ch.chapter_id}','${sc.scene_id}')" title="Generate illustration">🎨 Illustrate</button>
                        <button class="btn btn-sm" onclick="initStoryChat('${storyId}','${ch.chapter_id}','${sc.scene_id}')" title="Start story discussion">💬 Chat</button>
                        <button class="btn btn-sm btn-danger-subtle" onclick="deleteScene('${storyId}','${ch.chapter_id}','${sc.scene_id}')" title="Delete scene">🗑️</button>
                    </div>
                </div>
                ${sc.characters?.length ? `<div class="story-scene-entities">${sc.characters.map(c => `<span class="story-entity-chip">🎭 ${c}</span>`).join('')}${sc.location_id ? `<span class="story-entity-chip">📍 ${sc.location_id}</span>` : ''}</div>` : ''}
                <div class="story-scene-body">
                    ${hasImage ? `<div class="story-scene-illustration"><img src="${sc.image_url}" alt="Scene illustration" onclick="openStoryLightbox('${sc.image_url}')" /></div>` : ''}
                    ${hasText ? `<div class="story-scene-narrative">${escapeHtml(sc.narrative_text)}</div>` : '<div class="story-scene-empty">No narration yet. Click ✍️ Narrate to generate.</div>'}
                </div>
                <div id="story-chat-${sc.scene_id}"></div>
            </div>`;
        }).join('');

        return `
        <div class="story-chapter-block" id="chapter-${ch.chapter_id}">
            <div class="story-chapter-header">
                <div class="story-chapter-title-row">
                    <h3>Chapter ${ch.chapter_number}: ${escapeHtml(ch.title || 'Untitled')}</h3>
                    <div class="story-chapter-actions">
                        <button class="btn btn-sm" onclick="addSceneToChapter('${storyId}','${ch.chapter_id}')" title="Add scene">➕ Scene</button>
                        <button class="btn btn-sm" onclick="editChapter('${storyId}','${ch.chapter_id}','${escapeAttr(ch.title)}','${escapeAttr(ch.synopsis)}')" title="Edit chapter">✏️</button>
                        <button class="btn btn-sm btn-danger-subtle" onclick="deleteChapter('${storyId}','${ch.chapter_id}')" title="Delete chapter">🗑️</button>
                    </div>
                </div>
                ${ch.synopsis ? `<div class="story-chapter-synopsis">${escapeHtml(ch.synopsis)}</div>` : ''}
            </div>
            <div class="story-scenes-list">${scenesHtml || '<div class="story-scene-empty">No scenes yet. Click ➕ Scene to add one.</div>'}</div>
        </div>`;
    }).join('') : '<div class="empty-state" style="padding:2rem"><div class="empty-icon">📑</div><p>No chapters yet. Add one to start building your story.</p></div>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="story-detail-header">
                <div class="story-detail-nav">
                    <button class="btn btn-ghost" onclick="navigateTo('stories')">← Stories</button>
                    <button class="btn btn-primary" onclick="navigateTo('stories','${storyId}/read')">📖 Read Mode</button>
                </div>
                <div class="story-detail-title-row">
                    <div>
                        <h2>${escapeHtml(story.title)}</h2>
                        ${story.synopsis ? `<p class="story-detail-synopsis">${escapeHtml(story.synopsis)}</p>` : ''}
                    </div>
                    <div class="story-detail-actions">
                        ${statusBadge}
                        <button class="btn btn-sm" onclick="editStory('${storyId}')" title="Edit story">✏️ Edit</button>
                        <select class="settings-input form-input-sm" onchange="changeStoryStatus('${storyId}', this.value)" id="story-status-select">
                            <option value="">Status…</option>
                            ${['draft','active','completed','archived'].map(s => `<option value="${s}" ${s === story.status ? 'disabled' : ''}>${s}</option>`).join('')}
                        </select>
                        <button class="btn btn-sm btn-danger-subtle" onclick="deleteStory('${storyId}')" title="Delete story">🗑️</button>
                    </div>
                </div>
                <div class="story-detail-meta">
                    ${story.author ? `<span class="story-meta-chip">✍️ ${escapeHtml(story.author)}</span>` : ''}
                    <span class="story-meta-chip">📑 ${story.chapters.length} chapters</span>
                    <span class="story-meta-chip">🎬 ${story.chapters.reduce((a,c) => a + (c.scenes?.length || 0), 0)} scenes</span>
                    <span class="story-meta-chip">Updated ${formatDate(story.updated_at)}</span>
                </div>
            </div>

            <!-- F-043: Participant Selector -->
            <div class="story-participant-panel" id="story-participant-panel">
                <div class="participant-header" onclick="toggleStoryParticipants()">
                    <span class="participant-header-label">👥 Participants</span>
                    <span class="participant-counter" id="story-part-counter">0/10</span>
                    <span class="participant-chevron" id="story-part-chevron">▸</span>
                </div>
                <div class="participant-body" id="story-part-body" style="display:none">
                    <div class="participant-search">
                        <input type="text" class="settings-input" id="story-part-search"
                               placeholder="Search participants…" oninput="filterStoryParticipants()" />
                    </div>
                    <div class="participant-list" id="story-part-list">
                        <div style="color:var(--text-muted);padding:0.5rem">Loading…</div>
                    </div>
                </div>
            </div>

            <div class="story-add-chapter-bar">
                <button class="btn btn-primary" onclick="addChapter('${storyId}')">➕ Add Chapter</button>
            </div>

            <div class="story-chapters-container">${chaptersHtml}</div>
        </div>`;

    // F-043: Load available participants
    loadStoryParticipants();

    // Load active story chat if exists
    _loadActiveStoryChat(storyId);
}

// ─── Story Reader (Immersive Read Mode) ─────────────────────

async function renderStoryReader(storyId) {
    showLoading();
    let story;
    try { story = await api(`/api/stories/${storyId}`); } catch (e) { showError(e.message); return; }

    let contentHtml = '';

    story.chapters.forEach(ch => {
        contentHtml += `
            <div class="reader-chapter">
                <h2 class="reader-chapter-title">Chapter ${ch.chapter_number}</h2>
                <h3 class="reader-chapter-subtitle">${escapeHtml(ch.title || '')}</h3>
                ${ch.synopsis ? `<p class="reader-chapter-synopsis">${escapeHtml(ch.synopsis)}</p>` : ''}
                <div class="reader-chapter-divider"></div>`;

        (ch.scenes || []).forEach(sc => {
            const hasImage = sc.image_id && sc.image_url;
            contentHtml += `<div class="reader-scene">`;
            if (hasImage) {
                contentHtml += `<figure class="reader-illustration">
                    <img src="${sc.image_url}" alt="Scene illustration" onclick="openStoryLightbox('${sc.image_url}')" />
                </figure>`;
            }
            if (sc.narrative_text) {
                const paragraphs = sc.narrative_text.split('\n').filter(p => p.trim()).map(p => `<p>${escapeHtml(p)}</p>`).join('');
                contentHtml += `<div class="reader-narrative">${paragraphs}</div>`;
            }
            contentHtml += `</div>`;
        });

        contentHtml += `</div>`;
    });

    if (!story.chapters.length) {
        contentHtml = '<div class="reader-empty"><p>This story has no chapters yet.</p></div>';
    }

    $main().innerHTML = `
        <div class="view-enter">
            <div class="reader-container">
                <div class="reader-toolbar">
                    <button class="btn btn-ghost" onclick="navigateTo('stories','${storyId}')">← Back to Editor</button>
                    <span class="reader-title-bar">${escapeHtml(story.title)}</span>
                </div>
                <article class="reader-content">
                    <header class="reader-header">
                        <h1 class="reader-story-title">${escapeHtml(story.title)}</h1>
                        ${story.author ? `<p class="reader-author">by ${escapeHtml(story.author)}</p>` : ''}
                        ${story.synopsis ? `<p class="reader-synopsis">${escapeHtml(story.synopsis)}</p>` : ''}
                    </header>
                    ${contentHtml}
                </article>
            </div>
        </div>`;
}

// ─── Story CRUD Actions ────────────────────────────────────

async function addChapter(storyId) {
    const title = prompt('Chapter title (or leave blank):') ?? '';
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title: title.trim() }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('📑 Chapter added!');
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function editChapter(storyId, chapterId, currentTitle, currentSynopsis) {
    const newTitle = prompt('Chapter title:', currentTitle);
    if (newTitle === null) return;
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title: newTitle.trim() }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('✏️ Chapter updated!');
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function deleteChapter(storyId, chapterId) {
    if (!confirm('Delete this chapter and all its scenes?')) return;
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}`, { method: 'DELETE' });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('🗑️ Chapter deleted.');
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function addSceneToChapter(storyId, chapterId) {
    const moodPicker = MOOD_OPTIONS.map(m => `<option value="${m}">${m}</option>`).join('');
    const existing = document.getElementById('story-modal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'story-modal';
    modal.className = 'gen-modal-overlay story-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:520px">
            <div class="gen-modal-header story-modal-header">
                <h3>🎬 Add Scene</h3>
                <button class="detail-close" onclick="closeStoryModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="filter-group">
                    <label for="scene-mood">Mood</label>
                    <select id="scene-mood" class="settings-input"><option value="">Select mood…</option>${moodPicker}</select>
                </div>
                <div class="gen-form-grid" style="margin-top:var(--space-sm)">
                    <div class="filter-group">
                        <label for="scene-location">Location ID</label>
                        <input type="text" id="scene-location" class="settings-input" placeholder="LOC-0001 (optional)" />
                    </div>
                    <div class="filter-group">
                        <label for="scene-characters">Character IDs</label>
                        <input type="text" id="scene-characters" class="settings-input" placeholder="CH-0001, CH-0002" />
                    </div>
                </div>
                <div class="settings-field-hint" style="margin-top:var(--space-xs)">Comma-separated character IDs. Leave blank for scenery-only scenes.</div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeStoryModal()">Cancel</button>
                <button class="btn btn-primary" onclick="submitAddScene('${storyId}','${chapterId}')">🎬 Add Scene</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) closeStoryModal(); });
}

async function submitAddScene(storyId, chapterId) {
    const mood = document.getElementById('scene-mood')?.value || '';
    const locationId = (document.getElementById('scene-location')?.value || '').trim();
    const charsRaw = (document.getElementById('scene-characters')?.value || '').trim();
    const characters = charsRaw ? charsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}/scenes`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ mood, location_id: locationId, characters }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('🎬 Scene added!');
        closeStoryModal();
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function deleteScene(storyId, chapterId, sceneId) {
    if (!confirm('Delete this scene?')) return;
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}/scenes/${sceneId}`, { method: 'DELETE' });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('🗑️ Scene deleted.');
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function narrateScene(storyId, chapterId, sceneId) {
    const sceneEl = document.getElementById(`scene-${sceneId}`);
    if (sceneEl) {
        const narrateBtn = sceneEl.querySelector('button[onclick*="narrateScene"]');
        if (narrateBtn) { narrateBtn.disabled = true; narrateBtn.textContent = '⏳ Narrating…'; }
    }
    // F-043: Include selected participants
    const participants = getSelectedStoryParticipants();
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}/scenes/${sceneId}/narrate`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ participants }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Narration failed'); }
        const result = await resp.json();
        showToast(`✍️ Narration generated! (${result.model})`);

        // If participants are selected and no active chat, create one and inject narration
        if (participants.length > 0 && !window._storyChatId) {
            await _initStoryChatWithNarration(storyId, chapterId, sceneId, result.narrative_text, participants);
        }

        renderStoryDetail(storyId);
    } catch (err) {
        showToast('Narration error: ' + err.message, true);
        renderStoryDetail(storyId);
    }
}

async function illustrateScene(storyId, chapterId, sceneId) {
    const sceneEl = document.getElementById(`scene-${sceneId}`);
    if (sceneEl) {
        const illustrateBtn = sceneEl.querySelector('button[onclick*="illustrateScene"]');
        if (illustrateBtn) { illustrateBtn.disabled = true; illustrateBtn.textContent = '⏳ Generating…'; }
    }
    // F-043: Include selected participants
    const participants = getSelectedStoryParticipants();
    try {
        const resp = await fetch(`/api/stories/${storyId}/chapters/${chapterId}/scenes/${sceneId}/illustrate`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ participants }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Illustration failed'); }
        const result = await resp.json();
        showToast(`🎨 Illustration queued! Job: ${result.job_id}`);

        // Poll job status until completion, then refresh the view
        _pollIllustrationJob(result.job_id, storyId, sceneId);
    } catch (err) {
        showToast('Illustration error: ' + err.message, true);
        renderStoryDetail(storyId);
    }
}

function _pollIllustrationJob(jobId, storyId, sceneId) {
    const POLL_INTERVAL = 3000;
    const MAX_POLLS = 200; // ~10 min max
    let polls = 0;
    const timer = setInterval(async () => {
        polls++;
        if (polls > MAX_POLLS) {
            clearInterval(timer);
            showToast('Illustration timed out — check Generation Queue.', true);
            return;
        }
        try {
            const job = await api(`/api/generate/jobs/${jobId}`);
            // Update the button text with progress if scene element still exists
            const sceneEl = document.getElementById(`scene-${sceneId}`);
            if (sceneEl) {
                const btn = sceneEl.querySelector('button[onclick*="illustrateScene"]');
                if (btn) btn.textContent = `⏳ ${job.progress_pct || 0}%`;
            }
            if (job.stage === 'completed') {
                clearInterval(timer);
                showToast(`🎨 Illustration complete!`);
                renderStoryDetail(storyId);
            } else if (job.stage === 'failed' || job.stage === 'cancelled') {
                clearInterval(timer);
                showToast(`❌ Illustration ${job.stage}: ${job.error || 'Unknown error'}`, true);
                renderStoryDetail(storyId);
            }
        } catch {
            // If polling fails (e.g. page navigated away), stop silently
            clearInterval(timer);
        }
    }, POLL_INTERVAL);
}

async function editStory(storyId) {
    let story;
    try { story = await api(`/api/stories/${storyId}`); } catch (e) { showToast(e.message, true); return; }

    const existing = document.getElementById('story-modal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'story-modal';
    modal.className = 'gen-modal-overlay story-modal-overlay';
    modal.innerHTML = `
        <div class="gen-modal" style="max-width:560px">
            <div class="gen-modal-header story-modal-header">
                <h3>✏️ Edit Story</h3>
                <button class="detail-close" onclick="closeStoryModal()">✕</button>
            </div>
            <div class="gen-modal-body">
                <div class="filter-group">
                    <label for="edit-story-title">Title *</label>
                    <input type="text" id="edit-story-title" class="settings-input" value="${escapeAttr(story.title)}" />
                </div>
                <div class="filter-group">
                    <label for="edit-story-synopsis">Synopsis</label>
                    <textarea id="edit-story-synopsis" class="settings-input settings-textarea" rows="3">${escapeHtml(story.synopsis || '')}</textarea>
                </div>
                <div class="filter-group">
                    <label for="edit-story-author">Author</label>
                    <input type="text" id="edit-story-author" class="settings-input" value="${escapeAttr(story.author || '')}" />
                </div>
            </div>
            <div class="gen-modal-footer">
                <button class="btn btn-secondary" onclick="closeStoryModal()">Cancel</button>
                <button class="btn btn-primary" onclick="submitEditStory('${storyId}')">💾 Save Changes</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) closeStoryModal(); });
}

async function submitEditStory(storyId) {
    const title = (document.getElementById('edit-story-title')?.value || '').trim();
    if (!title) { showToast('Title is required.', true); return; }
    try {
        const resp = await fetch(`/api/stories/${storyId}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title,
                synopsis: (document.getElementById('edit-story-synopsis')?.value || '').trim(),
                author: (document.getElementById('edit-story-author')?.value || '').trim(),
            }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('✏️ Story updated!');
        closeStoryModal();
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function changeStoryStatus(storyId, newStatus) {
    if (!newStatus) return;
    try {
        const resp = await fetch(`/api/stories/${storyId}/status`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ status: newStatus }),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast(`Status changed to ${newStatus}`);
        renderStoryDetail(storyId);
    } catch (err) { showToast('Error: ' + err.message, true); }
}

async function deleteStory(storyId) {
    if (!confirm('Delete this entire story? This cannot be undone.')) return;
    try {
        const resp = await fetch(`/api/stories/${storyId}`, { method: 'DELETE' });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
        showToast('🗑️ Story deleted.');
        navigateTo('stories');
    } catch (err) { showToast('Error: ' + err.message, true); }
}

function openStoryLightbox(imageUrl) {
    const existing = document.getElementById('story-lightbox');
    if (existing) existing.remove();
    const lb = document.createElement('div');
    lb.id = 'story-lightbox';
    lb.className = 'story-lightbox';
    lb.onclick = () => lb.remove();
    lb.innerHTML = `<img src="${imageUrl}" alt="Illustration" />`;
    document.body.appendChild(lb);
}

// ═══════════════════════════════════════════════════════════════
// Story Participant Selector (F-043)
// ═══════════════════════════════════════════════════════════════

window._storyParticipants = [];
window._storyAvailableParticipants = [];

// ═══════════════════════════════════════════════════════════════
// Story Chat — Interactive Discussion within Scenes
// ═══════════════════════════════════════════════════════════════

window._storyChatId = null;
window._storyChatSceneId = null;
window._storyChatAvatarMap = {};

/**
 * Check for and load an active story chat for this story.
 */
async function _loadActiveStoryChat(storyId) {
    try {
        const data = await api(`/api/stories/${encodeURIComponent(storyId)}/chat/active`);
        if (data.chat_id && data.chat) {
            window._storyChatId = data.chat_id;
            window._storyChatSceneId = (data.chat.metadata || {}).scene_id || '';
            _showStoryChatPanel(data.chat, data.round, data.max_rounds);
        }
    } catch { /* no active chat, that's fine */ }
}

/**
 * Build avatar map from available participants.
 */
async function _buildStoryChatAvatarMap() {
    if (Object.keys(window._storyChatAvatarMap || {}).length > 0) return;
    try {
        const participants = await api('/api/participants/available');
        const map = {};
        participants.forEach(p => {
            if (p.avatar_url) map[p.name.toLowerCase()] = p.avatar_url;
        });
        window._storyChatAvatarMap = map;
    } catch { /* non-blocking */ }
}

/**
 * Create a story chat session and inject the narration as the first message.
 */
async function _initStoryChatWithNarration(storyId, chapterId, sceneId, narrationText, participants) {
    await _buildStoryChatAvatarMap();

    try {
        const chatData = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ participants, chapter_id: chapterId, scene_id: sceneId }),
        }).then(r => { if (!r.ok) throw new Error('Failed to create chat'); return r.json(); });

        window._storyChatId = chatData.chat_id;
        window._storyChatSceneId = sceneId;

        // Inject narration and trigger discussion
        await _injectStoryChatNarration(storyId, chatData.chat_id, narrationText, chapterId, sceneId);
    } catch (err) {
        showToast(`Chat init error: ${err.message}`, true);
    }
}

/**
 * Init story chat from the Chat button.
 */
async function initStoryChat(storyId, chapterId, sceneId) {
    // If chat already exists for this scene, just scroll to it
    if (window._storyChatId && window._storyChatSceneId === sceneId) {
        const chatEl = document.getElementById(`story-chat-${sceneId}`);
        if (chatEl) chatEl.scrollIntoView({ behavior: 'smooth' });
        return;
    }

    const participants = getSelectedStoryParticipants();
    if (!participants.length) {
        showToast('Select at least one participant in the Participants panel first.', true);
        return;
    }

    await _buildStoryChatAvatarMap();

    try {
        const chatData = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ participants, chapter_id: chapterId, scene_id: sceneId }),
        }).then(r => { if (!r.ok) throw new Error('Failed to create chat'); return r.json(); });

        window._storyChatId = chatData.chat_id;
        window._storyChatSceneId = sceneId;

        // Show empty chat panel
        _renderStoryChatSection(storyId, sceneId, chatData.chat_id, 0, chatData.max_rounds || 5);
        showToast('💬 Story chat created!');

    } catch (err) {
        showToast(`Chat init error: ${err.message}`, true);
    }
}

/**
 * Render the story chat section inside a scene item.
 */
function _renderStoryChatSection(storyId, sceneId, chatId, round, maxRounds, closed) {
    const container = document.getElementById(`story-chat-${sceneId}`);
    if (!container) return;

    const atLimit = round >= maxRounds || closed;
    const roundBadgeClass = atLimit ? 'story-chat-round-badge at-limit' : 'story-chat-round-badge';
    const roundLabel = closed ? 'Closed' : `Round ${round}/${maxRounds}`;

    container.innerHTML = `
        <div class="story-chat-section">
            <div class="story-chat-header">
                <h4>💬 Story Discussion</h4>
                <span class="${roundBadgeClass}" id="story-chat-round-badge">${roundLabel}</span>
            </div>
            <div class="story-chat-messages" id="story-chat-messages"></div>
            ${!atLimit ? `
            <div class="story-chat-input-bar" id="story-chat-input-bar">
                <input type="text" class="chat-input" id="story-chat-input"
                       placeholder="Join the discussion…" autocomplete="off"
                       onkeydown="if(event.key==='Enter')sendStoryChatMessage('${storyId}')" />
                <button class="btn btn-primary btn-sm" id="story-chat-send-btn"
                        onclick="sendStoryChatMessage('${storyId}')">Send</button>
            </div>
            <div class="story-chat-controls" id="story-chat-controls">
                <button class="btn btn-sm" onclick="continueStoryChat('${storyId}', '${chatId}')"
                        id="story-chat-continue-btn">🔄 Continue Discussion</button>
                <button class="btn btn-sm" onclick="narrateStoryRound('${storyId}', '${chatId}')"
                        id="story-chat-narrate-btn">📖 Narrate Next Round</button>
                <button class="btn btn-danger-subtle btn-sm"
                        onclick="closeStoryChat('${storyId}', '${chatId}')" title="End chat">End Chat</button>
            </div>` : `
            <div class="story-chat-controls" id="story-chat-controls">
                <span style="color:var(--text-muted);font-size:0.82rem;font-style:italic">Chat closed${round >= maxRounds ? ' (round limit reached)' : ''}.</span>
            </div>`}
        </div>`;
}

/**
 * Show the story chat panel with existing messages.
 */
function _showStoryChatPanel(chatData, round, maxRounds) {
    const meta = chatData.metadata || {};
    const sceneId = meta.scene_id || '';
    const storyId = meta.story_id || '';
    const chatId = chatData.chat_id;
    const closed = !!chatData.closed_at;

    _renderStoryChatSection(storyId, sceneId, chatId, round, maxRounds, closed);
    _buildStoryChatAvatarMap();

    const msgContainer = document.getElementById('story-chat-messages');
    if (!msgContainer) return;

    const messages = chatData.messages || [];
    if (messages.length === 0) {
        msgContainer.innerHTML = '<div class="story-chat-empty">No messages yet. Send a message or click a narration action to start.</div>';
        return;
    }

    messages.forEach(m => {
        const isHuman = m.role === 'human';
        const mmeta = m.metadata || {};

        if (mmeta.type === 'narration_inject') {
            const text = m.content.replace(/^📖 \*\*Narration:\*\*\n\n/, '');
            _appendStorySystemBubble(msgContainer, text);
            return;
        }

        if (isHuman) {
            _appendStoryHumanBubble(msgContainer, m.content);
        } else {
            const avatarUrl = (window._storyChatAvatarMap || {})[m.speaker?.toLowerCase()];
            _appendStoryChatBubble(msgContainer, m.speaker || 'Agent', m.content, avatarUrl);
        }
    });

    msgContainer.scrollTop = msgContainer.scrollHeight;
}

/**
 * Inject narration into the chat and stream participant responses.
 */
async function _injectStoryChatNarration(storyId, chatId, narrationText, chapterId, sceneId) {
    const msgContainer = document.getElementById('story-chat-messages');
    if (!msgContainer) return;

    // Clear empty state
    const emptyEl = msgContainer.querySelector('.story-chat-empty');
    if (emptyEl) emptyEl.remove();

    // Add narration bubble
    _appendStorySystemBubble(msgContainer, narrationText);

    // Typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-msg-header"><span class="chat-msg-speaker">Participants discussing…</span></div><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    try {
        const resp = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat/${encodeURIComponent(chatId)}/inject-narration`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ narration_text: narrationText, chapter_id: chapterId, scene_id: sceneId }),
        });
        if (!resp.ok) throw new Error('Inject failed');

        if (typingEl.parentNode) typingEl.remove();

        await _processStoryChatStream(resp, msgContainer, storyId);
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Chat error: ${err.message}`, true);
    }
}

/**
 * Send human message in the story chat + stream responses.
 */
async function sendStoryChatMessage(storyId) {
    const chatId = window._storyChatId;
    if (!chatId) {
        showToast('No active chat. Create one first!', true);
        return;
    }
    const input = document.getElementById('story-chat-input');
    const btn = document.getElementById('story-chat-send-btn');
    const content = input.value.trim();
    if (!content) { input.focus(); return; }

    input.disabled = true;
    btn.disabled = true;
    btn.textContent = '⏳';

    const msgContainer = document.getElementById('story-chat-messages');
    _appendStoryHumanBubble(msgContainer, content);
    input.value = '';

    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    try {
        const resp = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat/${encodeURIComponent(chatId)}/send-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (!resp.ok) throw new Error('Send failed');

        if (typingEl.parentNode) typingEl.remove();

        await _processStoryChatStream(resp, msgContainer, storyId);
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Chat error: ${err.message}`, true);
    } finally {
        input.disabled = false;
        btn.disabled = false;
        btn.textContent = 'Send';
        input.focus();
    }
}

/**
 * Continue AI-to-AI discussion.
 */
async function continueStoryChat(storyId, chatId) {
    const btn = document.getElementById('story-chat-continue-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Discussing…'; }

    const msgContainer = document.getElementById('story-chat-messages');

    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-msg-header"><span class="chat-msg-speaker">Participants continuing…</span></div><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    if (msgContainer) { msgContainer.appendChild(typingEl); msgContainer.scrollTop = msgContainer.scrollHeight; }

    try {
        const resp = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat/${encodeURIComponent(chatId)}/continue-stream`, {
            method: 'POST',
        });
        if (!resp.ok) throw new Error('Continue failed');

        if (typingEl.parentNode) typingEl.remove();

        await _processStoryChatStream(resp, msgContainer, storyId);
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Chat error: ${err.message}`, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🔄 Continue Discussion'; }
    }
}

/**
 * Trigger mid-conversation narration.
 */
async function narrateStoryRound(storyId, chatId) {
    const btn = document.getElementById('story-chat-narrate-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Narrating…'; }

    try {
        const resp = await fetch(`/api/stories/${encodeURIComponent(storyId)}/chat/${encodeURIComponent(chatId)}/narrate-round`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Narration failed'); }
        const result = await resp.json();

        // Show the narration in the chat
        const msgContainer = document.getElementById('story-chat-messages');
        if (msgContainer && result.narrative_text) {
            _appendStorySystemBubble(msgContainer, result.narrative_text);
        }

        // Update round badge
        _updateStoryRoundBadge(result.round, result.max_rounds);

        showToast(`📖 Narration generated! (${result.model})`);
    } catch (err) {
        showToast('Narration error: ' + err.message, true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📖 Narrate Next Round'; }
    }
}

/**
 * Close story chat early.
 */
async function closeStoryChat(storyId, chatId) {
    if (!confirm('End this story discussion?')) return;
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ summary: 'Story chat closed by user.' }),
        });
        window._storyChatId = null;
        window._storyChatSceneId = null;
        showToast('💬 Story chat ended.');
        renderStoryDetail(storyId);
    } catch (err) {
        showToast(`Error closing chat: ${err.message}`, true);
    }
}

/**
 * Process an SSE response stream from story chat endpoints.
 */
async function _processStoryChatStream(resp, msgContainer, storyId) {
    let responseTimer = startResponseTimer();
    if (msgContainer) {
        msgContainer.appendChild(responseTimer.el);
        msgContainer.scrollTop = msgContainer.scrollHeight;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
            if (!part.trim()) continue;
            const eventMatch = part.match(/^event:\s*(.+)$/m);
            const dataMatch = part.match(/^data:\s*(.+)$/m);
            if (!eventMatch || !dataMatch) continue;

            const eventType = eventMatch[1].trim();
            const data = JSON.parse(dataMatch[1]);

            if (eventType === 'message') {
                responseTimer.stop();
                const avatarUrl = (window._storyChatAvatarMap || {})[data.speaker.toLowerCase()];
                _appendStoryChatBubble(msgContainer, data.speaker, data.content, avatarUrl, data.response_time_ms);
                responseTimer = startResponseTimer();
                msgContainer.appendChild(responseTimer.el);
                msgContainer.scrollTop = msgContainer.scrollHeight;
            } else if (eventType === 'done') {
                responseTimer.stop();
                _updateStoryRoundBadge(data.round, data.max_rounds, data.at_limit);
                if (data.at_limit) {
                    // Disable input and controls
                    const inputBar = document.getElementById('story-chat-input-bar');
                    if (inputBar) inputBar.style.display = 'none';
                    const controls = document.getElementById('story-chat-controls');
                    if (controls) {
                        controls.innerHTML = `<span style="color:var(--text-muted);font-size:0.82rem;font-style:italic">Chat closed (round limit reached).</span>`;
                    }
                    window._storyChatId = null;
                    window._storyChatSceneId = null;
                }
                return;
            } else if (eventType === 'error') {
                responseTimer.stop();
                throw new Error(data.detail);
            }
        }
    }
    responseTimer.stop();
}

/**
 * Update round badge display.
 */
function _updateStoryRoundBadge(round, maxRounds, atLimit) {
    const badge = document.getElementById('story-chat-round-badge');
    if (!badge) return;
    const isAtLimit = atLimit || round >= maxRounds;
    badge.textContent = isAtLimit ? 'Closed' : `Round ${round}/${maxRounds}`;
    badge.className = isAtLimit ? 'story-chat-round-badge at-limit' : 'story-chat-round-badge';
}

/**
 * Append a narration system bubble.
 */
function _appendStorySystemBubble(container, text) {
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'story-chat-system-msg';
    bubble.innerHTML = `
        <div class="story-chat-system-icon">📖</div>
        <div class="story-chat-system-body">
            <div class="story-chat-system-label">Narration</div>
            <div class="story-chat-system-text">${renderMarkdown(text)}</div>
        </div>`;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

/**
 * Append an agent response bubble.
 */
function _appendStoryChatBubble(container, speaker, content, avatarUrl, responseTimeMs) {
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'chat-message chat-bubble-agent';
    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const responseTimeBadge = (responseTimeMs != null)
        ? `<span class="chat-response-time" title="Response time">${formatResponseTime(responseTimeMs)}</span>`
        : '';
    const avatarHtml = avatarUrl
        ? `<div class="member-avatar" style="background:url('${avatarUrl}') center/cover no-repeat;width:36px;height:36px;border-radius:50%"></div>`
        : memberAvatar(speaker, 0);
    bubble.innerHTML = `
        <div class="chat-msg-avatar">${avatarHtml}</div>
        <div class="chat-msg-body">
            <div class="chat-msg-header">
                <span class="chat-msg-speaker">${escapeHtml(speaker)}</span>
                <span class="chat-msg-time">${time}${responseTimeBadge}</span>
            </div>
            <div class="chat-msg-content">${renderMarkdown(content)}</div>
        </div>`;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

/**
 * Append a human message bubble.
 */
function _appendStoryHumanBubble(container, content) {
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'chat-message chat-bubble-human';
    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    bubble.innerHTML = `
        <div class="chat-msg-body">
            <div class="chat-msg-header">
                <span class="chat-msg-speaker">You</span>
                <span class="chat-msg-time">${time}</span>
            </div>
            <div class="chat-msg-content">${renderMarkdown(content)}</div>
        </div>`;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

async function loadStoryParticipants() {
    try {
        const participants = await api('/api/participants/available');
        window._storyAvailableParticipants = participants;
        renderStoryParticipantList(participants);
        updateStoryParticipantCounter();
    } catch {
        const list = document.getElementById('story-part-list');
        if (list) list.innerHTML = '<div style="color:var(--text-muted);padding:0.5rem">Failed to load participants.</div>';
    }
}

function renderStoryParticipantList(participants) {
    const list = document.getElementById('story-part-list');
    if (!list) return;

    if (!participants.length) {
        list.innerHTML = '<div style="color:var(--text-muted);padding:0.5rem">No participants available.</div>';
        return;
    }

    list.innerHTML = participants.map(p => {
        const isSelected = window._storyParticipants.some(
            sel => sel.id === p.id && sel.type === p.type
        );
        const typeBadge = p.type === 'council'
            ? '<span class="participant-type-badge participant-type-council">🏛️ Council</span>'
            : '<span class="participant-type-badge participant-type-character">🎭 Character</span>';
        const avatarHtml = p.avatar_url
            ? `<img class="participant-avatar" src="${p.avatar_url}" alt="" />`
            : `<div class="participant-avatar participant-avatar-placeholder">${escapeHtml(p.name.charAt(0))}</div>`;
        return `
            <label class="participant-item ${isSelected ? 'participant-item-selected' : ''}"
                   data-name="${escapeAttr(p.name.toLowerCase())}"
                   data-id="${escapeAttr(p.id)}">
                <input type="checkbox" class="story-part-cb"
                       data-pid="${escapeAttr(p.id)}" data-ptype="${escapeAttr(p.type)}"
                       ${isSelected ? 'checked' : ''}
                       onchange="toggleStoryParticipant(this)" />
                ${avatarHtml}
                <div class="participant-info">
                    <span class="participant-name">${escapeHtml(p.name)}</span>
                    ${typeBadge}
                </div>
                ${p.description ? `<span class="participant-desc">${escapeHtml(truncate(p.description, 60))}</span>` : ''}
            </label>`;
    }).join('');
}

function toggleStoryParticipants() {
    const body = document.getElementById('story-part-body');
    const chev = document.getElementById('story-part-chevron');
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    if (chev) chev.textContent = isOpen ? '▸' : '▾';
}

function filterStoryParticipants() {
    const query = (document.getElementById('story-part-search')?.value || '').toLowerCase();
    document.querySelectorAll('#story-part-list .participant-item').forEach(el => {
        const name = el.dataset.name || '';
        el.style.display = name.includes(query) ? '' : 'none';
    });
}

function toggleStoryParticipant(checkbox) {
    const pid = checkbox.dataset.pid;
    const ptype = checkbox.dataset.ptype;
    const label = checkbox.closest('.participant-item');

    if (checkbox.checked) {
        if (window._storyParticipants.length >= 10) {
            checkbox.checked = false;
            showToast('Maximum 10 participants allowed.', true);
            return;
        }
        if (!window._storyParticipants.some(p => p.id === pid && p.type === ptype)) {
            window._storyParticipants.push({ id: pid, type: ptype });
        }
        if (label) label.classList.add('participant-item-selected');
    } else {
        window._storyParticipants = window._storyParticipants.filter(
            p => !(p.id === pid && p.type === ptype)
        );
        if (label) label.classList.remove('participant-item-selected');
    }
    updateStoryParticipantCounter();
    _debounceSaveStoryParticipants();
}

// Debounced auto-save of participant selections to story metadata
let _storyPartSaveTimer = null;
function _debounceSaveStoryParticipants() {
    if (_storyPartSaveTimer) clearTimeout(_storyPartSaveTimer);
    _storyPartSaveTimer = setTimeout(() => {
        _saveStoryParticipants();
    }, 800);
}

function _saveStoryParticipants() {
    // Extract current story ID from the URL hash
    const hash = window.location.hash.slice(1) || '';
    const parts = hash.split('/');
    if (parts[0] !== 'stories' || !parts[1]) return;
    const storyId = parts[1];
    fetch(`/api/stories/${encodeURIComponent(storyId)}/participants`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participants: window._storyParticipants }),
    }).catch(() => { /* non-blocking save */ });
}

function updateStoryParticipantCounter() {
    const counter = document.getElementById('story-part-counter');
    if (counter) {
        const n = window._storyParticipants.length;
        counter.textContent = `${n}/10`;
        counter.style.color = n > 0 ? 'var(--accent)' : '';
    }
}

function getSelectedStoryParticipants() {
    return window._storyParticipants.length ? [...window._storyParticipants] : [];
}


// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Apply saved skin before anything renders
    applySkin(state.activeSkin);

    // Eagerly load model options so dropdowns work before Settings is visited
    loadModelOptions();

    // Start global generation toast poller (F-037g)
    startGenToastPoller();

    initNavigation();
    const hash = window.location.hash.slice(1) || 'dashboard';
    const [view, ...rest] = hash.split('/');
    navigateTo(view, rest.join('/') || null);
});
