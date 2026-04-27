/**
 * Chat module - handles chat input, streaming, and message display
 */

import { escapeHtml } from './utils.js';
import { renderMap } from './map.js';
import { renderGraph } from './graph.js';
import { loadCurrentModel, getCurrentModel } from './model-selector.js';
import { showThinkingPanel, appendToThinkingPanel, collapseThinkingPanel, resetThinkingState } from './thinking-panels.js';
import { addReasoningStep, addReasoningResult, addReasoningError } from './reasoning-steps.js';

// DOM elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const typingIndicator = document.getElementById('typing-indicator');
const pillProcessing = document.getElementById('pill-processing');
const clock = document.getElementById('clock');
const statQueries = document.getElementById('stat-queries');
const statAvg = document.getElementById('stat-avg');
const statTool = document.getElementById('stat-tool');
const historyList = document.getElementById('history-list');
const noHistory = document.getElementById('no-history');
const mapsLoading = document.getElementById('maps-loading');

let queryCount = 0;
let totalMs = 0;
let threadId = localStorage.getItem('geovision_thread_id');
console.log('[THREAD] Loaded thread ID from localStorage:', threadId);
let rawStreamBuffer = '';
let markdownRenderTimeout = null;

// Clock
function updateClock() {
    clock.textContent = new Date().toUTCString().slice(17, 25);
}
updateClock();
setInterval(updateClock, 1000);

// GPU status
async function fetchGpuStatus() {
    try {
        const res = await fetch('/system/status');
        const data = await res.json();

        const gpuPill = document.getElementById('pill-gpu');
        const gpuStatus = document.getElementById('gpu-status');

        if (data.status === 'processing') {
            gpuPill.className = 'status-pill gpu-active';
            gpuStatus.textContent = 'Processing';
        } else if (data.status === 'loading_model') {
            gpuPill.className = 'status-pill gpu-standby';
            gpuStatus.textContent = 'Loading Model...';
        } else if (data.status === 'ready' || data.model_loaded) {
            gpuPill.className = 'status-pill gpu-active';
            gpuStatus.textContent = 'GPU Active';
        } else if (data.status === 'idle' || data.gpu_available) {
            gpuPill.className = 'status-pill gpu-standby';
            gpuStatus.textContent = 'GPU Standby';
        } else if (data.status === 'error' || !data.gpu_available) {
            gpuPill.className = 'status-pill gpu-inactive';
            gpuStatus.textContent = 'GPU Unavailable';
        } else {
            gpuPill.className = 'status-pill gpu-standby';
            gpuStatus.textContent = 'GPU Standby';
        }
    } catch (e) {
        console.warn('Failed to fetch GPU status:', e);
    }
}
fetchGpuStatus();
setInterval(fetchGpuStatus, 3000);

// Load models
loadCurrentModel();

// Chat functions
export function addMessage(content, isUser = false) {
    const msg = document.createElement('div');
    msg.className = `chat-message ${isUser ? 'user' : ''}`;
    const rendered = (!isUser && typeof marked !== 'undefined') ? marked.parse(content) : content;
    msg.innerHTML = `<div class="chat-message-content markdown-content">${rendered}</div>`;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return msg.querySelector('.chat-message-content');
}

export function addHistory(q) {
    if (noHistory) noHistory.remove();

    const entry = document.createElement('div');
    entry.className = 'history-entry';
    entry.innerHTML = `
        <div class="history-entry-label">↻ Replay</div>
        <div class="history-entry-text">${escapeHtml(q)}</div>
    `;
    entry.addEventListener('click', () => {
        chatInput.value = q;
        chatInput.focus();
    });
    historyList.prepend(entry);

    while (historyList.children.length > 8) {
        historyList.lastChild.remove();
    }
}

function renderMarkdown(el) {
    if (typeof marked !== 'undefined' && rawStreamBuffer) {
        el.innerHTML = marked.parse(rawStreamBuffer);
        el.classList.add('md-rendered');
    }
    rawStreamBuffer = '';
}

function appendToMessageLive(el, text) {
    rawStreamBuffer += text;

    if (markdownRenderTimeout) clearTimeout(markdownRenderTimeout);
    markdownRenderTimeout = setTimeout(() => {
        if (rawStreamBuffer) {
            el.innerHTML = marked.parse(rawStreamBuffer) + '<span class="cursor-blink">○</span>';
            el.classList.add('md-rendered');
        }
    }, 100);

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Send query
async function sendQuery() {
    const q = chatInput.value.trim();
    if (!q) return;

    resetThinkingState();

    addMessage(escapeHtml(q), true);
    addHistory(q);

    chatInput.value = '';
    chatInput.disabled = true;
    sendBtn.disabled = true;
    typingIndicator.classList.add('show');
    pillProcessing.style.display = 'flex';

    if (mapsLoading) mapsLoading.style.display = 'flex';
    const graphLoadingEl = document.getElementById('graph-loading');
    if (graphLoadingEl) graphLoadingEl.style.display = 'flex';

    const responseEl = addMessage('');
    rawStreamBuffer = '';

    const t0 = Date.now();

    try {
        const fd = new FormData();
        fd.append('query', q);
        if (threadId) fd.append('thread_id', threadId);

        const res = await fetch('/chat/stream', { method: 'POST', body: fd });

        if (!res.ok) {
            const data = await res.json();
            responseEl.innerHTML = `<div class="error-message">Error: ${escapeHtml(data.answer || 'Unknown error')}</div>`;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const evt = JSON.parse(jsonStr);

                    if (evt.type === 'meta' && evt.thread_id) {
                        threadId = evt.thread_id;
                        window.currentThreadId = threadId;
                        localStorage.setItem('geovision_thread_id', threadId);
                    } else if (evt.type === 'status') {
                        addReasoningStep(evt.phase, evt.tool, evt.query, evt.model);
                        if (evt.tool && evt.tool !== 'unknown') {
                            statTool.textContent = evt.tool;
                        }
                    } else if (evt.type === 'tool_result') {
                        addReasoningResult(evt.tool, evt.summary, evt.content);
                    } else if (evt.type === 'rag_result') {
                        addReasoningResult(evt.tool || 'RAG', evt.summary, evt.hint || `Quality: ${evt.quality}`);
                    } else if (evt.type === 'ontology_updated') {
                        handleOntologyUpdated(evt.ontology);
                    } else if (evt.type === 'pending_ontology_updated') {
                        handlePendingOntologyUpdated(evt.pending_ontology);
                    } else if (evt.type === 'token') {
                        typingIndicator.classList.remove('show');
                        appendToMessageLive(responseEl, evt.content);
                    } else if (evt.type === 'thinking_start') {
                        showThinkingPanel();
                    } else if (evt.type === 'thinking_token') {
                        appendToThinkingPanel(evt.content);
                    } else if (evt.type === 'thinking_end') {
                        collapseThinkingPanel();
                    } else if (evt.type === 'error') {
                        responseEl.innerHTML = `<div class="error-message">Error: ${escapeHtml(evt.content)}</div>`;
                        addReasoningError(evt.tool || 'unknown', evt.content);
                    } else if (evt.type === 'ontology_error') {
                        handleOntologyError();
                    } else if (evt.type === 'done') {
                        if (markdownRenderTimeout) clearTimeout(markdownRenderTimeout);
                        const cursor = responseEl.querySelector('.cursor-blink');
                        if (cursor) cursor.remove();
                        if (rawStreamBuffer && !responseEl.classList.contains('md-rendered')) {
                            renderMarkdown(responseEl);
                        }
                    }
                } catch (parseErr) {
                    // Skip malformed
                }
            }
        }

        // Finalize
        if (markdownRenderTimeout) clearTimeout(markdownRenderTimeout);
        const cursor = responseEl.querySelector('.cursor-blink');
        if (cursor) cursor.remove();

        const ms = Date.now() - t0;
        queryCount++;
        totalMs += ms;
        statQueries.textContent = queryCount;
        statAvg.textContent = (totalMs / queryCount / 1000).toFixed(1) + 's';

    } catch (e) {
        responseEl.innerHTML = `<div class="error-message">Connection error: ${escapeHtml(e.message)}</div>`;
    } finally {
        typingIndicator.classList.remove('show');
        pillProcessing.style.display = 'none';
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

function handleOntologyUpdated(ontology) {
    if (mapsLoading) mapsLoading.style.display = 'none';
    const graphLoadingEl = document.getElementById('graph-loading');
    if (graphLoadingEl) graphLoadingEl.style.display = 'none';

    console.log("[DEBUG] Current SessionOntology data:", ontology);

    if (window.ontologyTabManager) {
        window.ontologyTabManager.updateOntology(ontology);
    }

    const entityCount = Object.keys(ontology.entities || {}).length;
    const linkCount = Object.keys(ontology.links || {}).length;
    const hasData = entityCount > 0 || linkCount > 0;

    const graphContainer = document.getElementById('graph-container');
    const graphEmptyState = document.getElementById('graph-empty-state');
    if (graphContainer) {
        if (hasData) {
            renderGraph(ontology, graphContainer);
            if (graphEmptyState) graphEmptyState.style.display = 'none';
            const winData = window.windowManager.windows.get('window-graph');
            if (winData && winData.minimized) {
                window.windowManager.restoreWindow('window-graph');
            }
        } else {
            if (graphEmptyState) graphEmptyState.style.display = 'flex';
        }
    }

    const mapContainer = document.getElementById('map-container');
    const mapEmptyState = document.getElementById('map-empty-state');
    const locations = Object.values(ontology.entities || {}).filter(
        e => e.type === 'Location' && e.properties && e.properties.lat && e.properties.lon
    ).map(e => ({
        name: e.name,
        type: e.type,
        lat: e.properties.lat,
        lon: e.properties.lon,
        relevance: e.properties.relevance || 0.5
    }));

    if (locations && locations.length > 0) {
        renderMap(locations, mapContainer);
        if (mapEmptyState) mapEmptyState.style.display = 'none';
        const winData = window.windowManager.windows.get('window-maps');
        if (winData && winData.minimized) {
            window.windowManager.restoreWindow('window-maps');
        }
    } else {
        if (mapEmptyState) mapEmptyState.style.display = 'flex';
    }
}

function handleOntologyError() {
    addReasoningError('ontology_subgraph', 'Ontology extraction failed');
    if (mapsLoading) mapsLoading.style.display = 'none';
    const graphLoadingEl = document.getElementById('graph-loading');
    if (graphLoadingEl) graphLoadingEl.style.display = 'none';

    const mapEmptyState = document.getElementById('map-empty-state');
    const graphEmptyState = document.getElementById('graph-empty-state');
    const mapLegend = document.getElementById('map-legend');

    if (mapEmptyState) {
        mapEmptyState.style.display = 'flex';
        mapEmptyState.querySelector('.empty-state-text').textContent = '⚠ Ontology extraction failed';
        mapEmptyState.querySelector('.empty-state-subtext').textContent = 'Continuing without map and graph updates';
    }
    if (graphEmptyState) {
        graphEmptyState.style.display = 'flex';
        graphEmptyState.querySelector('.empty-state-text').textContent = '⚠ Ontology extraction failed';
        graphEmptyState.querySelector('.empty-state-subtext').textContent = 'Continuing without map and graph updates';
    }
    if (mapLegend) {
        mapLegend.innerHTML = '<span style="color: var(--amber);">⚠ Ontology extraction failed</span>';
    }
}

function handlePendingOntologyUpdated(pendingOntology) {
    if (window.pendingOntologyManager) {
        window.pendingOntologyManager.updatePendingOntology(pendingOntology);
    }
}

// Event listeners
sendBtn.addEventListener('click', sendQuery);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendQuery();
});

// Expose addMessage for session manager hydration
window.addMessageFn = addMessage;
