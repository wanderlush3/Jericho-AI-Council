function obeliskBadge(balance) {
    if (!balance) return '';
    const parts = [];
    if (balance.gold)   parts.push(`<span class="obelisk-coin obelisk-gold">🥇 ${balance.gold}</span>`);
    if (balance.silver) parts.push(`<span class="obelisk-coin obelisk-silver">🥈 ${balance.silver}</span>`);
    if (balance.bronze) parts.push(`<span class="obelisk-coin obelisk-bronze">🥉 ${balance.bronze}</span>`);
    if (!parts.length)  parts.push(`<span class="obelisk-coin obelisk-empty">— empty —</span>`);
    return `<div class="obelisk-balance">${parts.join('')}</div>`;
}

function obeliskTotal(balance) {
    if (!balance) return '0.00';
    const rate = 100;
    const totalBronze = (balance.gold || 0) * rate * rate + (balance.silver || 0) * rate + (balance.bronze || 0);
    return (totalBronze / (rate * rate)).toFixed(2);
}

async function renderTreasury() {
    showLoading();
    const typeFilter = state._treasuryFilter || '';
    const url = typeFilter ? `/api/treasury?type=${encodeURIComponent(typeFilter)}` : '/api/treasury';
    const data = await api(url);

    const filterOptions = ['', 'council_member', 'character', 'user', 'government']
        .map(t => `<option value="${t}" ${t === typeFilter ? 'selected' : ''}>${t ? (ACCT_TYPE_LABELS[t]?.label || t) : 'All Types'}</option>`)
        .join('');

    if (!data.length) {
        $main().innerHTML = `
            <div class="view-enter">
                <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div>
                        <h2>🪙 Treasury — Obelisk Accounts</h2>
                        <p>No treasury accounts found. Initialize to create default accounts.</p>
                    </div>
                    <div style="display:flex;gap:var(--space-sm)">
                        <select class="settings-input" style="min-width:140px" onchange="state._treasuryFilter=this.value;renderTreasury()" id="treasury-filter">${filterOptions}</select>
                        <button class="btn btn-primary" onclick="initializeTreasury()" id="btn-treasury-init">⚡ Initialize Treasury</button>
                    </div>
                </div>
                <div class="empty-state"><div class="empty-icon">🪙</div><p>Click "Initialize Treasury" to create accounts for all council members, characters, and the government.</p></div>
            </div>`;
        return;
    }

    const cards = data.map(a => {
        const meta = ACCT_TYPE_LABELS[a.account_type] || { icon: '💰', label: a.account_type, badge: 'default' };
        const total = obeliskTotal(a.balance);
        return `
        <div class="card card-clickable treasury-card" onclick="navigateTo('treasury','${a.account_id}')">
            <div class="treasury-card-header">
                <div class="treasury-card-icon">${meta.icon}</div>
                <div class="treasury-card-info">
                    <div class="treasury-card-owner">${escapeHtml(a.owner_name)}</div>
                    <div class="treasury-card-id">${a.account_id}</div>
                </div>
                ${badge(meta.label, meta.badge)}
            </div>
            ${obeliskBadge(a.balance)}
            <div class="treasury-card-total">≈ ${total} Gold equivalent</div>
        </div>`;
    }).join('');

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
                <div>
                    <h2>🪙 Treasury — Obelisk Accounts</h2>
                    <p>${data.length} account${data.length !== 1 ? 's' : ''} across the Jericho economy</p>
                </div>
                <div style="display:flex;gap:var(--space-sm);flex-wrap:wrap">
                    <select class="settings-input" style="min-width:140px" onchange="state._treasuryFilter=this.value;renderTreasury()" id="treasury-filter">${filterOptions}</select>
                    <button class="btn btn-primary" onclick="initializeTreasury()" id="btn-treasury-init">⚡ Initialize</button>
                    <button class="btn btn-secondary" onclick="openTransferModal()" id="btn-treasury-transfer">💸 Transfer</button>
                </div>
            </div>
            <div class="treasury-grid">${cards}</div>
        </div>`;
}

async function renderTreasuryDetail(accountId) {
    showLoading();
    let data;
    try {
        data = await api(`/api/treasury/${encodeURIComponent(accountId)}`);
    } catch (err) {
        showError(`Account not found: ${accountId}`);
        return;
    }
    const meta = ACCT_TYPE_LABELS[data.account_type] || { icon: '💰', label: data.account_type, badge: 'default' };
    const total = obeliskTotal(data.balance);

    $main().innerHTML = `
        <div class="view-enter">
            <button class="back-btn" onclick="navigateTo('treasury')">← Back to Treasury</button>
            <div class="detail-panel">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-lg)">
                    <div>
                        <div style="font-size:0.78rem;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan);margin-bottom:var(--space-xs)">${data.account_id}</div>
                        <div style="font-size:1.4rem;font-weight:700">${meta.icon} ${escapeHtml(data.owner_name)}</div>
                        <div style="color:var(--text-secondary);margin-top:var(--space-xs);font-size:0.87rem">
                            ${badge(meta.label, meta.badge)}
                            · Created ${formatDate(data.created_at)}
                            ${data.updated_at ? ` · Updated ${formatDate(data.updated_at)}` : ''}
                        </div>
                    </div>
                    <button class="detail-close" onclick="navigateTo('treasury')">✕</button>
                </div>

                <!-- Balance Display -->
                <div class="detail-section treasury-balance-panel">
                    <h4>💰 Obelisk Balance</h4>
                    <div class="treasury-balance-grid">
                        <div class="treasury-tier treasury-tier-gold">
                            <div class="treasury-tier-icon">🥇</div>
                            <div class="treasury-tier-value">${data.balance.gold}</div>
                            <div class="treasury-tier-label">Gold</div>
                        </div>
                        <div class="treasury-tier treasury-tier-silver">
                            <div class="treasury-tier-icon">🥈</div>
                            <div class="treasury-tier-value">${data.balance.silver}</div>
                            <div class="treasury-tier-label">Silver</div>
                        </div>
                        <div class="treasury-tier treasury-tier-bronze">
                            <div class="treasury-tier-icon">🥉</div>
                            <div class="treasury-tier-value">${data.balance.bronze}</div>
                            <div class="treasury-tier-label">Bronze</div>
                        </div>
                    </div>
                    <div class="treasury-total-display">≈ <strong>${total}</strong> Gold equivalent</div>
                </div>

                <!-- Credit Form -->
                <div class="detail-section">
                    <h4>➕ Credit Funds</h4>
                    <div class="treasury-action-form" id="credit-form">
                        <div class="treasury-input-row">
                            <div class="treasury-input-group">
                                <label>Gold</label>
                                <input type="number" id="credit-gold" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Silver</label>
                                <input type="number" id="credit-silver" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Bronze</label>
                                <input type="number" id="credit-bronze" class="settings-input" value="0" min="0" />
                            </div>
                            <button class="btn btn-primary" onclick="treasuryCredit('${data.account_id}')" id="btn-credit">➕ Credit</button>
                        </div>
                    </div>
                </div>

                <!-- Debit Form -->
                <div class="detail-section">
                    <h4>➖ Debit Funds</h4>
                    <div class="treasury-action-form" id="debit-form">
                        <div class="treasury-input-row">
                            <div class="treasury-input-group">
                                <label>Gold</label>
                                <input type="number" id="debit-gold" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Silver</label>
                                <input type="number" id="debit-silver" class="settings-input" value="0" min="0" />
                            </div>
                            <div class="treasury-input-group">
                                <label>Bronze</label>
                                <input type="number" id="debit-bronze" class="settings-input" value="0" min="0" />
                            </div>
                            <button class="btn btn-secondary" onclick="treasuryDebit('${data.account_id}')" id="btn-debit" style="border-color:var(--accent-rose)">➖ Debit</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
}

async function initializeTreasury() {
    const btn = document.getElementById('btn-treasury-init');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Initializing…'; }

    try {
        const resp = await fetch('/api/treasury/initialize', { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Failed' }));
            throw new Error(err.detail);
        }
        const data = await resp.json();
        showToast(`Treasury initialized — ${data.created_count} account${data.created_count !== 1 ? 's' : ''} created ✅`);
        await renderTreasury();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Initialize Treasury'; }
    }
}

async function treasuryCredit(accountId) {
    const gold   = parseInt(document.getElementById('credit-gold').value)   || 0;
    const silver = parseInt(document.getElementById('credit-silver').value) || 0;
    const bronze = parseInt(document.getElementById('credit-bronze').value) || 0;
    if (!gold && !silver && !bronze) { showToast('Enter an amount to credit.', true); return; }

    const btn = document.getElementById('btn-credit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }

    try {
        const resp = await fetch(`/api/treasury/${encodeURIComponent(accountId)}/credit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Credit failed' }));
            throw new Error(err.detail);
        }
        showToast(`Credited ${gold}G ${silver}S ${bronze}B ✅`);
        await renderTreasuryDetail(accountId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '➕ Credit'; }
    }
}

async function treasuryDebit(accountId) {
    const gold   = parseInt(document.getElementById('debit-gold').value)   || 0;
    const silver = parseInt(document.getElementById('debit-silver').value) || 0;
    const bronze = parseInt(document.getElementById('debit-bronze').value) || 0;
    if (!gold && !silver && !bronze) { showToast('Enter an amount to debit.', true); return; }

    const btn = document.getElementById('btn-debit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }

    try {
        const resp = await fetch(`/api/treasury/${encodeURIComponent(accountId)}/debit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Debit failed' }));
            throw new Error(err.detail);
        }
        showToast(`Debited ${gold}G ${silver}S ${bronze}B ✅`);
        await renderTreasuryDetail(accountId);
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '➖ Debit'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Taxation View (F-034)
// ═══════════════════════════════════════════════════════════════

async function renderTaxation() {
    showLoading();
    let summary, events;
    try {
        [summary, events] = await Promise.all([
            api('/api/tax/summary'),
            api('/api/tax/events?limit=50'),
        ]);
    } catch (err) {
        showError('Failed to load taxation data: ' + err.message);
        return;
    }

    const policy = summary.policy || {};
    const total = summary.total_collected || {};
    const ratePct = Math.round((policy.rate || 0) * 100);
    const exempt = (policy.exempt_account_types || []).join(', ') || 'none';

    const eventsRows = events.length
        ? events.map(e => `
            <tr>
                <td style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:var(--accent-cyan)">${escapeHtml(e.event_id)}</td>
                <td>${escapeHtml(e.from_account)}</td>
                <td>${escapeHtml(e.to_account)}</td>
                <td>${obeliskBadge({gold: e.transaction_gold, silver: e.transaction_silver, bronze: e.transaction_bronze})}</td>
                <td>${obeliskBadge({gold: e.tax_gold, silver: e.tax_silver, bronze: e.tax_bronze})}</td>
                <td>${Math.round(e.tax_rate * 100)}%</td>
                <td style="font-size:0.8rem;color:var(--text-muted)">${formatDate(e.timestamp)}</td>
            </tr>`).join('')
        : '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:var(--space-lg)">No tax events recorded yet. Tax is collected automatically on transfers between non-exempt accounts.</td></tr>';

    $main().innerHTML = `
        <div class="view-enter">
            <div class="page-header">
                <h2>🏛️ Taxation — Obelisk Tax System</h2>
                <p>Government tax policy and collection ledger</p>
            </div>

            <div class="tax-panels-grid">
                <!-- Policy Panel -->
                <div class="card tax-policy-panel">
                    <h3>📋 Tax Policy</h3>
                    <div class="tax-policy-fields">
                        <div class="tax-field">
                            <label>Status</label>
                            <div class="tax-toggle-row">
                                <span class="badge badge-${policy.enabled ? 'active' : 'archived'}">${policy.enabled ? 'Enabled' : 'Disabled'}</span>
                                <button class="btn btn-sm" onclick="toggleTaxEnabled(${!policy.enabled})" id="btn-tax-toggle">
                                    ${policy.enabled ? '⏸ Disable' : '▶ Enable'}
                                </button>
                            </div>
                        </div>
                        <div class="tax-field">
                            <label for="tax-rate-slider">Tax Rate: <strong id="tax-rate-display">${ratePct}%</strong></label>
                            <div class="tax-rate-slider-row">
                                <input type="range" id="tax-rate-slider" class="tax-rate-slider" min="0" max="50" value="${ratePct}"
                                    oninput="document.getElementById('tax-rate-display').textContent = this.value + '%'" />
                                <button class="btn btn-sm btn-primary" onclick="updateTaxRate()" id="btn-tax-rate">Save</button>
                            </div>
                        </div>
                        <div class="tax-field">
                            <label>Exempt Account Types</label>
                            <div class="tax-exempt-list">
                                ${(policy.exempt_account_types || ['government']).map(t => `<span class="tax-exempt-badge">${t}</span>`).join('')}
                            </div>
                        </div>
                        <div class="tax-field" style="margin-top:var(--space-xs)">
                            <span style="font-size:0.78rem;color:var(--text-muted)">Last updated: ${formatDate(policy.updated_at)}</span>
                        </div>
                    </div>
                </div>

                <!-- Revenue Summary -->
                <div class="card tax-revenue-panel">
                    <h3>💰 Revenue Summary</h3>
                    <div class="tax-revenue-stats">
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${summary.event_count || 0}</div>
                            <div class="tax-rev-label">Total Events</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.gold || 0}</div>
                            <div class="tax-rev-label">🥇 Gold Collected</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.silver || 0}</div>
                            <div class="tax-rev-label">🥈 Silver Collected</div>
                        </div>
                        <div class="tax-rev-stat">
                            <div class="tax-rev-value">${total.bronze || 0}</div>
                            <div class="tax-rev-label">🥉 Bronze Collected</div>
                        </div>
                    </div>
                    ${obeliskBadge(total)}
                    <div class="treasury-total-display" style="margin-top:var(--space-sm)">≈ <strong>${obeliskTotal(total)}</strong> Gold equivalent total tax revenue</div>
                </div>
            </div>

            <!-- Tax Events Log -->
            <div class="card" style="margin-top:var(--space-lg)">
                <h3>📜 Tax Collection Ledger</h3>
                <div class="table-container">
                    <table class="data-table tax-events-table">
                        <thead>
                            <tr>
                                <th>Event ID</th>
                                <th>From</th>
                                <th>To</th>
                                <th>Transaction</th>
                                <th>Tax Collected</th>
                                <th>Rate</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>${eventsRows}</tbody>
                    </table>
                </div>
            </div>
        </div>`;
}

async function toggleTaxEnabled(enabled) {
    const btn = document.getElementById('btn-tax-toggle');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
        await fetch('/api/tax/policy', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        showToast(enabled ? 'Tax collection enabled ✅' : 'Tax collection disabled ⏸');
        await renderTaxation();
    } catch (err) {
        showToast('Failed: ' + err.message, true);
        if (btn) { btn.disabled = false; }
    }
}

async function updateTaxRate() {
    const slider = document.getElementById('tax-rate-slider');
    const btn = document.getElementById('btn-tax-rate');
    if (!slider) return;
    const rate = parseInt(slider.value, 10) / 100;
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
        const resp = await fetch('/api/tax/policy', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rate }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({detail: 'Failed'}));
            throw new Error(err.detail);
        }
        showToast(`Tax rate updated to ${slider.value}% ✅`);
        await renderTaxation();
    } catch (err) {
        showToast('Failed: ' + err.message, true);
        if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
    }
}

// ── Transfer Modal ──────────────────────────────────────────────

async function openTransferModal() {
    try {
        const accounts = await api('/api/treasury');
        if (accounts.length < 2) {
            showToast('Need at least 2 accounts for a transfer.', true);
            return;
        }

        const optionsHtml = accounts.map(a => {
            const meta = ACCT_TYPE_LABELS[a.account_type] || { label: a.account_type };
            return `<option value="${a.account_id}">${a.owner_name} (${meta.label}) — ${a.balance.gold}G ${a.balance.silver}S ${a.balance.bronze}B</option>`;
        }).join('');

        const existing = document.getElementById('transfer-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'transfer-modal';
        modal.className = 'promote-modal';
        modal.style.display = 'flex';
        modal.innerHTML = `
            <div class="promote-modal-content" style="max-width:520px">
                <div class="promote-modal-header">
                    <h3>💸 Transfer Obelisk</h3>
                    <button class="detail-close" onclick="closeTransferModal()">✕</button>
                </div>
                <div class="promote-modal-body">
                    <div class="promote-form-group">
                        <label for="xfer-from">From Account</label>
                        <select id="xfer-from" class="settings-input">${optionsHtml}</select>
                    </div>
                    <div class="promote-form-group">
                        <label for="xfer-to">To Account</label>
                        <select id="xfer-to" class="settings-input">${optionsHtml}</select>
                    </div>
                    <div class="treasury-input-row" style="margin-top:var(--space-sm)">
                        <div class="treasury-input-group">
                            <label>Gold</label>
                            <input type="number" id="xfer-gold" class="settings-input" value="0" min="0" />
                        </div>
                        <div class="treasury-input-group">
                            <label>Silver</label>
                            <input type="number" id="xfer-silver" class="settings-input" value="0" min="0" />
                        </div>
                        <div class="treasury-input-group">
                            <label>Bronze</label>
                            <input type="number" id="xfer-bronze" class="settings-input" value="0" min="0" />
                        </div>
                    </div>
                </div>
                <div class="promote-modal-footer">
                    <button class="btn" onclick="closeTransferModal()">Cancel</button>
                    <button class="btn btn-primary" onclick="executeTransfer()" id="btn-xfer-submit">💸 Transfer</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => { if (e.target === modal) closeTransferModal(); });

        // Auto-select different to-account
        if (accounts.length >= 2) {
            document.getElementById('xfer-to').selectedIndex = 1;
        }
    } catch (err) {
        showToast('Failed to load accounts: ' + err.message, true);
    }
}

function closeTransferModal() {
    const modal = document.getElementById('transfer-modal');
    if (modal) modal.remove();
}

async function executeTransfer() {
    const fromId = document.getElementById('xfer-from').value;
    const toId   = document.getElementById('xfer-to').value;
    const gold   = parseInt(document.getElementById('xfer-gold').value)   || 0;
    const silver = parseInt(document.getElementById('xfer-silver').value) || 0;
    const bronze = parseInt(document.getElementById('xfer-bronze').value) || 0;

    if (fromId === toId) { showToast('Cannot transfer to the same account.', true); return; }
    if (!gold && !silver && !bronze) { showToast('Enter an amount to transfer.', true); return; }

    const btn = document.getElementById('btn-xfer-submit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Transferring…'; }

    try {
        const resp = await fetch('/api/treasury/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from: fromId, to: toId, gold, silver, bronze }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Transfer failed' }));
            throw new Error(err.detail);
        }
        showToast(`Transferred ${gold}G ${silver}S ${bronze}B ✅`);
        closeTransferModal();
        await renderTreasury();
    } catch (err) {
        showToast(`Error: ${err.message}`, true);
        if (btn) { btn.disabled = false; btn.textContent = '💸 Transfer'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// Evolution View (Expanded — Conv 2)
// ═══════════════════════════════════════════════════════════════

let _evoOverlayFilter = 'all';

