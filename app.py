import json
import re
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime

MOCK_API_BASE_URL = 'http://127.0.0.1:5001'
DATA_FILE = 'data/mock_accounts.json'

app = Flask(__name__)

def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON data. Check mock_accounts.json file format.")
        return None

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def log_audit_event(user_id, intent, status, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] User: {user_id} | Intent: {intent} | Status: {status} | Details: {details}"
    print(f"AUDIT LOG: {log_entry}")

def nlu_engine(text):
    data = load_data()
    if not data:
        return None, None, None
    
    text_lower = text.lower()
    user_id = data['user_details']['user_id']
    intent = "Unknown"

    if re.search(r'(top up|deposit|add money)\b', text_lower):
        intent = "Transfer_Funds" 
        
        amount_match = re.search(r'(\d+)', text_lower)
        amount = float(amount_match.group(1)) if amount_match else None
        
        recipient = data['user_details']['name']
        
        if not amount:
            log_audit_event(user_id, intent, "NLU_MISSING_ENTITY", "Missing amount for top-up.")
            return intent, None, recipient 
            
        log_audit_event(user_id, intent, "NLU_TOPUP_SUCCESS", f"Amount: {amount}, Recipient: {recipient}")
        return intent, amount, recipient 

    if re.search(r'(balance|money i have|how much is in)\b', text_lower):
        intent = "Check_Balance"
    elif re.search(r'(account statement|full statement|credit and debit)\b', text_lower):
        intent = "Account_Statement"
    elif re.search(r'(my account details|account holder name|account number)\b', text_lower):
        intent = "Account_Details"
    elif re.search(r'(history|transactions|spent|last payment)\b', text_lower):
        intent = "View_History"
    elif re.search(r'(loan|rate|limit|credit)\b', text_lower):
        intent = "Loan_Inquiry"
    elif re.search(r'(remind me|set alert|set reminder|set payment)\b', text_lower):
        intent = "Set_Reminder"
    
    elif re.search(r'(send|transfer|move|pay)\b', text_lower):
        intent = "Transfer_Funds"
        
        amount_match = re.search(r'(\d+)', text_lower)
        amount = float(amount_match.group(1)) if amount_match else None

        recipient = None
        known_recipients = data['beneficiaries'].keys()
        for name in known_recipients:
            if name.lower() in text_lower:
                recipient = name
                break
        
        return intent, amount, recipient

    return intent, None, None

def check_context_and_security(user_id, amount, recipient, current_balance):
    data = load_data()
    if not data:
        log_audit_event(user_id, "Transfer_Funds", "FAILED", "Internal data error.")
        return {"is_safe": False, "prompt": "System error. Cannot verify context."}

    user_name = data['user_details']['name']
    
    is_deposit = (recipient == user_name)

    if not is_deposit and amount > current_balance:
        log_audit_event(user_id, "Transfer_Funds", "BLOCKED", f"Insufficient funds: {amount}")
        return {"is_safe": False, "prompt": "I cannot proceed; you have insufficient funds for this transfer."}

    threshold = data['anomaly_thresholds'].get(recipient, 10000)
    
    risk_score = 0.0

    if not is_deposit:
        if amount > threshold:
            risk_score += (amount / threshold) * 25

        if 22 <= datetime.now().hour or datetime.now().hour < 6:
            risk_score += 15.0 

        risk_score = min(risk_score, 100.0)
    
    RISK_THRESHOLD = 50.0

    if risk_score > RISK_THRESHOLD:
        log_audit_event(user_id, "Transfer_Funds", "SECURITY_CHALLENGE", f"Risk Score: {risk_score:.2f}%")
        return {
            "is_safe": False,
            "prompt": (
                f"⚠️ HIGH RISK ({risk_score:.0f}%): This transfer of ${amount:.2f} to {recipient} is highly unusual for you. "
                f"Please verbally confirm you wish to proceed by saying 'CONFIRM HIGH RISK TRANSFER'."
            ),
            "risk_score": f"{risk_score:.0f}%"
        }
    
    log_audit_event(user_id, "Transfer_Funds", "LOW_RISK_PASS", f"Risk Score: {risk_score:.2f}%")
    return {
        "is_safe": True,
        "prompt": f"Transferring ${amount:.2f} to {recipient}. Please say 'CONFIRM TRANSACTION' to proceed."
    }

def call_integration_fabric(amount, recipient):
    transfer_payload = {
        "amount": amount,
        "recipient": recipient
    }
    
    try:
        response = requests.post(
            f'{MOCK_API_BASE_URL}/v1/execute_transfer', 
            json=transfer_payload
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling Mock Banking API: {e}")
        return {"status": "error", "message": "Transaction failed due to connectivity error."}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/process_voice', methods=['POST'])
def process_voice():
    user_text = request.json.get('text', '')
    
    if not user_text:
        return jsonify({"response_text": "I didn't hear anything. Please try again."})

    intent, amount, recipient = nlu_engine(user_text)
    data = load_data()
    
    if not data:
        return jsonify({"response_text": "Error: Could not load user data."})

    user_id = data['user_details']['user_id']
    current_balance = data['user_details']['balance']
    proactive_alert = None
    
    if current_balance < 500.00:
        proactive_alert = f"❗ LOW BALANCE: Your balance is only ${current_balance:.2f}."
    
    log_audit_event(user_id, intent, "NLU_SUCCESS", f"Input: {user_text}")

    if intent == "Check_Balance":
        response_text = f"Your current account balance is ${current_balance:.2f}."
        return jsonify({
            "response_text": response_text,
            "intent": "Check_Balance",
            "proactive_alert": proactive_alert
        })
    
    elif intent == "Account_Details":
        user_name = data['user_details']['name']
        account_number = data['user_details']['primary_account']
        user_id = data['user_details']['user_id']
        
        response_text = (
            f"Here are your primary account details: Account Holder: {user_name}, "
            f"Account Number (Last 4): {account_number[-4:]}. Your system User ID is: {user_id}."
        )
        return jsonify({
            "response_text": response_text,
            "intent": "Account_Details",
            "proactive_alert": proactive_alert
        })

    elif intent == "Account_Statement":
        all_history = data['transaction_history']
        user_name = data['user_details']['name']
        statement_summary = []
        for t in all_history[-5:]:
            txn_type = "Debit"
            if t.get('type') == 'Top-Up/Deposit':
                 txn_type = "Credit"
            
            summary_line = f"{txn_type} of ${t['amount']:.2f} to {t['recipient']}"
            statement_summary.append(summary_line)

        
        response_text = "Here is a summary of your recent statement transactions: " + "; ".join(statement_summary) + "."
        return jsonify({
            "response_text": response_text,
            "intent": "Account_Statement",
            "proactive_alert": proactive_alert
        })

    elif intent == "View_History":
        history = data['transaction_history'][-3:]
        history_list = [f"{t['recipient']} for ${t['amount']:.2f}" for t in history]
        
        response_text = f"Your last three transactions were: " + "; ".join(history_list) + "."
        return jsonify({
            "response_text": response_text,
            "intent": "View_History",
            "proactive_alert": proactive_alert
        })
    
    elif intent == "Loan_Inquiry":
        products = data['credit_details']['loan_products']
        
        loan_summary = [f"{p['name']} at {p['rate']}" for p in products if p['name'] != 'Credit Limit']
        credit_limit = next(p['max_limit'] for p in products if p['name'] == 'Credit Limit')
        
        response_text = (
            f"We offer: {', '.join(loan_summary)}. Your current credit card limit is ${credit_limit:.0f}. "
            f"Would you like details on a specific product?"
        )
        return jsonify({
            "response_text": response_text,
            "intent": "Loan_Inquiry",
            "proactive_alert": proactive_alert
        })

    elif intent == "Set_Reminder":
        if re.search(r'rent', user_text, re.IGNORECASE):
            data['reminders'].append({"id": len(data['reminders']) + 1, "type": "Payment", "description": "Rent Payment Reminder Set", "date": "2026-01-01"})
            save_data(data)
            response_text = "I've set a reminder to pay your rent on the first of next month."
        else:
            response_text = "I can set a reminder for a payment or alert. What payment would you like to be reminded about?"
            
        return jsonify({
            "response_text": response_text,
            "intent": "Set_Reminder",
            "proactive_alert": proactive_alert
        })

    elif intent == "Transfer_Funds":
        if not amount or not recipient:
            return jsonify({
                "response_text": "To transfer funds, please tell me the amount and the recipient name.",
                "intent": "Transfer_Funds",
                "proactive_alert": proactive_alert
            })

        security_check = check_context_and_security(user_id, amount, recipient, current_balance)
        
        return jsonify({
            "intent": intent,
            "amount": amount,
            "recipient": recipient,
            "security_check": security_check,
            "proactive_alert": proactive_alert
        })

    else:
        return jsonify({
            "response_text": "I can only help with core banking tasks. What would you like to do?",
            "intent": "Unknown",
            "proactive_alert": proactive_alert
        })


@app.route('/api/execute_transaction', methods=['POST'])
def execute_transaction():
    payload = request.json
    amount = payload.get('amount')
    recipient = payload.get('recipient')
    
    data = load_data()
    user_id = data['user_details']['user_id']
    
    transfer_result = call_integration_fabric(amount, recipient)
    
    if transfer_result.get('status') == 'success':
        log_audit_event(user_id, "Transfer_Funds", "EXECUTION_SUCCESS", f"Transfer of {amount} to {recipient}")
        
        data_after_transfer = load_data()
        new_balance = data_after_transfer['user_details']['balance'] if data_after_transfer else "..."
        
        response_text = f"Transfer complete. Transfer of ${amount:.2f} to {recipient} executed successfully. Your new balance is ${new_balance:.2f}."
        
        return jsonify({
            "status": "success",
            "response_text": response_text,
            "new_balance": new_balance
        })
    else:
        log_audit_event(user_id, "Transfer_Funds", "EXECUTION_FAILURE", transfer_result.get('message', 'Unknown error.'))
        response_text = f"Transfer failed: {transfer_result.get('message', 'Unknown error.')}"
        
        return jsonify({
            "status": "failure",
            "response_text": response_text
        })


if __name__ == '__main__':
    print("--- Conversational Guardian (NLP/Orchestration) Running on Port 5000 ---")
    app.run(debug=True)