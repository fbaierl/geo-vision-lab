/**
 * RAG configuration - handles loading and saving RAG settings
 */

export function initRAGConfig() {
    loadRAGConfig();

    const graderToggle = document.getElementById('grader-toggle');
    const rerankerToggle = document.getElementById('reranker-toggle');

    if (graderToggle) {
        graderToggle.addEventListener('change', function(e) {
            saveRAGConfig({ grader_enabled: e.target.checked });
        });
    }

    if (rerankerToggle) {
        rerankerToggle.addEventListener('change', function(e) {
            saveRAGConfig({ reranker_enabled: e.target.checked });
        });
    }
}

async function loadRAGConfig() {
    try {
        const res = await fetch('/api/v1/rag/config');
        if (!res.ok) throw new Error('Failed to load RAG config');
        const config = await res.json();

        // Update toggle states
        document.getElementById('grader-toggle').checked = config.grader_enabled;
        document.getElementById('reranker-toggle').checked = config.reranker_enabled;

        console.log('[RAG_CONFIG] Loaded configuration:', config);
    } catch (error) {
        console.warn('[RAG_CONFIG] Failed to load config:', error);
    }
}

async function saveRAGConfig(updates) {
    const statusEl = document.getElementById('rag-config-status');
    const statusText = document.getElementById('rag-status-text');

    if (statusEl) statusEl.style.display = 'block';
    if (statusText) statusText.textContent = 'Saving...';

    try {
        const res = await fetch('/api/v1/rag/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (!res.ok) throw new Error('Failed to save RAG config');
        const config = await res.json();

        if (statusText) statusText.textContent = 'Configuration saved successfully';
        if (statusEl) {
            statusEl.style.background = 'rgba(124, 179, 66, 0.2)';
            statusEl.style.color = 'var(--green)';
        }

        setTimeout(() => {
            if (statusEl) statusEl.style.display = 'none';
        }, 3000);

        console.log('[RAG_CONFIG] Saved configuration:', config);
    } catch (error) {
        console.error('[RAG_CONFIG] Failed to save config:', error);
        if (statusEl) {
            statusEl.style.display = 'block';
            if (statusText) statusText.textContent = 'Failed to save configuration';
            statusEl.style.background = 'rgba(229, 57, 53, 0.2)';
            statusEl.style.color = 'var(--red)';
        }
    }
}
