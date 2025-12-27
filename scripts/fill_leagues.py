import json
import os
import time
import re
from google import genai

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
BATCH_SIZE = 10       # Send 10 teams per API Call
TOTAL_LIMIT = 50      # Process max 50 teams per run
SLEEP_TIME = 10       # Wait 10s between batches (Very Safe)

def get_best_model(client):
    try:
        all_models = list(client.models.list())
        # Priority: Flash models are faster/cheaper/higher rate limits
        priorities = ['gemini-1.5-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash-002', 'gemini-2.0-flash-exp']
        available_names = [m.name.replace('models/', '') for m in all_models]
        for p in priorities:
            if p in available_names: return p
        return 'gemini-1.5-flash'
    except: return 'gemini-1.5-flash'

def clean_json(text):
    # Remove markdown code blocks if AI adds them
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
    prompt_template = settings.get("extraction_prompt", "")

    # 1. Get Unfilled Teams
    unfilled = [t for t in db if not t.get('League')]
    print(f" > Found {len(unfilled)} pending teams.")

    # 2. Limit to TOTAL_LIMIT (e.g. 50)
    targets = unfilled[:TOTAL_LIMIT]
    
    changes = False

    # 3. Process in Batches
    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i : i + BATCH_SIZE]
        
        # Prepare Data for AI
        ai_input = [{"Team": t['Team'], "Sport": t['Sport']} for t in batch]
        
        print(f"   Batch {i//BATCH_SIZE + 1}: Asking for {len(batch)} teams...")
        
        try:
            prompt = prompt_template.replace("{batch_data}", json.dumps(ai_input))
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            
            # Parse Response
            raw_text = clean_json(response.text.strip())
            results = json.loads(raw_text) # Expecting List of Objects
            
            # Map results back to DB objects
            # Create a quick lookup for the current batch
            batch_map = {t['Team']: t for t in batch}
            
            for res in results:
                team_name = res.get('Team')
                league = res.get('League')
                
                if team_name in batch_map and league and league != "Unknown":
                    batch_map[team_name]['League'] = league
                    batch_map[team_name]['Status'] = "AI_Filled"
                    changes = True
            
            print(f"     ✅ Processed batch successfully.")

        except Exception as e:
            print(f"     [!] Batch Failed: {e}")

        # Sleep to prevent 429 Error
        time.sleep(SLEEP_TIME)

    # 4. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("--- Phase 2 Complete. Database Updated. ---")
    else:
        print("--- Phase 2 Complete. No changes. ---")

if __name__ == "__main__":
    main()
