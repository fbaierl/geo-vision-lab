/**
 * Main application entry point - initializes all modules
 */

import { OntologyTabManager } from './ontology-tabs.js';
import { OntologyImportExportHandler } from './import-export.js';
import { SessionManager } from './sessions.js';
import { initModelStatusMonitoring } from './model-status.js';
import { initRAGConfig } from './rag-config.js';
import { MainTabManager } from './main-tabs.js';
import { PendingOntologyManager } from './pending-ontology.js';
// Import chat module (initializes models, GPU status, and event listeners)
import './chat.js';

// Initialize ontology tab manager
const ontologyTabManager = new OntologyTabManager();
window.ontologyTabManager = ontologyTabManager;

// Initialize import/export handler
const ontologyImportExport = new OntologyImportExportHandler();
window.ontologyImportExport = ontologyImportExport;

// Initialize main tab manager (User, Sources, Ontology)
const mainTabManager = new MainTabManager();
window.mainTabManager = mainTabManager;

// Initialize pending ontology manager
const pendingOntologyManager = new PendingOntologyManager();
window.pendingOntologyManager = pendingOntologyManager;

// Initialize session manager
(async function initSessionManager() {
    const sessionManager = new SessionManager();
    await sessionManager.init();
    
    // After session init, load pending ontology
    const threadId = localStorage.getItem('geovision_thread_id') || 'default';
    pendingOntologyManager.setThreadId(threadId);
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


