/**
 * Main Tab Manager
 */

import { escapeHtml } from './utils.js';

export class MainTabManager {
    constructor() {
        this.currentTab = 'user';
        this.tabs = document.querySelectorAll('.main-tab');
        this.panels = document.querySelectorAll('.main-tab-panel');
        this.shelfItems = document.querySelectorAll('.shelf-item[data-target^="panel-"]');
        this._bindEvents();
    }

    _bindEvents() {
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
        });
        this.shelfItems.forEach(item => {
            item.addEventListener('click', () => {
                this.switchTab(item.dataset.target.replace('panel-', ''));
            });
        });
    }

    switchTab(tabName) {
        if (tabName === this.currentTab) return;
        this.currentTab = tabName;

        this.tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.tab === tabName));
        this.panels.forEach(panel => panel.classList.toggle('active', panel.id === `panel-${tabName}`));
        this.shelfItems.forEach(item => item.classList.toggle('active', item.dataset.target === `panel-${tabName}`));

        if (tabName === 'sources') this._renderSources();
    }

    _renderSources() {
        this._renderIntelLog();
        this._loadDocuments();
    }

    _renderIntelLog() {
        const log = window.sourceLog || [];
        const container = document.getElementById('sources-intel-log');
        const countEl = document.getElementById('intel-log-count');
        if (!container) return;

        if (countEl) countEl.textContent = `${log.length} entries`;

        if (log.length === 0) {
            container.innerHTML = `
                <div class="sources-empty" id="intel-log-empty">
                    <div class="sources-empty-icon">📋</div>
                    <div class="sources-empty-text">No queries yet</div>
                    <div class="sources-empty-subtext">Submit a query to start building intelligence</div>
                </div>
            `;
            return;
        }

        container.innerHTML = log.slice().reverse().map((entry, i) => {
            const tools = entry.tools || [];
            const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
            const toolBadges = tools.map(t => {
                let cls = '';
                const tl = t.name.toLowerCase();
                if (tl.includes('rag') || tl.includes('vector')) cls = 'rag';
                else if (tl.includes('search') || tl.includes('duckduckgo') || tl.includes('wikipedia') || tl.includes('news')) cls = 'search';
                else if (tl.includes('ontology')) cls = 'ontology';
                return `<span class="intel-log-tool-badge ${cls}">${escapeHtml(t.name)}</span>`;
            }).join('');

            const toolResults = tools.filter(t => t.summary).map(t => `
                <div class="intel-log-tool-result">
                    <span class="intel-log-tool-name">${escapeHtml(t.name)}</span>
                    <span class="intel-log-tool-summary">${escapeHtml(t.summary)}</span>
                </div>
            `).join('');

            const responseHtml = entry.response ? `<div class="intel-log-response">${entry.response}</div>` : '';

            return `
                <div class="intel-log-entry" data-index="${i}">
                    <div class="intel-log-header">
                        <span class="intel-log-arrow">▶</span>
                        <span class="intel-log-query">${escapeHtml(entry.query.substring(0, 80))}${entry.query.length > 80 ? '...' : ''}</span>
                        <div class="intel-log-tools">${toolBadges}</div>
                        <span class="intel-log-time">${time}</span>
                    </div>
                    <div class="intel-log-body">
                        ${responseHtml}
                        ${toolResults}
                    </div>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.intel-log-header').forEach(header => {
            header.addEventListener('click', () => {
                header.parentElement.classList.toggle('expanded');
            });
        });
    }

    async _loadDocuments() {
        const threadId = localStorage.getItem('geovision_thread_id') || 'default';
        try {
            const res = await fetch(`/api/sessions/${threadId}/documents`);
            if (res.ok) {
                const data = await res.json();
                this._renderDocuments(data.documents || []);
            }
        } catch (e) {
            console.warn('[SOURCES] Failed to load documents:', e);
        }
    }

    _renderDocuments(documents) {
        const container = document.getElementById('sources-documents-list');
        if (!container) return;

        if (documents.length === 0) {
            container.innerHTML = `
                <div class="sources-empty">
                    <div class="sources-empty-icon">📡</div>
                    <div class="sources-empty-text">No documents ingested</div>
                    <div class="sources-empty-subtext">Upload documents to the \`documents/\` folder for RAG retrieval</div>
                </div>
            `;
            return;
        }

        container.innerHTML = documents.map(doc => {
            const icon = this._getFileIcon(doc.name);
            const size = this._formatSize(doc.size);
            const modified = new Date(doc.modified).toLocaleDateString();
            return `
                <div class="source-document-item">
                    <span class="source-doc-icon">${icon}</span>
                    <div class="source-doc-info">
                        <div class="source-doc-name">${escapeHtml(doc.name)}</div>
                        <div class="source-doc-meta">${doc.path} • ${modified}</div>
                    </div>
                    <span class="source-doc-size">${size}</span>
                </div>
            `;
        }).join('');
    }

    _getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            pdf: '📄', txt: '📝', md: '📝', csv: '📊',
            json: '📋', xml: '📋', html: '🌐', doc: '📄',
            docx: '📄', xlsx: '📊',
        };
        return icons[ext] || '📁';
    }

    _formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
}
