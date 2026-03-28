# Ontology v2: Session Persistence & Management

## Overview

Implement full session persistence to MongoDB, enabling users to save, load, and manage multiple conversation sessions with their associated ontologies and chat history.

## User Stories

1. **As a user**, I want my conversations to persist across browser restarts so I don't lose my work
2. **As a user**, I want to switch between multiple sessions so I can work on different topics
3. **As a user**, I want sessions to have meaningful titles so I can identify them later
4. **As a user**, I want to delete old sessions so I can keep my workspace organized
5. **As a user**, I want my ontology to persist automatically so it accumulates across queries

## Requirements

### Backend

#### 1. MongoDB Schema

**Collection: `sessions`**
```javascript
{
  _id: ObjectId,
  thread_id: UUID,              // Unique session identifier
  title: String,                // Auto-generated or user-edited
  created_at: ISODate,
  updated_at: ISODate,
  messages: [                   // Full chat history
    {
      role: "user" | "assistant",
      content: String,
      timestamp: ISODate,
      metadata: Object          // Optional: tool calls, reasoning traces
    }
  ],
  ontology: {                   // Current ontology state
    entities: {                 // UUID -> Entity mapping
      "uuid-1": {
        "uuid": "uuid-1",
        "name": "Germany",
        "type": "Location",
        "properties": {...},
        "mentions": [...]
      }
    },
    links: {                    // UUID -> Link mapping
      "uuid-2": {
        "uuid": "uuid-2",
        "source_uuid": "uuid-1",
        "target_uuid": "uuid-3",
        "type": "LOCATED_IN",
        ...
      }
    }
  }
}
```

#### 2. API Endpoints

**`POST /api/sessions`** - Create new session
- Request: `{ title?: string }`
- Response: `{ thread_id: UUID, created_at: ISODate }`
- Auto-generates UUID, creates empty session

**`GET /api/sessions`** - List all sessions
- Response: `[{ thread_id, title, updated_at, message_count }]`
- Sorted by `updated_at` descending

**`GET /api/sessions/{thread_id}`** - Get full session
- Response: `{ thread_id, title, messages[], ontology{} }`
- Returns complete session state

**`PUT /api/sessions/{thread_id}`** - Update session
- Request: `{ title?: string, ontology?: object, messages?: array }`
- Updates specified fields, updates `updated_at`

**`DELETE /api/sessions/{thread_id}`** - Delete session
- Removes session from MongoDB
- No confirmation (instant delete)

**`POST /api/sessions/{thread_id}/save`** - Auto-save after query
- Called automatically after each query completes
- Request: `{ messages: [], ontology: {} }`
- Upserts session, updates `updated_at`

#### 3. Auto-Title Generation

```python
def extract_title_from_query(query: str) -> str:
    """Generate session title from first query."""
    words = query.split()[:6]
    title = " ".join(words)
    if len(query.split()) > 6:
        title += "..."
    return title
```

#### 4. Auto-Save Integration

In `process_query_stream()`:
- After streaming completes, call `save_session()` with:
  - Full message history from LangGraph state
  - Current ontology from `STATE_KEY_ONTOLOGY`
- Triggered automatically, transparent to user

### Frontend

#### 1. History Window Integration

**Current**: Shows query count, average time, last tool used

**New**: Session list with:
```
┌─────────────────────────────────┐
│ History                         │
├─────────────────────────────────┤
│ Queries: 15  |  Avg: 12s        │
├─────────────────────────────────┤
│ Sessions                        │
│ ┌─────────────────────────────┐ │
│ │ ● Iran Conflict Analysis    │ │
│ │   Updated 2 min ago         │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ○ German Chancellors        │ │
│ │   Updated 1 hour ago        │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ○ Weather Query             │ │
│ │   Updated yesterday         │ │
│ └─────────────────────────────┘ │
│                                 │
│ [+ New Session]                 │
└─────────────────────────────────┘
```

**Features**:
- Click session → Navigate to `/?thread={thread_id}` (full reload)
- Hover session → Show delete button (×)
- Active session highlighted with `●`
- "+ New Session" button creates new session

#### 2. Session Title Display

**Location**: Top of chat window (near model selector)

```
┌─────────────────────────────────────────┐
│ Iran Conflict Analysis          [Edit]  │
│ Qwen 3.5 4B                      ▼      │
└─────────────────────────────────────────┘
```

**Edit Flow**:
- Click [Edit] → Title becomes input field
- Press Enter or blur → Save via `PUT /api/sessions/{id}`
- Auto-save title after first query

#### 3. Thread ID Management

**On Page Load**:
```javascript
// Priority: URL param > localStorage > default
const threadId = getUrlParam('thread') 
              || localStorage.getItem('geovision_thread_id')
              || 'default';

// Load session and hydrate UI
const session = await fetch(`/api/sessions/${threadId}`);
hydrateChat(session.messages);
hydrateOntology(session.ontology);
```

**On Session Switch**:
```javascript
function switchSession(threadId) {
    localStorage.setItem('geovision_thread_id', threadId);
    window.location.href = `/?thread=${threadId}`;
}
```

#### 4. Auto-Save After Query

In `process_query_stream()` completion:
```javascript
// After streaming completes
await fetch(`/api/sessions/${threadId}/save`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        messages: currentMessages,
        ontology: currentOntology
    })
});
```

## Implementation Checklist

### Phase 1: Backend Foundation
- [ ] Create MongoDB `sessions` collection schema
- [ ] Implement `POST /api/sessions` (create)
- [ ] Implement `GET /api/sessions` (list)
- [ ] Implement `GET /api/sessions/{id}` (get)
- [ ] Implement `PUT /api/sessions/{id}` (update)
- [ ] Implement `DELETE /api/sessions/{id}` (delete)
- [ ] Implement `POST /api/sessions/{id}/save` (auto-save)
- [ ] Add auto-title extraction function
- [ ] Integrate auto-save into `process_query_stream()`

### Phase 2: Frontend - Session Management
- [ ] Update History window HTML/CSS for session list
- [ ] Fetch sessions on page load
- [ ] Render session list with active indicator
- [ ] Implement session click → navigation
- [ ] Implement delete button (instant, no confirm)
- [ ] Implement "+ New Session" button

### Phase 3: Frontend - Title Editing
- [ ] Add session title display in chat header
- [ ] Implement inline edit (click → input → save)
- [ ] Auto-set title after first query

### Phase 4: Thread ID Flow
- [ ] Load thread ID from URL param on page load
- [ ] Fallback to localStorage
- [ ] Fallback to 'default'
- [ ] Update localStorage on session switch
- [ ] Hydrate chat + ontology from session data

### Phase 5: Testing & Polish
- [ ] Test session creation
- [ ] Test session switching
- [ ] Test auto-save after queries
- [ ] Test ontology persistence
- [ ] Test chat history persistence
- [ ] Test title editing
- [ ] Test session deletion
- [ ] Test page reload preserves state

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **UI Location** | History Window | Reuse existing UI element, familiar to users |
| **Auto-Title** | Query Truncation | Instant, no latency, good enough |
| **Session Switch** | Full Page Reload | Simpler implementation, clean state |
| **Default Session** | Always Available | No friction for first-time users |
| **Delete** | Instant (no confirm) | Faster workflow, export as backup |
| **Auto-Save** | After Each Query | No data loss, acceptable DB load |
| **Versioning** | Current State Only | Simpler, less storage |
| **Chat History** | Full Storage | Can resume conversations, context preserved |

## Migration Notes

- Existing `sessions` collection used for ontology storage → extend schema
- `thread_id` already used in LangGraph checkpoints → maintain compatibility
- Export/Import format unchanged (already includes `thread_id` in metadata)

## Future Enhancements

- [ ] Session search/filter
- [ ] Session tags/categories
- [ ] Ontology versioning (snapshots over time)
- [ ] Session sharing/export as bundle
- [ ] Merge sessions
- [ ] Session templates
- [ ] Archive old sessions
