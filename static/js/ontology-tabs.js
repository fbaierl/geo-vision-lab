/**
 * Ontology Tab Manager - handles tab switching and delegates to sub-modules
 */

import { renderCards } from './ontology-cards.js';
import { renderJsonTree, expandAllJson, collapseAllJson, copyJsonToClipboard, downloadJson } from './ontology-json-tree.js';
import { getNetworkInstance } from './graph.js';

const TYPE_COLORS = {
    Person: '#D97706',
    Location: '#2563EB',
    Organization: '#4F46E5',
    Event: '#DC2626',
    Equipment: '#059669',
    Concept: '#9333EA',
    default: '#4B5563'
};

export class OntologyTabManager {
    constructor() {
        this.currentTab = 'graph';
        this.currentOntology = { entities: {}, links: {} };
        this.cardFilter = 'all';
        this.selectedGraphNodeIds = [];
        this.init();
    }

    init() {
        // Tab switching
        document.querySelectorAll('.ontology-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const targetTab = e.target.closest('.ontology-tab')?.dataset.tab;
                if (targetTab) this.switchTab(targetTab);
            });
        });

        // Toolbar actions
        document.getElementById('json-expand-all')?.addEventListener('click', () => expandAllJson());
        document.getElementById('json-collapse-all')?.addEventListener('click', () => collapseAllJson());
        document.getElementById('json-copy')?.addEventListener('click', () => copyJsonToClipboard(this.currentOntology));
        document.getElementById('json-download')?.addEventListener('click', () => downloadJson(this.currentOntology));

        // Card filter buttons
        document.querySelectorAll('.card-toolbar-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const filter = e.target.closest('.card-toolbar-btn')?.dataset.cardFilter;
                if (filter) this.setCardFilter(filter);
            });
        });

        // Table sortable headers
        document.querySelectorAll('.data-table th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const sortKey = th.dataset.sort;
                const tableId = th.closest('table').id;
                this.sortTable(tableId, sortKey);
            });
        });

        // Discover relationships button
        this.discoverBtn = document.getElementById('discover-relationships-btn');
        this.discoverBtn?.addEventListener('click', () => this._discoverRelationships());

        // Selection panel clear button
        document.getElementById('graph-selection-clear')?.addEventListener('click', () => {
            const network = getNetworkInstance();
            if (network) {
                network.unselectAll();
            }
            this.selectedGraphNodeIds = [];
            this._updateDiscoverButton();
            this._renderSelectionPanel();
        });

        // Listen for graph selection changes
        document.addEventListener('graph-selection-change', (e) => {
            this.selectedGraphNodeIds = e.detail.selectedIds || [];
            this._updateDiscoverButton();
            this._renderSelectionPanel();
        });
    }

    _getEntityByUuid(uuid) {
        // Check current ontology
        if (this.currentOntology.entities && this.currentOntology.entities[uuid]) {
            return this.currentOntology.entities[uuid];
        }
        // Check pending ontology
        const pending = window.pendingOntologyManager?.pendingOntology;
        if (pending && pending.entities && pending.entities[uuid]) {
            return pending.entities[uuid];
        }
        return null;
    }

    _renderSelectionPanel() {
        const panel = document.getElementById('graph-selection-panel');
        const list = document.getElementById('graph-selection-list');
        const countEl = document.getElementById('graph-selection-count');
        if (!panel || !list || !countEl) return;

        const count = this.selectedGraphNodeIds.length;
        countEl.textContent = count;

        if (count === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';

        const html = this.selectedGraphNodeIds.map(uuid => {
            const ent = this._getEntityByUuid(uuid);
            if (!ent) return '';
            const color = TYPE_COLORS[ent.type] || TYPE_COLORS.default;
            const name = this.escapeHtml(ent.name || 'Unknown');
            const type = this.escapeHtml(ent.type || 'Unknown');
            return `
                <div class="graph-selection-item">
                    <span class="dot" style="background: ${color};"></span>
                    <span class="name" title="${name}">${name}</span>
                    <span class="type">${type}</span>
                </div>
            `;
        }).join('');

        list.innerHTML = html || '<div class="graph-selection-item"><span class="name" style="color:var(--text-muted)">Unknown entity</span></div>';
    }

    _updateDiscoverButton() {
        if (!this.discoverBtn) return;
        const count = this.selectedGraphNodeIds.length;
        const countEl = document.getElementById('selection-count');
        if (count >= 2) {
            this.discoverBtn.disabled = false;
            if (countEl) countEl.textContent = count;
        } else {
            this.discoverBtn.disabled = true;
            if (countEl) countEl.textContent = '';
        }
    }

    async _discoverRelationships() {
        if (this.selectedGraphNodeIds.length < 2) return;

        const btn = this.discoverBtn;
        const spinner = btn.querySelector('.btn-spinner');
        btn.disabled = true;
        if (spinner) spinner.style.display = 'inline-block';

        const threadId = localStorage.getItem('geovision_thread_id') || 'default';

        try {
            const res = await fetch(`/api/sessions/${threadId}/discover-relationships`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entity_uuids: this.selectedGraphNodeIds }),
            });

            if (res.ok) {
                const data = await res.json();
                // Add to Intelligence Log so the user can inspect the LLM prompt
                if (data.prompt) {
                    if (!window.sourceLog) window.sourceLog = [];
                    const entry = {
                        query: `Discover relationships (${this.selectedGraphNodeIds.length} entities)`,
                        timestamp: Date.now(),
                        response: data.message || `Discovered ${data.links_discovered || 0} relationships, ${data.entities_discovered || 0} new entities`,
                        tools: [],
                        prompt: data.prompt,
                    };
                    window.sourceLog.push(entry);
                    try {
                        fetch(`/api/sessions/${threadId}/intel-log`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(entry),
                        });
                    } catch (e) {
                        console.warn('[INTEL_LOG] Failed to persist:', e);
                    }
                    if (window.mainTabManager) {
                        window.mainTabManager._renderIntelLog();
                    }
                }
                // Refresh pending ontology
                if (window.pendingOntologyManager) {
                    await window.pendingOntologyManager.loadPendingOntology();
                }
                // Show success notification via pending status
                if (window.pendingOntologyManager) {
                    window.pendingOntologyManager._showStatus(
                        `Discovered ${data.links_discovered} relationships (${data.entities_discovered} new entities)`,
                        'success'
                    );
                }
            } else {
                const err = await res.text();
                console.error('[DISCOVER] Failed:', err);
                if (window.pendingOntologyManager) {
                    window.pendingOntologyManager._showStatus('Discovery failed', 'error');
                }
            }
        } catch (e) {
            console.error('[DISCOVER] Error:', e);
            if (window.pendingOntologyManager) {
                window.pendingOntologyManager._showStatus('Discovery failed', 'error');
            }
        } finally {
            if (spinner) spinner.style.display = 'none';
            this._updateDiscoverButton();
        }
    }

    switchTab(tabId) {
        this.currentTab = tabId;

        // Update tab buttons
        document.querySelectorAll('.ontology-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabId);
        });

        // Update content visibility
        document.querySelectorAll('.ontology-tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabId}-tab-content`);
        });

        // Render content for specific tabs
        if (tabId === 'json') {
            renderJsonTree(this.currentOntology);
        } else if (tabId === 'table') {
            this.renderTables(this.currentOntology);
        } else if (tabId === 'card') {
            renderCards(this.currentOntology, this.cardFilter);
        }
    }

    updateOntology(ontology) {
        this.currentOntology = ontology;

        // Update stats
        const entityCount = Object.keys(ontology.entities || {}).length;
        const linkCount = Object.keys(ontology.links || {}).length;

        document.getElementById('json-entity-count').textContent = `${entityCount} entit${entityCount === 1 ? 'y' : 'ies'}`;
        document.getElementById('json-link-count').textContent = `${linkCount} relationship${linkCount === 1 ? 'y' : 'ships'}`;

        // Re-render based on current tab
        if (this.currentTab === 'json') {
            renderJsonTree(ontology);
        } else if (this.currentTab === 'table') {
            this.renderTables(ontology);
        } else if (this.currentTab === 'card') {
            renderCards(ontology, this.cardFilter);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // TABLE VIEW
    // ═══════════════════════════════════════════════════════════════

    renderTables(ontology) {
        const entities = Object.values(ontology.entities || {});
        const links = Object.values(ontology.links || {});

        // Update counts
        document.getElementById('table-entity-count').textContent = entities.length;
        document.getElementById('table-link-count').textContent = links.length;

        // Render entities table
        const entitiesBody = document.getElementById('entities-table-body');
        if (entitiesBody) {
            entitiesBody.innerHTML = entities.map(e => {
                const mentionCount = e.mentions?.length || 0;
                const createdDate = e.created_at ? new Date(e.created_at).toLocaleDateString() : '-';
                return `<tr>
                    <td>${this.escapeHtml(e.name || 'Unknown')}</td>
                    <td><span class="entity-type ${e.type || 'Thing'}">${e.type || 'Thing'}</span></td>
                    <td>${mentionCount}</td>
                    <td>${createdDate}</td>
                </tr>`;
            }).join('');
        }

        // Render links table
        const linksBody = document.getElementById('links-table-body');
        if (linksBody) {
            linksBody.innerHTML = links.map(link => {
                const sourceUuid = link.source_uuid || link.source_id || link.source;
                const targetUuid = link.target_uuid || link.target_id || link.target;
                const sourceEntity = ontology.entities && ontology.entities[sourceUuid];
                const targetEntity = ontology.entities && ontology.entities[targetUuid];
                const sourceName = sourceEntity ? sourceEntity.name : 'Unknown';
                const targetName = targetEntity ? targetEntity.name : 'Unknown';
                const mentionCount = link.mentions?.length || 0;

                return `<tr>
                    <td>${this.escapeHtml(sourceName)}</td>
                    <td>${this.escapeHtml(targetName)}</td>
                    <td>${link.type || 'related'}</td>
                    <td>${mentionCount}</td>
                </tr>`;
            }).join('');
        }
    }

    sortTable(tableId, sortKey) {
        const table = document.getElementById(tableId);
        const tbody = table?.querySelector('tbody');
        if (!tbody) return;

        const rows = Array.from(tbody.querySelectorAll('tr'));
        const th = table.querySelector(`th[data-sort="${sortKey}"]`);
        const isAsc = !th.classList.contains('sorted-asc');

        // Clear sort indicators
        table.querySelectorAll('th.sortable').forEach(h => {
            h.classList.remove('sorted-asc', 'sorted-desc');
        });
        th.classList.add(isAsc ? 'sorted-asc' : 'sorted-desc');

        rows.sort((a, b) => {
            const cells = a.querySelectorAll('td');
            let aVal, bVal;

            if (sortKey === 'name') {
                aVal = cells[0].textContent.toLowerCase();
                bVal = cells[0].textContent.toLowerCase();
            } else if (sortKey === 'type') {
                aVal = cells[1].textContent.toLowerCase();
                bVal = cells[1].textContent.toLowerCase();
            } else if (sortKey === 'mentions') {
                aVal = parseInt(cells[2].textContent) || 0;
                bVal = parseInt(cells[2].textContent) || 0;
            } else {
                return 0;
            }

            if (aVal < bVal) return isAsc ? -1 : 1;
            if (aVal > bVal) return isAsc ? 1 : -1;
            return 0;
        });

        rows.forEach(row => tbody.appendChild(row));
    }

    setCardFilter(filter) {
        this.cardFilter = filter;

        // Update button states
        document.querySelectorAll('.card-toolbar-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.cardFilter === filter);
        });

        // Re-render cards
        renderCards(this.currentOntology, this.cardFilter);
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}
