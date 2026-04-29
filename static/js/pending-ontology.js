/**
 * Pending Ontology Review Module
 */

import { escapeHtml } from './utils.js';

const TYPE_COLORS = {
    Person: 'Person',
    Location: 'Location',
    Organization: 'Organization',
    Country: 'Country',
    Event: 'Event',
    Concept: 'Concept',
    Military: 'Military',
};

function typeClass(type) {
    return TYPE_COLORS[type] || 'default';
}

export class PendingOntologyManager {
    constructor() {
        this.pendingOntology = { entities: {}, links: {} };
        this.selectedEntities = new Set();
        this.selectedLinks = new Set();
        this.threadId = localStorage.getItem('geovision_thread_id') || 'default';

        this.panel = document.getElementById('pending-review-panel');
        this.content = document.getElementById('pending-content');
        this.countEl = document.getElementById('pending-count');
        this.emptyEl = document.getElementById('pending-empty');
        this.actionsEl = document.getElementById('pending-actions');
        this.statusEl = document.getElementById('pending-status');
        this.pipelinePendingDot = document.getElementById('pipeline-pending-dot');
        this.pipelinePendingCount = document.getElementById('pipeline-pending-count');

        this._bindEvents();
    }

    _bindEvents() {
        document.getElementById('pending-approve-selected')?.addEventListener('click', () => this.approveSelected());
        document.getElementById('pending-reject-selected')?.addEventListener('click', () => this.rejectSelected());
        document.getElementById('pending-approve-all')?.addEventListener('click', () => this.approveAll());
        document.getElementById('pending-reject-all')?.addEventListener('click', () => this.rejectAll());
    }

    updatePendingOntology(pendingOntology) {
        this.pendingOntology = pendingOntology || { entities: {}, links: {} };
        this.selectedEntities.clear();
        this.selectedLinks.clear();
        this._render();
        this._updatePipelineStatus();
    }

    async loadPendingOntology() {
        try {
            const res = await fetch(`/api/sessions/${this.threadId}/pending-ontology`);
            if (res.ok) {
                const data = await res.json();
                this.pendingOntology = {
                    entities: data.entities || {},
                    links: data.links || {},
                };
                this._render();
                this._updatePipelineStatus();
                const graphContainer = document.getElementById('graph-container');
                const graphEmptyState = document.getElementById('graph-empty-state');
                const hasPending = Object.keys(this.pendingOntology.entities).length > 0 ||
                                   Object.keys(this.pendingOntology.links).length > 0;
                if (graphContainer && window.renderMergedGraph) {
                    window.renderMergedGraph(graphContainer);
                }
                if (graphEmptyState && hasPending) {
                    graphEmptyState.style.display = 'none';
                }
            }
        } catch (e) {
            console.warn('[PENDING] Failed to load pending ontology:', e);
        }
    }

    async approveSelected() {
        const entityUuids = this.selectedEntities.size > 0 ? Array.from(this.selectedEntities) : null;
        const linkUuids = this.selectedLinks.size > 0 ? Array.from(this.selectedLinks) : null;
        if (!entityUuids && !linkUuids) return;
        await this._sendApprove(entityUuids, linkUuids, 'selected');
    }

    async approveAll() {
        const entityUuids = Object.keys(this.pendingOntology.entities);
        const linkUuids = Object.keys(this.pendingOntology.links);
        if (entityUuids.length === 0 && linkUuids.length === 0) return;
        await this._sendApprove(entityUuids, linkUuids, 'all');
    }

    async _reloadCommittedOntology() {
        try {
            const ontRes = await fetch(`/api/ontology/${this.threadId}`);
            if (!ontRes.ok) return;
            const ontData = await ontRes.json();
            const ontology = {
                entities: Object.fromEntries((ontData.entities || []).map(e => [e.uuid, e])),
                links: Object.fromEntries((ontData.links || []).map(l => [l.uuid, l])),
            };
            if (window.ontologyTabManager) {
                window.ontologyTabManager.updateOntology(ontology);
            }
            const graphContainer = document.getElementById('graph-container');
            const graphEmptyState = document.getElementById('graph-empty-state');
            if (graphContainer && window.renderMergedGraph) {
                window.renderMergedGraph(graphContainer);
            }
            if (graphEmptyState) {
                const hasCommitted = Object.keys(ontology.entities || {}).length > 0 ||
                                     Object.keys(ontology.links || {}).length > 0;
                const hasPending = Object.keys(this.pendingOntology.entities || {}).length > 0 ||
                                   Object.keys(this.pendingOntology.links || {}).length > 0;
                graphEmptyState.style.display = (hasCommitted || hasPending) ? 'none' : 'flex';
            }
        } catch (e) {
            console.warn('[PENDING] Failed to reload committed ontology:', e);
        }
    }

    async _sendApprove(entityUuids, linkUuids, mode) {
        const btn = mode === 'all'
            ? document.getElementById('pending-approve-all')
            : document.getElementById('pending-approve-selected');
        this._setButtonLoading(btn, true);

        try {
            const body = {};
            if (entityUuids) body.entity_uuids = entityUuids;
            if (linkUuids) body.link_uuids = linkUuids;

            const res = await fetch(`/api/sessions/${this.threadId}/pending-ontology/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (res.ok) {
                const data = await res.json();
                this._showStatus(`✓ Approved ${data.approved_entities} entities, ${data.approved_links} links`, 'success');
                await this.loadPendingOntology();
                await this._reloadCommittedOntology();
            } else {
                this._showStatus('Approval failed', 'error');
            }
        } catch (e) {
            console.error('[PENDING] Failed to approve:', e);
            this._showStatus('Approval failed', 'error');
        } finally {
            this._setButtonLoading(btn, false);
        }
    }

    async rejectSelected() {
        const entityUuids = this.selectedEntities.size > 0 ? Array.from(this.selectedEntities) : null;
        const linkUuids = this.selectedLinks.size > 0 ? Array.from(this.selectedLinks) : null;
        if (!entityUuids && !linkUuids) return;
        await this._sendReject(entityUuids, linkUuids, 'selected');
    }

    async rejectAll() {
        await this._sendReject(null, null, 'all');
    }

    async _sendReject(entityUuids, linkUuids, mode) {
        const btn = mode === 'all'
            ? document.getElementById('pending-reject-all')
            : document.getElementById('pending-reject-selected');
        this._setButtonLoading(btn, true);

        try {
            const body = {};
            if (entityUuids) body.entity_uuids = entityUuids;
            if (linkUuids) body.link_uuids = linkUuids;

            const res = await fetch(`/api/sessions/${this.threadId}/pending-ontology/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (res.ok) {
                const data = await res.json();
                this._showStatus(`✗ Rejected ${data.rejected_entities} entities, ${data.rejected_links} links`, 'error');
                await this.loadPendingOntology();
                await this._reloadCommittedOntology();
            } else {
                this._showStatus('Rejection failed', 'error');
            }
        } catch (e) {
            console.error('[PENDING] Failed to reject:', e);
            this._showStatus('Rejection failed', 'error');
        } finally {
            this._setButtonLoading(btn, false);
        }
    }

    _setButtonLoading(btn, loading) {
        if (!btn) return;
        btn.classList.toggle('loading', loading);
        btn.disabled = loading;
    }

    _showStatus(message, type) {
        if (!this.statusEl) return;
        this.statusEl.textContent = message;
        this.statusEl.className = `pending-status ${type}`;
        this.statusEl.style.display = 'inline-block';
        setTimeout(() => {
            this.statusEl.style.display = 'none';
        }, 3000);
    }

    _render() {
        const entities = this.pendingOntology.entities || {};
        const links = this.pendingOntology.links || {};
        const totalCount = Object.keys(entities).length + Object.keys(links).length;

        this.countEl.textContent = totalCount;

        if (totalCount === 0) {
            this.panel.classList.remove('has-pending');
            this.panel.classList.add('collapsed');
            this.content.style.display = 'none';
            this.actionsEl.style.display = 'none';
            this.emptyEl.style.display = 'flex';
            return;
        }

        this.panel.classList.add('has-pending');
        this.panel.classList.remove('collapsed');
        this.content.style.display = 'block';
        this.actionsEl.style.display = 'flex';
        this.emptyEl.style.display = 'none';

        let html = '';

        // Entities section
        const entityEntries = Object.entries(entities);
        if (entityEntries.length > 0) {
            html += `<div class="pending-section-header">
                <input type="checkbox" id="select-all-entities" data-section="entities">
                <span class="pending-section-title">New Entities (${entityEntries.length})</span>
            </div>`;
            for (const [uuid, entity] of entityEntries) {
                const checked = this.selectedEntities.has(uuid) ? 'checked' : '';
                const type = entity.type || 'Unknown';
                const name = escapeHtml(entity.name || 'Unnamed');
                const tc = typeClass(type);
                let meta = '';
                if (entity.properties?.lat && entity.properties?.lon) {
                    meta = `<span class="pending-item-coords">(${entity.properties.lat}, ${entity.properties.lon})</span>`;
                }
                let sourceHtml = '';
                if (entity.mentions && entity.mentions.length > 0) {
                    const src = entity.mentions[0].source_text;
                    if (src) {
                        sourceHtml = `<div class="pending-source">${escapeHtml(src.substring(0, 120))}${src.length > 120 ? '...' : ''}</div>`;
                    }
                }
                html += `
                    <div class="pending-item" data-uuid="${uuid}" data-type="entity">
                        <input type="checkbox" data-type="entity" data-uuid="${uuid}" ${checked}>
                        <div class="pending-item-body">
                            <div class="pending-item-main">
                                <span class="pending-item-label">${name}</span>
                                <span class="pending-item-type ${tc}">${escapeHtml(type)}</span>
                                ${meta}
                            </div>
                            ${sourceHtml}
                        </div>
                    </div>
                `;
            }
        }

        // Links section
        const linkEntries = Object.entries(links);
        if (linkEntries.length > 0) {
            html += `<div class="pending-section-header">
                <input type="checkbox" id="select-all-links" data-section="links">
                <span class="pending-section-title">New Relationships (${linkEntries.length})</span>
            </div>`;
            for (const [uuid, link] of linkEntries) {
                const checked = this.selectedLinks.has(uuid) ? 'checked' : '';
                const linkType = escapeHtml(link.type || 'RELATED');
                const sourceName = this._getEntityName(link.source_uuid, entities);
                const targetName = this._getEntityName(link.target_uuid, entities);
                html += `
                    <div class="pending-item" data-uuid="${uuid}" data-type="link">
                        <input type="checkbox" data-type="link" data-uuid="${uuid}" ${checked}>
                        <div class="pending-item-body">
                            <div class="pending-item-link">
                                <span class="pending-link-entity">${sourceName}</span>
                                <span class="pending-link-arrow">→</span>
                                <span class="pending-link-type">${linkType}</span>
                                <span class="pending-link-arrow">→</span>
                                <span class="pending-link-entity">${targetName}</span>
                            </div>
                        </div>
                    </div>
                `;
            }
        }

        this.content.innerHTML = html;

        // Bind individual checkbox events
        this.content.querySelectorAll('input[type="checkbox"][data-type]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const { type, uuid } = e.target.dataset;
                if (type === 'entity') {
                    if (e.target.checked) this.selectedEntities.add(uuid);
                    else this.selectedEntities.delete(uuid);
                } else if (type === 'link') {
                    if (e.target.checked) this.selectedLinks.add(uuid);
                    else this.selectedLinks.delete(uuid);
                }
                this._updateButtonStates();
            });
        });

        // Bind select-all checkboxes
        this.content.querySelectorAll('input[type="checkbox"][data-section]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const section = e.target.dataset.section;
                const checked = e.target.checked;
                if (section === 'entities') {
                    entityEntries.forEach(([uuid]) => {
                        if (checked) this.selectedEntities.add(uuid);
                        else this.selectedEntities.delete(uuid);
                    });
                    this.content.querySelectorAll('input[data-type="entity"]').forEach(i => { i.checked = checked; });
                } else if (section === 'links') {
                    linkEntries.forEach(([uuid]) => {
                        if (checked) this.selectedLinks.add(uuid);
                        else this.selectedLinks.delete(uuid);
                    });
                    this.content.querySelectorAll('input[data-type="link"]').forEach(i => { i.checked = checked; });
                }
                this._updateButtonStates();
            });
        });

        this._updateButtonStates();
    }

    _updateButtonStates() {
        const hasSelection = this.selectedEntities.size > 0 || this.selectedLinks.size > 0;
        const approveSelected = document.getElementById('pending-approve-selected');
        const rejectSelected = document.getElementById('pending-reject-selected');
        if (approveSelected) approveSelected.disabled = !hasSelection;
        if (rejectSelected) rejectSelected.disabled = !hasSelection;
    }

    _getEntityName(uuid, entities) {
        if (entities[uuid]) {
            return escapeHtml(entities[uuid].name || 'Unknown');
        }
        return escapeHtml(String(uuid).slice(0, 8) + '...');
    }

    _updatePipelineStatus() {
        const totalCount = Object.keys(this.pendingOntology.entities || {}).length +
                          Object.keys(this.pendingOntology.links || {}).length;

        if (this.pipelinePendingDot) {
            this.pipelinePendingDot.style.display = totalCount > 0 ? 'inline-block' : 'none';
        }
        if (this.pipelinePendingCount) {
            this.pipelinePendingCount.textContent = totalCount > 0 ? `${totalCount} pending` : '';
            this.pipelinePendingCount.style.display = totalCount > 0 ? 'inline-block' : 'none';
        }
    }

    setThreadId(threadId) {
        this.threadId = threadId;
        this.loadPendingOntology();
    }
}
