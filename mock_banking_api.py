import json
from flask import Flask, request, jsonify

MOCK_API_PORT = 5001
DATA_FILE = 'data/mock_accounts.json'

app = Flask(__name__)

def load_mock_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {DATA_FILE} not found. Please check Step 2.")
        return None

def save_mock_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False


@app.route('/v1/execute_transfer', methods=['POST'])
def execute_transfer():
    payload = request.get_json()
    amount = payload.get('amount')
    recipient_name = payload.get('recipient')

    if not all([amount, recipient_name]):
        return jsonify({"status": "error", "message": "Missing amount or recipient in payload."}), 400

    data = load_mock_data()
    if not data:
        return jsonify({"status": "error", "message": "Internal data error."}), 500

    user_name = data['user_details']['name']
    is_deposit = (recipient_name == user_name)
    current_balance = data['user_details']['balance']

    if is_deposit:
        data['user_details']['balance'] += amount
        transfer_type = "Top-Up/Deposit"
        result_message = f"Top-up of ${amount:.2f} successfully credited."
    else:
        if current_balance < amount:
            return jsonify({"status": "failed", "message": "Insufficient funds for outbound transfer."}), 200

        data['user_details']['balance'] -= amount
        transfer_type = "Voice Transfer"
        result_message = f"Transfer of ${amount:.2f} to {recipient_name} executed successfully."
        
    data['transaction_history'].append({
        "recipient": recipient_name,
        "amount": amount,
        "type": transfer_type
    })
    
    if not save_mock_data(data):
        return jsonify({"status": "error", "message": "Could not persist changes."}), 500

    return jsonify({
        "status": "success",
        "message": result_message,
        "new_balance": data['user_details']['balance']
    }), 200


if __name__ == '__main__':
    print(f"--- Mock Banking API (Integration Fabric Target) Running on Port {MOCK_API_PORT} ---")
    app.run(port=MOCK_API_PORT, debug=True)