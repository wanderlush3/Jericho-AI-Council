async function renderImageGallery(entityType, entityId) {
    _galleryEntityType = entityType;
    _galleryEntityId = entityId;

    try {
        const images = await api(`/api/images/${entityType}/${encodeURIComponent(entityId)}`);
        _galleryImages = images;
    } catch {
        _galleryImages = [];
    }

    const thumbs = _galleryImages.map((img, idx) => {
        const primaryBadge = img.is_primary
            ? '<div class="gallery-primary-badge">⭐ Primary</div>'
            : '';

        const promptIndicator = img.prompt
            ? `<div class="gallery-prompt-indicator" title="View prompt info">ℹ
                 <div class="gallery-prompt-tooltip">
                     <strong>Prompt</strong>${escapeHtml(img.prompt)}
                     ${img.negative_prompt ? `<strong>Negative</strong>${escapeHtml(img.negative_prompt)}` : ''}
                     ${img.template_id ? `<strong>Template</strong>${escapeHtml(img.template_id)}` : ''}
                 </div>
               </div>`
            : '';

        const actions = `
            <div class="gallery-actions">
                ${!img.is_primary ? `<button class="gallery-action-btn gallery-action-primary" onclick="event.stopPropagation(); gallerySetPrimary('${img.id}')" title="Set as primary">⭐</button>` : ''}
                <button class="gallery-action-btn" onclick="event.stopPropagation(); galleryDownload('${img.id}')" title="Download">⬇</button>
                <button class="gallery-action-btn gallery-action-delete" onclick="event.stopPropagation(); galleryDelete('${img.id}')" title="Delete">🗑️</button>
            </div>`;

        return `
            <div class="gallery-thumb" onclick="openGalleryLightbox(${idx})">
                ${primaryBadge}
                ${promptIndicator}
                <img src="${img.url}" alt="Image ${img.id}" loading="lazy" />
                ${actions}
            </div>`;
    }).join('');

    const uploadZone = `
        <div class="gallery-upload-zone" id="gallery-upload-zone"
             onclick="openGalleryUpload('${entityType}', '${escapeAttr(entityId)}')"
             title="Upload a new image">
            <div class="gallery-upload-icon">📁</div>
            <span>Upload</span>
        </div>`;

    return `
        <div class="image-gallery detail-section" id="entity-gallery">
            <div class="gallery-header">
                <h4>🖼️ Image Gallery (${_galleryImages.length})</h4>
                <button class="btn btn-sm btn-generate" onclick="openGenerateModal('${entityType}', '${escapeAttr(entityId)}')" title="Generate a new image with AI">
                    🎨 Generate Image
                </button>
            </div>
            <div class="gallery-grid">
                ${thumbs}
                ${uploadZone}
            </div>
            <div id="generate-progress-inline"></div>
        </div>`;
}

/* ── Lightbox ────────────────────────────────────────────────── */

function openGalleryLightbox(index) {
    if (!_galleryImages.length) return;
    if (index < 0) index = _galleryImages.length - 1;
    if (index >= _galleryImages.length) index = 0;

    const img = _galleryImages[index];
    const overlay = document.createElement('div');
    overlay.className = 'gallery-lightbox';
    overlay.id = 'gallery-lightbox';
    overlay.innerHTML = `
        <div class="gallery-lb-content">
            <button class="gallery-lb-close" onclick="closeGalleryLightbox()" title="Close">✕</button>
            ${_galleryImages.length > 1
                ? `<button class="gallery-lb-nav gallery-lb-prev" onclick="navigateGalleryLb(${index - 1})">◀</button>
                   <button class="gallery-lb-nav gallery-lb-next" onclick="navigateGalleryLb(${index + 1})">▶</button>`
                : ''}
            <img src="${img.url}" alt="${img.id}" />
            <div class="gallery-lb-info">
                <span>${img.id} · ${index + 1} / ${_galleryImages.length}${img.is_primary ? ' · ⭐ Primary' : ''}</span>
                <div class="gallery-lb-actions">
                    ${!img.is_primary ? `<button class="gallery-lb-action-btn" onclick="gallerySetPrimary('${img.id}')">⭐ Set Primary</button>` : ''}
                    <button class="gallery-lb-action-btn" onclick="galleryDownload('${img.id}')">⬇ Download</button>
                    <button class="gallery-lb-action-btn" onclick="galleryDelete('${img.id}')">🗑️ Delete</button>
                </div>
            </div>
            ${img.prompt ? `<div style="color:rgba(255,255,255,0.5);font-size:0.75rem;max-width:600px;text-align:center;margin-top:var(--space-xs)">
                <strong style="color:rgba(255,255,255,0.7)">Prompt:</strong> ${escapeHtml(img.prompt)}
            </div>` : ''}
        </div>`;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeGalleryLightbox();
    });
    document.body.appendChild(overlay);

    // Keyboard navigation
    overlay._keyHandler = (e) => {
        if (e.key === 'Escape') closeGalleryLightbox();
        if (e.key === 'ArrowLeft') navigateGalleryLb(index - 1);
        if (e.key === 'ArrowRight') navigateGalleryLb(index + 1);
    };
    document.addEventListener('keydown', overlay._keyHandler);
}

function closeGalleryLightbox() {
    const lb = document.getElementById('gallery-lightbox');
    if (lb) {
        if (lb._keyHandler) document.removeEventListener('keydown', lb._keyHandler);
        lb.remove();
    }
}

function navigateGalleryLb(index) {
    closeGalleryLightbox();
    openGalleryLightbox(index);
}

/* ── Upload Modal ────────────────────────────────────────────── */

let _galleryUploadData = null;

function openGalleryUpload(entityType, entityId) {
    _galleryUploadData = null;
    const modal = document.createElement('div');
    modal.className = 'gallery-upload-modal';
    modal.id = 'gallery-upload-modal';
    modal.innerHTML = `
        <div class="gallery-upload-modal-content">
            <h3>📁 Upload Image — ${entityType}/${entityId}</h3>
            <div class="gallery-upload-drop" id="gallery-upload-drop"
                 onclick="document.getElementById('gallery-file-input').click()">
                <input type="file" id="gallery-file-input" accept="image/png,image/jpeg,image/webp"
                       style="display:none" onchange="handleGalleryFileSelect(event)" />
                <div class="gallery-upload-icon" style="font-size:2rem;margin-bottom:var(--space-sm)">📁</div>
                <div style="color:var(--text-secondary);font-size:0.85rem">Click or drag an image here</div>
                <div style="color:var(--text-muted);font-size:0.72rem;margin-top:var(--space-xs)">PNG, JPEG, or WebP</div>
                <img id="gallery-upload-preview-img" class="gallery-upload-preview" />
            </div>
            <div class="gallery-upload-footer">
                <button class="btn btn-secondary" onclick="closeGalleryUpload()">Cancel</button>
                <button class="btn btn-primary" id="gallery-upload-save-btn"
                        onclick="submitGalleryUpload('${entityType}', '${escapeAttr(entityId)}')" disabled>
                    📤 Upload
                </button>
            </div>
        </div>`;

    // Drag and drop
    setTimeout(() => {
        const drop = document.getElementById('gallery-upload-drop');
        if (drop) {
            drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('gallery-drag-over'); };
            drop.ondragleave = () => drop.classList.remove('gallery-drag-over');
            drop.ondrop = (e) => {
                e.preventDefault();
                drop.classList.remove('gallery-drag-over');
                const file = e.dataTransfer.files[0];
                if (file) loadGalleryFile(file);
            };
        }
    }, 50);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeGalleryUpload();
    });
    document.body.appendChild(modal);
}

function closeGalleryUpload() {
    const m = document.getElementById('gallery-upload-modal');
    if (m) m.remove();
    _galleryUploadData = null;
}

function handleGalleryFileSelect(event) {
    const file = event.target.files[0];
    if (file) loadGalleryFile(file);
}

function loadGalleryFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        _galleryUploadData = { dataUrl: e.target.result, filename: file.name };
        const preview = document.getElementById('gallery-upload-preview-img');
        if (preview) {
            preview.src = e.target.result;
            preview.style.display = 'block';
        }
        const btn = document.getElementById('gallery-upload-save-btn');
        if (btn) btn.disabled = false;
    };
    reader.readAsDataURL(file);
}

async function submitGalleryUpload(entityType, entityId) {
    if (!_galleryUploadData) return;
    const btn = document.getElementById('gallery-upload-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading…'; }

    try {
        const resp = await fetch(`/api/images/${entityType}/${encodeURIComponent(entityId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_data: _galleryUploadData.dataUrl,
                original_filename: _galleryUploadData.filename || '',
            }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail);
        }
        showToast('Image uploaded ✅');
        closeGalleryUpload();
        await refreshGallery();
    } catch (err) {
        showToast(`Upload error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '📤 Upload'; }
    }
}

/* ── Gallery Actions ──────────────────────────────────────────── */

async function gallerySetPrimary(imageId) {
    try {
        await fetch(`/api/images/set-primary/${imageId}`, { method: 'POST' });
        showToast('Primary image updated ⭐');
        closeGalleryLightbox();
        await refreshGallery();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

async function galleryDelete(imageId) {
    if (!confirm('Delete this image?')) return;
    try {
        const resp = await fetch(`/api/images/delete/${imageId}`, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Delete failed' }));
            throw new Error(err.detail);
        }
        showToast('Image deleted 🗑️');
        closeGalleryLightbox();
        await refreshGallery();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
    }
}

function galleryDownload(imageId) {
    const link = document.createElement('a');
    link.href = `/api/images/file/${imageId}`;
    link.download = `${imageId}.png`;
    link.click();
}

/**
 * Re-render just the gallery section without reloading the entire page.
 */
async function refreshGallery() {
    const container = document.getElementById('entity-gallery');
    if (!container || !_galleryEntityType || !_galleryEntityId) return;
    const html = await renderImageGallery(_galleryEntityType, _galleryEntityId);
    container.outerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
// Generation Pipeline & Progress UI (F-037f)
// ═══════════════════════════════════════════════════════════════

let _generateEntityType = '';
let _generateEntityId = '';
let _generateActiveJobId = null;
let _generateEventSource = null;
let _generateMembers = [];

/**
 * Open the AI image generation modal for any entity.
 */
