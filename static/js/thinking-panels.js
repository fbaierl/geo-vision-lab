/**
 * Thinking panels - manages thinking visualization in reasoning window
 */

const reasoningContent = document.getElementById('reasoning-content');
const reasoningPlaceholder = document.getElementById('reasoning-placeholder');
const reasoningLoading = document.getElementById('reasoning-loading');

let thinkingPanels = [];
let currentThinkingPanel = null;
let currentThinkingPanelContent = null;
let currentThinkingPanelHeader = null;
let thinkingSessionCounter = 0;

export function showThinkingPanel() {
    if (reasoningPlaceholder) reasoningPlaceholder.style.display = 'none';
    if (reasoningLoading) reasoningLoading.style.display = 'none';

    thinkingSessionCounter++;

    const thinkingPanel = document.createElement('div');
    thinkingPanel.className = 'thinking-panel';
    thinkingPanel.id = `thinking-panel-${thinkingSessionCounter}`;

    const thinkingPanelHeader = document.createElement('div');
    thinkingPanelHeader.className = 'thinking-header';
    thinkingPanelHeader.innerHTML = `
        <span class="thinking-header-icon">🧠</span>
        <span class="thinking-header-label">THINKING</span>
        <span class="thinking-header-toggle">▼</span>
    `;

    const thinkingPanelContent = document.createElement('div');
    thinkingPanelContent.className = 'thinking-body';

    thinkingPanel.appendChild(thinkingPanelHeader);
    thinkingPanel.appendChild(thinkingPanelContent);
    reasoningContent.appendChild(thinkingPanel);

    currentThinkingPanel = thinkingPanel;
    currentThinkingPanelHeader = thinkingPanelHeader;
    currentThinkingPanelContent = thinkingPanelContent;

    thinkingPanels.push({
        panel: thinkingPanel,
        header: thinkingPanelHeader,
        content: thinkingPanelContent,
        completed: false
    });

    thinkingPanelHeader.addEventListener('click', () => {
        if (thinkingPanelContent.style.display === 'none') {
            thinkingPanelContent.style.display = 'block';
            thinkingPanelHeader.querySelector('.thinking-header-toggle').style.transform = 'rotate(0deg)';
        } else {
            thinkingPanelContent.style.display = 'none';
            thinkingPanelHeader.querySelector('.thinking-header-toggle').style.transform = 'rotate(-180deg)';
        }
    });

    reasoningContent.scrollTop = reasoningContent.scrollHeight;
}

export function appendToThinkingPanel(text) {
    if (!currentThinkingPanelContent) return;
    currentThinkingPanelContent.textContent += text;
    currentThinkingPanelContent.scrollTop = currentThinkingPanelContent.scrollHeight;
}

export function collapseThinkingPanel() {
    if (!currentThinkingPanel) return;

    if (currentThinkingPanelContent) currentThinkingPanelContent.style.display = 'none';
    if (currentThinkingPanelHeader) {
        currentThinkingPanelHeader.querySelector('.thinking-header-toggle').style.transform = 'rotate(-180deg)';
        const label = currentThinkingPanelHeader.querySelector('.thinking-header-label');
        if (label) label.textContent = 'THINKING (complete)';
    }

    const currentPanel = thinkingPanels.find(p => p.panel === currentThinkingPanel);
    if (currentPanel) currentPanel.completed = true;
}

export function resetThinkingState() {
    currentThinkingPanel = null;
    currentThinkingPanelContent = null;
    currentThinkingPanelHeader = null;
}
