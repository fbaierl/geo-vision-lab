/**
 * JSON tree renderer for ontology tab manager
 */

import { escapeHtml, escapeJsonString, showToast } from './utils.js';

export function renderJsonTree(ontology) {
    const container = document.getElementById('json-tree-container');
    if (!container) return;

    const treeHtml = buildJsonTree(ontology, null, 0, null, ontology);
    container.innerHTML = treeHtml;
}

function buildJsonTree(data, key = null, depth = 0, parentKey = null, fullOntology = null) {
    if (data === null) {
        return `<li class="json-tree-node">
            ${key !== null ? `<span class="json-tree-key">"${key}"</span><span class="json-tree-separator">:</span> ` : ''}
            <span class="json-tree-value-null">null</span>
        </li>`;
    }

    if (typeof data !== 'object') {
        const valueClass = typeof data === 'string' ? 'json-tree-value-string' :
                          typeof data === 'number' ? 'json-tree-value-number' :
                          'json-tree-value-boolean';
        const displayValue = typeof data === 'string' ? `"${escapeJsonString(data)}"` : String(data);

        return `<li class="json-tree-node">
            ${key !== null ? `<span class="json-tree-key">"${key}"</span><span class="json-tree-separator">:</span> ` : ''}
            <span class="${valueClass}">${displayValue}</span>
        </li>`;
    }

    const isArray = Array.isArray(data);
    const items = isArray ? data : Object.entries(data);
    const bracketOpen = isArray ? '[' : '{';
    const bracketClose = isArray ? ']' : '}';
    const itemCount = items.length;

    if (itemCount === 0) {
        return `<li class="json-tree-node">
            ${key !== null ? `<span class="json-tree-key">"${key}"</span><span class="json-tree-separator">:</span> ` : ''}
            <span class="json-tree-bracket">${bracketOpen}${bracketClose}</span>
        </li>`;
    }

    let html = `<li class="json-tree-node">`;

    if (key !== null) {
        html += `<span class="json-tree-toggle collapsed" onclick="this.parentElement.classList.toggle('collapsed')"></span>`;

        let displayKey = key;
        if (parentKey === 'entities' && typeof data === 'object' && data !== null && data.name) {
            displayKey = `${data.name} (${data.type || 'Entity'})`;
        } else if (parentKey === 'links' && typeof data === 'object' && data !== null && data.type && fullOntology) {
            const sourceUuid = data.source_uuid || data.source_id || data.source;
            const targetUuid = data.target_uuid || data.target_id || data.target;
            const sourceEntity = fullOntology.entities && fullOntology.entities[sourceUuid];
            const targetEntity = fullOntology.entities && fullOntology.entities[targetUuid];
            const sourceName = sourceEntity ? sourceEntity.name : 'Unknown';
            const targetName = targetEntity ? targetEntity.name : 'Unknown';
            displayKey = `${sourceName} → ${targetName} [${data.type}]`;
        }

        html += `<span class="json-tree-key">"${displayKey}"</span><span class="json-tree-separator">:</span> `;
    } else {
        html += `<span class="json-tree-toggle collapsed" onclick="this.parentElement.classList.toggle('collapsed')"></span>`;
    }

    html += `<span class="json-tree-bracket">${bracketOpen}</span>`;

    if (itemCount <= 3 && depth < 5) {
        html += `<span class="json-tree-preview">${itemCount} item${itemCount === 1 ? '' : 's'}</span>`;
    }

    html += `<ul class="json-tree-children">`;

    if (isArray) {
        data.forEach((item, index) => {
            html += buildJsonTree(item, index, depth + 1, key, fullOntology);
        });
    } else {
        for (const [k, v] of items) {
            html += buildJsonTree(v, k, depth + 1, key, fullOntology);
        }
    }

    html += `</ul><span class="json-tree-bracket">${bracketClose}</span></li>`;

    return html;
}

export function expandAllJson() {
    document.querySelectorAll('.json-tree-toggle.collapsed').forEach(toggle => {
        toggle.classList.remove('collapsed');
        toggle.classList.add('expanded');
        toggle.parentElement.classList.remove('collapsed');
    });
}

export function collapseAllJson() {
    document.querySelectorAll('.json-tree-toggle.expanded').forEach(toggle => {
        toggle.classList.remove('expanded');
        toggle.classList.add('collapsed');
        toggle.parentElement.classList.add('collapsed');
    });
}

export function copyJsonToClipboard(ontology) {
    const jsonString = JSON.stringify(ontology, null, 2);
    navigator.clipboard.writeText(jsonString).then(() => {
        showToast('JSON copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy JSON:', err);
        showToast('Failed to copy JSON', 'error');
    });
}

export function downloadJson(ontology) {
    const jsonString = JSON.stringify(ontology, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ontology_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Ontology downloaded');
}
