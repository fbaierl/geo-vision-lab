/**
 * Model selector - handles model switching and settings
 */

let currentModel = 'qwen3.5:4b';
const modelToggle = document.getElementById('model-toggle');
const modelMenu = document.getElementById('model-menu');
const currentModelDisplay = document.getElementById('current-model');

// Model selector toggle
modelToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    modelMenu.classList.toggle('show');
});

document.addEventListener('click', (e) => {
    if (!modelToggle.contains(e.target) && !modelMenu.contains(e.target)) {
        modelMenu.classList.remove('show');
    }
});

// Load current model and settings
export async function loadCurrentModel() {
    try {
        const res = await fetch('/settings');
        const data = await res.json();

        if (data.all_models) {
            modelMenu.innerHTML = '';

            if (data.active_model_name) {
                currentModelDisplay.textContent = data.active_model_name;
                currentModel = data.active_model_name;
            }

            // Add Online LLM toggle
            const toggleContainer = document.createElement('div');
            toggleContainer.className = 'model-llm-toggle';
            toggleContainer.innerHTML = `
                <div class="llm-toggle-row">
                    <div class="llm-toggle-info">
                        <span class="llm-toggle-label">Use Online LLM</span>
                        <span class="llm-toggle-provider">Groq</span>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" id="online-llm-toggle" ${data.online_llm_enabled ? 'checked' : ''} ${!data.groq_api_key_configured ? 'disabled' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                ${!data.groq_api_key_configured ? '<div class="llm-toggle-warning">⚠️ GROQ_API_KEY not configured</div>' : ''}
            `;
            modelMenu.appendChild(toggleContainer);

            // Add separator
            const separator = document.createElement('div');
            separator.className = 'model-separator';
            separator.textContent = 'Available Models';
            modelMenu.appendChild(separator);

            // Add model options
            const localModels = data.all_models.filter(m => m.type === 'local');
            const onlineModels = data.all_models.filter(m => m.type === 'online');

            localModels.forEach(model => {
                const opt = createModelOption(model, data.online_llm_enabled);
                modelMenu.appendChild(opt);
            });

            if (data.groq_api_key_configured || data.online_llm_enabled) {
                onlineModels.forEach(model => {
                    const opt = createModelOption(model, data.online_llm_enabled);
                    modelMenu.appendChild(opt);
                });
            }

            // Set up toggle listener
            const toggle = document.getElementById('online-llm-toggle');
            if (toggle) {
                toggle.addEventListener('change', async function() {
                    const enabled = this.checked;
                    if (enabled && !data.groq_api_key_configured) {
                        showErrorModal();
                        this.checked = false;
                        return;
                    }
                    try {
                        const postRes = await fetch('/settings', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ use_online_llm: enabled })
                        });
                        const responseData = await postRes.json();
                        if (!responseData.success && responseData.error === 'groq_api_key_missing') {
                            showErrorModal();
                            this.checked = false;
                        } else {
                            loadCurrentModel();
                        }
                    } catch (e) {
                        console.error('Error toggling online LLM:', e);
                        this.checked = !enabled;
                    }
                });
            }
        }
    } catch (e) {
        console.warn('Failed to load settings:', e);
    }
}

function createModelOption(model, isOnlineEnabled) {
    const opt = document.createElement('div');
    opt.className = 'model-option';
    opt.setAttribute('data-value', model.id);

    const nameDiv = document.createElement('div');
    nameDiv.className = 'model-option-name';
    nameDiv.textContent = model.name;

    const badge = document.createElement('span');
    badge.className = `model-type-badge ${model.type}`;
    badge.textContent = model.type === 'online' ? 'Online' : 'Local';

    const nameContainer = document.createElement('div');
    nameContainer.className = 'model-name-container';
    nameContainer.appendChild(nameDiv);
    nameContainer.appendChild(badge);

    const providerDiv = document.createElement('div');
    providerDiv.className = 'model-option-provider';
    providerDiv.textContent = model.provider;

    opt.appendChild(nameContainer);
    opt.appendChild(providerDiv);

    if (model.current) {
        opt.classList.add('active');
        currentModelDisplay.textContent = model.name;
        currentModel = model.id;
    }

    if (model.type === 'online' && !isOnlineEnabled) {
        opt.classList.add('disabled');
        opt.title = 'Enable "Use Online LLM" toggle to select online models';
    } else {
        opt.addEventListener('click', async function() {
            const selected = this.getAttribute('data-value');
            modelMenu.classList.remove('show');

            modelMenu.querySelectorAll('.model-option').forEach(o => o.classList.remove('active'));
            this.classList.add('active');
            currentModelDisplay.textContent = this.querySelector('.model-option-name').textContent;
            currentModel = selected;

            try {
                const postRes = await fetch('/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: selected })
                });
                const responseData = await postRes.json();
                if (!responseData.success) {
                    console.error('Failed to switch model:', responseData.message);
                    if (responseData.error === 'groq_api_key_missing') {
                        showErrorModal();
                    }
                    loadCurrentModel();
                }
            } catch (e) {
                console.error('Error switching model:', e);
                loadCurrentModel();
            }
        });
    }

    return opt;
}

function showErrorModal() {
    let modal = document.getElementById('api-key-modal');
    if (modal) {
        modal.style.display = 'flex';
        return;
    }

    modal = document.createElement('div');
    modal.id = 'api-key-modal';
    modal.className = 'api-key-modal';
    modal.innerHTML = `
        <div class="api-key-modal-content">
            <div class="api-key-modal-header">
                <h3>⚠️ Groq API Key Required</h3>
                <button class="api-key-modal-close" onclick="this.closest('.api-key-modal').style.display='none'">×</button>
            </div>
            <div class="api-key-modal-body">
                <p>To use online LLM models, you need to configure your Groq API key.</p>
                <ol>
                    <li>Get your API key from <a href="https://console.groq.com" target="_blank">console.groq.com</a></li>
                    <li>Add it to your <code>.env</code> file:</li>
                </ol>
                <pre>GROQ_API_KEY=gsk_...</pre>
                <p>Then restart the application.</p>
            </div>
            <div class="api-key-modal-footer">
                <button class="api-key-modal-btn" onclick="this.closest('.api-key-modal').style.display='none'">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    modal.style.display = 'flex';
}

export function getCurrentModel() {
    return currentModel;
}
