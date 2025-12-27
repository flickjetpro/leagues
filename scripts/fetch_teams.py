import json
import requests
import os
import time

# CONFIG
DB_FILE = 'db.json'
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes"

# EXACT HEADERS FROM YOUR WORKING ASSET SCRIPT
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

def main():
    print("--- [Phase 1] Starting Backend Sync ---")
    
    # 1. Load Local DB
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: db = json.load(f)
        except: db = []
    else:
        db = []
    
    existing_map = {item['Team']: item for item in db}
    initial_count = len(db)

    # 2. Fetch Backend (With Timeout & Headers)
    try:
        print(f" > Connecting to: {BACKEND_URL}")
        resp = requests.get(BACKEND_URL, headers=HEADERS, timeout=20) # 20s Timeout
        
        if resp.status_code != 200:
            print(f" [!] Failed Status: {resp.status_code}")
            return

        data = resp.json()
        matches = data.get('matches', [])
        print(f" > Received {len(matches)} matches.")
        
    except Exception as e:
        print(f" [!] CRITICAL NETWORK ERROR: {e}")
        return

    # 3. Process Data
    changes = 0
    for m in matches:
        sport = m.get('sport') or "Unknown"
        for role in ['team_a', 'team_b']:
            t_name = m.get(role)
            if t_name and t_name not in existing_map:
                print(f"   [+] New Team: {t_name}")
                new_entry = {
                    "Team": t_name,
                    "Sport": sport,
                    "League": "",
                    "Status": "Pending"
                }
                db.append(new_entry)
                existing_map[t_name] = new_entry
                changes += 1

    # 4. Save
    if changes > 0:
        with open(DB_FILE, 'w') as f:
            json.dump(db, f, indent=4)
        print(f"--- Sync Complete. Added {changes} teams. Total: {len(db)} ---")
    else:
        print("--- Sync Complete. No new teams found. ---")

if __name__ == "__main__":
    main()
