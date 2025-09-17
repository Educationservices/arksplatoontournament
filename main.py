from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')  # Set a secret key for sessions

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

def require_teacher_auth(f):
    """Decorator to require teacher authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher_authenticated' not in session or not session['teacher_authenticated']:
            return redirect(url_for('teacher_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    """Serve the tournament form"""
    return """
    <h1>Splatoon Tournament Backend</h1>
    <p>Backend is running! Your form should submit to /submit-registration</p>
    <p>Make sure to update your frontend to point to this backend.</p>
    <p><a href="/teacher">Teacher Dashboard</a></p>
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
        
        # Validate ages (must be between 11-14)
        try:
            player1_age = int(player1.get('age', 0))
            player2_age = int(player2.get('age', 0))
            
            if not (11 <= player1_age <= 14):
                return jsonify({"error": "Player 1 age must be between 11-14"}), 400
            if not (11 <= player2_age <= 14):
                return jsonify({"error": "Player 2 age must be between 11-14"}), 400
                
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid age provided"}), 400
        
        # Generate a team ID
        team_id = f"TEAM_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Prepare row data - Set both payment agreements to "No" initially
        row_data = [
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            player1.get('fullName', ''),
            str(player1_age),
            f"{player1.get('formNumber', '')} {player1.get('formName', '')}".strip(),
            'No',  # Player 1 payment agreement set to No
            player2.get('fullName', ''),
            str(player2_age),
            f"{player2.get('formNumber', '')} {player2.get('formName', '')}".strip(),
            'No',  # Player 2 payment agreement set to No
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

@app.route('/teacher')
@require_teacher_auth
def teacher_dashboard():
    """Teacher dashboard to view and manage registrations"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return "Error: Cannot connect to Google Sheets", 500
        
        records = sheet.get_all_records()
        
        # HTML template for the teacher dashboard
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Teacher Dashboard - Tournament Registrations</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #f2f2f2; }
                tr:nth-child(even) { background-color: #f9f9f9; }
                .payment-yes { background-color: #d4edda; color: #155724; }
                .payment-no { background-color: #f8d7da; color: #721c24; }
                .update-btn { padding: 5px 10px; margin: 2px; cursor: pointer; }
                .btn-yes { background-color: #28a745; color: white; border: none; }
                .btn-no { background-color: #dc3545; color: white; border: none; }
                .logout-btn { float: right; padding: 10px 15px; background-color: #6c757d; color: white; text-decoration: none; }
                h1 { color: #333; }
                .stats { margin: 20px 0; padding: 15px; background-color: #e9ecef; border-radius: 5px; }
            </style>
        </head>
        <body>
            <a href="/teacher/logout" class="logout-btn">Logout</a>
            <h1>Tournament Registrations Dashboard</h1>
            
            <div class="stats">
                <strong>Total Registrations:</strong> {{ total_count }}<br>
                <strong>Teams with Full Payment:</strong> {{ full_payment_count }}<br>
                <strong>Teams with Partial Payment:</strong> {{ partial_payment_count }}<br>
                <strong>Teams with No Payment:</strong> {{ no_payment_count }}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Team ID</th>
                        <th>Timestamp</th>
                        <th>Player 1</th>
                        <th>Age</th>
                        <th>Form</th>
                        <th>P1 Payment</th>
                        <th>Player 2</th>
                        <th>Age</th>
                        <th>Form</th>
                        <th>P2 Payment</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in records %}
                    <tr>
                        <td><strong>{{ record['Team ID'] }}</strong></td>
                        <td>{{ record['Timestamp'] }}</td>
                        <td>{{ record['Player 1 Name'] }}</td>
                        <td>{{ record['Player 1 Age'] }}</td>
                        <td>{{ record['Player 1 Form'] }}</td>
                        <td class="{% if record['Player 1 Payment Agreement'] == 'Yes' %}payment-yes{% else %}payment-no{% endif %}">
                            {{ record['Player 1 Payment Agreement'] }}
                        </td>
                        <td>{{ record['Player 2 Name'] }}</td>
                        <td>{{ record['Player 2 Age'] }}</td>
                        <td>{{ record['Player 2 Form'] }}</td>
                        <td class="{% if record['Player 2 Payment Agreement'] == 'Yes' %}payment-yes{% else %}payment-no{% endif %}">
                            {{ record['Player 2 Payment Agreement'] }}
                        </td>
                        <td>
                            <button class="update-btn btn-yes" onclick="updatePayment('{{ record['Team ID'] }}', 'player1', 'Yes')">P1: Yes</button>
                            <button class="update-btn btn-no" onclick="updatePayment('{{ record['Team ID'] }}', 'player1', 'No')">P1: No</button>
                            <br>
                            <button class="update-btn btn-yes" onclick="updatePayment('{{ record['Team ID'] }}', 'player2', 'Yes')">P2: Yes</button>
                            <button class="update-btn btn-no" onclick="updatePayment('{{ record['Team ID'] }}', 'player2', 'No')">P2: No</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <script>
                function updatePayment(teamId, player, status) {
                    fetch('/teacher/update-payment', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            team_id: teamId,
                            player: player,
                            payment_status: status
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert('Error updating payment: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error updating payment');
                    });
                }
            </script>
        </body>
        </html>
        """
        
        # Calculate statistics
        total_count = len(records)
        full_payment_count = sum(1 for r in records if r.get('Player 1 Payment Agreement') == 'Yes' and r.get('Player 2 Payment Agreement') == 'Yes')
        partial_payment_count = sum(1 for r in records if (r.get('Player 1 Payment Agreement') == 'Yes') != (r.get('Player 2 Payment Agreement') == 'Yes'))
        no_payment_count = sum(1 for r in records if r.get('Player 1 Payment Agreement') == 'No' and r.get('Player 2 Payment Agreement') == 'No')
        
        return render_template_string(html_template, 
                                    records=records,
                                    total_count=total_count,
                                    full_payment_count=full_payment_count,
                                    partial_payment_count=partial_payment_count,
                                    no_payment_count=no_payment_count)
        
    except Exception as e:
        return f"Error loading dashboard: {str(e)}", 500

@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    """Teacher login page"""
    if request.method == 'POST':
        password = request.form.get('password') or request.json.get('password') if request.is_json else None
        teacher_password = os.getenv('TEACHER_PASSWORD', 'admin123')  # Default password if not set
        
        if password == teacher_password:
            session['teacher_authenticated'] = True
            return redirect(url_for('teacher_dashboard'))
        else:
            error = "Invalid password"
            if request.is_json:
                return jsonify({"error": error}), 401
            return render_template_string(login_template, error=error)
    
    login_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Teacher Login</title>
        <style>
            body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f5f5f5; }
            .login-container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            input[type="password"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
            button { width: 100%; padding: 10px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            .error { color: red; margin-top: 10px; }
            h2 { text-align: center; color: #333; }
        </style>
    </head>
    <body>
        <div class="login-container">
            <h2>Teacher Dashboard Login</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Enter teacher password" required>
                <button type="submit">Login</button>
                {% if error %}
                <div class="error">{{ error }}</div>
                {% endif %}
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(login_template)

@app.route('/teacher/logout')
def teacher_logout():
    """Logout teacher"""
    session.pop('teacher_authenticated', None)
    return redirect(url_for('home'))

@app.route('/teacher/update-payment', methods=['POST'])
@require_teacher_auth
def update_payment():
    """Update payment status for a player"""
    try:
        data = request.get_json()
        team_id = data.get('team_id')
        player = data.get('player')  # 'player1' or 'player2'
        payment_status = data.get('payment_status')  # 'Yes' or 'No'
        
        if not all([team_id, player, payment_status]):
            return jsonify({"error": "Missing required fields"}), 400
        
        if player not in ['player1', 'player2']:
            return jsonify({"error": "Invalid player specified"}), 400
        
        if payment_status not in ['Yes', 'No']:
            return jsonify({"error": "Invalid payment status"}), 400
        
        sheet = get_google_sheet()
        if not sheet:
            return jsonify({"error": "Cannot connect to Google Sheets"}), 500
        
        # Find the row with the matching team ID
        records = sheet.get_all_records()
        row_index = None
        
        for i, record in enumerate(records):
            if record.get('Team ID') == team_id:
                row_index = i + 2  # +2 because sheets are 1-indexed and we have a header row
                break
        
        if row_index is None:
            return jsonify({"error": "Team ID not found"}), 404
        
        # Update the appropriate column
        if player == 'player1':
            col_index = 5  # Player 1 Payment Agreement column (E)
        else:  # player2
            col_index = 9  # Player 2 Payment Agreement column (I)
        
        # Update the cell
        sheet.update_cell(row_index, col_index, payment_status)
        
        return jsonify({
            "success": True,
            "message": f"Payment status updated for {player} of {team_id}",
            "team_id": team_id,
            "player": player,
            "new_status": payment_status
        })
        
    except Exception as e:
        print(f"Error updating payment: {e}")
        return jsonify({"error": str(e)}), 500

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
