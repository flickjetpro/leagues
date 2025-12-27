import json
import requests
import os
import time
import re
from google import genai

# ==========================================
# 1. CONFIGURATION
# ==========================================
FILL_LIMIT = 50       # Max teams to fill per hour
BATCH_SIZE = 30       # Verification batch size
SLEEP_TIME = 5        # 5s delay to satisfy Free Tier limits

# Paths
SETTINGS_FILE = 'settings.json'
DB_FILE = 'db.json'
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes"

# SPOOF HEADERS (Fixes Phase 1 Stuck Issue)
FAKE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

# ==========================================
# 2. SETUP & KEYS
# ==========================================
# Load Settings (Prompts only now)
try:
    with open(SETTINGS_FILE, 'r') as f: config = json.load(f)
except:
    config = {}

# Load Keys from GitHub Secrets (Environment Variables)
KEY_FILL = os.environ.get("GEMINI_KEY_EXTRACTION")
KEY_VERIFY = os.environ.get("GEMINI_KEY_VERIFICATION")

PROMPT_FILL = config.get("extraction_prompt", "")
PROMPT_VERIFY = config.get("verification_prompt", "")
ENABLE_VERIFY = config.get("enable_verification", False)

# ==========================================
# 3. AI HELPERS
# ==========================================
def ask_ai_fill(team, sport):
    if not KEY_FILL: return "Error"
    try:
        client = genai.Client(api_key=KEY_FILL)
        prompt = PROMPT_FILL.replace("{team}", str(team)).replace("{sport}", str(sport))
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        return "Error"

def ask_ai_verify_batch(batch_data):
    if not KEY_VERIFY: return []
    try:
        client = genai.Client(api_key=KEY_VERIFY)
        prompt = PROMPT_VERIFY.replace("{batch_data}", json.dumps(batch_data))
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```json|^```|```$", "", text, flags=re.MULTILINE).strip()
        return json.loads(text)
    except Exception:
        return []

# ==========================================
# 4. MAIN LOGIC
# ==========================================
def main():
    # Load DB
    try:
        with open(DB_FILE, 'r') as f: db = json.load(f)
    except: db = []
    
    existing_map = {item['Team']: item for item in db}
    changes_made = False

    # --------------------------------------
    # PHASE 1: SYNC (Backend -> DB)
    # --------------------------------------
    print("🌍 Phase 1: Syncing from Backend...")
    try:
        # TIMEOUT + HEADERS ADDED HERE
        resp = requests.get(BACKEND_URL, headers=FAKE_HEADERS, timeout=30)
        resp.raise_for_status()
        matches = resp.json().get('matches', [])
    except Exception as e:
        print(f"❌ Backend Error: {e}")
        matches = []

    for m in matches:
        sport = m.get('sport') or "Unknown"
        for role in ['team_a', 'team_b']:
            t_name = m.get(role)
            if t_name and t_name not in existing_map:
                print(f"   🆕 Found: {t_name}")
                new_entry = {
                    "Team": t_name, 
                    "Sport": sport, 
                    "League": "", 
                    "Status": "Pending"
                }
                db.append(new_entry)
                existing_map[t_name] = new_entry
                changes_made = True

    # --------------------------------------
    # PHASE 2: FILL BLANKS (AI #1)
    # --------------------------------------
    print(f"\n🤖 Phase 2: Filling Blanks (Limit: {FILL_LIMIT})...")
    if not KEY_FILL:
        print("   ⚠️ No Extraction Key in Secrets. Skipping.")
    else:
        unfilled = [t for t in db if not t.get('League')]
        count = 0
        for t in unfilled:
            if count >= FILL_LIMIT: break
            
            print(f"   ✏️ Filling: {t['Team']}")
            res = ask_ai_fill(t['Team'], t['Sport'])
            time.sleep(SLEEP_TIME)
            
            if res and res != "Error":
                t['League'] = res
                t['Status'] = "AI_Filled"
                changes_made = True
                count += 1
        if count == 0: print("   ✅ No actions needed.")

    # --------------------------------------
    # PHASE 3: VERIFY (AI #2)
    # --------------------------------------
    if ENABLE_VERIFY and KEY_VERIFY:
        print(f"\n🕵️ Phase 3: Verifying ({len(db)} teams)...")
        # Check teams that HAVE a league
        to_check = [t for t in db if t.get('League')]
        
        for i in range(0, len(to_check), BATCH_SIZE):
            batch = to_check[i : i + BATCH_SIZE]
            mini_batch = [{"Team": x["Team"], "League": x["League"], "Sport": x["Sport"]} for x in batch]
            
            print(f"   Batch {i}-{i+len(batch)}...")
            corrections = ask_ai_verify_batch(mini_batch)
            time.sleep(SLEEP_TIME)
            
            if corrections:
                for fix in corrections:
                    t_name = fix.get("Team")
                    correct_league = fix.get("League")
                    if t_name in existing_map:
                        rec = existing_map[t_name]
                        if rec['League'] != correct_league:
                            print(f"   ⚠️ Correction: {t_name} -> {correct_league}")
                            rec['League'] = correct_league
                            rec['Status'] = "Modified"
                            changes_made = True
    elif ENABLE_VERIFY and not KEY_VERIFY:
        print("\n🕵️ Phase 3 Skipped (No Verification Key)")

    # --------------------------------------
    # SAVE
    # --------------------------------------
    if changes_made:
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)
        print("\n💾 Saved.")
    else:
        print("\n💤 No changes.")

if __name__ == "__main__":
    main()
