import json
import os
import time
import re
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
CURSOR_FILE = 'scripts/verification_cursor.txt'
BATCH_SIZE = 50       # Check 50 teams per API Call
BATCHES_PER_RUN = 5   # Run 5 batches (Total 250 teams)
SLEEP_TIME = 8        # Wait 8s between batches

def get_best_model(client):
    try:
        all_models = list(client.models.list())
        priorities = ['gemini-1.5-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash-002', 'gemini-2.0-flash-exp']
        available_names = [m.name.replace('models/', '') for m in all_models]
        for p in priorities:
            if p in available_names: return p
        return 'gemini-1.5-flash'
    except: return 'gemini-1.5-flash'

def clean_json(text):
    if "```" in text:
        text = re.sub(r"^```json|^```|```$", "", text, flags=re.MULTILINE).strip()
    return text

def main():
    print("--- [Phase 3] Starting Rolling Verification ---")

    api_key = os.environ.get("GEMINI_KEY_VERIFICATION")
    
    try:
        with open(SETTINGS_FILE, 'r') as f: settings = json.load(f)
        if not settings.get("enable_verification", False): return
        
        with open(DB_FILE, 'r') as f: db = json.load(f)
    except: return

    # 1. Load Cursor
    start_index = 0
    if os.path.exists(CURSOR_FILE):
        try:
            with open(CURSOR_FILE, 'r') as f: start_index = int(f.read().strip())
        except: start_index = 0

    if start_index >= len(db): start_index = 0
    print(f" > Cursor Position: {start_index} / {len(db)}")

    client = genai.Client(api_key=api_key)
    model_name = get_best_model(client)
    prompt_template = settings.get("verification_prompt", "")
    
    changes = False
    current_index = start_index

    # 2. Run Batches
    for i in range(BATCHES_PER_RUN):
        # Slice the next batch of raw teams
        raw_batch = db[current_index : current_index + BATCH_SIZE]
        
        if not raw_batch: 
            current_index = 0 
            break

        # --- STRICT FILTERING ---
        # Only send teams that ALREADY have a league. 
        # We explicitly exclude blanks so AI never wastes tokens on them.
        valid_payload = [
            {"Team": t['Team'], "League": t['League'], "Sport": t['Sport']} 
            for t in raw_batch 
            if t.get('League') and t.get('League') != "Unknown"
        ]

        skipped_count = len(raw_batch) - len(valid_payload)
        
        print(f"   Batch {i+1}: Checking {len(valid_payload)} teams (Skipped {skipped_count} blanks)...")
        
        # Only call AI if we have valid teams to check
        if valid_payload:
            try:
                prompt = prompt_template.replace("{batch_data}", json.dumps(valid_payload))
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                raw_text = clean_json(response.text.strip())
                corrections = json.loads(raw_text)
                
                if corrections:
                    team_map = {t['Team']: t for t in db}
                    for fix in corrections:
                        t_name = fix.get("Team")
                        correct_league = fix.get("League")
                        
                        if t_name in team_map:
                            rec = team_map[t_name]
                            if rec['League'] != correct_league:
                                print(f"     ⚠️ Correction: {t_name} -> {correct_league}")
                                rec['League'] = correct_league
                                rec['Status'] = "Modified"
                                changes = True
            except Exception as e:
                print(f"     [!] Verification Batch Failed: {e}")
        
        else:
            print("     [i] Batch contained only blank teams. No API call made.")

        # Advance Cursor
        current_index += len(raw_batch)
        if current_index >= len(db):
            current_index = 0
        
        # Only sleep if we actually made a call
        if valid_payload:
            time.sleep(SLEEP_TIME)

    # 3. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print(" > Database Updated.")
        
    with open(CURSOR_FILE, 'w') as f: f.write(str(current_index))
    print(f" > Next run starts at Index: {current_index}")

if __name__ == "__main__":
    main()
