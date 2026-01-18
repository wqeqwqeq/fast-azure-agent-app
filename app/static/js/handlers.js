// ============================================================
// Event Handlers
// ============================================================

// Close dropdowns when clicking outside
document.addEventListener('click', (e) => {
    // Keep model selector open if clicking inside it
    if (e.target.closest('.model-selector-container')) {
        // Close agent dropdowns if clicking outside them but inside model selector
        if (!e.target.closest('.agent-model-dropdown') && !e.target.closest('.agent-model-btn')) {
            document.querySelectorAll('.agent-model-dropdown.open').forEach(dropdown => {
                dropdown.classList.remove('open');
            });
        }
        return;
    }
    // Keep config dropdown open if clicking inside the menu (not trigger)
    if (e.target.closest('.config-dropdown .dropdown-menu')) {
        return;
    }
    // Close everything when clicking outside
    if (!e.target.closest('.menu-wrapper') && !e.target.closest('.top-bar-dropdown')) {
        closeAllDropdowns();
    }
});

// ============================================================
// Chat Event Handlers
// ============================================================

async function handleNewChat() {
    const newConvo = await createConversation();
    currentConversationId = newConvo.id;
    // Reset agent-level overrides for new conversation
    agent_level_llm_overwrite = {};
    await fetchConversations();
    setActiveNavItem(null);
    renderConversationsList();
    renderModelSelector();
    renderWelcomeScreen();
}

async function selectConversation(id) {
    currentConversationId = id;

    // Load full conversation if messages not loaded
    let convo = conversations.find(c => c.id === id);
    if (!convo || !convo.messages || convo.messages.length === 0) {
        convo = await fetchConversation(id);
        const index = conversations.findIndex(c => c.id === id);
        if (index !== -1) {
            conversations[index] = convo;
        }
    }

    // Track if we need to re-render model selector
    let modelChanged = false;

    // Update selected model to match conversation's model
    if (convo.model && convo.model !== selectedModel) {
        selectedModel = convo.model;
        modelChanged = true;
    }

    // Restore agent-level LLM overwrite from conversation (or clear if none)
    if (convo.agent_level_llm_overwrite && Object.keys(convo.agent_level_llm_overwrite).length > 0) {
        agent_level_llm_overwrite = { ...convo.agent_level_llm_overwrite };
        modelChanged = true;
    } else if (Object.keys(agent_level_llm_overwrite).length > 0) {
        // Clear existing overrides if conversation has none
        agent_level_llm_overwrite = {};
        modelChanged = true;
    }

    // Re-render model selector if anything changed
    if (modelChanged) {
        renderModelSelector();
    }

    setActiveNavItem(null);

    if (convo.messages.length === 0) {
        renderWelcomeScreen();
    } else {
        renderConversation(convo);
    }

    renderConversationsList();
}

async function handleMenuAction(e) {
    e.stopPropagation();
    const action = e.currentTarget.dataset.action;
    const id = e.currentTarget.dataset.id;

    closeAllDropdowns();

    if (action === 'rename') {
        startInlineRename(id);
    } else if (action === 'delete') {
        await deleteConversation(id);

        if (currentConversationId === id) {
            await handleNewChat();
        } else {
            await fetchConversations();
            renderConversationsList();
        }
    }
}

function startInlineRename(id) {
    const convo = conversations.find(c => c.id === id);
    if (!convo) return;

    const chatItems = document.querySelectorAll('.chat-item');
    let targetChatItem = null;
    chatItems.forEach(item => {
        const titleSpan = item.querySelector('.chat-title');
        if (titleSpan && titleSpan.dataset.id === id) {
            targetChatItem = item;
        }
    });

    if (!targetChatItem) return;

    const titleSpan = targetChatItem.querySelector('.chat-title');
    const currentTitle = convo.title;

    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentTitle;
    input.className = 'chat-title-input';
    input.style.cssText = `
        flex: 1;
        background: white;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 0.95rem;
        font-family: inherit;
        color: var(--text-primary);
        outline: none;
        margin-right: 8px;
    `;

    titleSpan.replaceWith(input);
    input.focus();
    input.select();

    const saveRename = async () => {
        const newTitle = input.value.trim();
        if (newTitle && newTitle !== currentTitle) {
            await renameConversation(id, newTitle);
            await fetchConversations();
        }
        renderConversationsList();
    };

    const cancelRename = () => {
        renderConversationsList();
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveRename();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelRename();
        }
    });

    input.addEventListener('blur', saveRename);

    input.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

// ============================================================
// Model Sync Helper
// ============================================================

async function syncModelToCurrentConversation() {
    if (currentConversationId) {
        const convo = conversations.find(c => c.id === currentConversationId);
        if (convo && convo.model !== selectedModel) {
            await fetch(`${API_BASE}/api/conversations/${currentConversationId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: selectedModel })
            });
            convo.model = selectedModel;
        }
    }
}

// ============================================================
// Message Sending
// ============================================================

// Track current assistant message sequence for evaluation
let currentAssistantSeq = 0;

async function handleSendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();

    if (!message) return;

    input.value = '';
    input.disabled = true;

    const isOnWelcomeScreen = !document.querySelector('.messages-container');

    try {
        // Create new chat if needed
        if (!currentConversationId) {
            const newConvo = await createConversation();
            currentConversationId = newConvo.id;
        }

        // Transition from welcome screen to conversation view if needed
        if (isOnWelcomeScreen) {
            renderConversationFromWelcome();
        }

        // Immediately show user message
        appendUserMessage(message);

        // Show thinking indicator
        showThinkingIndicator();

        // Send message and stream response
        const response = await sendMessageStream(currentConversationId, message);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Parse SSE stream
        await streamSSE(response, {
            message: (data) => {
                if (data.type === 'assistant') {
                    currentAssistantSeq = data.seq;
                    replaceThinkingWithResponse(data.content, data.seq);
                    // Update title if changed
                    if (data.title) {
                        updateConversationTitle(data.title);
                    }
                }
            },
            thinking: (data) => {
                appendThinkingEvent(data);
            },
            stream: (data) => {
                // Handle streaming text from summary agent
                if (data.text) {
                    appendStreamingText(data.text);
                }
            },
            done: () => {
                // Stream complete
            }
        });

        // Update sidebar (conversation moved to top, title may have changed)
        await fetchConversations();
        renderConversationsList();

    } catch (error) {
        console.error('Error sending message:', error);
        const thinkingMsg = document.querySelector('.thinking-message');
        if (thinkingMsg) thinkingMsg.remove();
        alert('Failed to send message. Please try again.');
    } finally {
        const currentInput = document.getElementById('message-input');
        if (currentInput) {
            currentInput.disabled = false;
            currentInput.focus();
        }
    }
}

// Update conversation title in sidebar
function updateConversationTitle(newTitle) {
    const convo = conversations.find(c => c.id === currentConversationId);
    if (convo) {
        convo.title = newTitle;
    }
    renderConversationsList();
}

// ============================================================
// Configuration Dropdown Handler
// ============================================================

function initConfigDropdown() {
    // Initialize dropdown using generic function
    initDropdown('config-trigger-btn', 'config-dropdown');

    // ReAct Mode toggle handler (specific logic)
    const reactCheckbox = document.getElementById('react-mode-checkbox');
    if (reactCheckbox) {
        reactCheckbox.addEventListener('change', async (e) => {
            reactModeEnabled = e.target.checked;

            // Clear agent model overrides when switching modes
            // (agent lists differ between triage and dynamic workflows)
            agent_level_llm_overwrite = {};

            // Refresh agents list for new mode
            availableAgents = await fetchAgents(reactModeEnabled);

            // Re-render model selector with new agent list
            renderModelSelector();
        });
    }

    // Memory Agent toggle handler
    const memoryCheckbox = document.getElementById('memory-agent-checkbox');
    if (memoryCheckbox) {
        memoryCheckbox.checked = memoryAgentEnabled;
        memoryCheckbox.addEventListener('change', (e) => {
            memoryAgentEnabled = e.target.checked;
        });
    }
}

// ============================================================
// Input Handlers
// ============================================================

function attachInputHandlers() {
    const input = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');

    if (sendBtn) {
        sendBtn.addEventListener('click', handleSendMessage);
    }

    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
            }
        });
    }
}
