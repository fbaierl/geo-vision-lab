/**
 * Ontology Tab Manager - handles tab switching and delegates to sub-modules
 */

import { renderCards } from './ontology-cards.js';
import { renderJsonTree, expandAllJson, collapseAllJson, copyJsonToClipboard, downloadJson } from './ontology-json-tree.js';

export class OntologyTabManager {
    constructor() {
        this.currentTab = 'graph';
        this.currentOntology = { entities: {}, links: {} };
        this.cardFilter = 'all';
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
