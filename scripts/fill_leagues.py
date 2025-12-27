import json
import os
import time
import re
from google import genai
from google.genai import types

# CONFIG
DB_FILE = 'db.json'
SETTINGS_FILE = 'settings.json'
BATCH_SIZE = 5        # Reduced to 5 for maximum safety
TOTAL_LIMIT = 50      # Process max 50 teams per run
SLEEP_TIME = 20       # 20s delay between successful batches

def get_text(response):
    """Safely extracts text from the new Google GenAI response object"""
    try:
        # The new SDK structure is nested
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text.strip()
    except Exception:
        pass
    return ""

def clean_json(text):
    if not text: return ""
    # Remove markdown code blocks
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

    # FORCE STABLE MODEL
    model_name = "gemini-1.5-flash"
    client = genai.Client(api_key=api_key)
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
        
        # RETRY LOGIC (Exponential Backoff)
        max_retries = 3
        retry_delay = 60 # Start with 60s wait
        success = False
        
        for attempt in range(max_retries):
            try:
                prompt = prompt_template.replace("{batch_data}", json.dumps(ai_input))
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                
                # SAFE TEXT EXTRACTION
                raw_text = clean_json(get_text(response))
                if not raw_text:
                    raise ValueError("Empty response from AI")

                results = json.loads(raw_text)
                
                # Handle single object vs list
                if isinstance(results, dict): results = [results]
                
                batch_map = {t['Team']: t for t in batch}
                
                for res in results:
                    team_name = res.get('Team')
                    league = res.get('League')
                    
                    # Normalize and Check
                    if team_name in batch_map and league:
                        clean_league = str(league).strip()
                        if clean_league.lower() != "unknown" and clean_league != "":
                            batch_map[team_name]['League'] = clean_league
                            batch_map[team_name]['Status'] = "AI_Filled"
                            changes = True
                
                print(f"     ✅ Success.")
                success = True
                break # Exit retry loop

            except Exception as e:
                error_str = str(e)
                print(f"     ⚠️ Attempt {attempt+1} Failed: {error_str[:100]}...")
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"        ⏳ Quota hit. Waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Double wait time next time (60 -> 120 -> 240)
                else:
                    break # Don't retry logic errors

        # If we failed all retries, stop the whole script to save logs
        if not success:
            print("     [!] Failed all retries. Stopping Phase 2.")
            break

        # Normal Sleep between successful batches
        time.sleep(SLEEP_TIME)

    # 3. Save
    if changes:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("--- Phase 2 Complete. Database Updated. ---")
    else:
        print("--- Phase 2 Complete. No changes. ---")

if __name__ == "__main__":
    main()
