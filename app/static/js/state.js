// ============================================================
// State Management
// ============================================================

let conversations = [];
let currentConversationId = null;
let selectedModel = 'gpt-4o-mini';
let userInfo = null;
let openDropdown = null;  // Track which dropdown is open

// Thinking events storage for flyout panel
let currentThinkingEvents = [];

// Feature flags from backend
let showFuncResult = true;

// Evaluation state tracking - keyed by "conversationId:seq"
let messageEvaluations = {};  // {"convId:seq": {is_satisfy: bool, comment: string}}
