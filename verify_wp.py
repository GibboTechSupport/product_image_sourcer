
import requests
import os
import base64

# User provided info
WP_URL = "https://harbourstreet.gibbotrading.com" 
# Trying 'Admin' from .env, but user didn't specify.
WP_USER = "Script"
# User provided password
WP_APP_PASSWORD = "yEdV m6P7 5bH8 OvYS 1PWb uQvZ"

def verify_connection():
    print(f"Testing connection to {WP_URL}...")
    
    # Basic auth header
    credentials = f"{WP_USER}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    headers = {'Authorization': f'Basic {token}'}
    
    try:
        # Try to get current user to verify auth
        response = requests.get(f"{WP_URL}/wp-json/wp/v2/users/me", headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("SUCCESS: Authentication successful!")
            user_data = response.json()
            print(f"Logged in as: {user_data.get('name')} (ID: {user_data.get('id')})")
            return True
        else:
            print(f"FAILED: Status {response.status_code}")
            print(response.text[:200])
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    verify_connection()
