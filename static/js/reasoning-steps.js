/**
 * Reasoning steps - manages reasoning step visualization in reasoning window
 */

import { escapeHtml } from './utils.js';

const reasoningContent = document.getElementById('reasoning-content');
const reasoningPlaceholder = document.getElementById('reasoning-placeholder');
const reasoningLoading = document.getElementById('reasoning-loading');

const reasoningSteps = new Map();

export function addReasoningStep(phase, tool, query, model) {
    if (reasoningLoading && reasoningLoading.style.display !== 'none') {
        reasoningLoading.style.display = 'none';
        if (reasoningPlaceholder) reasoningPlaceholder.style.display = 'none';
    }

    if (reasoningPlaceholder) reasoningPlaceholder.remove();

    const step = document.createElement('div');
    step.className = `reasoning-step phase-${phase}`;

    let label = phase.toUpperCase();
    let desc = '';
    let hasQuery = false;

    if (phase === 'reasoning') desc = 'Planning analysis approach...';
    else if (phase === 'reviewing') desc = 'QA review in progress...';
    else if (phase === 'revising') desc = 'Formulating corrected response...';
    else if (phase === 'vector_search') {
        desc = 'Searching archival database...';
        hasQuery = true;
    }
    else if (phase === 'online_search') {
        desc = 'Querying live sources...';
        hasQuery = true;
    }
    else if (phase === 'streaming') desc = 'Delivering response...';
    else if (phase === 'extracting_locations') desc = 'Extracting geographic locations...';

    let modelTag = model ? ` <span class="reasoning-step-model">[${model}]</span>` : '';

    step.innerHTML = `
        <div class="reasoning-step-label">▸ ${label}${modelTag}</div>
        <div class="reasoning-step-desc">${escapeHtml(desc)}</div>
        ${hasQuery ? `<div class="reasoning-step-section">
            <div class="reasoning-step-toggle reasoning-step-query-toggle">
                <span class="arrow">▼</span>
                <span>Query</span>
            </div>
            <div class="reasoning-step-content reasoning-step-query-content">${escapeHtml(query)}</div>
        </div>` : ''}
        <div class="reasoning-step-result-section">
            <div class="reasoning-step-toggle reasoning-step-result-toggle">
                <span class="arrow">▼</span>
                <span>Result</span>
            </div>
            <div class="reasoning-step-content reasoning-step-result-content"></div>
        </div>
    `;

    reasoningContent.appendChild(step);

    if (tool && tool !== 'unknown') {
        reasoningSteps.set(tool, {
            step,
            resultSection: step.querySelector('.reasoning-step-result-section'),
            resultContent: step.querySelector('.reasoning-step-result-content')
        });
    }

    step.querySelectorAll('.reasoning-step-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const content = toggle.nextElementSibling;
            const arrow = toggle.querySelector('.arrow');
            const isExpanded = content.style.display !== 'none';
            content.style.display = isExpanded ? 'none' : 'block';
            arrow.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(180deg)';
        });
    });

    reasoningContent.scrollTop = reasoningContent.scrollHeight;
}

export function addReasoningResult(tool, summary, content) {
    const stepData = reasoningSteps.get(tool);
    if (!stepData) return;

    const { resultSection, resultContent } = stepData;

    resultSection.style.display = 'block';

    let displayContent = summary;
    if (content && content.length > 500) {
        displayContent = summary + '\n\n' + content.substring(0, 500) + '\n\n... (truncated)';
    } else if (content) {
        displayContent = summary + '\n\n' + content;
    }

    resultContent.textContent = displayContent;
}

export function addReasoningError(tool, errorMessage) {
    const errorStep = document.createElement('div');
    errorStep.className = 'reasoning-step phase-error';

    const errorHTML = `
        <div class="reasoning-step-label" style="color: var(--amber);">▸ ERROR</div>
        <div class="reasoning-step-desc" style="color: var(--text);">Tool: ${escapeHtml(tool)}</div>
        <div class="reasoning-step-content" style="display: block; margin-top: 6px; padding: 8px; background: rgba(229, 57, 53, 0.1); border: 1px solid var(--red); border-radius: 4px; font-size: 0.75rem; color: var(--red); white-space: pre-wrap; word-break: break-word;">${escapeHtml(errorMessage)}</div>
    `;

    errorStep.innerHTML = errorHTML;
    reasoningContent.appendChild(errorStep);
    reasoningContent.scrollTop = reasoningContent.scrollHeight;
}
