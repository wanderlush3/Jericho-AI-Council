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

    // Scene strip — show focus area label when available
    const scenesHtml = (data.scenes || []).map((s, idx) => `
        <div class="explore-scene-thumb" onclick="openExploreSceneLightbox(${idx})">
            <img src="${s.image_url}" alt="${escapeAttr(s.description || s.scene_id)}" loading="lazy" />
            <div class="explore-scene-type">${s.focus_area || s.scene_type}</div>
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

            <div id="explore-movement-panel">
                ${_buildMovementPanel(data, locationId)}
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

            <div class="explore-section explore-chat-section" id="explore-chat-section">
                <div class="explore-section-header">
                    <h4>💬 Location Discussion</h4>
                    <div class="explore-chat-controls" id="explore-chat-controls"></div>
                </div>
                <div class="explore-chat-messages" id="explore-chat-messages">
                    <div class="chat-empty">Select participants above and click <strong>"Look Around"</strong> to start a discussion about this location.</div>
                </div>
                <div class="explore-chat-input-bar" id="explore-chat-input-bar" style="display:none">
                    <input id="explore-chat-input" class="chat-input" type="text"
                           placeholder="Type your message…" autocomplete="off"
                           onkeydown="if(event.key==='Enter')sendExploreChatMessage('${locationId}')" />
                    <button class="btn btn-primary chat-send-btn" id="explore-chat-send-btn"
                            onclick="sendExploreChatMessage('${locationId}')">
                        Send ➤
                    </button>
                </div>
            </div>

            ${navHtml}
        </div>`;

    // Store scenes data for lightbox
    window._exploreScenes = data.scenes || [];
    // Store current exploration state
    window._exploreState = data.exploration_state || null;
    window._exploreFeatures = data.features || [];
    // F-042: Reset participant selections
    window._exploreParticipants = [];
    // Explore chat state
    window._exploreChatId = null;
    window._exploreChatAvatarMap = {};

    // Check if there's an active explore chat for this location
    _loadActiveExploreChat(locationId);
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

/* ── F-079: Movement Panel Builder ────────────────────────── */

function _buildMovementPanel(data, locationId) {
    const state = data.exploration_state;
    if (!state) {
        // No exploration started yet — show nothing
        return '';
    }

    const moves = state.available_moves || [];
    const progress = state.progress || { explored: 0, total: 0, percentage: 0 };
    const currentFocus = state.current_focus || 'initial';
    const mode = state.mode || 'guided';

    // Feature type → icon map
    const typeIcons = {
        'landmark': '🏛️', 'natural': '🌿', 'building': '🏠',
        'district': '🏘️', 'infrastructure': '🔧', 'custom': '📍',
        'exterior': '🌅', 'imaginative': '🔮',
    };

    // Build focus indicator
    const focusLabel = currentFocus === 'initial' ? 'Not started'
        : currentFocus === 'exterior' ? 'Exterior Overview'
        : currentFocus === 'imaginative' ? 'Exploring Beyond…'
        : currentFocus;

    const modeLabel = mode === 'imaginative'
        ? '<span class="explore-mode-badge explore-mode-imaginative">✨ Imaginative Mode</span>'
        : '';

    // Build movement cards
    const moveCards = moves.map(m => {
        // Look up feature type for icon
        let icon = typeIcons[m.type] || '📍';
        if (m.type === 'feature') {
            const feature = (data.features || []).find(f => f.name === m.target);
            if (feature) icon = typeIcons[feature.feature_type] || '📍';
        }

        const exploredClass = m.explored ? 'explore-move-card-explored' : '';
        const activeClass = m.target === currentFocus ? 'explore-move-card-active' : '';
        const imaginativeClass = m.type === 'imaginative' ? 'explore-move-card-imaginative' : '';

        return `
            <div class="explore-move-card ${exploredClass} ${activeClass} ${imaginativeClass}"
                 onclick="exploreLookAround('${locationId}', '${escapeAttr(m.target)}')"
                 title="${m.explored ? 'Revisit' : 'Explore'}: ${escapeAttr(m.label)}">
                <div class="explore-move-icon">${icon}</div>
                <div class="explore-move-label">${escapeHtml(m.label)}</div>
                ${m.explored ? '<div class="explore-move-check">✅</div>' : ''}
            </div>`;
    }).join('');

    // Progress bar
    const progressHtml = progress.total > 0 ? `
        <div class="explore-progress-section">
            <div class="explore-progress-info">
                <span>Progress: ${progress.explored} / ${progress.total} areas</span>
                <span>${progress.percentage}%</span>
            </div>
            <div class="explore-progress-track">
                <div class="explore-progress-fill" style="width: ${progress.percentage}%"></div>
            </div>
        </div>` : '';

    return `
        <div class="explore-section explore-movement-section">
            <div class="explore-section-header">
                <h4>📍 Exploration</h4>
                <div class="explore-state-actions">
                    ${modeLabel}
                    <button class="btn btn-secondary btn-sm" onclick="resetExploration('${locationId}')" title="Reset exploration">
                        🔄 Reset
                    </button>
                </div>
            </div>
            <div class="explore-state-indicator">
                <span class="explore-focus-label">Currently viewing: <strong>${escapeHtml(focusLabel)}</strong></span>
            </div>
            ${progressHtml}
            <div class="explore-movement-grid">${moveCards}</div>
        </div>`;
}

async function resetExploration(locationId) {
    if (!confirm('Reset exploration? This clears all movement history.')) return;
    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/state/reset`, { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Reset failed' }));
            throw new Error(err.detail);
        }
        showToast('Exploration reset \u2714');
        window._exploreState = null;
        await renderExploreLocation(locationId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

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

async function exploreLookAround(locationId, target) {
    const btn = document.getElementById('explore-look-around-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating…'; }

    // Disable movement cards during generation
    document.querySelectorAll('.explore-move-card').forEach(c => c.classList.add('explore-move-card-disabled'));

    const progressEl = document.getElementById('explore-gen-progress');
    const fillEl = document.getElementById('explore-gen-fill');
    const statusEl = document.getElementById('explore-gen-status');
    if (progressEl) progressEl.style.display = 'block';

    // F-042: Gather selected participants
    const participants = getSelectedParticipants();
    // Save for chat creation (poll callback runs after page re-render resets checkboxes)
    window._exploreSavedParticipants = participants;

    const payload = { participants };
    if (target) payload.target = target;

    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/look-around`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Generation failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        const pCount = participants.length;
        const pLabel = pCount > 0 ? ` with ${pCount} participant${pCount !== 1 ? 's' : ''}` : '';
        const targetLabel = data.target && data.target !== 'initial' ? ` — ${data.target}` : '';
        showToast(`Scene generation started${pLabel}${targetLabel} (${data.job_id}) 🎨`);

        // Update exploration state from response
        if (data.exploration_state) {
            window._exploreState = data.exploration_state;
        }

        // Poll for job status
        _pollExploreGeneration(data.job_id, locationId, fillEl, statusEl);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '👁️ Look Around'; }
        if (progressEl) progressEl.style.display = 'none';
        document.querySelectorAll('.explore-move-card').forEach(c => c.classList.remove('explore-move-card-disabled'));
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
                let imageUrl = '';
                if (data.image_id) {
                    imageUrl = `/api/images/file/${data.image_id}`;
                    // Use focus_area from metadata if available
                    const focusArea = (data.metadata && data.metadata.focus_area) || '';
                    const sceneType = (data.metadata && data.metadata.scene_type) || 'overview';
                    try {
                        await fetch(`/api/explore/${encodeURIComponent(locationId)}/scenes`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                image_id: data.image_id,
                                scene_type: sceneType,
                                description: focusArea ? `Scene: ${focusArea}` : 'Scene generated via Look Around',
                                focus_area: focusArea,
                            }),
                        });
                    } catch { /* scene add failed, image still exists */ }
                }

                // Participants already saved in exploreLookAround() above

                // Refresh the explore page to show new scene
                await renderExploreLocation(locationId);

                // Inject the scene prompt into explore chat
                const promptText = data.prompt_positive || data.message || '';
                if (promptText) {
                    await _initExploreChatAndInject(locationId, promptText, imageUrl);
                }
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


/* ── Explore Chat Functions ─────────────────────────────────── */

/**
 * Check for and load an active explore chat for this location.
 */
async function _loadActiveExploreChat(locationId) {
    try {
        const data = await api(`/api/explore/${encodeURIComponent(locationId)}/chat/active`);
        if (data.chat_id && data.chat) {
            window._exploreChatId = data.chat_id;
            _showExploreChatPanel(data.chat);
        }
    } catch { /* no active chat, that's fine */ }
}

/**
 * Build avatar map from available participants for explore chat.
 */
async function _buildExploreChatAvatarMap() {
    if (Object.keys(window._exploreChatAvatarMap || {}).length > 0) return;
    try {
        const participants = await api('/api/participants/available');
        const map = {};
        participants.forEach(p => {
            if (p.avatar_url) map[p.name.toLowerCase()] = p.avatar_url;
        });
        window._exploreChatAvatarMap = map;
    } catch { /* non-blocking */ }
}

/**
 * Create explore chat (if needed) and inject the scene prompt.
 */
async function _initExploreChatAndInject(locationId, promptText, imageUrl) {
    // Ensure avatar map is loaded
    await _buildExploreChatAvatarMap();

    // Create chat if we don't have one
    if (!window._exploreChatId) {
        // Use saved participants from before the re-render, or try current checkboxes
        const participants = (window._exploreSavedParticipants && window._exploreSavedParticipants.length)
            ? window._exploreSavedParticipants
            : getSelectedParticipants();
        // Clear saved participants after use
        window._exploreSavedParticipants = null;

        if (!participants.length) {
            // No participants selected, skip chat
            return;
        }
        try {
            const chatData = await fetch(`/api/explore/${encodeURIComponent(locationId)}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ participants }),
            }).then(r => { if (!r.ok) throw new Error('Failed to create chat'); return r.json(); });
            window._exploreChatId = chatData.chat_id;
        } catch (err) {
            showToast(`Chat init error: ${err.message}`, true);
            return;
        }
    }

    const chatId = window._exploreChatId;
    const inputBar = document.getElementById('explore-chat-input-bar');
    if (inputBar) inputBar.style.display = 'flex';

    const msgContainer = document.getElementById('explore-chat-messages');
    if (!msgContainer) return;

    // Clear empty state
    const emptyEl = msgContainer.querySelector('.chat-empty');
    if (emptyEl) emptyEl.remove();

    // Add narrator scene inject bubble
    _appendExploreSystemBubble(msgContainer, promptText, imageUrl);

    // Show typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-msg-header"><span class="chat-msg-speaker">Participants discussing…</span></div><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    // Stream participant responses via inject-scene endpoint
    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/chat/${encodeURIComponent(chatId)}/inject-scene`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt_text: promptText, image_url: imageUrl }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Inject failed' }));
            throw new Error(err.detail);
        }

        if (typingEl.parentNode) typingEl.remove();

        let responseTimer = startResponseTimer();
        msgContainer.appendChild(responseTimer.el);
        msgContainer.scrollTop = msgContainer.scrollHeight;

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
                    const avatarUrl = window._exploreChatAvatarMap[data.speaker.toLowerCase()];
                    _appendExploreChatBubble(msgContainer, data.speaker, data.content, avatarUrl, data.response_time_ms);
                    responseTimer = startResponseTimer();
                    msgContainer.appendChild(responseTimer.el);
                    msgContainer.scrollTop = msgContainer.scrollHeight;
                } else if (eventType === 'done') {
                    responseTimer.stop();
                    _updateExploreChatControls(locationId, chatId);
                    return;
                } else if (eventType === 'error') {
                    responseTimer.stop();
                    throw new Error(data.detail);
                }
            }
        }
        responseTimer.stop();
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Chat error: ${err.message}`, true);
    }
}

/**
 * Show the explore chat panel with existing messages.
 */
function _showExploreChatPanel(chatData) {
    const chatSection = document.getElementById('explore-chat-section');
    if (!chatSection) return;

    // Show the input bar for active chat
    const inputBar = document.getElementById('explore-chat-input-bar');
    if (inputBar) inputBar.style.display = 'flex';

    _buildExploreChatAvatarMap();

    const msgContainer = document.getElementById('explore-chat-messages');
    if (!msgContainer) return;

    const messages = chatData.messages || [];
    if (messages.length === 0) return;

    // Clear empty state
    msgContainer.innerHTML = '';

    messages.forEach(m => {
        const isHuman = m.role === 'human';
        const meta = m.metadata || {};

        if (meta.type === 'scene_inject') {
            // Render as narrator/system bubble
            const promptText = m.content.replace(/^🌍 \*\*Scene Description:\*\*\n\n/, '');
            const imageUrl = meta.image_url || '';
            _appendExploreSystemBubble(msgContainer, promptText, imageUrl);
            return;
        }

        if (isHuman) {
            _appendExploreHumanBubble(msgContainer, m.content);
        } else {
            const avatarUrl = (window._exploreChatAvatarMap || {})[m.speaker?.toLowerCase()];
            _appendExploreChatBubble(msgContainer, m.speaker || 'Agent', m.content, avatarUrl);
        }
    });

    msgContainer.scrollTop = msgContainer.scrollHeight;

    const locationId = chatData.metadata?.explore_location_id;
    if (locationId) {
        _updateExploreChatControls(locationId, chatData.chat_id);
    }
}

/**
 * Append a narrator/system message bubble for scene injection.
 */
function _appendExploreSystemBubble(container, promptText, imageUrl) {
    const bubble = document.createElement('div');
    bubble.className = 'explore-chat-system-msg';
    let html = `<div class="explore-chat-system-icon">🌍</div><div class="explore-chat-system-body">`;
    html += `<div class="explore-chat-system-label">Scene Description</div>`;
    html += `<div class="explore-chat-system-text">${renderMarkdown(promptText)}</div>`;
    if (imageUrl) {
        html += `<img class="explore-chat-system-img" src="${imageUrl}" alt="Generated scene" />`;
    }
    html += '</div>';
    bubble.innerHTML = html;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

/**
 * Append an agent response bubble (explore chat version).
 */
function _appendExploreChatBubble(container, speaker, content, avatarUrl, responseTimeMs) {
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
function _appendExploreHumanBubble(container, content) {
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

/**
 * Update the explore chat header controls (continue/pause buttons).
 */
function _updateExploreChatControls(locationId, chatId) {
    const controls = document.getElementById('explore-chat-controls');
    if (!controls) return;
    controls.innerHTML = `
        <button class="btn btn-primary btn-sm" id="explore-chat-continue-btn" onclick="continueExploreChat('${locationId}', '${chatId}')">
            🔄 Continue Discussion
        </button>
        <button class="btn btn-danger-subtle btn-sm" onclick="closeExploreChat('${locationId}', '${chatId}')" title="End chat">
            End Chat
        </button>
    `;
}

/**
 * Send a human message in the explore chat.
 */
async function sendExploreChatMessage(locationId) {
    const chatId = window._exploreChatId;
    if (!chatId) {
        showToast('No active chat. Generate a scene first!', true);
        return;
    }
    const input = document.getElementById('explore-chat-input');
    const btn = document.getElementById('explore-chat-send-btn');
    const content = input.value.trim();
    if (!content) { input.focus(); return; }

    input.disabled = true;
    btn.disabled = true;
    btn.textContent = '⏳ Thinking…';

    const msgContainer = document.getElementById('explore-chat-messages');

    // Immediately show human bubble
    _appendExploreHumanBubble(msgContainer, content);
    input.value = '';

    // Show typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    msgContainer.appendChild(typingEl);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/chat/${encodeURIComponent(chatId)}/send-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Send failed' }));
            throw new Error(err.detail);
        }

        if (typingEl.parentNode) typingEl.remove();

        let responseTimer = startResponseTimer();
        msgContainer.appendChild(responseTimer.el);
        msgContainer.scrollTop = msgContainer.scrollHeight;

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
                    const avatarUrl = (window._exploreChatAvatarMap || {})[data.speaker.toLowerCase()];
                    _appendExploreChatBubble(msgContainer, data.speaker, data.content, avatarUrl, data.response_time_ms);
                    responseTimer = startResponseTimer();
                    msgContainer.appendChild(responseTimer.el);
                    msgContainer.scrollTop = msgContainer.scrollHeight;
                } else if (eventType === 'done') {
                    responseTimer.stop();
                    input.disabled = false;
                    btn.disabled = false;
                    btn.textContent = 'Send ➤';
                    input.focus();
                    return;
                } else if (eventType === 'error') {
                    responseTimer.stop();
                    throw new Error(data.detail);
                }
            }
        }
        responseTimer.stop();
        input.disabled = false;
        btn.disabled = false;
        btn.textContent = 'Send ➤';
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Error: ${err.message}`, true);
        input.disabled = false;
        btn.disabled = false;
        btn.textContent = 'Send ➤';
    }
}

/**
 * Trigger one round of AI-to-AI discussion in explore chat.
 */
async function continueExploreChat(locationId, chatId) {
    const msgContainer = document.getElementById('explore-chat-messages');
    const continueBtn = document.getElementById('explore-chat-continue-btn');
    if (continueBtn) continueBtn.disabled = true;

    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message chat-bubble-agent chat-typing';
    typingEl.innerHTML = `<div class="chat-msg-body"><div class="chat-msg-header"><span class="chat-msg-speaker">Participants deliberating…</span></div><div class="chat-typing-dots"><span></span><span></span><span></span></div></div>`;
    if (msgContainer) {
        msgContainer.appendChild(typingEl);
        msgContainer.scrollTop = msgContainer.scrollHeight;
    }

    try {
        const resp = await fetch(`/api/explore/${encodeURIComponent(locationId)}/chat/${encodeURIComponent(chatId)}/continue-stream`, { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Continue failed' }));
            throw new Error(err.detail);
        }

        if (typingEl.parentNode) typingEl.remove();

        let responseTimer = startResponseTimer();
        msgContainer.appendChild(responseTimer.el);
        msgContainer.scrollTop = msgContainer.scrollHeight;

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
                    const avatarUrl = (window._exploreChatAvatarMap || {})[data.speaker.toLowerCase()];
                    _appendExploreChatBubble(msgContainer, data.speaker, data.content, avatarUrl, data.response_time_ms);
                    responseTimer = startResponseTimer();
                    msgContainer.appendChild(responseTimer.el);
                    msgContainer.scrollTop = msgContainer.scrollHeight;
                } else if (eventType === 'done') {
                    responseTimer.stop();
                    _updateExploreChatControls(locationId, chatId);
                    return;
                } else if (eventType === 'error') {
                    responseTimer.stop();
                    throw new Error(data.detail);
                }
            }
        }
        responseTimer.stop();
    } catch (err) {
        if (typingEl.parentNode) typingEl.remove();
        showToast(`Error: ${err.message}`, true);
        if (continueBtn) continueBtn.disabled = false;
    }
}

/**
 * Close / end the explore chat.
 */
async function closeExploreChat(locationId, chatId) {
    if (!confirm('End this exploration discussion?')) return;
    try {
        await fetch(`/api/chat/${encodeURIComponent(chatId)}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        showToast('Exploration chat ended ✅');
        window._exploreChatId = null;
        // Reset to placeholder state
        const inputBar = document.getElementById('explore-chat-input-bar');
        if (inputBar) inputBar.style.display = 'none';
        const controls = document.getElementById('explore-chat-controls');
        if (controls) controls.innerHTML = '';
        const msgContainer = document.getElementById('explore-chat-messages');
        if (msgContainer) msgContainer.innerHTML = '<div class="chat-empty">Chat ended. Generate a new scene to start a new discussion.</div>';
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

// ═══════════════════════════════════════════════════════════════
// Characters View
// ═══════════════════════════════════════════════════════════════

