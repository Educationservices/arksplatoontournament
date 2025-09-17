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
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>Error: index.html not found</h1>
        <p>Make sure index.html is in the same folder as this Python file.</p>
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
                body { 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    min-height: 100vh;
                    color: white;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 15px;
                    padding: 30px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                    color: #1e3c72;
                }
                table { 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin-top: 20px; 
                    background: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                }
                th, td { 
                    border: 1px solid #e3f2fd; 
                    padding: 12px; 
                    text-align: left; 
                }
                th { 
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    color: white;
                    font-weight: 600;
                    text-transform: uppercase;
                    font-size: 12px;
                    letter-spacing: 1px;
                }
                tr:nth-child(even) { background-color: #f8fbff; }
                tr:hover { background-color: #e3f2fd; transition: background-color 0.3s; }
                .payment-yes { 
                    background-color: #c8e6c9; 
                    color: #2e7d32; 
                    font-weight: bold;
                    text-align: center;
                    border-radius: 5px;
                    padding: 5px;
                }
                .payment-no { 
                    background-color: #ffcdd2; 
                    color: #c62828; 
                    font-weight: bold;
                    text-align: center;
                    border-radius: 5px;
                    padding: 5px;
                }
                .update-btn { 
                    padding: 6px 12px; 
                    margin: 2px; 
                    cursor: pointer; 
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: bold;
                    transition: all 0.3s ease;
                }
                .btn-yes { 
                    background: linear-gradient(135deg, #4caf50 0%, #66bb6a 100%); 
                    color: white; 
                }
                .btn-yes:hover { 
                    background: linear-gradient(135deg, #388e3c 0%, #4caf50 100%);
                    transform: translateY(-1px);
                }
                .btn-no { 
                    background: linear-gradient(135deg, #f44336 0%, #e57373 100%); 
                    color: white; 
                }
                .btn-no:hover { 
                    background: linear-gradient(135deg, #d32f2f 0%, #f44336 100%);
                    transform: translateY(-1px);
                }
                .logout-btn { 
                    float: right; 
                    padding: 12px 20px; 
                    background: linear-gradient(135deg, #37474f 0%, #546e7a 100%); 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 25px;
                    font-weight: bold;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                }
                .logout-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
                }
                h1 { 
                    color: #1e3c72; 
                    text-align: center;
                    font-size: 2.5rem;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
                }
                .stats { 
                    margin: 20px 0; 
                    padding: 20px; 
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                    border-radius: 10px; 
                    color: white;
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                }
                .stat-item {
                    text-align: center;
                    padding: 10px;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }
                .stat-number {
                    font-size: 2rem;
                    font-weight: bold;
                    display: block;
                    color: #ffd54f;
                }
                .stat-label {
                    font-size: 0.9rem;
                    opacity: 0.9;
                }
                .header-section {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    flex-wrap: wrap;
                }
                .team-id {
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    color: white;
                    padding: 5px 10px;
                    border-radius: 15px;
                    font-size: 12px;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header-section">
                    <h1>🎮 Tournament Dashboard</h1>
                    <a href="/teacher/logout" class="logout-btn">Logout</a>
                </div>
                
                <div class="stats">
                    <div class="stat-item">
                        <span class="stat-number">{{ total_count }}</span>
                        <span class="stat-label">Total Teams</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{ full_payment_count }}</span>
                        <span class="stat-label">Full Payment</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{ partial_payment_count }}</span>
                        <span class="stat-label">Partial Payment</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{ no_payment_count }}</span>
                        <span class="stat-label">No Payment</span>
                    </div>
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
                            <td><span class="team-id">{{ record['Team ID'] }}</span></td>
                            <td>{{ record['Timestamp'] }}</td>
                            <td><strong>{{ record['Player 1 Name'] }}</strong></td>
                            <td>{{ record['Player 1 Age'] }}</td>
                            <td>{{ record['Player 1 Form'] }}</td>
                            <td>
                                <span class="{% if record['Player 1 Payment Agreement'] == 'Yes' %}payment-yes{% else %}payment-no{% endif %}">
                                    {{ record['Player 1 Payment Agreement'] }}
                                </span>
                            </td>
                            <td><strong>{{ record['Player 2 Name'] }}</strong></td>
                            <td>{{ record['Player 2 Age'] }}</td>
                            <td>{{ record['Player 2 Form'] }}</td>
                            <td>
                                <span class="{% if record['Player 2 Payment Agreement'] == 'Yes' %}payment-yes{% else %}payment-no{% endif %}">
                                    {{ record['Player 2 Payment Agreement'] }}
                                </span>
                            </td>
                            <td>
                                <button class="update-btn btn-yes" onclick="updatePayment('{{ record['Team ID'] }}', 'player1', 'Yes')">P1: ✓</button>
                                <button class="update-btn btn-no" onclick="updatePayment('{{ record['Team ID'] }}', 'player1', 'No')">P1: ✗</button>
                                <br>
                                <button class="update-btn btn-yes" onclick="updatePayment('{{ record['Team ID'] }}', 'player2', 'Yes')">P2: ✓</button>
                                <button class="update-btn btn-no" onclick="updatePayment('{{ record['Team ID'] }}', 'player2', 'No')">P2: ✗</button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

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
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0; 
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                color: white;
            }
            .login-container { 
                background: rgba(255, 255, 255, 0.95); 
                padding: 50px; 
                border-radius: 20px; 
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
                min-width: 350px;
                text-align: center;
            }
            h2 { 
                color: #1e3c72; 
                margin-bottom: 30px;
                font-size: 2rem;
                font-weight: 600;
            }
            .login-icon {
                font-size: 4rem;
                color: #1e3c72;
                margin-bottom: 20px;
            }
            input[type="password"] { 
                width: 100%; 
                padding: 15px; 
                margin: 15px 0; 
                border: 2px solid #e3f2fd; 
                border-radius: 10px; 
                font-size: 16px;
                background: white;
                color: #1e3c72;
                transition: all 0.3s ease;
                box-sizing: border-box;
            }
            input[type="password"]:focus {
                outline: none;
                border-color: #2a5298;
                box-shadow: 0 0 10px rgba(42, 82, 152, 0.3);
            }
            button { 
                width: 100%; 
                padding: 15px; 
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                color: white; 
                border: none; 
                border-radius: 10px; 
                cursor: pointer; 
                font-size: 16px;
                font-weight: bold;
                transition: all 0.3s ease;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            button:hover { 
                background: linear-gradient(135deg, #0d47a1 0%, #1e3c72 100%);
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
            }
            .error { 
                color: #f44336; 
                margin-top: 15px; 
                padding: 10px;
                background: rgba(244, 67, 54, 0.1);
                border-radius: 5px;
                border: 1px solid rgba(244, 67, 54, 0.3);
            }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
                font-style: italic;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="login-icon">🎮</div>
            <h2>Teacher Dashboard</h2>
            <p class="subtitle">Tournament Management Portal</p>
            <form method="POST">
                <input type="password" name="password" placeholder="Enter teacher password" required>
                <button type="submit">Access Dashboard</button>
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
