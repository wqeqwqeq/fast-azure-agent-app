// ============================================================
// API Client Functions
// ============================================================
const API_BASE = '';  // Same origin

async function fetchUser() {
    const res = await fetch(`${API_BASE}/api/user`);
    return res.json();
}

async function fetchConversations() {
    const res = await fetch(`${API_BASE}/api/conversations`);
    conversations = await res.json();
    return conversations;
}

async function fetchConversation(id) {
    const res = await fetch(`${API_BASE}/api/conversations/${id}`);
    return res.json();
}

async function createConversation() {
    const res = await fetch(`${API_BASE}/api/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: selectedModel })
    });
    return res.json();
}

async function renameConversation(id, title) {
    const res = await fetch(`${API_BASE}/api/conversations/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
    });
    return res.json();
}

async function deleteConversation(id) {
    await fetch(`${API_BASE}/api/conversations/${id}`, {
        method: 'DELETE'
    });
}

// Send message and return Response for SSE streaming
async function sendMessageStream(id, message) {
    return fetch(`${API_BASE}/api/conversations/${id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, react_mode: reactModeEnabled })
    });
}

async function fetchModels() {
    const res = await fetch(`${API_BASE}/api/models`);
    const data = await res.json();
    return data.models || [];
}

async function fetchSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        const settings = await res.json();
        showFuncResult = settings.show_func_result;
    } catch (error) {
        console.error('Failed to fetch settings:', error);
    }
}

// ============================================================
// Evaluation API Functions
// ============================================================

async function setEvaluation(conversationId, sequenceNumber, isSatisfy, comment = null) {
    const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages/${sequenceNumber}/evaluation`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_satisfy: isSatisfy, comment })
    });
    return res.json();
}

async function clearEvaluation(conversationId, sequenceNumber) {
    const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages/${sequenceNumber}/evaluation/clear`, {
        method: 'PATCH'
    });
    return res.json();
}
