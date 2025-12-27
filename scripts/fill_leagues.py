import json
import os
import time
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
FILL_LIMIT = 50
SLEEP_TIME = 5

def get_best_model(client):
    """Auto-detects the best available model for this API Key"""
    try:
        # List all models available to your key
        # We look for 'generateContent' supported models
        all_models = list(client.models.list())
        
        # Priority List (Fastest/Cheapest first)
        priorities = [
            'gemini-1.5-flash',
            'gemini-1.5-flash-001',
            'gemini-1.5-flash-002',
            'gemini-2.0-flash-exp',
            'gemini-1.5-pro',
            'gemini-pro'
        ]
        
        # Check against available models (names usually look like 'models/gemini-1.5-flash')
        available_names = [m.name.replace('models/', '') for m in all_models]
        
        for p in priorities:
            if p in available_names:
                return p
                
        # Fallback: Just return the first one that contains 'gemini'
        for name in available_names:
            if 'gemini' in name: return name
            
        return 'gemini-1.5-flash' # Absolute fallback
    except Exception as e:
        print(f" [!] Model Auto-Detect Failed: {e}")
        return 'gemini-1.5-flash'

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
    
    # AUTO-DETECT MODEL
    model_name = get_best_model(client)
    print(f" > Using AI Model: {model_name}")

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
            
            response = client.models.generate_content(
                model=model_name,
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
