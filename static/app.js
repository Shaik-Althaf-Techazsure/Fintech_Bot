document.addEventListener('DOMContentLoaded', () => {
    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const tts = window.speechSynthesis;

    let pendingTransaction = null;
    let isAwaitingConfirmation = false;

    function displayMessage(text, sender, speak = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-msg`;
        messageDiv.textContent = text;
        chatLog.appendChild(messageDiv);
        chatLog.scrollTop = chatLog.scrollHeight;

        if (speak) {
            const utterance = new SpeechSynthesisUtterance(text);
            tts.speak(utterance);
        }
    }

    function renderTransactionCard(transferDetails) {
        const { amount, recipient, new_balance } = transferDetails;
        
        const cardHTML = `
            <div class="transaction-card">
                <h4>✅ Transfer Executed Successfully</h4>
                <strong>Amount:</strong> $${parseFloat(amount).toFixed(2)}<br>
                <strong>Recipient:</strong> ${recipient}<br>
                <strong>New Balance:</strong> $${parseFloat(new_balance).toFixed(2)}
            </div>
        `;
        chatLog.insertAdjacentHTML('beforeend', cardHTML);
        chatLog.scrollTop = chatLog.scrollHeight;

        const ttsMessage = `Transfer of $${amount} complete. Your new balance is $${new_balance}.`;
        const utterance = new SpeechSynthesisUtterance(ttsMessage);
        tts.speak(utterance);
    }

    async function processCommand() {
        const text = userInput.value.trim();
        if (!text) return;

        displayMessage(text, 'user');
        userInput.value = '';

        if (isAwaitingConfirmation) {
            if (text.toUpperCase().includes('CONFIRM') || text.toUpperCase().includes('YES')) {
                await executeTransfer();
            } else {
                displayMessage("Transaction cancelled. You can start a new request.", 'system', true);
                isAwaitingConfirmation = false;
                pendingTransaction = null;
            }
            return;
        }

        try {
            const response = await fetch('/api/process_voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            const data = await response.json();

            const alertContainer = document.getElementById('proactive-alert');
            alertContainer.innerHTML = ''; 
            if (data.proactive_alert) {
                alertContainer.innerHTML = `<div class="low-balance-alert">${data.proactive_alert}</div>`;
            }

            if (data.intent === 'Transfer_Funds' && data.security_check) {
                pendingTransaction = {
                    amount: data.amount,
                    recipient: data.recipient
                };
                isAwaitingConfirmation = true;

                displayMessage(data.security_check.prompt, 'system', true);

            } else {
                displayMessage(data.response_text || "Error processing request.", 'system', true);
            }
            
        } catch (error) {
            console.error('API Error:', error);
            displayMessage("Sorry, I encountered a network error connecting to the Orchestration Service (Flask:5000).", 'system', true);
        }
    }

    async function executeTransfer() {
        try {
            const response = await fetch('/api/execute_transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pendingTransaction)
            });
            const data = await response.json();

            if (data.status === 'success') {
                renderTransactionCard({
                    amount: pendingTransaction.amount,
                    recipient: pendingTransaction.recipient,
                    new_balance: data.new_balance
                });
            } else {
                 displayMessage(data.response_text || "Transfer failed due to a banking error.", 'system', true);
            }

        } catch (error) {
            console.error('Execution Error:', error);
            displayMessage("Critical error: Transaction execution failed connecting to the Integration Fabric target.", 'system', true);
        } finally {
            isAwaitingConfirmation = false;
            pendingTransaction = null;
        }
    }

    sendBtn.addEventListener('click', processCommand);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            processCommand();
        }
    });

    const quickActionsContainer = document.getElementById('quick-actions');
    quickActionsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('action-btn')) {
            userInput.value = e.target.getAttribute('data-command');
            processCommand();
        }
    });

    if ('speechSynthesis' in window) {
        tts.onvoiceschanged = () => {
            console.log("TTS Voices ready.");
        };
    } else {
        displayMessage("Browser does not support Text-to-Speech (TTS). Voice output will be limited.", 'system', false);
    }
});