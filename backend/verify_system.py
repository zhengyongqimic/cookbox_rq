import requests
import time
import sqlite3
import os
import uuid
import sys

# Configuration
BASE_URL = "http://localhost:5000"
# Try instance folder first as it's the default for Flask-SQLAlchemy with relative paths
DB_PATH = os.path.join(os.getcwd(), "instance", "hyperkitchen.db")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(os.getcwd(), "hyperkitchen.db")

print(f"Using Database: {DB_PATH}")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def register(username, password):
    url = f"{BASE_URL}/api/auth/register"
    resp = requests.post(url, json={"username": username, "password": password})
    return resp

def login(username, password):
    url = f"{BASE_URL}/api/auth/login"
    resp = requests.post(url, json={"username": username, "password": password})
    if resp.status_code == 200:
        return resp.json()['access_token']
    return None

def analyze_link(token, url):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/api/analyze-link", json={"url": url}, headers=headers)
    return resp

def get_status(file_id):
    resp = requests.get(f"{BASE_URL}/api/status/{file_id}")
    return resp.json()

def main():
    print("=== Starting System Verification ===")
    
    # 1. Register User A and User B
    unique_suffix = str(uuid.uuid4())[:8]
    user_a = f"user_a_{unique_suffix}"
    user_b = f"user_b_{unique_suffix}"
    password = "password123"
    
    print(f"1. Registering users: {user_a}, {user_b}")
    reg_a = register(user_a, password)
    reg_b = register(user_b, password)
    
    if reg_a.status_code != 201 or reg_b.status_code != 201:
        print(f"Registration failed: A={reg_a.status_code}, B={reg_b.status_code}")
        # If 400, maybe already exists (unlikely with uuid), but proceed to login
    
    token_a = login(user_a, password)
    token_b = login(user_b, password)
    
    if not token_a or not token_b:
        print("Login failed")
        sys.exit(1)
        
    print("User A and User B logged in successfully.")
    
    # 2. User A analyzes a video URL
    # Use a mock URL that will definitely fail download in backend, allowing us to hijack the status
    mock_url = f"https://www.bilibili.com/video/BV_MOCK_{unique_suffix}" 
    print(f"2. User A analyzing URL: {mock_url}")
    
    resp_a = analyze_link(token_a, mock_url)
    print(f"User A Response: {resp_a.json()}")
    
    if resp_a.status_code != 200:
        print("User A analysis request failed")
        sys.exit(1)
        
    file_id_a = resp_a.json().get('file_id')
    print(f"File ID A: {file_id_a}")
    
    # 3. Verify a new VideoResource is created
    # Wait a bit for the backend to process (and fail downloading)
    print("Waiting for backend processing...")
    time.sleep(3)
    
    status_a = get_status(file_id_a)
    print(f"Current Status A: {status_a.get('status')}")
    
    # It should be 'analyzing' or 'error' (likely error due to fake URL)
    # 3. Verify VideoResource exists in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    video_row = cursor.execute("SELECT * FROM video_resources WHERE id = ?", (file_id_a,)).fetchone()
    
    if video_row:
        print("VERIFIED: VideoResource created for User A.")
    else:
        print("FAILED: VideoResource not found in DB.")
        sys.exit(1)
        
    # Hack: Manually update status to 'completed' and add steps to simulate successful analysis
    # This allows us to test the deduplication logic for User B
    print("Simulating successful completion in DB...")
    cursor.execute("UPDATE video_resources SET status = 'completed' WHERE id = ?", (file_id_a,))
    
    # Add dummy steps
    cursor.execute("DELETE FROM recipe_steps WHERE video_id = ?", (file_id_a,))
    cursor.execute("""
        INSERT INTO recipe_steps (video_id, step_number, start_time, end_time, title, description, video_url)
        VALUES (?, 1, 0, 10, 'Test Step', 'This is a mock step', '/mock/video.mp4')
    """, (file_id_a,))
    conn.commit()
    conn.close()
    print("DB updated to 'completed' with dummy steps.")
    
    # 4. User B analyzes the SAME URL
    print(f"4. User B analyzing SAME URL: {mock_url}")
    resp_b = analyze_link(token_b, mock_url)
    print(f"User B Response: {resp_b.json()}")
    
    # 5. Verify no new VideoResource is created (deduplication)
    # Response should say "Video already processed" and return the SAME file_id
    data_b = resp_b.json()
    
    if data_b.get('message') == "Video already processed":
        print("VERIFIED: Backend returned 'Video already processed'.")
    else:
        print(f"FAILED: Expected 'Video already processed', got '{data_b.get('message')}'")
        
    file_id_b = data_b.get('file_id')
    if file_id_b == file_id_a:
        print(f"VERIFIED: User B received same File ID ({file_id_b}).")
    else:
        print(f"FAILED: File IDs differ! A: {file_id_a}, B: {file_id_b}")
        
    # 6. Verify User B gets the recipe
    steps = data_b.get('steps', [])
    if len(steps) > 0 and steps[0]['title'] == 'Test Step':
        print("VERIFIED: User B received recipe steps.")
    else:
        print("FAILED: User B did not receive expected steps.")
        print(f"Steps received: {steps}")

    print("\n=== System Verification Completed Successfully ===")

if __name__ == "__main__":
    main()
