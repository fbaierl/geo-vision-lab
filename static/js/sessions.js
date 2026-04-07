/**
 * Session Manager - handles session loading, switching, creation, and deletion
 */

import { escapeHtml, getTimeAgo, showToast } from './utils.js';
import { renderGraph } from './graph.js';
import { renderMap } from './map.js';

export class SessionManager {
    constructor() {
        this.currentThreadId = null;
    }

    async init() {
        // Load thread ID from URL param, then localStorage, then default
        const urlParams = new URLSearchParams(window.location.search);
        this.currentThreadId = urlParams.get('thread')
                            || localStorage.getItem('geovision_thread_id')
                            || 'default';

        console.log('[SESSION] Loaded thread ID:', this.currentThreadId);

        // Persist to localStorage
        localStorage.setItem('geovision_thread_id', this.currentThreadId);

        // Load session data and hydrate UI
        await this.loadSessionData();

        // Load sessions for sidebar
        this.loadSessions();

        // New session button
        document.getElementById('new-session-btn')?.addEventListener('click', () => {
            this.createNewSession();
        });

        // Clear all sessions button
        document.getElementById('clear-all-sessions-btn')?.addEventListener('click', () => {
            this.clearAllSessions();
        });
    }

    async loadSessionData() {
        try {
            console.log('[SESSION] Loading session data for:', this.currentThreadId);
            const response = await fetch(`/api/sessions/${this.currentThreadId}`);
            if (!response.ok) throw new Error('Failed to load session');

            const session = await response.json();
            console.log('[SESSION] Loaded session:', session);

            // Hydrate chat messages
            if (session.messages && session.messages.length > 0) {
                this.hydrateChat(session.messages);
            }

            // Hydrate ontology
            if (session.ontology && (session.ontology.entities || session.ontology.links)) {
                this.hydrateOntology(session.ontology);
            }
        } catch (error) {
            console.error('[SESSION] Error loading session data:', error);
        }
    }

    hydrateChat(messages) {
        console.log('[SESSION] Hydrating chat with', messages.length, 'messages');
        const messagesContainer = document.getElementById('chat-messages');
        if (!messagesContainer) return;

        // Clear existing messages (keep system message)
        const systemMsg = messagesContainer.querySelector('.chat-message.system');
        messagesContainer.innerHTML = '';
        if (systemMsg) messagesContainer.appendChild(systemMsg);

        // Add messages - need access to addMessage from chat module
        window.addMessageFn = window.addMessageFn || (() => {});
        
        messages.forEach(msg => {
            if (msg.role === 'user') {
                window.addMessageFn(escapeHtml(msg.content), true);
            } else if (msg.role === 'assistant') {
                window.addMessageFn(msg.content, false);
            }
        });
    }

    hydrateOntology(ontology) {
        console.log('[SESSION] Hydrating ontology:',
            Object.keys(ontology.entities || {}).length, 'entities',
            Object.keys(ontology.links || {}).length, 'links');

        // Update ontology tab manager
        if (window.ontologyTabManager) {
            window.ontologyTabManager.updateOntology(ontology);
        }

        // Render graph if we have data
        const entityCount = Object.keys(ontology.entities || {}).length;
        const linkCount = Object.keys(ontology.links || {}).length;
        const hasData = entityCount > 0 || linkCount > 0;

        const graphContainer = document.getElementById('graph-container');
        const graphEmptyState = document.getElementById('graph-empty-state');

        if (graphContainer && hasData) {
            renderGraph(ontology, graphContainer);
            if (graphEmptyState) graphEmptyState.style.display = 'none';
        } else if (graphEmptyState) {
            graphEmptyState.style.display = 'flex';
        }

        // Extract map locations and render map
        const mapContainer = document.getElementById('map-container');
        const mapEmptyState = document.getElementById('map-empty-state');
        const locations = Object.values(ontology.entities || {}).filter(
            e => e.type === 'Location' && e.properties && e.properties.lat && e.properties.lon
        ).map(e => ({
            name: e.name,
            type: e.type,
            lat: e.properties.lat,
            lon: e.properties.lon,
            relevance: e.properties.relevance || 0.5
        }));

        if (mapContainer && locations.length > 0) {
            renderMap(locations, mapContainer);
            if (mapEmptyState) mapEmptyState.style.display = 'none';
            const winData = window.windowManager?.windows?.get('window-maps');
            if (winData && winData.minimized) {
                window.windowManager.restoreWindow('window-maps');
            }
        } else if (mapEmptyState) {
            mapEmptyState.style.display = 'flex';
        }
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/sessions');
            if (!response.ok) throw new Error('Failed to load sessions');

            const sessions = await response.json();
            this.renderSessions(sessions);
        } catch (error) {
            console.error('[SESSION] Error loading sessions:', error);
        }
    }

    renderSessions(sessions) {
        const container = document.getElementById('sessions-list');
        if (!container) return;

        if (sessions.length === 0) {
            container.innerHTML = '<div class="no-sessions">No sessions yet</div>';
            return;
        }

        container.innerHTML = sessions.map(session => {
            const isActive = session.thread_id === this.currentThreadId;
            const updated = new Date(session.updated_at);
            const timeAgo = getTimeAgo(updated);

            return `
                <div class="session-item ${isActive ? 'active' : ''}" data-thread-id="${session.thread_id}">
                    <span class="session-title-text">${escapeHtml(session.title)}</span>
                    <span class="session-updated">${timeAgo}</span>
                    <button class="session-delete" data-thread-id="${session.thread_id}" title="Delete">×</button>
                </div>
            `;
        }).join('');

        // Add click handlers
        container.querySelectorAll('.session-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (!e.target.classList.contains('session-delete')) {
                    const threadId = item.dataset.threadId;
                    this.switchSession(threadId);
                }
            });
        });

        container.querySelectorAll('.session-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const threadId = btn.dataset.threadId;
                this.deleteSession(threadId);
            });
        });
    }

    switchSession(threadId) {
        console.log('[SESSION] Switching to:', threadId);
        localStorage.setItem('geovision_thread_id', threadId);
        window.location.href = `/?thread=${threadId}`;
    }

    async createNewSession() {
        try {
            const response = await fetch('/api/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ title: null })
            });

            if (!response.ok) throw new Error('Failed to create session');

            const result = await response.json();
            console.log('[SESSION] Created new session:', result.thread_id);

            // Navigate to new session
            this.switchSession(result.thread_id);
        } catch (error) {
            console.error('[SESSION] Error creating session:', error);
        }
    }

    async deleteSession(threadId) {
        try {
            const response = await fetch(`/api/sessions/${threadId}`, {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error('Failed to delete session');

            console.log('[SESSION] Deleted session:', threadId);

            // If deleting current session, create new one
            if (threadId === this.currentThreadId) {
                this.createNewSession();
            } else {
                // Reload sessions list
                this.loadSessions();
            }
        } catch (error) {
            console.error('[SESSION] Error deleting session:', error);
        }
    }

    async clearAllSessions() {
        if (!confirm('Are you sure you want to delete all sessions? This cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch('/api/sessions', {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error('Failed to clear all sessions');

            const result = await response.json();
            console.log('[SESSION] Cleared all sessions:', result);

            // Create a new session after clearing all
            this.createNewSession();
        } catch (error) {
            console.error('[SESSION] Error clearing all sessions:', error);
        }
    }

    getThreadId() {
        return this.currentThreadId;
    }
}
