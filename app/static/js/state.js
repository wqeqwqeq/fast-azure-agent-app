// ============================================================
// State Management
// ============================================================

let conversations = [];
let currentConversationId = null;
let selectedModel = 'gpt-4.1-mini';
let userInfo = null;
let openDropdown = null;  // Track which dropdown is open

// Thinking events storage for flyout panel
let currentThinkingEvents = [];

// Token usage tracking for current message
let currentMessageTokens = 0;

// Feature flags from backend
let showFuncResult = true;

// ReAct mode toggle state (false = Triage, true = Dynamic/ReAct)
let reactModeEnabled = false;

// Memory Agent toggle state (true = enabled by default)
let memoryAgentEnabled = true;

// Model selection cache (fetched once at startup, agents refresh on react mode change)
let availableModels = [];     // ["gpt-4.1", "gpt-4.1-mini"]
let availableAgents = [];     // ["triage", "servicenow", ...] - varies by react mode

// Per-agent model overrides (agent_key -> model_name or null)
let agent_level_llm_overwrite = {};   // {"triage": "gpt-4.1-mini", ...}

// Evaluation state tracking - keyed by "conversationId:seq"
let messageEvaluations = {};  // {"convId:seq": {is_satisfy: bool, comment: string}}
