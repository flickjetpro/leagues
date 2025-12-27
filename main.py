import json
import requests
import google.generativeai as genai
import time
import os

# --- LOAD SETTINGS ---
try:
    with open('settings.json', 'r') as f:
        config = json.load(f)
except:
    print("❌ Settings file not found.")
    exit(1)

# KEYS
KEY_EXTRACT = config.get("extraction_key")
KEY_VERIFY = config.get("verification_key")

# PROMPTS
PROMPT_EXTRACT = config.get("extraction_prompt")
PROMPT_VERIFY = config.get("verification_prompt")
ENABLE_VERIFY = config.get("enable_verification")

# --- BACKEND URL ---
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes"

# --- AI HELPER FUNCTION ---
def ask_gemini(api_key, prompt_text):
    if not api_key:
        return "Missing Key"
    try:
        # Configure the specific key for this request
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt_text)
        time.sleep(1.5) # Pause to be kind to the free API
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return "Error"

# --- MAIN PROCESS ---
def main():
    # 1. Load Local Database
    try:
        with open('db.json', 'r') as f:
            db = json.load(f)
    except:
        db = []

    # Map existing teams for quick lookup
    # Structure: {'TeamName': {Object}}
    existing_teams = {item['Team']: item for item in db}
    
    # 2. Fetch External Data
    print(f"🌍 Fetching data from: {BACKEND_URL}")
    try:
        resp = requests.get(BACKEND_URL)
        data = resp.json()
        matches = data.get('matches', [])
    except Exception as e:
        print(f"❌ Error fetching backend: {e}")
        return

    changes_made = False

    # 3. Process Teams (Extract from Team A and Team B)
    # We use a set to avoid processing the same team twice in one run
    teams_to_process = []
    
    for match in matches:
        # Get Sport (Important for context)
        sport = match.get('sport', 'unknown')
        
        # Add Team A
        teams_to_process.append({'name': match['team_a'], 'sport': sport})
        # Add Team B
        teams_to_process.append({'name': match['team_b'], 'sport': sport})

    # 4. AI EXTRACTION LOOP (Using Extraction Key)
    for t in teams_to_process:
        name = t['name']
        sport = t['sport']
        
        if name not in existing_teams:
            print(f"🆕 New Team found: {name} ({sport})")
            
            # Prepare Prompt
            prompt = PROMPT_EXTRACT.replace("{team}", name).replace("{sport}", sport)
            
            # Call AI #1
            league_guess = ask_gemini(KEY_EXTRACT, prompt)
            
            new_entry = {
                "Team": name,
                "League": league_guess,
                "Sport": sport, # Saving sport helps verification later
                "Verified": False
            }
            
            db.append(new_entry)
            existing_teams[name] = new_entry # Add to temp lookup to avoid duplicates in same run
            changes_made = True

    # 5. AI VERIFICATION LOOP (Using Verification Key)
    if ENABLE_VERIFY:
        for entry in db:
            # Check if needs verification AND has a valid key
            if not entry.get("Verified", False) and KEY_VERIFY:
                print(f"🕵️ Verifying: {entry['Team']} -> {entry['League']}")
                
                sport = entry.get('Sport', 'Sports')
                prompt = PROMPT_VERIFY.replace("{team}", entry['Team']).replace("{league}", entry['League']).replace("{sport}", sport)
                
                # Call AI #2
                decision = ask_gemini(KEY_VERIFY, prompt)
                
                if "CORRECT" in decision.upper():
                    print("   ✅ Confirmed Correct.")
                    entry["Verified"] = True
                    changes_made = True
                elif decision != "Error" and decision != "Missing Key":
                    print(f"   ⚠️ Correction: {entry['League']} -> {decision}")
                    entry["League"] = decision
                    entry["Verified"] = True
                    changes_made = True

    # 6. Save Data
    if changes_made:
        with open('db.json', 'w') as f:
            json.dump(db, f, indent=4)
        print("💾 Database updated successfully.")
    else:
        print("💤 No new teams or verifications needed.")

if __name__ == "__main__":
    main()