// ============================================================
// UI Rendering Functions
// ============================================================

// ============================================================
// Dropdown Management
// ============================================================
function closeAllDropdowns() {
    // Close all chat menu dropdowns
    document.querySelectorAll('.menu-wrapper.open').forEach(wrapper => {
        wrapper.classList.remove('open');
    });
    // Close all top-bar dropdowns (model-selector, config-dropdown)
    document.querySelectorAll('.top-bar-dropdown.open').forEach(dropdown => {
        dropdown.classList.remove('open');
    });
    // Close agent model dropdowns
    document.querySelectorAll('.agent-model-dropdown.open').forEach(dropdown => {
        dropdown.classList.remove('open');
    });
    openDropdown = null;
}

// Generic dropdown initialization (reusable for any top-bar dropdown)
function initDropdown(triggerId, containerId) {
    const triggerBtn = document.getElementById(triggerId);
    const container = document.getElementById(containerId);

    if (triggerBtn && container) {
        triggerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const wasOpen = container.classList.contains('open');
            closeAllDropdowns();
            if (!wasOpen) {
                container.classList.add('open');
            }
        });
    }
}

// ============================================================
// Navigation Item Active State
// ============================================================
function setActiveNavItem(itemId) {
    // Remove active class from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Remove active class from all chat items
    document.querySelectorAll('.chat-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add active class to specified item
    if (itemId) {
        const item = document.getElementById(itemId);
        if (item) {
            item.classList.add('active');
        }
    }
}

// ============================================================
// User Info Rendering
// ============================================================
function renderUserInfo() {
    const avatarDiv = document.getElementById('user-avatar');
    const userNameSpan = document.getElementById('user-name');
    const userTagSpan = document.getElementById('user-tag');

    if (userInfo.mode === 'local') {
        avatarDiv.textContent = 'L';
        userNameSpan.textContent = 'Local Mode';
        userTagSpan.textContent = '';
    } else if (userInfo.mode === 'local_psql') {
        avatarDiv.textContent = userInfo.user_name.charAt(0).toUpperCase();
        userNameSpan.textContent = userInfo.user_name;
        userTagSpan.textContent = 'Test (PostgreSQL)';
    } else if (userInfo.mode === 'local_redis') {
        avatarDiv.textContent = userInfo.user_name.charAt(0).toUpperCase();
        userNameSpan.textContent = userInfo.user_name;
        userTagSpan.textContent = 'Test (Redis)';
    } else {
        avatarDiv.textContent = userInfo.user_name.charAt(0).toUpperCase();
        userNameSpan.textContent = userInfo.user_name;
        userTagSpan.textContent = '';
    }
}

// ============================================================
// Conversations List Rendering
// ============================================================
function renderConversationsList() {
    const chatListDiv = document.getElementById('chat-list');
    chatListDiv.innerHTML = '';

    if (conversations.length === 0) {
        chatListDiv.innerHTML = '<div style="padding: 12px; color: #999; font-size: 0.85rem;">No chats yet</div>';
        return;
    }

    conversations.forEach(convo => {
        const chatItemDiv = document.createElement('div');
        chatItemDiv.className = convo.id === currentConversationId ? 'chat-item active' : 'chat-item';
        chatItemDiv.innerHTML = `
            <span class="chat-title" data-id="${convo.id}">${escapeHtml(convo.title)}</span>
            <div class="menu-wrapper" data-menu-id="${convo.id}">
                <button class="options-trigger">
                    <svg class="icon icon-sm" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="1"></circle>
                        <circle cx="19" cy="12" r="1"></circle>
                        <circle cx="5" cy="12" r="1"></circle>
                    </svg>
                </button>
                <div class="dropdown-menu">
                    <div class="menu-item" data-action="rename" data-id="${convo.id}">
                        <svg class="icon icon-sm" viewBox="0 0 24 24">
                            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
                        </svg>
                        Rename
                    </div>
                    <div class="menu-item delete" data-action="delete" data-id="${convo.id}">
                        <svg class="icon icon-sm" viewBox="0 0 24 24">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        Delete
                    </div>
                </div>
            </div>
        `;

        // Click handler for chat title
        chatItemDiv.querySelector('.chat-title').addEventListener('click', () => {
            selectConversation(convo.id);
        });

        // Click handler for options trigger (3-dots button)
        const menuWrapper = chatItemDiv.querySelector('.menu-wrapper');
        const trigger = chatItemDiv.querySelector('.options-trigger');
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const wasOpen = menuWrapper.classList.contains('open');
            closeAllDropdowns();
            if (!wasOpen) {
                menuWrapper.classList.add('open');
                openDropdown = convo.id;
            }
        });

        chatListDiv.appendChild(chatItemDiv);
    });

    // Attach menu item handlers
    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', handleMenuAction);
    });
}

// ============================================================
// Welcome Screen
// ============================================================
function renderWelcomeScreen() {
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.className = 'chat-canvas welcome';

    setActiveNavItem(null);

    const firstName = userInfo.first_name || userInfo.user_name.split(' ')[0];
    chatCanvas.innerHTML = `
        <div class="chat-content-wrapper" style="align-items: center; justify-content: center;">
            <h1 class="welcome-text welcome-title">GenericAI</h1>
            <h2 class="welcome-text welcome-subtitle">How can I help, ${escapeHtml(firstName)}?</h2>
        </div>
        <div class="input-wrapper">
            <div class="input-box">
                <button class="icon-btn">
                    <svg class="icon" viewBox="0 0 24 24">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                </button>
                <input type="text" class="input-text" placeholder="Ask anything" id="message-input">
                <button class="icon-btn" id="send-btn">
                    <svg class="icon" style="fill:#999; stroke:none;" viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
                    </svg>
                </button>
            </div>
        </div>
    `;

    attachInputHandlers();
}

// ============================================================
// Conversation Rendering
// ============================================================
function renderConversation(convo) {
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.className = 'chat-canvas';

    setActiveNavItem(null);

    // Build messages HTML with evaluation buttons for assistant messages
    let messageSeq = 0;
    const messagesHtml = convo.messages.map(msg => {
        const seq = messageSeq++;
        if (msg.role === 'assistant') {
            return `
                <div class="message ${msg.role}">
                    <div class="message-role">Assistant</div>
                    <div class="message-content">${DOMPurify.sanitize(marked.parse(msg.content))}</div>
                    ${renderEvaluationButtons(seq)}
                </div>
            `;
        } else {
            return `
                <div class="message ${msg.role}">
                    <div class="message-role">You</div>
                    <div class="message-content">${escapeHtml(msg.content)}</div>
                </div>
            `;
        }
    }).join('');

    chatCanvas.innerHTML = `
        <div class="messages-container">
            ${messagesHtml}
        </div>
        <div class="input-wrapper">
            <div class="input-box">
                <button class="icon-btn">
                    <svg class="icon" viewBox="0 0 24 24">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                </button>
                <input type="text" class="input-text" placeholder="Message…" id="message-input">
                <button class="icon-btn" id="send-btn">
                    <svg class="icon" style="fill:#999; stroke:none;" viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
                    </svg>
                </button>
            </div>
        </div>
    `;

    attachInputHandlers();
    attachEvaluationHandlers();

    // Scroll to bottom
    setTimeout(() => {
        chatCanvas.scrollTop = chatCanvas.scrollHeight;
    }, 0);
}

// ============================================================
// Model Selector
// ============================================================
function renderModelSelector() {
    const modelMenu = document.getElementById('model-menu');
    const modelDisplay = document.getElementById('current-model-display');
    const modelVersion = document.getElementById('current-model-version');

    // Update display
    modelDisplay.textContent = 'GPT';
    if (selectedModel === 'gpt-4.1') {
        modelVersion.textContent = '4.1';
    } else if (selectedModel === 'gpt-4.1-mini') {
        modelVersion.textContent = '4.1-mini';
    } else {
        modelVersion.textContent = selectedModel.replace('gpt-', '');
    }

    // Count active overrides for badge display
    const overrideCount = Object.values(agent_level_llm_overwrite).filter(v => v !== null).length;
    const overrideBadge = overrideCount > 0 ? ` <span class="override-badge">${overrideCount}</span>` : '';
    modelVersion.innerHTML = modelVersion.textContent + overrideBadge;

    // Build two-level dropdown HTML using cached availableModels and availableAgents
    let menuHtml = '';

    availableModels.forEach(model => {
        const displayName = model.replace('gpt-', 'GPT-');
        const isSelected = model === selectedModel;

        menuHtml += `
            <div class="model-option-group ${isSelected ? 'expanded' : ''}" data-model="${model}">
                <div class="workflow-model ${isSelected ? 'selected' : ''}" data-model="${model}">
                    <span class="model-name">${displayName}</span>
                    <svg class="expand-icon" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
                </div>
                <div class="agent-submenu">
                    ${availableAgents.map(agent => {
                        const agentModel = agent_level_llm_overwrite[agent] || null;
                        // Show actual model name: override if set, otherwise workflow model
                        const effectiveModel = agentModel || model;
                        const agentDisplayModel = effectiveModel.replace('gpt-', 'GPT-');
                        return `
                            <div class="agent-row" data-agent="${agent}">
                                <span class="agent-name">${agent}</span>
                                <div class="agent-model-selector">
                                    <button class="agent-model-btn" data-agent="${agent}">${agentDisplayModel}</button>
                                    <div class="agent-model-dropdown">
                                        ${availableModels.map(m => {
                                            const mDisplay = m.replace('gpt-', 'GPT-');
                                            const isAgentModelSelected = effectiveModel === m;
                                            return `<div class="agent-model-choice ${isAgentModelSelected ? 'selected' : ''}" data-agent="${agent}" data-model="${m}">${mDisplay}</div>`;
                                        }).join('')}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    });

    modelMenu.innerHTML = menuHtml;

    // Attach click handlers for workflow model row
    // Click = select model + toggle expand
    document.querySelectorAll('.workflow-model').forEach(option => {
        option.addEventListener('click', async (e) => {
            e.stopPropagation();
            const model = option.dataset.model;
            const group = option.closest('.model-option-group');

            // If already selected, just toggle expand
            if (model === selectedModel) {
                group.classList.toggle('expanded');
            } else {
                // Select this model and expand it
                selectedModel = model;
                // Clear agent overrides when switching workflow model
                agent_level_llm_overwrite = {};
                // Collapse other groups, expand this one
                document.querySelectorAll('.model-option-group').forEach(g => g.classList.remove('expanded'));
                group.classList.add('expanded');
                // Update UI
                renderModelSelector();
                await syncModelToCurrentConversation();
            }
        });
    });

    // Attach click handlers for agent model buttons (toggle dropdown)
    document.querySelectorAll('.agent-model-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const dropdown = btn.nextElementSibling;
            // Close other agent dropdowns
            document.querySelectorAll('.agent-model-dropdown.open').forEach(d => {
                if (d !== dropdown) d.classList.remove('open');
            });
            dropdown.classList.toggle('open');
        });
    });

    // Attach click handlers for agent model choices
    document.querySelectorAll('.agent-model-choice').forEach(choice => {
        choice.addEventListener('click', (e) => {
            e.stopPropagation();
            const agent = choice.dataset.agent;
            const newModel = choice.dataset.model;

            // Update agent model mapping
            // If selecting the workflow model (same as parent group), clear the override
            const parentGroup = choice.closest('.model-option-group');
            const workflowModel = parentGroup ? parentGroup.dataset.model : selectedModel;

            if (newModel === workflowModel) {
                delete agent_level_llm_overwrite[agent];
            } else {
                agent_level_llm_overwrite[agent] = newModel;
            }

            // Update button text inline (don't re-render whole menu)
            const agentRow = choice.closest('.agent-row');
            const btn = agentRow.querySelector('.agent-model-btn');
            btn.textContent = newModel.replace('gpt-', 'GPT-');

            // Update selected state in dropdown
            const dropdown = choice.closest('.agent-model-dropdown');
            dropdown.querySelectorAll('.agent-model-choice').forEach(c => c.classList.remove('selected'));
            choice.classList.add('selected');

            // Close only the agent dropdown, keep submenu open
            dropdown.classList.remove('open');

            // Update badge count in header
            const overrideCount = Object.values(agent_level_llm_overwrite).filter(v => v !== null).length;
            const modelVersion = document.getElementById('current-model-version');
            const baseVersion = selectedModel === 'gpt-4.1' ? '4.1' : selectedModel.replace('gpt-', '');
            modelVersion.innerHTML = overrideCount > 0
                ? `${baseVersion} <span class="override-badge">${overrideCount}</span>`
                : baseVersion;
        });
    });
}

function initModelSelector() {
    // Use generic dropdown initialization
    initDropdown('model-trigger-btn', 'model-selector-container');
}

// ============================================================
// Transition from welcome screen to conversation view
// ============================================================
function renderConversationFromWelcome() {
    const chatCanvas = document.getElementById('chat-canvas');
    chatCanvas.className = 'chat-canvas';

    chatCanvas.innerHTML = `
        <div class="messages-container"></div>
        <div class="input-wrapper">
            <div class="input-box">
                <button class="icon-btn">
                    <svg class="icon" viewBox="0 0 24 24">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                </button>
                <input type="text" class="input-text" placeholder="Message…" id="message-input">
                <button class="icon-btn" id="send-btn">
                    <svg class="icon" style="fill:#999; stroke:none;" viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
                    </svg>
                </button>
            </div>
        </div>
    `;

    attachInputHandlers();
}
