/**
 * Main application entry point - initializes all modules
 */

import { WindowManager } from './window-manager.js';
import { OntologyTabManager } from './ontology-tabs.js';
import { OntologyImportExportHandler } from './import-export.js';
import { SessionManager } from './sessions.js';
import { initModelStatusMonitoring } from './model-status.js';
import { initRAGConfig } from './rag-config.js';
// Import chat module (initializes models, GPU status, and event listeners)
import './chat.js';

// Initialize window manager
const windowManager = new WindowManager();
window.windowManager = windowManager;

// Initialize ontology tab manager
const ontologyTabManager = new OntologyTabManager();
window.ontologyTabManager = ontologyTabManager;

// Initialize import/export handler
const ontologyImportExport = new OntologyImportExportHandler();
window.ontologyImportExport = ontologyImportExport;

// Initialize session manager
(async function initSessionManager() {
    const sessionManager = new SessionManager();
    await sessionManager.init();
})();

// Initialize model status monitoring
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
initModelStatusMonitoring(chatInput, sendBtn);

// Initialize RAG config
initRAGConfig();

// Close menus when clicking outside
document.addEventListener('click', function(e) {
    document.querySelectorAll('.menu-item').forEach(menu => {
        if (!menu.contains(e.target)) {
            menu.classList.remove('open');
        }
    });
});
