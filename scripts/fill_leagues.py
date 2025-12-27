import json
import os
import time
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
FILL_LIMIT = 50
SLEEP_TIME = 5

def main():
    print(f"--- [Phase 2] Starting AI Filling (Limit: {FILL_LIMIT}) ---")

    # 1. Setup
    api_key = os.environ.get("GEMINI_KEY_EXTRACTION")
    if not api_key:
        print(" [!] No Extraction API Key found in Secrets.")
        return

    try:
        with open(DB_FILE, 'r') as f: db = json.load(f)
        with open(SETTINGS_FILE, 'r') as f: settings = json.load(f)
    except Exception as e:
        print(f" [!] Error loading files: {e}")
        return

    prompt_template = settings.get("extraction_prompt", "")
    
    # Initialize Client
    client = genai.Client(api_key=api_key)

    # 2. Identify Targets
    unfilled = [t for t in db if not t.get('League')]
    print(f" > Found {len(unfilled)} pending teams.")

    count = 0
    changes = False

    # 3. AI Loop
    for t in unfilled:
        if count >= FILL_LIMIT: break
        
        team_name = t['Team']
        sport = t['Sport']
        
        print(f"   [{count+1}/{FILL_LIMIT}] Asking AI: {team_name} ({sport})...")
        
        try:
            prompt = prompt_template.replace("{team}", str(team_name)).replace("{sport}", str(sport))
            
            # UPDATED MODEL NAME: Using specific version 'gemini-1.5-flash-001' to fix 404 error
            response = client.models.generate_content(
                model='gemini-1.5-flash-001',
                contents=prompt
            )
            
            result = response.text.strip()
            
            if result and "error" not in result.lower():
                t['League'] = result
                t['Status'] = "AI_Filled"
                changes = True
                count += 1
                print(f"     ✅ Result: {result}")
            else:
                print("     [-] AI returned unclear response.")

            time.sleep(SLEEP_TIME)

        except Exception as e:
            print(f"     [!] AI Error: {e}")
            time.sleep(SLEEP_TIME)

    # 4. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print(f"--- Phase 2 Complete. Filled {count} teams. ---")
    else:
        print("--- Phase 2 Complete. No changes. ---")

if __name__ == "__main__":
    main()
