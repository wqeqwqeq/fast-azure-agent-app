// ============================================================
// Thinking Indicator Functions
// ============================================================

// Append a single user message to the current chat
function appendUserMessage(message) {
    const container = document.querySelector('.messages-container');
    if (!container) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message user';
    msgDiv.innerHTML = `
        <div class="message-role">You</div>
        <div class="message-content">${escapeHtml(message)}</div>
    `;
    container.appendChild(msgDiv);

    // Scroll to bottom
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.scrollTop = chatCanvas.scrollHeight;
}

// Show thinking indicator with container for streaming events
function showThinkingIndicator() {
    const container = document.querySelector('.messages-container');
    if (!container) return;

    // Clear previous thinking events
    currentThinkingEvents = [];

    // Close any open flyout
    closeThinkingFlyout();

    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'message assistant thinking-message';
    thinkingDiv.innerHTML = `
        <div class="message-role">Assistant</div>
        <div class="thinking-indicator">
            <div class="thinking-header">
                <span class="thinking-text">Thinking</span>
                <span class="thinking-dots"></span>
            </div>
        </div>
    `;
    container.appendChild(thinkingDiv);

    // Scroll to bottom
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.scrollTop = chatCanvas.scrollHeight;
}

// Append a thinking event to the indicator
function appendThinkingEvent(message) {
    const indicator = document.querySelector('.thinking-indicator');
    if (!indicator) return;

    const trimmedMessage = typeof message === 'string' ? message.trim() : JSON.stringify(message);

    // Try to parse as JSON for structured function events
    let eventData;
    try {
        eventData = typeof message === 'object' ? message : JSON.parse(trimmedMessage);
    } catch {
        // Plain text event (agent events) - store as text type
        currentThinkingEvents.push({ type: 'text', content: trimmedMessage });

        const eventDiv = document.createElement('div');
        eventDiv.className = 'thinking-event';
        eventDiv.textContent = trimmedMessage;
        indicator.appendChild(eventDiv);

        const chatCanvas = document.getElementById('chat-canvas');
        chatCanvas.scrollTop = chatCanvas.scrollHeight;
        return;
    }

    // Handle structured function events
    if (eventData.type === 'function_start') {
        currentThinkingEvents.push({
            type: 'function_start',
            function: eventData.function,
            arguments: eventData.arguments
        });

        const eventDiv = document.createElement('div');
        eventDiv.className = 'thinking-event';
        eventDiv.textContent = `Calling ${eventData.function}...`;
        indicator.appendChild(eventDiv);
    } else if (eventData.type === 'function_end') {
        currentThinkingEvents.push({
            type: 'function_end',
            function: eventData.function,
            result: eventData.result
        });

        const eventDiv = document.createElement('div');
        eventDiv.className = 'thinking-event';
        eventDiv.textContent = `${eventData.function} finished`;
        indicator.appendChild(eventDiv);
    } else if (eventData.type === 'agent_invoked') {
        currentThinkingEvents.push({ type: 'text', content: `Agent: ${eventData.agent}` });

        const eventDiv = document.createElement('div');
        eventDiv.className = 'thinking-event';
        eventDiv.textContent = `Agent: ${eventData.agent}`;
        indicator.appendChild(eventDiv);
    } else if (eventData.type === 'agent_finished') {
        currentThinkingEvents.push({ type: 'text', content: `Agent ${eventData.agent} finished` });

        const eventDiv = document.createElement('div');
        eventDiv.className = 'thinking-event';
        eventDiv.textContent = `Agent ${eventData.agent} finished`;
        indicator.appendChild(eventDiv);
    }

    // Scroll to bottom
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.scrollTop = chatCanvas.scrollHeight;
}

// Append streaming text to the current assistant message
function appendStreamingText(text) {
    const thinkingMsg = document.querySelector('.thinking-message');
    if (!thinkingMsg) return;

    // Find or create streaming content container
    let streamingContent = thinkingMsg.querySelector('.streaming-content');
    if (!streamingContent) {
        // Hide thinking indicator dots when streaming starts
        const thinkingDots = thinkingMsg.querySelector('.thinking-dots');
        if (thinkingDots) thinkingDots.style.display = 'none';

        // Update thinking text
        const thinkingText = thinkingMsg.querySelector('.thinking-text');
        if (thinkingText) thinkingText.textContent = 'Responding';

        streamingContent = document.createElement('div');
        streamingContent.className = 'streaming-content message-content';
        thinkingMsg.appendChild(streamingContent);
    }

    // Append text and re-render markdown
    const currentText = streamingContent.getAttribute('data-raw-text') || '';
    const newText = currentText + text;
    streamingContent.setAttribute('data-raw-text', newText);
    streamingContent.innerHTML = DOMPurify.sanitize(marked.parse(newText));

    // Scroll to bottom
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.scrollTop = chatCanvas.scrollHeight;
}

// Replace thinking indicator with actual response, keeping collapsed thinking
function replaceThinkingWithResponse(content, seq) {
    const thinkingMsg = document.querySelector('.thinking-message');
    if (thinkingMsg) {
        thinkingMsg.classList.remove('thinking-message');

        // Check if we already have streamed content
        const streamingContent = thinkingMsg.querySelector('.streaming-content');
        const hasStreamedContent = streamingContent && streamingContent.getAttribute('data-raw-text');

        // Keep the collapsed thinking indicator if there were events
        const thinkingCollapsed = currentThinkingEvents.length > 0 ? `
            <div class="thinking-collapsed-wrapper">
                <div class="thinking-collapsed" onclick="toggleThinkingFlyout(this)">
                    <svg class="thinking-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <path d="M12 6v6l4 2"></path>
                    </svg>
                    <span>Thinking finished</span>
                    <svg class="thinking-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </div>
            </div>
        ` : '';

        if (hasStreamedContent) {
            // We already streamed the content - just finalize the UI
            // Use the streamed content instead of the final content
            const streamedText = streamingContent.getAttribute('data-raw-text');
            thinkingMsg.innerHTML = `
                <div class="message-role">Assistant</div>
                ${thinkingCollapsed}
                <div class="message-content">${DOMPurify.sanitize(marked.parse(streamedText))}</div>
                ${renderEvaluationButtons(seq)}
            `;
        } else {
            // No streaming happened - use the final content
            thinkingMsg.innerHTML = `
                <div class="message-role">Assistant</div>
                ${thinkingCollapsed}
                <div class="message-content">${DOMPurify.sanitize(marked.parse(content))}</div>
                ${renderEvaluationButtons(seq)}
            `;
        }

        // Attach evaluation handlers for the new buttons
        attachEvaluationHandlers();
    }

    // Scroll to bottom
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.scrollTop = chatCanvas.scrollHeight;
}

// ============================================================
// Function Card Rendering for Flyout
// ============================================================

function renderFunctionCard(funcName, args, result) {
    const argsJson = JSON.stringify(args, null, 2);
    const resultJson = result !== null && result !== undefined ? JSON.stringify(result, null, 2) : null;

    return `
        <div class="function-card">
            <div class="function-header">
                <span class="function-name">Calling ${escapeHtml(funcName)}...</span>
            </div>
            <div class="function-details">
                <div class="function-section">
                    <div class="function-section-header" onclick="toggleFunctionSection(this)">
                        <svg class="section-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                        <span>Input Parameters</span>
                    </div>
                    <div class="function-section-content collapsed">
                        <pre class="json-display">${escapeHtml(argsJson)}</pre>
                    </div>
                </div>
                ${resultJson !== null ? `
                <div class="function-section">
                    <div class="function-section-header" onclick="toggleFunctionSection(this)">
                        <svg class="section-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                        <span>Output Result</span>
                    </div>
                    <div class="function-section-content collapsed">
                        <pre class="json-display">${escapeHtml(resultJson)}</pre>
                    </div>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

// Toggle collapsible section in function card
function toggleFunctionSection(header) {
    const content = header.nextElementSibling;
    const chevron = header.querySelector('.section-chevron');
    content.classList.toggle('collapsed');
    chevron.classList.toggle('expanded');
}

// Render all flyout events with function cards
function renderFlyoutEvents() {
    let html = '';
    let i = 0;

    while (i < currentThinkingEvents.length) {
        const event = currentThinkingEvents[i];

        if (event.type === 'text') {
            html += `<div class="flyout-event">${escapeHtml(event.content)}</div>`;
            i++;
        } else if (event.type === 'function_start') {
            if (showFuncResult) {
                const funcName = event.function;
                const args = event.arguments;
                let result = null;

                // Find matching end event
                for (let j = i + 1; j < currentThinkingEvents.length; j++) {
                    if (currentThinkingEvents[j].type === 'function_end'
                        && currentThinkingEvents[j].function === funcName) {
                        result = currentThinkingEvents[j].result;
                        break;
                    }
                }

                html += renderFunctionCard(funcName, args, result);
            } else {
                html += `<div class="flyout-event">Calling ${escapeHtml(event.function)}...</div>`;
            }
            i++;
        } else if (event.type === 'function_end') {
            if (!showFuncResult) {
                html += `<div class="flyout-event">${escapeHtml(event.function)} finished</div>`;
            }
            i++;
        } else {
            i++;
        }
    }

    return html;
}

// ============================================================
// Thinking Flyout Panel
// ============================================================

function toggleThinkingFlyout(element) {
    const existing = document.querySelector('.thinking-flyout');
    const mainArea = document.querySelector('.main-area');

    if (existing) {
        existing.remove();
        mainArea.classList.remove('flyout-open');
        document.querySelectorAll('.thinking-collapsed').forEach(el => {
            el.classList.remove('expanded');
        });
        return;
    }

    mainArea.classList.add('flyout-open');

    if (element) {
        element.classList.add('expanded');
    }

    const flyout = document.createElement('div');
    flyout.className = 'thinking-flyout';
    flyout.innerHTML = `
        <div class="flyout-header">
            <span>Thinking</span>
            <button class="flyout-close" onclick="closeThinkingFlyout()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        <div class="flyout-content">
            ${renderFlyoutEvents()}
        </div>
    `;
    mainArea.appendChild(flyout);
}

function closeThinkingFlyout() {
    const flyout = document.querySelector('.thinking-flyout');
    if (flyout) {
        flyout.remove();
    }
    const mainArea = document.querySelector('.main-area');
    if (mainArea) {
        mainArea.classList.remove('flyout-open');
    }
    document.querySelectorAll('.thinking-collapsed').forEach(el => {
        el.classList.remove('expanded');
    });
}
