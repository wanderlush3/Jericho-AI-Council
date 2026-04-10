async function renderExplore() {
    showLoading();
    let locations = [];
    try {
        locations = await api('/api/explore');
    } catch {
        locations = [];
    }

    if (!locations.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header">
                    <h2>🧭 Explore</h2>
                    <p>No active locations to explore yet. Create locations in the <a href="#locations" style="color:var(--accent-cyan)">Locations</a> section and set them to active.</p>
                </div>
                <div class="empty-state">
                    <div class="empty-icon">🗺️</div>
                    <p>Your world awaits — create some locations first!</p>
                </div>
            </div>`;
        return;
    }

    const cards = locations.map(loc => {
        const imgStyle = loc.primary_image_url
            ? `background: url('${loc.primary_image_url}') center/cover no-repeat`
            : `background: linear-gradient(135deg, hsl(200,30%,20%), hsl(220,25%,15%))`;

        const scenesBadge = loc.scene_count > 0
            ? `<span class="explore-scene-badge">${loc.scene_count} scene${loc.scene_count !== 1 ? 's' : ''}</span>`
            : '';

        return `
            <div class="explore-card card-clickable" onclick="navigateTo('explore','${loc.id}')">
                <div class="explore-card-image" style="${imgStyle}">
                    ${!loc.primary_image_url ? '<div class="explore-card-placeholder">🗺️</div>' : ''}
                    ${scenesBadge}
                </div>
                <div class="explore-card-info">
                    <div class="explore-card-name">${escapeHtml(loc.name)}</div>
                    <div class="explore-card-desc">${truncate(loc.description, 80)}</div>
                    ${loc.tags && loc.tags.length ? `<div class="explore-card-tags">${loc.tags.slice(0, 3).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                </div>
            </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>🧭 Explore the World</h2>
                    <p>${locations.length} location${locations.length !== 1 ? 's' : ''} to explore</p>
                </div>
            </div>
            <div class="explore-grid">${cards}</div>
        </div>`;
}

async function renderExploreLocation(locationId) {
    showLoading();
    let data;
    try {
        data = await api(`/api/explore/${encodeURIComponent(locationId)}`);
    } catch (err) {
        showError(`Location not found: ${err.message}`);
        return;
    }

    // F-042: Fetch available participants
    let availableParticipants = [];
    try {
        availableParticipants = await api('/api/participants/available');
    } catch { /* optional */ }

    // Hero image
    const heroImageUrl = data.primary_image_url || '';
    const heroStyle = heroImageUrl
        ? `background-image: url('${heroImageUrl}')`
        : `background: linear-gradient(135deg, hsl(220,30%,18%), hsl(250,25%,12%))`;

    // Features list
    const featuresHtml = (data.features || []).map(f => `
        <div class="explore-feature-item">
            <span class="explore-feature-icon">${f.feature_type === 'landmark' ? '🏛️' : f.feature_type === 'natural' ? '🌿' : f.feature_type === 'building' ? '🏠' : f.feature_type === 'district' ? '🏘️' : '📍'}</span>
            <div>
                <div class="explore-feature-name">${escapeHtml(f.name)}</div>
                <div class="explore-feature-desc">${escapeHtml(f.description || '')}</div>
            </div>
        </div>`).join('');

    // Scene strip
    const scenesHtml = (data.scenes || []).map((s, idx) => `
        <div class="explore-scene-thumb" onclick="openExploreSceneLightbox(${idx})">
            <img src="${s.image_url}" alt="${escapeAttr(s.description || s.scene_id)}" loading="lazy" />
            <div class="explore-scene-type">${s.scene_type}</div>
            <button class="explore-scene-delete" onclick="event.stopPropagation(); deleteExploreScene('${locationId}', '${s.scene_id}')" title="Delete scene">🗑️</button>
        </div>`).join('');

    // Navigation cards
    const navHtml = _buildExploreNavPanel(data.navigation);

    // Tags
    const tagsHtml = (data.tags || []).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join('');

    // F-042: Build participant selector HTML
    const participantListHtml = availableParticipants.map(p => {
        const typeIcon = p.type === 'council' ? '🏛️' : '🎭';
        const typeBadge = p.type === 'council' ? 'Council' : 'Character';
        const avatarStyle = p.avatar_url
            ? `background: url('${p.avatar_url}') center/cover no-repeat`
            : `background: linear-gradient(135deg, hsl(${p.type === 'council' ? '260,40%,30%' : '200,40%,30%'}), hsl(${p.type === 'council' ? '280,30%,20%' : '220,30%,20%'}))`;
        return `
            <label class="participant-item" data-pid="${escapeAttr(p.id)}" data-ptype="${escapeAttr(p.type)}">
                <input type="checkbox" class="participant-cb" value="${escapeAttr(p.id)}"
                       data-ptype="${escapeAttr(p.type)}" data-pname="${escapeAttr(p.name)}"
                       onchange="updateParticipantCount()" />
                <div class="participant-avatar" style="${avatarStyle}">
                    ${!p.avatar_url ? `<span>${typeIcon}</span>` : ''}
                </div>
                <div class="participant-info">
                    <div class="participant-name">${escapeHtml(p.name)}</div>
                    <div class="participant-desc">${truncate(p.description || p.role || '', 60)}</div>
                </div>
                <span class="participant-type-badge participant-type-${p.type}">${typeBadge}</span>
            </label>`;
    }).join('');

    const participantSectionHtml = availableParticipants.length ? `
        <div class="explore-section explore-participants-section">
            <div class="explore-participants-header" onclick="toggleParticipantPanel()">
                <h4>👥 Participants</h4>
                <div class="explore-participants-meta">
                    <span class="participant-counter" id="participant-counter">0 / 10</span>
                    <span class="participant-toggle-icon" id="participant-toggle-icon">▶</span>
                </div>
            </div>
            <div class="explore-participants-body" id="explore-participants-body" style="display:none">
                <div class="participant-search-row">
                    <input type="text" class="settings-input participant-search" id="participant-search"
                           placeholder="Search participants…" oninput="filterParticipants()" />
                    <button class="btn btn-secondary btn-sm" onclick="clearAllParticipants()" title="Clear all">✕ Clear</button>
                </div>
                <div class="participant-list" id="participant-list">
                    ${participantListHtml}
                </div>
                <div class="participant-hint">
                    Select up to 10 council members or characters to join this exploration.
                    Their identity, memories, and world knowledge will enrich the scene.
                </div>
            </div>
        </div>` : '';

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('explore')">← Back to Explore</button>

            <div class="explore-hero" style="${heroStyle}">
                <div class="explore-hero-overlay">
                    <div class="explore-hero-content">
                        <h2 class="explore-hero-title">${escapeHtml(data.name)}</h2>
                        ${data.coordinates ? `<div class="explore-hero-coords">📍 ${escapeHtml(data.coordinates)}</div>` : ''}
                        <p class="explore-hero-desc">${escapeHtml(data.description || '')}</p>
                        ${tagsHtml ? `<div class="explore-hero-tags">${tagsHtml}</div>` : ''}
                    </div>
                    <div class="explore-hero-actions">
                        <button class="btn explore-look-around-btn" onclick="exploreLookAround('${locationId}')" id="explore-look-around-btn">
                            👁️ Look Around
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="navigateTo('locations', '${locationId}')" title="Open location detail page">
                            🗺️ Location Page
                        </button>
                    </div>
                </div>
            </div>

            <div id="explore-gen-progress" style="display:none">
                <div class="explore-gen-progress-bar">
                    <div class="explore-gen-progress-fill" id="explore-gen-fill"></div>
                </div>
                <div class="explore-gen-status" id="explore-gen-status">Generating scene…</div>
            </div>

            ${participantSectionHtml}

            ${data.lore ? `
                <div class="explore-section">
                    <h4>📜 Lore</h4>
                    <p class="explore-lore-text">${escapeHtml(data.lore)}</p>
                </div>` : ''}

            ${featuresHtml ? `
                <div class="explore-section">
                    <h4>🏛️ Notable Features</h4>
                    <div class="explore-features-grid">${featuresHtml}</div>
                </div>` : ''}

            <div class="explore-section">
                <div class="explore-section-header">
                    <h4>🖼️ Scene Gallery (${(data.scenes || []).length})</h4>
                </div>
                ${scenesHtml
                    ? `<div class="explore-scene-strip" id="explore-scene-strip">${scenesHtml}</div>`
                    : `<div class="explore-empty-scenes">
                        <div class="empty-icon">👁️</div>
                        <p>No scenes yet. Click <strong>"Look Around"</strong> to generate your first scene!</p>
                    </div>`
                }
            </div>

            ${navHtml}
        </div>`;

    // Store scenes data for lightbox
    window._exploreScenes = data.scenes || [];
    // F-042: Reset participant selections
    window._exploreParticipants = [];
}

function _buildExploreNavPanel(nav) {
    if (!nav) return '';
    const allTargets = [];

    if (nav.parent) {
        allTargets.push({ ...nav.parent, relation: '⬆️ Parent' });
    }
    (nav.children || []).forEach(c => {
        allTargets.push({ ...c, relation: '⬇️ Child' });
    });
    (nav.siblings || []).forEach(s => {
        allTargets.push({ ...s, relation: '↔️ Sibling' });
    });

    if (!allTargets.length) return '';

    const cards = allTargets.map(t => {
        const imgStyle = t.primary_image_url
            ? `background: url('${t.primary_image_url}') center/cover no-repeat`
            : `background: linear-gradient(135deg, hsl(200,30%,20%), hsl(220,25%,15%))`;

        return `
            <div class="explore-nav-card card-clickable" onclick="navigateTo('explore','${t.id}')">
                <div class="explore-nav-card-img" style="${imgStyle}">
                    ${!t.primary_image_url ? '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:1.5rem;opacity:0.4">🗺️</div>' : ''}
                </div>
                <div class="explore-nav-card-info">
                    <span class="explore-nav-relation">${t.relation}</span>
                    <div class="explore-nav-card-name">${escapeHtml(t.name)}</div>
                    <div class="explore-nav-card-desc">${truncate(t.description, 60)}</div>
                </div>
            </div>`;
    }).join('');

    return `
        <div class="explore-section">
            <h4>🧭 Connected Locations</h4>
            <div class="explore-nav-grid">${cards}</div>
        </div>`;
}

/* ── F-042: Participant Selector Helpers ───────────────────── */

function toggleParticipantPanel() {
    const body = document.getElementById('explore-participants-body');
    const icon = document.getElementById('participant-toggle-icon');
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    if (icon) icon.textContent = isOpen ? '▶' : '▼';
}

function updateParticipantCount() {
    const checked = document.querySelectorAll('.participant-cb:checked');
    const counter = document.getElementById('participant-counter');
    const count = checked.length;
    if (counter) {
        counter.textContent = `${count} / 10`;
        counter.classList.toggle('participant-counter-full', count >= 10);
        counter.classList.toggle('participant-counter-active', count > 0 && count < 10);
    }

    // Disable unchecked checkboxes when at max
    const allCbs = document.querySelectorAll('.participant-cb');
    allCbs.forEach(cb => {
        if (!cb.checked) {
            cb.disabled = count >= 10;
            cb.closest('.participant-item')?.classList.toggle('participant-disabled', count >= 10);
        } else {
            cb.disabled = false;
            cb.closest('.participant-item')?.classList.remove('participant-disabled');
        }
    });
}

function filterParticipants() {
    const query = (document.getElementById('participant-search')?.value || '').toLowerCase();
    const items = document.querySelectorAll('.participant-item');
    items.forEach(item => {
        const name = (item.querySelector('.participant-name')?.textContent || '').toLowerCase();
        const desc = (item.querySelector('.participant-desc')?.textContent || '').toLowerCase();
        const type = item.dataset.ptype || '';
        const match = !query || name.includes(query) || desc.includes(query) || type.includes(query);
        item.style.display = match ? '' : 'none';
    });
}

function clearAllParticipants() {
    const cbs = document.querySelectorAll('.participant-cb:checked');
    cbs.forEach(cb => { cb.checked = false; });
    updateParticipantCount();
}

function getSelectedParticipants() {
    const checked = document.querySelectorAll('.participant-cb:checked');
    return Array.from(checked).map(cb => ({
        id: cb.value,
        type: cb.dataset.ptype || 'character',
    }));
}

/* ── Look Around Generation ────────────────────────────────── */

async function exploreLookAround(locationId) {
    const btn = document.getElementById('explore-look-around-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating…'; }

    const progressEl = document.getElementById('explore-gen-progress');
    const fillEl = document.getElementById('explore-gen-fill');
    const statusEl = document.getElementById('explore-gen-status');
    if (progressEl) progressEl.style.display = 'block';

    // F-042: Gather selected participants
    const participants = getSelectedParticipants();

    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/look-around`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ participants }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Generation failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        const pCount = participants.length;
        const pLabel = pCount > 0 ? ` with ${pCount} participant${pCount !== 1 ? 's' : ''}` : '';
        showToast(`Scene generation started${pLabel} (${data.job_id}) 🎨`);

        // Poll for job status
        _pollExploreGeneration(data.job_id, locationId, fillEl, statusEl);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
        if (progressEl) progressEl.style.display = 'none';
    }
}

async function _pollExploreGeneration(jobId, locationId, fillEl, statusEl) {
    const stageLabels = {
        'prompt_generating': '🧠 Generating prompt…',
        'template_filling': '📋 Preparing workflow…',
        'queued': '📤 Queued…',
        'running': '⚡ Generating image…',
        'downloading': '📥 Downloading…',
        'saving': '💾 Saving…',
        'completed': '✅ Scene ready!',
        'failed': '❌ Failed',
        'cancelled': '🚫 Cancelled',
    };

    const poll = async () => {
        try {
            const data = await api(`/api/generate/jobs/${encodeURIComponent(jobId)}`);
            if (fillEl) fillEl.style.width = `${data.progress_pct || 0}%`;
            if (statusEl) statusEl.textContent = stageLabels[data.stage] || data.stage;

            if (data.stage === 'completed') {
                showToast('Scene generated! 🎨');

                // Auto-add the scene to this location
                if (data.image_id) {
                    try {
                        await fetch(`/api/explore/${encodeURIComponent(locationId)}/scenes`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                image_id: data.image_id,
                                scene_type: 'overview',
                                description: `Scene generated via Look Around`,
                            }),
                        });
                    } catch { /* scene add failed, image still exists */ }
                }

                // Refresh the explore page
                setTimeout(() => renderExploreLocation(locationId), 500);
                return;
            }

            if (data.stage === 'failed' || data.stage === 'cancelled') {
                showToast(`Generation ${data.stage}: ${data.error || ''}`, true);
                const btn = document.getElementById('explore-look-around-btn');
                if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
                const progressEl = document.getElementById('explore-gen-progress');
                if (progressEl) setTimeout(() => progressEl.style.display = 'none', 2000);
                return;
            }

            // Continue polling
            setTimeout(poll, 1500);
        } catch (err) {
            showToast(`Poll error: ${err.message}`, true);
            const btn = document.getElementById('explore-look-around-btn');
            if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
        }
    };

    setTimeout(poll, 2000);
}

/* ── Scene Lightbox ────────────────────────────────────────── */

function openExploreSceneLightbox(index) {
    const scenes = window._exploreScenes || [];
    if (!scenes.length) return;
    if (index < 0) index = scenes.length - 1;
    if (index >= scenes.length) index = 0;

    const scene = scenes[index];
    const overlay = document.createElement('div');
    overlay.className = 'gallery-lightbox';
    overlay.id = 'explore-scene-lightbox';
    overlay.innerHTML = `
        <div class="gallery-lb-content">
            <button class="gallery-lb-close" onclick="closeExploreSceneLightbox()" title="Close">✕</button>
            ${scenes.length > 1
                ? `<button class="gallery-lb-nav gallery-lb-prev" onclick="navigateExploreSceneLb(${index - 1})">◀</button>
                   <button class="gallery-lb-nav gallery-lb-next" onclick="navigateExploreSceneLb(${index + 1})">▶</button>`
                : ''}
            <img src="${scene.image_url}" alt="${escapeAttr(scene.description || scene.scene_id)}" />
            <div class="gallery-lb-info">
                <span>${scene.scene_id} · ${index + 1} / ${scenes.length} · ${scene.scene_type}</span>
            </div>
            ${scene.description ? `<div style="color:rgba(255,255,255,0.5);font-size:0.75rem;max-width:600px;text-align:center;margin-top:var(--space-xs)">
                ${escapeHtml(scene.description)}
            </div>` : ''}
        </div>`;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeExploreSceneLightbox();
    });
    document.body.appendChild(overlay);

    overlay._keyHandler = (e) => {
        if (e.key === 'Escape') closeExploreSceneLightbox();
        if (e.key === 'ArrowLeft') navigateExploreSceneLb(index - 1);
        if (e.key === 'ArrowRight') navigateExploreSceneLb(index + 1);
    };
    document.addEventListener('keydown', overlay._keyHandler);
}

function closeExploreSceneLightbox() {
    const lb = document.getElementById('explore-scene-lightbox');
    if (lb) {
        if (lb._keyHandler) document.removeEventListener('keydown', lb._keyHandler);
        lb.remove();
    }
}

function navigateExploreSceneLb(index) {
    closeExploreSceneLightbox();
    openExploreSceneLightbox(index);
}

/* ── Delete Scene ──────────────────────────────────────────── */

async function deleteExploreScene(locationId, sceneId) {
    if (!confirm('Delete this scene?')) return;
    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/scenes/${encodeURIComponent(sceneId)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast('Scene deleted 🗑️');
        renderExploreLocation(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}


// ═══════════════════════════════════════════════════════════════
// Characters View
// ═══════════════════════════════════════════════════════════════

