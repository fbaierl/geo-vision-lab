/**
 * Main Tab Manager
 * 
 * Handles switching between the three main tabs: User, Sources, Ontology
 */

export class MainTabManager {
    constructor() {
        this.currentTab = 'user';
        this.tabs = document.querySelectorAll('.main-tab');
        this.panels = document.querySelectorAll('.main-tab-panel');
        this.shelfItems = document.querySelectorAll('.shelf-item[data-target^="panel-"]');
        
        this._bindEvents();
    }

    _bindEvents() {
        // Tab buttons
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchTab(tab.dataset.tab);
            });
        });

        // Shelf items
        this.shelfItems.forEach(item => {
            item.addEventListener('click', () => {
                const target = item.dataset.target;
                const tabName = target.replace('panel-', '');
                this.switchTab(tabName);
            });
        });
    }

    switchTab(tabName) {
        if (tabName === this.currentTab) return;
        this.currentTab = tabName;

        // Update tab buttons
        this.tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update panels
        this.panels.forEach(panel => {
            panel.classList.toggle('active', panel.id === `panel-${tabName}`);
        });

        // Update shelf items
        this.shelfItems.forEach(item => {
            item.classList.toggle('active', item.dataset.target === `panel-${tabName}`);
        });

        // Trigger tab-specific initialization
        if (tabName === 'sources') {
            this._loadSources();
        }
    }

    async _loadSources() {
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
        const empty = document.getElementById('sources-empty');

        if (!container) return;

        if (documents.length === 0) {
            container.innerHTML = '';
            container.appendChild(empty || this._createEmptyState());
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
                        <div class="source-doc-name">${this._escapeHtml(doc.name)}</div>
                        <div class="source-doc-meta">${doc.path} • ${modified}</div>
                    </div>
                    <span class="source-doc-size">${size}</span>
                </div>
            `;
        }).join('');
    }

    _createEmptyState() {
        const div = document.createElement('div');
        div.className = 'sources-empty';
        div.id = 'sources-empty';
        div.innerHTML = `
            <div class="sources-empty-icon">📡</div>
            <div class="sources-empty-text">No documents ingested</div>
            <div class="sources-empty-subtext">Upload documents to the \`documents/\` folder for RAG retrieval</div>
        `;
        return div;
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

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}
