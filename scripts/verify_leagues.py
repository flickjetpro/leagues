import json
import os
import time
import re
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
BATCH_SIZE = 30
SLEEP_TIME = 5

def main():
    print("--- [Phase 3] Starting AI Verification ---")

    # 1. Setup
    api_key = os.environ.get("GEMINI_KEY_VERIFICATION")
    
    try:
        with open(SETTINGS_FILE, 'r') as f: settings = json.load(f)
        if not settings.get("enable_verification", False):
            print(" > Verification disabled in settings.json")
            return
        if not api_key:
            print(" [!] No Verification Key in Secrets.")
            return

        with open(DB_FILE, 'r') as f: db = json.load(f)
    except: return

    prompt_template = settings.get("verification_prompt", "")
    client = genai.Client(api_key=api_key)
    
    # 2. Filter Targets
    targets = [t for t in db if t.get('League')]
    print(f" > Verifying {len(targets)} teams in batches of {BATCH_SIZE}...")
    
    changes = False

    # 3. Batch Loop
    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i : i + BATCH_SIZE]
        mini_payload = [{"Team": x["Team"], "League": x["League"], "Sport": x["Sport"]} for x in batch]
        
        print(f"   > Batch {i}-{i+len(batch)}...")

        try:
            prompt = prompt_template.replace("{batch_data}", json.dumps(mini_payload))
            
            # UPDATED MODEL NAME: 'gemini-1.5-flash-001'
            response = client.models.generate_content(
                model='gemini-1.5-flash-001',
                contents=prompt
            )
            
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```json|^```|```$", "", text, flags=re.MULTILINE).strip()
            
            corrections = json.loads(text)
            
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
            
            time.sleep(SLEEP_TIME)

        except Exception as e:
            print(f"     [!] Batch Error: {e}")

    # 4. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("--- Verification Complete. Saved corrections. ---")
    else:
        print("--- Verification Complete. All good. ---")

if __name__ == "__main__":
    main()
