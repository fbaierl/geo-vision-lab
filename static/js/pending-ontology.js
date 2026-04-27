/**
 * Pending Ontology Review Module
 * 
 * Handles batch review of pending ontology changes:
 * - Displays pending entities and links
 * - Allows selective approve/reject
 * - Syncs with backend API
 */

import { escapeHtml } from './utils.js';

export class PendingOntologyManager {
    constructor() {
        this.pendingOntology = { entities: {}, links: {} };
        this.selectedEntities = new Set();
        this.selectedLinks = new Set();
        this.threadId = localStorage.getItem('geovision_thread_id') || 'default';
        
        this.panel = document.getElementById('pending-review-panel');
        this.content = document.getElementById('pending-content');
        this.countEl = document.getElementById('pending-count');
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
            }
        } catch (e) {
            console.warn('[PENDING] Failed to load pending ontology:', e);
        }
    }

    async approveSelected() {
        const entityUuids = this.selectedEntities.size > 0 ? Array.from(this.selectedEntities) : null;
        const linkUuids = this.selectedLinks.size > 0 ? Array.from(this.selectedLinks) : null;

        if (!entityUuids && !linkUuids) {
            console.warn('[PENDING] No items selected for approval');
            return;
        }

        await this._sendApprove(entityUuids, linkUuids);
    }

    async approveAll() {
        const entityUuids = Object.keys(this.pendingOntology.entities);
        const linkUuids = Object.keys(this.pendingOntology.links);

        if (entityUuids.length === 0 && linkUuids.length === 0) return;

        await this._sendApprove(entityUuids, linkUuids);
    }

    async _sendApprove(entityUuids, linkUuids) {
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
                // Reload pending to get remaining items
                await this.loadPendingOntology();
                // Trigger ontology reload to show newly approved items
                if (window.ontologyTabManager) {
                    window.ontologyTabManager.loadOntology();
                }
                console.log(`[PENDING] Approved ${data.approved_entities} entities, ${data.approved_links} links`);
            }
        } catch (e) {
            console.error('[PENDING] Failed to approve:', e);
        }
    }

    async rejectSelected() {
        const entityUuids = this.selectedEntities.size > 0 ? Array.from(this.selectedEntities) : null;
        const linkUuids = this.selectedLinks.size > 0 ? Array.from(this.selectedLinks) : null;

        if (!entityUuids && !linkUuids) {
            console.warn('[PENDING] No items selected for rejection');
            return;
        }

        await this._sendReject(entityUuids, linkUuids);
    }

    async rejectAll() {
        await this._sendReject(null, null);
    }

    async _sendReject(entityUuids, linkUuids) {
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
                await this.loadPendingOntology();
                console.log(`[PENDING] Rejected ${data.rejected_entities} entities, ${data.rejected_links} links`);
            }
        } catch (e) {
            console.error('[PENDING] Failed to reject:', e);
        }
    }

    _render() {
        const entities = this.pendingOntology.entities || {};
        const links = this.pendingOntology.links || {};
        const totalCount = Object.keys(entities).length + Object.keys(links).length;

        if (totalCount === 0) {
            this.panel.style.display = 'none';
            return;
        }

        this.panel.style.display = 'block';
        this.countEl.textContent = totalCount;

        let html = '';

        // Entities section
        const entityEntries = Object.entries(entities);
        if (entityEntries.length > 0) {
            html += '<div class="pending-section-title">New Entities</div>';
            for (const [uuid, entity] of entityEntries) {
                const checked = this.selectedEntities.has(uuid) ? 'checked' : '';
                const type = entity.type || 'Unknown';
                const name = escapeHtml(entity.name || 'Unnamed');
                let extra = '';
                if (entity.properties?.lat && entity.properties?.lon) {
                    extra = ` (${entity.properties.lat}, ${entity.properties.lon})`;
                }
                html += `
                    <div class="pending-item">
                        <input type="checkbox" data-type="entity" data-uuid="${uuid}" ${checked}>
                        <span class="pending-item-type">${escapeHtml(type)}</span>
                        <span class="pending-item-label">${name}${extra}</span>
                    </div>
                `;
            }
        }

        // Links section
        const linkEntries = Object.entries(links);
        if (linkEntries.length > 0) {
            html += '<div class="pending-section-title">New Relationships</div>';
            for (const [uuid, link] of linkEntries) {
                const checked = this.selectedLinks.has(uuid) ? 'checked' : '';
                const linkType = escapeHtml(link.type || 'RELATED');
                const sourceName = this._getEntityName(link.source_uuid, entities);
                const targetName = this._getEntityName(link.target_uuid, entities);
                html += `
                    <div class="pending-item">
                        <input type="checkbox" data-type="link" data-uuid="${uuid}" ${checked}>
                        <span class="pending-item-link">
                            ${sourceName} <span class="pending-link-type">[${linkType}]</span> ${targetName}
                        </span>
                    </div>
                `;
            }
        }

        this.content.innerHTML = html;

        // Bind checkbox events
        this.content.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const { type, uuid } = e.target.dataset;
                if (type === 'entity') {
                    if (e.target.checked) this.selectedEntities.add(uuid);
                    else this.selectedEntities.delete(uuid);
                } else if (type === 'link') {
                    if (e.target.checked) this.selectedLinks.add(uuid);
                    else this.selectedLinks.delete(uuid);
                }
            });
        });
    }

    _getEntityName(uuid, entities) {
        if (entities[uuid]) {
            return escapeHtml(entities[uuid].name || 'Unknown');
        }
        // Try to find in full ontology
        return escapeHtml(uuid.slice(0, 8) + '...');
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
