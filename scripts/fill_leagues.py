import json
import os
import time
import re
from google import genai
from google.genai import types

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
BATCH_SIZE = 5        # Safe Batch Size
TOTAL_LIMIT = 50      # Max teams to fill
SLEEP_TIME = 20       # Delay between batches

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
    """
    Tests multiple model names to find one that works for this API Key.
    """
    print(" > 🔍 Hunting for a working model...")
    # List of models to try (Stable -> Specific -> Pro -> Experimental)
    candidates = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-001',
        'gemini-1.5-flash-002',
        'gemini-1.5-flash-8b',
        'gemini-1.5-pro',
        'gemini-1.0-pro'
    ]
    
    for model in candidates:
        try:
            # Try a 1-token ping
            response = client.models.generate_content(
                model=model,
                contents="Hi"
            )
            if response and get_text(response):
                print(f"   ✅ Found working model: {model}")
                return model
        except Exception as e:
            error = str(e)
            if "429" in error:
                print(f"   ❌ {model}: Quota Exceeded (Skipping)")
            elif "404" in error:
                print(f"   ❌ {model}: Not Found (Skipping)")
            else:
                print(f"   ❌ {model}: Error ({error[:50]}...)")
    
    print("   ⚠️ No working models found. Defaulting to gemini-1.5-flash")
    return 'gemini-1.5-flash'

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

    # Initialize Client
    client = genai.Client(api_key=api_key)
    
    # HUNT FOR MODEL
    model_name = find_working_model(client)
    
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
        
        # RETRY LOGIC (Exponential Backoff)
        max_retries = 3
        retry_delay = 30
        success = False
        
        for attempt in range(max_retries):
            try:
                prompt = prompt_template.replace("{batch_data}", json.dumps(ai_input))
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                raw_text = clean_json(get_text(response))
                if not raw_text: raise ValueError("Empty response")

                results = json.loads(raw_text)
                if isinstance(results, dict): results = [results]
                
                batch_map = {t['Team']: t for t in batch}
                
                for res in results:
                    team_name = res.get('Team')
                    league = res.get('League')
                    
                    if team_name in batch_map and league:
                        clean_league = str(league).strip()
                        if clean_league.lower() != "unknown" and clean_league != "":
                            batch_map[team_name]['League'] = clean_league
                            batch_map[team_name]['Status'] = "AI_Filled"
                            changes = True
                
                print(f"     ✅ Success.")
                success = True
                break

            except Exception as e:
                error_str = str(e)
                print(f"     ⚠️ Attempt {attempt+1} Failed.")
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"        ⏳ Quota hit. Waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 
                elif "404" in error_str:
                     print("        [!] Model 404'd mid-run. Aborting batch.")
                     break
                else:
                    print(f"        [!] Error: {error_str[:100]}")
                    break

        if not success:
            print("     [!] Failed batch. Stopping Phase 2.")
            break

        time.sleep(SLEEP_TIME)

    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("--- Phase 2 Complete. Database Updated. ---")
    else:
        print("--- Phase 2 Complete. No changes. ---")

if __name__ == "__main__":
    main()
