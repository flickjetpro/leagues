import json
import requests
from google import genai 
import time
import re

# --- CONFIGURATION ---
FILL_LIMIT = 50       # How many blank teams to fill per hour
BATCH_SIZE = 30       # How many teams to verify at once
SLEEP_TIME = 5        # 5 Seconds delay = Safe for Free Tier (Avoids 429 Errors)

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

# --- BROWSER HEADERS (Spoofing a Real User) ---
# This makes Vercel think we are a real Chrome browser, preventing the 7-minute delay.
FAKE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive"
}

# --- AI HELPERS ---
def ask_ai_fill(api_key, team, sport):
    if not api_key: return "Error"
    try:
        client = genai.Client(api_key=api_key)
        prompt = PROMPT_FILL.replace("{team}", str(team)).replace("{sport}", str(sport))
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        # print(f"AI Error: {e}") 
        return "Error"

def ask_ai_verify_batch(api_key, batch_data):
    if not api_key: return []
    try:
        client = genai.Client(api_key=api_key)
        prompt = PROMPT_VERIFY.replace("{batch_data}", json.dumps(batch_data))
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        text = response.text.strip()
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
    
    existing_map = {item['Team']: item for item in db}
    changes_made = False

    # ======================================================
    # PHASE 1: SYNC (Extract Backend -> DB)
    # ======================================================
    print("🌍 Phase 1: Syncing from Backend...")
    try:
        # UPDATED REQUEST: Added Headers and Timeout
        resp = requests.get(BACKEND_URL, headers=FAKE_HEADERS, timeout=30)
        resp.raise_for_status() # Check for HTTP errors
        matches = resp.json().get('matches', [])
    except Exception as e:
        print(f"❌ Backend Error (Check URL or Vercel Status): {e}")
        matches = []

    for m in matches:
        sport = m.get('sport') or "Unknown"
        for role in ['team_a', 'team_b']:
            t_name = m.get(role)
            # Only add if name exists and isn't in DB
            if t_name and t_name not in existing_map:
                print(f"   🆕 Found new team: {t_name}")
                new_entry = {
                    "Team": t_name,
                    "Sport": sport,
                    "League": "",       # BLANK intentionally
                    "Status": "Pending" 
                }
                db.append(new_entry)
                existing_map[t_name] = new_entry
                changes_made = True

    # ======================================================
    # PHASE 2: FILL BLANKS (AI #1)
    # ======================================================
    print(f"\n🤖 Phase 2: Filling Empty Leagues (Limit: {FILL_LIMIT})...")
    
    unfilled_teams = [t for t in db if not t.get('League')]
    
    fill_count = 0
    for team in unfilled_teams:
        if fill_count >= FILL_LIMIT:
            break
        
        if not KEY_FILL:
            print("   ⚠️ No Extraction Key found. Skipping Phase 2.")
            break

        print(f"   ✏️ Filling: {team['Team']}")
        result = ask_ai_fill(KEY_FILL, team['Team'], team['Sport'])
        
        # SLOW DOWN to avoid Google Rate Limits
        time.sleep(SLEEP_TIME)
        
        if result and result != "Error":
            team['League'] = result
            team['Status'] = "AI_Filled"
            changes_made = True
            fill_count += 1
    
    if fill_count == 0:
        print("   ✅ No blank teams found (or limit reached/key error).")

    # ======================================================
    # PHASE 3: VERIFY ALL (AI #2)
    # ======================================================
    if config.get("enable_verification"):
        print(f"\n🕵️ Phase 3: Verifying ALL teams ({len(db)} teams)...")
        
        teams_to_check = [t for t in db if t.get('League')]
        
        for i in range(0, len(teams_to_check), BATCH_SIZE):
            if not KEY_VERIFY:
                 print("   ⚠️ No Verification Key found. Skipping Phase 3.")
                 break

            batch = teams_to_check[i : i + BATCH_SIZE]
            mini_batch = [{"Team": t["Team"], "League": t["League"], "Sport": t["Sport"]} for t in batch]
            
            print(f"   Scanning batch {i}-{i+len(batch)}...")
            corrections = ask_ai_verify_batch(KEY_VERIFY, mini_batch)
            
            # SLOW DOWN batch requests too
            time.sleep(SLEEP_TIME)
            
            if corrections:
                for fix in corrections:
                    t_name = fix.get("Team")
                    correct_league = fix.get("League")
                    
                    if t_name in existing_map:
                        rec = existing_map[t_name]
                        if rec['League'] != correct_league:
                            print(f"   ⚠️ Correction: {t_name} [{rec['League']} -> {correct_league}]")
                            rec['League'] = correct_league
                            rec['Status'] = "Modified"
                            changes_made = True

    # 4. SAVE
    if changes_made:
        with open('db.json', 'w') as f: json.dump(db, f, indent=4)
        print("\n💾 Database Saved.")
    else:
        print("\n💤 No changes required.")

if __name__ == "__main__":
    main()
