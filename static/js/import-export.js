/**
 * Import/Export handler for ontology projects
 */

import { showToast } from './utils.js';

export class OntologyImportExportHandler {
    constructor() {
        this.pendingFile = null;
        this.init();
    }

    init() {
        // File input change
        document.getElementById('ontology-import-input')?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.showImportModal(e.target.files[0]);
            }
        });

        // Global menu - File > Export Project
        document.getElementById('export-project-global')?.addEventListener('click', () => {
            this.exportProject();
            this.closeFileMenu();
        });

        // Global menu - File > Import Project
        document.getElementById('import-project-global')?.addEventListener('click', () => {
            document.getElementById('ontology-import-input').click();
            this.closeFileMenu();
        });

        // File menu toggle
        const fileMenu = document.getElementById('file-menu');
        if (fileMenu) {
            fileMenu.addEventListener('click', (e) => {
                e.stopPropagation();
                fileMenu.classList.toggle('open');
            });
        }

        // Close menu when clicked outside
        document.addEventListener('click', () => {
            this.closeFileMenu();
        });
    }

    closeFileMenu() {
        document.getElementById('file-menu')?.classList.remove('open');
    }

    async exportProject() {
        try {
            const threadId = window.currentThreadId || 'default';
            const response = await fetch(`/api/ontology/${threadId}/export`);

            if (!response.ok) throw new Error('Export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `geovision_project_${threadId}_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            showToast('Project exported successfully');
        } catch (error) {
            showToast(`Export failed: ${error.message}`, 'error');
        }
    }

    showImportModal(file) {
        this.pendingFile = file;
        document.getElementById('ontology-import-modal').style.display = 'flex';
    }

    async confirmImport() {
        const mode = document.querySelector('input[name="import-mode"]:checked').value;

        try {
            console.log('[IMPORT] Starting import...', {
                fileName: this.pendingFile?.name,
                threadId: window.currentThreadId || 'default',
                mode: mode
            });

            const formData = new FormData();
            formData.append('file', this.pendingFile);

            const threadId = window.currentThreadId || 'default';
            console.log('[IMPORT] Fetching', `/api/ontology/${threadId}/import?mode=${mode}`);

            const response = await fetch(`/api/ontology/${threadId}/import?mode=${mode}`, {
                method: 'POST',
                body: formData
            });

            console.log('[IMPORT] Response status:', response.status);

            if (!response.ok) {
                const error = await response.json();
                console.error('[IMPORT] Server error:', error);
                throw new Error(error.detail || 'Import failed');
            }

            const result = await response.json();
            console.log('[IMPORT] Success:', result);

            // Store the thread ID from the import result
            if (result.thread_id) {
                localStorage.setItem('geovision_thread_id', result.thread_id);
                window.currentThreadId = result.thread_id;
                console.log('[IMPORT] Stored thread ID:', result.thread_id);
            }

            this.closeImportModal();
            showToast(`Project imported: ${result.imported_entities} entities, ${result.imported_links} relationships (${mode} mode)`);

            // Reload page to show imported ontology
            console.log('[IMPORT] Reloading page in 1 second...');
            setTimeout(() => window.location.reload(), 1000);

        } catch (error) {
            console.error('[IMPORT] Error:', error);
            showToast(`Import failed: ${error.message}`, 'error');
        }
    }

    closeImportModal() {
        document.getElementById('ontology-import-modal').style.display = 'none';
        document.getElementById('ontology-import-input').value = '';
        this.pendingFile = null;
    }
}

// Expose functions for modal buttons
window.closeImportModal = () => {
    if (window.ontologyImportExport) {
        window.ontologyImportExport.closeImportModal();
    }
};
window.confirmImport = () => {
    if (window.ontologyImportExport) {
        window.ontologyImportExport.confirmImport();
    }
};
