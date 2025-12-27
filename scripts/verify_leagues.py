import json
import os
import time
import re
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
CURSOR_FILE = 'scripts/verification_cursor.txt'
BATCH_SIZE = 50       
BATCHES_PER_RUN = 5   
SLEEP_TIME = 15       

def get_text(response):
    try:
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text.strip()
    except: pass
    return ""

def clean_json(text):
    if not text: return ""
    text = re.sub(r"^```json|^```|```$", "", text, flags=re.MULTILINE).strip()
    return text

def find_working_model(client):
    candidates = ['gemini-1.5-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash-002', 'gemini-1.5-pro']
    for model in candidates:
        try:
            res = client.models.generate_content(model=model, contents="Hi")
            if res: return model
        except: pass
    return 'gemini-1.5-flash'

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
    # AUTO-DISCOVER MODEL
    model_name = find_working_model(client)
    print(f" > Using Model: {model_name}")
    
    prompt_template = settings.get("verification_prompt", "")
    changes = False
    current_index = start_index

    # 2. Run Batches
    for i in range(BATCHES_PER_RUN):
        raw_batch = db[current_index : current_index + BATCH_SIZE]
        if not raw_batch: 
            current_index = 0 
            break

        # Filter out blanks
        valid_payload = [
            {"Team": t['Team'], "League": t['League'], "Sport": t['Sport']} 
            for t in raw_batch 
            if t.get('League') and str(t.get('League')).lower() != "unknown"
        ]

        print(f"   Batch {i+1}: Checking {len(valid_payload)} teams...")
        
        if valid_payload:
            try:
                prompt = prompt_template.replace("{batch_data}", json.dumps(valid_payload))
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                raw_text = clean_json(get_text(response))
                if raw_text:
                    corrections = json.loads(raw_text)
                    if isinstance(corrections, dict): corrections = [corrections]
                    
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
                print(f"     [!] Batch Failed: {str(e)[:100]}")
                if "429" in str(e): time.sleep(60)
        
        current_index += len(raw_batch)
        if current_index >= len(db): current_index = 0
        
        if valid_payload: time.sleep(SLEEP_TIME)

    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print(" > Database Updated.")
        
    with open(CURSOR_FILE, 'w') as f: f.write(str(current_index))

if __name__ == "__main__":
    main()
