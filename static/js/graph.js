/**
 * Graph rendering module - handles vis-network ontology graph visualization
 */

let networkInstance = null;
let selectedNodeIds = new Set();

export function getNetworkInstance() {
    return networkInstance;
}

export function getSelectedNodeIds() {
    return Array.from(selectedNodeIds);
}

function _notifySelectionChange() {
    const event = new CustomEvent('graph-selection-change', {
        detail: { selectedIds: Array.from(selectedNodeIds), count: selectedNodeIds.size }
    });
    document.dispatchEvent(event);
}

// ─── Visual styling for pending ("staged") items ───
// Pending items keep their normal type colors; only borders and edges get dashed.

// Format colors based on type
const typeColors = {
    Person: { background: '#D97706', border: '#B45309', hover: '#F59E0B' },
    Location: { background: '#2563EB', border: '#1D4ED8', hover: '#3B82F6' },
    Organization: { background: '#4F46E5', border: '#4338CA', hover: '#6366F1' },
    Event: { background: '#DC2626', border: '#B91C1C', hover: '#EF4444' },
    Equipment: { background: '#059669', border: '#047857', hover: '#10B981' },
    Concept: { background: '#9333EA', border: '#7E22CE', hover: '#A855F7' },
    default: { background: '#4B5563', border: '#374151', hover: '#6B7280' }
};

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildNode(id, ent, isPending) {
    const colors = typeColors[ent.type] || typeColors.default;
    const propertiesStr = Object.entries(ent.properties || {})
        .map(([k, v]) => `<b>${escapeHtml(k)}</b>: ${escapeHtml(String(v))}`)
        .join('<br>');

    const pendingBadge = isPending ? '<span style="color:#FFB300;font-weight:bold">[STAGED]</span><br>' : '';
    const tooltipHtml = document.createElement('div');
    tooltipHtml.innerHTML = `${pendingBadge}<b>${escapeHtml(ent.name)}</b><br><i>${escapeHtml(ent.type)}</i><br><br>${propertiesStr}`;

    if (isPending) {
        return {
            id: id,
            label: ent.name,
            title: tooltipHtml,
            color: {
                background: colors.background,
                border: '#ffffff',
                highlight: {
                    background: colors.hover,
                    border: '#ffffff'
                }
            },
            font: { color: '#ffffff' },
            shape: 'dot',
            size: 24,
            shapeProperties: { borderDashes: [6, 4] },
            borderWidth: 3,
            shadow: { enabled: true, color: 'rgba(255, 179, 0, 0.4)', size: 10, x: 0, y: 0 }
        };
    }

    return {
        id: id,
        label: ent.name,
        title: tooltipHtml,
        color: {
            background: colors.background,
            border: colors.border,
            highlight: {
                background: colors.hover,
                border: colors.border
            }
        },
        font: { color: '#ffffff' },
        shape: 'dot',
        size: 20
    };
}

function buildEdge(id, link, entities, isPending) {
    const sourceId = link.source_id || link.source || link.source_uuid;
    const targetId = link.target_id || link.target || link.target_uuid;
    const relationType = link.type || link.relation_type;
    const description = link.description || link.relation_type || link.type;

    if (!entities[sourceId] || !entities[targetId]) {
        if (!entities[sourceId]) console.warn(`Edge ${id}: Source entity ${sourceId} not found`);
        if (!entities[targetId]) console.warn(`Edge ${id}: Target entity ${targetId} not found`);
        return null;
    }

    if (isPending) {
        return {
            id: id,
            from: sourceId,
            to: targetId,
            label: relationType,
            title: `${description || relationType} (staged)`,
            color: {
                color: '#9CA3AF',
                highlight: '#5ec0ff'
            },
            font: {
                color: '#ffffff',
                size: 13,
                strokeWidth: 3,
                strokeColor: '#15171e',
                align: 'middle',
                face: 'sans-serif',
                bold: true
            },
            arrows: {
                to: {
                    enabled: true,
                    type: 'arrow',
                    scaleFactor: 1.2,
                    color: { inherit: 'from' }
                }
            },
            smooth: { type: 'curvedCW', roundness: 0.2 },
            width: 2,
            dashes: [8, 6],
            shadow: { enabled: true, color: 'rgba(255, 179, 0, 0.3)', size: 6, x: 0, y: 0 }
        };
    }

    return {
        id: id,
        from: sourceId,
        to: targetId,
        label: relationType,
        title: description || relationType,
        color: {
            color: '#9CA3AF',
            highlight: '#5ec0ff'
        },
        font: {
            color: '#ffffff',
            size: 13,
            strokeWidth: 3,
            strokeColor: '#15171e',
            align: 'middle',
            face: 'sans-serif',
            bold: true
        },
        arrows: {
            to: {
                enabled: true,
                type: 'arrow',
                scaleFactor: 1.2,
                color: { inherit: 'from' }
            }
        },
        smooth: { type: 'curvedCW', roundness: 0.2 },
        width: 2,
        shadow: {
            enabled: true,
            color: 'rgba(0, 0, 0, 0.5)',
            size: 4,
            x: 2,
            y: 2
        }
    };
}

export function renderGraph(ontology, container, pendingOntology = null) {
    if (!container) return;

    const nodes = [];
    const edges = [];

    // Build a unified entity map so pending edges can reference current + pending entities
    const allEntities = {};

    // Current (approved) entities
    if (ontology && ontology.entities) {
        for (const [id, ent] of Object.entries(ontology.entities)) {
            allEntities[id] = ent;
            nodes.push(buildNode(id, ent, false));
        }
    }

    // Pending entities
    if (pendingOntology && pendingOntology.entities) {
        for (const [id, ent] of Object.entries(pendingOntology.entities)) {
            allEntities[id] = ent;
            nodes.push(buildNode(id, ent, true));
        }
    }

    // Current (approved) links
    if (ontology && ontology.links) {
        for (const [id, link] of Object.entries(ontology.links)) {
            const edge = buildEdge(id, link, allEntities, false);
            if (edge) edges.push(edge);
        }
    }

    // Pending links
    if (pendingOntology && pendingOntology.links) {
        for (const [id, link] of Object.entries(pendingOntology.links)) {
            const edge = buildEdge(id, link, allEntities, true);
            if (edge) edges.push(edge);
        }
    }

    const data = {
        nodes: new vis.DataSet(nodes),
        edges: new vis.DataSet(edges)
    };

    const options = {
        physics: {
            forceAtlas2Based: {
                gravitationalConstant: -100,
                centralGravity: 0.005,
                springLength: 200,
                springConstant: 0.04
            },
            maxVelocity: 50,
            solver: 'forceAtlas2Based',
            timestep: 0.35,
            stabilization: { iterations: 200 }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            hoverConnectedEdges: true,
            multiselect: true,
            keyboard: true
        },
        nodes: {
            borderWidthSelected: 5,
            color: {
                highlight: {
                    border: '#ffffff',
                    background: '#5ec0ff'
                }
            },
            shadow: {
                enabled: true,
                color: 'rgba(94, 192, 255, 0.6)',
                size: 15,
                x: 0,
                y: 0
            }
        },
        edges: {
            hoverWidth: 3
        }
    };

    if (!networkInstance) {
        networkInstance = new vis.Network(container, data, options);

        // Track selection changes
        networkInstance.on('selectNode', (params) => {
            selectedNodeIds = new Set(params.nodes);
            _notifySelectionChange();
        });
        networkInstance.on('deselectNode', (params) => {
            selectedNodeIds = new Set(params.nodes);
            _notifySelectionChange();
        });

        // Keyboard: Escape to clear selection
        container.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && selectedNodeIds.size > 0) {
                networkInstance.unselectAll();
                selectedNodeIds = new Set();
                _notifySelectionChange();
            }
        });
        container.setAttribute('tabindex', '0');
    } else {
        // Preserve selection across re-renders
        const prevSelection = Array.from(selectedNodeIds);
        networkInstance.setData(data);
        // Restore selection for nodes that still exist
        const existingNodes = new Set(data.nodes.getIds());
        const toReselect = prevSelection.filter(id => existingNodes.has(id));
        if (toReselect.length > 0) {
            networkInstance.selectNodes(toReselect);
            selectedNodeIds = new Set(toReselect);
            _notifySelectionChange();
        }
    }
}

/**
 * Render the merged graph using the current approved ontology + pending ontology
 * from the global managers. Call this whenever either side changes.
 */
export function renderMergedGraph(container) {
    const rawCurrentOntology = window.ontologyTabManager?.currentOntology || { entities: {}, links: {} };
    const pendingOntology = window.pendingOntologyManager?.pendingOntology || { entities: {}, links: {} };

    // Guard against stale merged data in ontologyTabManager: strip any items
    // whose UUIDs also appear in pending, so the graph only renders them once
    // with the pending (amber/dashed) visual style.
    const currentEntities = { ...rawCurrentOntology.entities };
    const currentLinks = { ...rawCurrentOntology.links };
    for (const uuid of Object.keys(pendingOntology.entities || {})) {
        delete currentEntities[uuid];
    }
    for (const uuid of Object.keys(pendingOntology.links || {})) {
        delete currentLinks[uuid];
    }

    // Deduplicate by name: if the same name exists in both committed and pending,
    // only show the pending version (it has visual staging indicators).
    // Also deduplicate within pending as a safety net.
    const pendingNames = new Set();
    const dedupedPendingEntities = {};
    for (const [uuid, ent] of Object.entries(pendingOntology.entities || {})) {
        const name = (ent.name || '').toLowerCase().trim();
        if (name && !pendingNames.has(name)) {
            pendingNames.add(name);
            dedupedPendingEntities[uuid] = ent;
        }
    }

    const dedupedCurrentEntities = {};
    for (const [uuid, ent] of Object.entries(currentEntities)) {
        const name = (ent.name || '').toLowerCase().trim();
        if (name && !pendingNames.has(name)) {
            dedupedCurrentEntities[uuid] = ent;
        }
    }

    renderGraph(
        { entities: dedupedCurrentEntities, links: currentLinks },
        container,
        { entities: dedupedPendingEntities, links: pendingOntology.links || {} }
    );
}

window.renderMergedGraph = renderMergedGraph;
