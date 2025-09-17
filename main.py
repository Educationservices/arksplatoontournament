from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_google_sheet():
    """Initialize and return the Google Sheet"""
    try:
        # Load credentials from environment variable or file
        if os.getenv('GOOGLE_CREDENTIALS'):
            # For deployment (Render, Heroku, etc.)
            creds_dict = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            # For local development
            creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
        
        client = gspread.authorize(creds)
        
        # Open the spreadsheet (replace with your sheet ID)
        sheet_id = os.getenv('GOOGLE_SHEET_ID', 'YOUR_SHEET_ID_HERE')
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Create headers if sheet is empty
        if not sheet.get_all_records():
            headers = [
                'Timestamp',
                'Player 1 Name',
                'Player 1 Age',
                'Player 1 Form',
                'Player 1 Payment Agreement',
                'Player 2 Name',
                'Player 2 Age',
                'Player 2 Form',
                'Player 2 Payment Agreement',
                'Team ID'
            ]
            sheet.append_row(headers)
        
        return sheet
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None

@app.route('/')
def home():
    """Serve the tournament form"""
    # You can serve your HTML file here or return it as a string
    return """
    <h1>Splatoon Tournament Backend</h1>
    <p>Backend is running! Your form should submit to /submit-registration</p>
    <p>Make sure to update your frontend to point to this backend.</p>
    """

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/submit-registration', methods=['POST'])
def submit_registration():
    """Handle tournament registration submission"""
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        # Validate required fields
        required_fields = ['player1', 'player2']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing {field} data"}), 400
        
        # Extract player data
        player1 = data['player1']
        player2 = data['player2']
        
        # Generate a team ID
        team_id = f"TEAM_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Prepare row data
        row_data = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            player1.get('fullName', ''),
            player1.get('age', ''),
            f"{player1.get('formNumber', '')} {player1.get('formName', '')}".strip(),
            'Yes' if player1.get('paymentAgreement') else 'No',
            player2.get('fullName', ''),
            player2.get('age', ''),
            f"{player2.get('formNumber', '')} {player2.get('formName', '')}".strip(),
            'Yes' if player2.get('paymentAgreement') else 'No',
            team_id
        ]
        
        # Try to save to Google Sheets
        sheet = get_google_sheet()
        if sheet:
            sheet.append_row(row_data)
            sheet_success = True
        else:
            sheet_success = False
            # Fallback: save to local file or database
            save_to_local_file(row_data)
        
        # Return success response
        response_data = {
            "success": True,
            "message": "Registration submitted successfully!",
            "team_id": team_id,
            "saved_to_sheets": sheet_success,
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error processing registration: {e}")
        return jsonify({
            "error": "Failed to process registration", 
            "details": str(e)
        }), 500

def save_to_local_file(row_data):
    """Fallback method to save data locally"""
    try:
        filename = 'tournament_registrations.txt'
        with open(filename, 'a', encoding='utf-8') as f:
            f.write('|'.join(str(item) for item in row_data) + '\n')
        print(f"Data saved to {filename}")
    except Exception as e:
        print(f"Error saving to local file: {e}")

@app.route('/get-registrations')
def get_registrations():
    """Get all registrations (for admin purposes)"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return jsonify({"error": "Cannot connect to Google Sheets"}), 500
        
        records = sheet.get_all_records()
        return jsonify({
            "success": True,
            "registrations": records,
            "count": len(records)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # For development
    app.run(debug=True, host='0.0.0.0', port=5000)
