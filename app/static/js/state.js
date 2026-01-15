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

// Feature flags from backend
let showFuncResult = true;

// ReAct mode toggle state (false = Triage, true = Dynamic/ReAct)
let reactModeEnabled = false;

// Evaluation state tracking - keyed by "conversationId:seq"
let messageEvaluations = {};  // {"convId:seq": {is_satisfy: bool, comment: string}}
