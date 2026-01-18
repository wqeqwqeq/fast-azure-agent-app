// ============================================================
// Evaluation Functions (Thumbs Up/Down)
// ============================================================

// Get evaluation key for the current conversation
function getEvalKey(seq) {
    return `${currentConversationId}:${seq}`;
}

// Render evaluation buttons HTML with optional token display
function renderEvaluationButtons(seq, totalTokens = 0) {
    const key = getEvalKey(seq);
    const evaluation = messageEvaluations[key];
    const thumbsUpActive = evaluation?.is_satisfy === true ? 'active' : '';
    const thumbsDownActive = evaluation?.is_satisfy === false ? 'active' : '';
    const containerClass = evaluation?.is_satisfy === true ? 'thumbs-up-active' :
                          evaluation?.is_satisfy === false ? 'thumbs-down-active' : '';

    // Format token display (e.g., "2,096 tokens")
    const tokenDisplay = totalTokens > 0
        ? `<span class="token-count">${totalTokens.toLocaleString()} tokens</span>`
        : '';

    return `
        <div class="evaluation-buttons ${containerClass}" data-seq="${seq}">
            <button class="eval-btn thumbs-up ${thumbsUpActive}" data-seq="${seq}" title="Good response">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
                </svg>
            </button>
            <button class="eval-btn thumbs-down ${thumbsDownActive}" data-seq="${seq}" title="Bad response">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path>
                </svg>
            </button>
            ${tokenDisplay}
        </div>
    `;
}

// Attach event handlers to evaluation buttons
function attachEvaluationHandlers() {
    document.querySelectorAll('.eval-btn.thumbs-up').forEach(btn => {
        btn.onclick = () => handleThumbsUp(parseInt(btn.dataset.seq));
    });

    document.querySelectorAll('.eval-btn.thumbs-down').forEach(btn => {
        btn.onclick = () => handleThumbsDown(parseInt(btn.dataset.seq));
    });
}

// Handle thumbs up click
async function handleThumbsUp(seq) {
    const key = getEvalKey(seq);
    const currentEval = messageEvaluations[key];

    // If already thumbs up, clear it
    if (currentEval?.is_satisfy === true) {
        await clearEvaluation(currentConversationId, seq);
        delete messageEvaluations[key];
    } else {
        // Set thumbs up
        await setEvaluation(currentConversationId, seq, true);
        messageEvaluations[key] = { is_satisfy: true, comment: null };
    }

    updateEvaluationButtonState(seq);
}

// Handle thumbs down click - show feedback popup
function handleThumbsDown(seq) {
    const key = getEvalKey(seq);
    const currentEval = messageEvaluations[key];

    // If already thumbs down, clear it
    if (currentEval?.is_satisfy === false) {
        clearEvaluation(currentConversationId, seq);
        delete messageEvaluations[key];
        updateEvaluationButtonState(seq);
    } else {
        // Show feedback popup
        showFeedbackPopup(seq);
    }
}

// Update button visual state
function updateEvaluationButtonState(seq) {
    const key = getEvalKey(seq);
    const evaluation = messageEvaluations[key];
    const container = document.querySelector(`.evaluation-buttons[data-seq="${seq}"]`);
    if (!container) return;

    const thumbsUp = container.querySelector('.thumbs-up');
    const thumbsDown = container.querySelector('.thumbs-down');

    // Clear all states
    thumbsUp.classList.remove('active');
    thumbsDown.classList.remove('active');
    container.classList.remove('thumbs-up-active', 'thumbs-down-active');

    if (evaluation?.is_satisfy === true) {
        thumbsUp.classList.add('active');
        container.classList.add('thumbs-up-active');
    } else if (evaluation?.is_satisfy === false) {
        thumbsDown.classList.add('active');
        container.classList.add('thumbs-down-active');
    }
}

// ============================================================
// Feedback Popup
// ============================================================

function showFeedbackPopup(seq) {
    // Remove any existing popup
    closeFeedbackPopup();

    const popup = document.createElement('div');
    popup.className = 'feedback-popup-overlay';
    popup.id = 'feedback-popup';
    popup.dataset.seq = seq;
    popup.innerHTML = `
        <div class="feedback-popup">
            <div class="feedback-popup-header">
                <span>What could be improved?</span>
                <button class="feedback-popup-close" onclick="closeFeedbackPopupAndSubmit()">&times;</button>
            </div>
            <textarea class="feedback-textarea" id="feedback-textarea" placeholder="Optional feedback..."></textarea>
            <button class="feedback-submit-btn" onclick="submitFeedback()">Submit</button>
        </div>
    `;

    document.body.appendChild(popup);

    // Focus textarea
    document.getElementById('feedback-textarea').focus();

    // Close on overlay click
    popup.addEventListener('click', (e) => {
        if (e.target === popup) {
            closeFeedbackPopupAndSubmit();
        }
    });

    // Handle Escape key
    document.addEventListener('keydown', handleFeedbackPopupKeydown);
}

function handleFeedbackPopupKeydown(e) {
    if (e.key === 'Escape') {
        closeFeedbackPopupAndSubmit();
    }
}

function closeFeedbackPopup() {
    const popup = document.getElementById('feedback-popup');
    if (popup) {
        popup.remove();
    }
    document.removeEventListener('keydown', handleFeedbackPopupKeydown);
}

// Close popup and submit negative feedback (with no comment)
async function closeFeedbackPopupAndSubmit() {
    const popup = document.getElementById('feedback-popup');
    if (!popup) return;

    const seq = parseInt(popup.dataset.seq);
    const key = getEvalKey(seq);

    // Submit negative feedback with no comment
    await setEvaluation(currentConversationId, seq, false, null);
    messageEvaluations[key] = { is_satisfy: false, comment: null };

    closeFeedbackPopup();
    updateEvaluationButtonState(seq);
}

// Submit feedback with optional comment
async function submitFeedback() {
    const popup = document.getElementById('feedback-popup');
    if (!popup) return;

    const seq = parseInt(popup.dataset.seq);
    const key = getEvalKey(seq);
    const textarea = document.getElementById('feedback-textarea');
    const comment = textarea.value.trim() || null;

    // Submit negative feedback with comment
    await setEvaluation(currentConversationId, seq, false, comment);
    messageEvaluations[key] = { is_satisfy: false, comment };

    closeFeedbackPopup();
    updateEvaluationButtonState(seq);
}
