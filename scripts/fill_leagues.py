import json
import os
import time
import re
from google import genai
from google.genai import types

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
BATCH_SIZE = 10       # 10 teams per call
TOTAL_LIMIT = 50      # Max 50 teams per run
SLEEP_TIME = 20       # Increased to 20s to be safe

def get_best_model(client):
    """
    Prioritizes STABLE models over Experimental ones to avoid 'limit: 0' errors.
    """
    try:
        all_models = list(client.models.list())
        # NEW PRIORITY: Stable Flash -> Legacy Flash -> Pro -> Experimental (Last)
        priorities = [
            'gemini-1.5-flash',
            'gemini-1.5-flash-001',
            'gemini-1.5-flash-002',
            'gemini-1.5-pro',
            'gemini-2.0-flash-exp' 
        ]
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
    print(f"--- [Phase 2] Starting AI Filling (Batch Size: {BATCH_SIZE}) ---")

    api_key = os.environ.get("GEMINI_KEY_EXTRACTION")
    if not api_key:
        print(" [!] No Extraction API Key found.")
        return

    try:
        with open(DB_FILE, 'r') as f: db = json.load(f)
        with open(SETTINGS_FILE, 'r') as f: settings = json.load(f)
    except: return

    client = genai.Client(api_key=api_key)
    model_name = get_best_model(client)
    print(f" > Using Model: {model_name}")
    
    prompt_template = settings.get("extraction_prompt", "")

    # 1. Get Unfilled Teams
    unfilled = [t for t in db if not t.get('League')]
    print(f" > Found {len(unfilled)} pending teams.")

    targets = unfilled[:TOTAL_LIMIT]
    changes = False

    # 2. Process in Batches
    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i : i + BATCH_SIZE]
        ai_input = [{"Team": t['Team'], "Sport": t['Sport']} for t in batch]
        
        print(f"   Batch {i//BATCH_SIZE + 1}: Asking for {len(batch)} teams...")
        
        # RETRY LOGIC (Max 3 attempts)
        attempts = 0
        success = False
        
        while attempts < 3 and not success:
            try:
                prompt = prompt_template.replace("{batch_data}", json.dumps(ai_input))
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                raw_text = clean_json(response.text.strip())
                results = json.loads(raw_text)
                
                batch_map = {t['Team']: t for t in batch}
                for res in results:
                    team_name = res.get('Team')
                    league = res.get('League')
                    if team_name in batch_map and league and league != "Unknown":
                        batch_map[team_name]['League'] = league
                        batch_map[team_name]['Status'] = "AI_Filled"
                        changes = True
                
                print(f"     ✅ Success.")
                success = True

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"     ⚠️ Quota Limit. Waiting 60s before retry...")
                    time.sleep(60) # Wait 1 minute if blocked
                    attempts += 1
                else:
                    print(f"     [!] Error: {e}")
                    attempts = 3 # Stop trying for non-quota errors

        # Normal Sleep between batches
        if success:
            time.sleep(SLEEP_TIME)

    # 3. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("--- Phase 2 Complete. Database Updated. ---")
    else:
        print("--- Phase 2 Complete. No changes. ---")

if __name__ == "__main__":
    main()
