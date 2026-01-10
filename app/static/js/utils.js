// ============================================================
// Utility Functions
// ============================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// SSE Stream Parser for unified POST /messages endpoint
async function streamSSE(response, callbacks) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();  // Keep incomplete line

        let eventType = 'message';
        for (const line of lines) {
            if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
                try {
                    const data = JSON.parse(line.slice(5).trim());
                    if (callbacks[eventType]) {
                        callbacks[eventType](data);
                    }
                } catch (e) {
                    console.error('Failed to parse SSE data:', e);
                }
            }
        }
    }
}
