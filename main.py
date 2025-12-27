import json
import requests
import google.generativeai as genai
import time
import re

# --- CONFIGURATION ---
FILL_LIMIT = 50       # How many blank teams to fill per hour (AI #1)
BATCH_SIZE = 30       # How many teams to verify at once (AI #2)
SLEEP_TIME = 2        # Delay to respect free tier limits

# --- LOAD SETTINGS ---
try:
    with open('settings.json', 'r') as f: config = json.load(f)
except:
    print("❌ Settings file not found.")
    exit(1)

KEY_FILL = config.get("extraction_key")
KEY_VERIFY = config.get("verification_key")
PROMPT_FILL = config.get("extraction_prompt")
PROMPT_VERIFY = config.get("verification_prompt")

BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes"

# --- AI HELPERS ---
def ask_ai_fill(api_key, team, sport):
    if not api_key: return "Error"
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = PROMPT_FILL.replace("{team}", str(team)).replace("{sport}", str(sport))
        response = model.generate_content(prompt)
        return response.text.strip()
    except: return "Error"

def ask_ai_verify_batch(api_key, batch_data):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = PROMPT_VERIFY.replace("{batch_data}", json.dumps(batch_data))
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean JSON
        if text.startswith("```"):
            text = re.sub(r"^```json|^```|```$", "", text, flags=re.MULTILINE).strip()
        return json.loads(text)
    except Exception as e:
        print(f"   ⚠️ Batch Verify Error: {e}")
        return []

# --- MAIN LOGIC ---
def main():
    # 1. LOAD DB
    try:
        with open('db.json', 'r') as f: db = json.load(f)
    except: db = []
    
    # Create lookup map for fast checking
    existing_map = {item['Team']: item for item in db}
    changes_made = False

    # ======================================================
    # PHASE 1: SYNC (Extract Backend -> DB) - NO AI HERE
    # ======================================================
    print("🌍 Phase 1: Syncing from Backend...")
    try:
        resp = requests.get(BACKEND_URL)
        matches = resp.json().get('matches', [])
    except Exception as e:
        print(f"❌ Backend Error: {e}")
        matches = []

    for m in matches:
        sport = m.get('sport') or "Unknown"
        # Check both teams
        for role in ['team_a', 'team_b']:
            t_name = m.get(role)
            # If valid name and NOT in DB yet
            if t_name and t_name not in existing_map:
                print(f"   🆕 Found new team: {t_name}")
                new_entry = {
                    "Team": t_name,
                    "Sport": sport,
                    "League": "",       # BLANK intentionally
                    "Status": "Pending" # Waiting for AI or Manual
                }
                db.append(new_entry)
                existing_map[t_name] = new_entry
                changes_made = True

    # ======================================================
    # PHASE 2: FILL BLANKS (AI #1) - Limit 50
    # ======================================================
    print(f"\n🤖 Phase 2: Filling Empty Leagues (Limit: {FILL_LIMIT})...")
    
    # Get list of teams that have NO league
    unfilled_teams = [t for t in db if not t.get('League')]
    
    fill_count = 0
    for team in unfilled_teams:
        if fill_count >= FILL_LIMIT:
            break
        
        print(f"   ✏️ Filling: {team['Team']}")
        result = ask_ai_fill(KEY_FILL, team['Team'], team['Sport'])
        time.sleep(SLEEP_TIME)
        
        if result and result != "Error":
            team['League'] = result
            team['Status'] = "AI_Filled"
            changes_made = True
            fill_count += 1
    
    if fill_count == 0:
        print("   ✅ No blank teams found (or limit reached).")

    # ======================================================
    # PHASE 3: VERIFY ALL (AI #2) - Batch Check
    # ======================================================
    if config.get("enable_verification"):
        print(f"\n🕵️ Phase 3: Verifying ALL teams ({len(db)} teams)...")
        
        # Filter: We only verify teams that HAVE a league (filled by AI or Manual)
        teams_to_check = [t for t in db if t.get('League')]
        
        for i in range(0, len(teams_to_check), BATCH_SIZE):
            batch = teams_to_check[i : i + BATCH_SIZE]
            
            # Prepare minimal payload
            mini_batch = [{"Team": t["Team"], "League": t["League"], "Sport": t["Sport"]} for t in batch]
            
            print(f"   Scanning batch {i}-{i+len(batch)}...")
            corrections = ask_ai_verify_batch(KEY_VERIFY, mini_batch)
            time.sleep(SLEEP_TIME)
            
            if corrections:
                for fix in corrections:
                    t_name = fix.get("Team")
                    correct_league = fix.get("League")
                    
                    # Update local DB
                    if t_name in existing_map:
                        rec = existing_map[t_name]
                        # Only update if actually different
                        if rec['League'] != correct_league:
                            print(f"   ⚠️ Correction: {t_name} [{rec['League']} -> {correct_league}]")
                            rec['League'] = correct_league
                            rec['Status'] = "Modified" # Flag for Admin
                            changes_made = True

    # 4. SAVE
    if changes_made:
        with open('db.json', 'w') as f: json.dump(db, f, indent=4)
        print("\n💾 Database Saved.")
    else:
        print("\n💤 No changes required.")

if __name__ == "__main__":
    main()
