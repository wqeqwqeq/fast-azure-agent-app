// ============================================================
// Initialization
// ============================================================

async function init() {
    // Load settings/feature flags
    await fetchSettings();

    // Load user info
    userInfo = await fetchUser();
    renderUserInfo();

    // Initialize model selector (attach event listener once)
    initModelSelector();

    // Initialize ReAct mode toggle
    initReactModeToggle();

    // Cache models and agents at startup (fetched once, agents refresh on react mode change)
    availableModels = await fetchModels();
    availableAgents = await fetchAgents(reactModeEnabled);

    // Render model selector display
    renderModelSelector();

    // Load conversations
    await fetchConversations();
    renderConversationsList();

    // Select first conversation or show welcome
    if (conversations.length > 0 && conversations[0].messages && conversations[0].messages.length > 0) {
        selectConversation(conversations[0].id);
    } else {
        renderWelcomeScreen();
    }

    // Attach new chat button handler
    document.getElementById('new-chat-btn').addEventListener('click', handleNewChat);

    // Search button placeholder
    document.getElementById('search-chats-btn').addEventListener('click', () => {
        alert('Search chats feature coming soon!');
    });
}

// Start app
init();
