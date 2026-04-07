/**
 * Card view renderer for ontology tab manager
 */

import { escapeHtml } from './utils.js';

export function renderCards(ontology, cardFilter) {
    const container = document.getElementById('card-view-container');
    if (!container) return;

    const entities = Object.values(ontology.entities || {});
    const links = Object.values(ontology.links || {});

    let itemsHtml = '';

    if (cardFilter === 'all' || cardFilter === 'entities') {
        entities.forEach(entity => {
            itemsHtml += renderEntityCard(entity, ontology);
        });
    }

    if (cardFilter === 'all' || cardFilter === 'links') {
        links.forEach(link => {
            itemsHtml += renderLinkCard(link, ontology);
        });
    }

    const emptyState = container.querySelector('.card-empty-state');
    if (!itemsHtml) {
        if (emptyState) emptyState.style.display = 'flex';
        container.innerHTML = '';
        container.appendChild(emptyState || createEmptyState());
    } else {
        if (emptyState) emptyState.style.display = 'none';
        container.innerHTML = itemsHtml;
    }
}

function renderEntityCard(entity, ontology) {
    const props = entity.properties || {};
    const propsHtml = Object.entries(props).map(([key, value]) => {
        const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
        return `<div class="card-property">
            <span class="card-property-key">${escapeHtml(key)}:</span>
            <span class="card-property-value">${escapeHtml(displayValue)}</span>
        </div>`;
    }).join('');

    const mentions = entity.mentions || [];
    const mentionsHtml = mentions.length > 0 ? `
        <div class="card-section">
            <div class="card-section-title">Mentions (${mentions.length})</div>
            ${mentions.map(m => `
                <div class="card-mention">
                    <div class="mention-text">${escapeHtml(m.source_text || '')}</div>
                    <div class="mention-meta">
                        <span class="mention-confidence">${(m.confidence * 100).toFixed(0)}%</span>
                        <span class="mention-date">${m.extracted_at ? new Date(m.extracted_at).toLocaleString() : ''}</span>
                    </div>
                </div>
            `).join('')}
        </div>
    ` : '';

    const entityUuid = entity.uuid;
    const relatedLinks = Object.values(ontology.links || {}).filter(
        link => (link.source_uuid === entityUuid) || (link.target_uuid === entityUuid)
    );
    const connectionsHtml = relatedLinks.length > 0 ? `
        <div class="card-section card-connections">
            <div class="card-section-title">Connections (${relatedLinks.length})</div>
            ${relatedLinks.map(link => {
                const isSource = link.source_uuid === entityUuid;
                const otherUuid = isSource ? link.target_uuid : link.source_uuid;
                const otherEntity = ontology.entities && ontology.entities[otherUuid];
                const otherName = otherEntity ? otherEntity.name : 'Unknown';
                return `<div class="card-connection-item" data-link-uuid="${link.uuid}" data-target-uuid="${otherUuid}">${isSource ? '→' : '←'} ${escapeHtml(otherName)} <span class="connection-type">(${link.type})</span></div>`;
            }).join('')}
        </div>
    ` : '';

    const metaHtml = `
        <div class="card-section card-meta">
            <div class="card-meta-row">
                <span class="card-meta-key">UUID:</span>
                <span class="card-meta-value">${entity.uuid || ''}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Created:</span>
                <span class="card-meta-value">${entity.created_at ? new Date(entity.created_at).toLocaleString() : ''}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Updated:</span>
                <span class="card-meta-value">${entity.updated_at ? new Date(entity.updated_at).toLocaleString() : ''}</span>
            </div>
            ${entity.created_by ? `
            <div class="card-meta-row">
                <span class="card-meta-key">By:</span>
                <span class="card-meta-value">${escapeHtml(entity.created_by)}</span>
            </div>` : ''}
        </div>
    `;

    return `<div class="entity-card" data-uuid="${entity.uuid}">
        <div class="card-header">
            <span class="card-title">${escapeHtml(entity.name || 'Unknown')}</span>
            <span class="card-type-badge">${entity.type || 'Thing'}</span>
        </div>
        <div class="card-body">
            ${metaHtml}
            <div class="card-section">
                <div class="card-section-title">Properties</div>
                <div class="card-properties">
                    ${propsHtml || '<div class="card-property"><span class="card-property-value" style="color: var(--text-muted)">No properties</span></div>'}
                </div>
            </div>
            ${mentionsHtml}
            ${connectionsHtml}
        </div>
    </div>`;
}

function renderLinkCard(link, ontology) {
    const sourceUuid = link.source_uuid || link.source_id || link.source;
    const targetUuid = link.target_uuid || link.target_id || link.target;
    const sourceEntity = ontology.entities && ontology.entities[sourceUuid];
    const targetEntity = ontology.entities && ontology.entities[targetUuid];
    const sourceName = sourceEntity ? sourceEntity.name : 'Unknown';
    const targetName = targetEntity ? targetEntity.name : 'Unknown';

    const props = link.properties || {};
    const propsHtml = Object.entries(props).map(([key, value]) => {
        const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
        return `<div class="card-property">
            <span class="card-property-key">${escapeHtml(key)}:</span>
            <span class="card-property-value">${escapeHtml(displayValue)}</span>
        </div>`;
    }).join('');

    const mentions = link.mentions || [];
    const mentionsHtml = mentions.length > 0 ? `
        <div class="card-section">
            <div class="card-section-title">Mentions (${mentions.length})</div>
            ${mentions.map(m => `
                <div class="card-mention">
                    <div class="mention-text">${escapeHtml(m.source_text || '')}</div>
                    <div class="mention-meta">
                        <span class="mention-confidence">${(m.confidence * 100).toFixed(0)}%</span>
                        <span class="mention-date">${m.extracted_at ? new Date(m.extracted_at).toLocaleString() : ''}</span>
                    </div>
                </div>
            `).join('')}
        </div>
    ` : '';

    const metaHtml = `
        <div class="card-section card-meta">
            <div class="card-meta-row">
                <span class="card-meta-key">UUID:</span>
                <span class="card-meta-value">${link.uuid || ''}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Source:</span>
                <span class="card-meta-value">${sourceName}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Target:</span>
                <span class="card-meta-value">${targetName}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Created:</span>
                <span class="card-meta-value">${link.created_at ? new Date(link.created_at).toLocaleString() : ''}</span>
            </div>
            <div class="card-meta-row">
                <span class="card-meta-key">Updated:</span>
                <span class="card-meta-value">${link.updated_at ? new Date(link.updated_at).toLocaleString() : ''}</span>
            </div>
        </div>
    `;

    return `<div class="link-card" data-uuid="${link.uuid}">
        <div class="card-header">
            <span class="card-title">${escapeHtml(sourceName)} → ${escapeHtml(targetName)}</span>
            <span class="card-type-badge">${link.type || 'related'}</span>
        </div>
        <div class="card-body">
            ${metaHtml}
            <div class="card-section">
                <div class="card-section-title">Properties</div>
                <div class="card-properties">
                    ${propsHtml || '<div class="card-property"><span class="card-property-value" style="color: var(--text-muted)">No properties</span></div>'}
                </div>
            </div>
            ${mentionsHtml}
        </div>
    </div>`;
}

function createEmptyState() {
    const div = document.createElement('div');
    div.className = 'card-empty-state';
    div.innerHTML = `
        <div class="empty-state-icon">◈</div>
        <div class="empty-state-text">No items to display</div>
        <div class="empty-state-subtext">Switch to another view or wait for data</div>
    `;
    return div;
}
