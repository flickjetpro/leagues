import json
import requests
import google.generativeai as genai
import time
import os

# --- CONFIGURATION ---
BATCH_LIMIT = 50  # Max AI calls per hour (Keeps us safe from limits)
SLEEP_TIME = 4    # Seconds between calls (Keeps us under 15 requests/min)

# --- LOAD SETTINGS ---
try:
    with open('settings.json', 'r') as f:
        config = json.load(f)
except:
    print("❌ Settings file not found.")
    exit(1)

KEY_EXTRACT = config.get("extraction_key")
KEY_VERIFY = config.get("verification_key")
PROMPT_EXTRACT = config.get("extraction_prompt")
PROMPT_VERIFY = config.get("verification_prompt")
ENABLE_VERIFY = config.get("enable_verification")

BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes"

# --- AI HELPER ---
def ask_gemini(api_key, prompt_text):
    if not api_key: return "Missing Key"
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt_text)
        return response.text.strip()
    except Exception as e:
        print(f"   ⚠️ AI Error: {e}")
        return "Error"

# --- MAIN PROCESS ---
def main():
    # 1. Load Database
    try:
        with open('db.json', 'r') as f:
            db = json.load(f)
    except:
        db = []

    existing_teams_map = {item['Team']: item for item in db}
    
    # 2. Fetch Backend Data
    print(f"🌍 Fetching data from Backend...")
    try:
        resp = requests.get(BACKEND_URL)
        data = resp.json()
        matches = data.get('matches', [])
    except Exception as e:
        print(f"❌ Error fetching backend: {e}")
        return

    # 3. Identify New Teams
    new_teams_queue = []
    for match in matches:
        sport = match.get('sport') or "Unknown"
        # Check Team A
        ta = match.get('team_a')
        if ta and ta not in existing_teams_map:
            # Avoid duplicates in the queue
            if not any(x['name'] == ta for x in new_teams_queue):
                new_teams_queue.append({'name': ta, 'sport': sport})
        
        # Check Team B
        tb = match.get('team_b')
        if tb and tb not in existing_teams_map:
            if not any(x['name'] == tb for x in new_teams_queue):
                new_teams_queue.append({'name': tb, 'sport': sport})

    print(f"📊 Status: {len(db)} teams in DB. {len(new_teams_queue)} new teams waiting.")
    
    ai_calls_made = 0
    changes_made = False

    # --- PHASE 1: EXTRACTION (Priority) ---
    print(f"🚀 Starting Batch Processing (Limit: {BATCH_LIMIT} calls)...")

    for item in new_teams_queue:
        if ai_calls_made >= BATCH_LIMIT:
            break # Stop if budget used
        
        name = item['name']
        sport = item['sport']
        
        print(f"[{ai_calls_made+1}/{BATCH_LIMIT}] 🆕 Extracting: {name} ({sport})")
        
        prompt = PROMPT_EXTRACT.replace("{team}", str(name)).replace("{sport}", str(sport))
        league_guess = ask_gemini(KEY_EXTRACT, prompt)
        time.sleep(SLEEP_TIME) # Rate limit safety
        ai_calls_made += 1

        if league_guess != "Error":
            new_entry = {
                "Team": name,
                "League": league_guess,
                "Sport": sport,
                "Verified": False, # Needs verification later
                "Status": "New"
            }
            db.append(new_entry)
            existing_teams_map[name] = new_entry
            changes_made = True

    # --- PHASE 2: VERIFICATION (Fill remaining budget) ---
    # We filter for teams that are NOT verified yet
    unverified_teams = [t for t in db if t.get("Verified") is False]

    if ENABLE_VERIFY and ai_calls_made < BATCH_LIMIT:
        for entry in unverified_teams:
            if ai_calls_made >= BATCH_LIMIT:
                break
            
            print(f"[{ai_calls_made+1}/{BATCH_LIMIT}] 🕵️ Verifying: {entry['Team']}")
            
            prompt = PROMPT_VERIFY.replace("{team}", str(entry['Team']))\
                                  .replace("{league}", str(entry['League']))\
                                  .replace("{sport}", str(entry.get('Sport', 'Unknown')))
            
            decision = ask_gemini(KEY_VERIFY, prompt)
            time.sleep(SLEEP_TIME)
            ai_calls_made += 1

            if "CORRECT" in decision.upper():
                print("   ✅ Verified Correct.")
                entry["Verified"] = True
                entry["Status"] = "Verified"
                changes_made = True
            elif decision != "Error" and len(decision) < 50:
                # If AI returned a league name (not an error message)
                print(f"   ⚠️ Modified: {entry['League']} -> {decision}")
                entry["League"] = decision
                entry["Verified"] = True
                entry["Status"] = "Modified" # Special flag for admin panel
                changes_made = True

    # 4. Save
    if changes_made:
        with open('db.json', 'w') as f:
            json.dump(db, f, indent=4)
        print("💾 Database updated.")
    else:
        print("💤 No changes made this run.")
        
    print(f"🏁 Run Complete. Used {ai_calls_made} AI credits.")

if __name__ == "__main__":
    main()
