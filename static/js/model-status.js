/**
 * Model status monitoring - polls /system/models/status and updates the loading banner
 */

export function initModelStatusMonitoring(chatInput, sendBtn) {
    const modelStatusBanner = document.getElementById('model-status-banner');
    const modelStatusText = document.getElementById('model-status-text');
    const modelStatusAvatar = document.getElementById('model-status-avatar');

    // Disable input until models are ready
    chatInput.disabled = true;
    chatInput.placeholder = 'AI models are loading — please wait…';
    sendBtn.disabled = true;

    function setModelItemUI(elId, modelStatus, label) {
        const el = document.getElementById(elId);
        if (!el) return;
        const dot = el.querySelector('.msi-dot');
        const lbl = el.querySelector('.msi-label');
        if (lbl && label) lbl.textContent = label;
        if (dot) {
            dot.className = 'msi-dot';
            if (modelStatus === 'ready') dot.classList.add('ready');
            else if (modelStatus === 'error') dot.classList.add('error');
            else dot.classList.add('loading');
        }
        // Prepend emoji
        if (lbl) {
            const emoji = modelStatus === 'ready' ? '✅ ' : modelStatus === 'error' ? '❌ ' : '⏳ ';
            lbl.textContent = emoji + (label || lbl.textContent.replace(/^[✅❌⏳] /, ''));
        }
    }

    function updateModelStatusUI(status) {
        if (!modelStatusBanner) return;

        const models = status.models || {};
        setModelItemUI('status-ner', (models.ner || {}).status, (models.ner || {}).label);
        setModelItemUI('status-embeddings', (models.embeddings || {}).status, (models.embeddings || {}).label);
        setModelItemUI('status-reranker', (models.reranker || {}).status, (models.reranker || {}).label);
        setModelItemUI('status-llm', (models.llm || {}).status, (models.llm || {}).label);

        if (status.ready) {
            // All models ready — update banner then auto-dismiss
            modelStatusAvatar.textContent = '✅';
            modelStatusText.innerHTML = '<strong>All AI models loaded and ready!</strong>';
            modelStatusBanner.classList.add('models-ready');

            // Re-enable chat input
            chatInput.disabled = false;
            chatInput.placeholder = 'Enter your intelligence query…';
            sendBtn.disabled = false;

            // Auto-dismiss banner after 3 seconds
            setTimeout(() => {
                modelStatusBanner.style.opacity = '0';
                modelStatusBanner.style.transition = 'opacity 0.6s ease';
                setTimeout(() => { modelStatusBanner.style.display = 'none'; }, 700);
            }, 3000);
        } else if (status.any_error) {
            modelStatusText.innerHTML = '<strong>⚠️ Some models failed to load.</strong> Queries may not work correctly.';
            // Still enable the input so the user can try
            chatInput.disabled = false;
            chatInput.placeholder = 'Enter your intelligence query…';
            sendBtn.disabled = false;
        }
    }

    // Poll model status every 2 seconds
    async function pollModelStatus() {
        try {
            const response = await fetch('/system/models/status');
            const status = await response.json();
            updateModelStatusUI(status);
            if (!status.ready && !status.any_error) {
                setTimeout(pollModelStatus, 2000);
            }
        } catch (e) {
            // API might not be up yet — keep retrying
            setTimeout(pollModelStatus, 2000);
        }
    }

    // Start polling immediately on page load
    pollModelStatus();
}
