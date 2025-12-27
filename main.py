import json
import requests
from google import genai
import time
import re
import os

# ==========================================================
# CONFIGURATION
# ==========================================================
FILL_LIMIT = 50
BATCH_SIZE = 30
SLEEP_TIME = 5

# IMPORTANT: use the FAST backend path
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes?country=us"
BACKEND_TIMEOUT = 15  # HARD STOP (never hang)

# ==========================================================
# LOAD SETTINGS
# ==========================================================
try:
    with open("settings.json", "r") as f:
        config = json.load(f)
except Exception:
    print("❌ settings.json not found")
    exit(1)

KEY_FILL = config.get("extraction_key")
KEY_VERIFY = config.get("verification_key")
PROMPT_FILL = config.get("extraction_prompt")
PROMPT_VERIFY = config.get("verification_prompt")
ENABLE_VERIFICATION = config.get("enable_verification", False)

# ==========================================================
# HEADERS
# ==========================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json"
}

# ==========================================================
# GEMINI CLIENTS (CREATE ONCE)
# ==========================================================
FILL_CLIENT = genai.Client(api_key=KEY_FILL) if KEY_FILL else None
VERIFY_CLIENT = genai.Client(api_key=KEY_VERIFY) if KEY_VERIFY else None

# ==========================================================
# UTILS
# ==========================================================
def norm(name):
    return name.strip().lower() if name else ""

def safe_json_extract(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except Exception:
        return []

# ==========================================================
# AI HELPERS
# ==========================================================
def ask_ai_fill(team, sport):
    if not FILL_CLIENT:
        return None
    try:
        prompt = PROMPT_FILL.format(team=team, sport=sport)
        r = FILL_CLIENT.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return r.text.strip()
    except Exception:
        return None

def ask_ai_verify_batch(batch_data):
    if not VERIFY_CLIENT:
        return []
    try:
        prompt = PROMPT_VERIFY.replace("{batch_data}", json.dumps(batch_data))
        r = VERIFY_CLIENT.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return safe_json_extract(r.text)
    except Exception:
        return []

# ==========================================================
# MAIN
# ==========================================================
def main():
    # ------------------------------------------------------
    # LOAD DB
    # ------------------------------------------------------
    try:
        with open("db.json", "r") as f:
            db = json.load(f)
    except Exception:
        db = []

    existing = {norm(t["Team"]): t for t in db}
    changes_made = False

    # ------------------------------------------------------
    # PHASE 1 — FAST BACKEND SYNC (NON-BLOCKING)
    # ------------------------------------------------------
    print("🌍 Phase 1: Syncing from Backend...")
    try:
        resp = requests.get(BACKEND_URL, headers=HEADERS, timeout=BACKEND_TIMEOUT)
        resp.raise_for_status()
        matches = resp.json().get("matches", [])
    except Exception as e:
        print(f"⚠️ Backend skipped: {e}")
        matches = []

    for m in matches:
        sport = m.get("sport") or "Unknown"
        for key in ("team_a", "team_b"):
            name = m.get(key)
            n = norm(name)
            if name and n not in existing:
                print(f"   🆕 New team: {name}")
                rec = {
                    "Team": name,
                    "Sport": sport,
                    "League": "",
                    "Status": "Pending"
                }
                db.append(rec)
                existing[n] = rec
                changes_made = True

    # ------------------------------------------------------
    # PHASE 2 — FILL LEAGUES
    # ------------------------------------------------------
    print(f"\n🤖 Phase 2: Filling leagues (limit {FILL_LIMIT})")
    filled = 0

    for t in db:
        if filled >= FILL_LIMIT:
            break
        if t["League"]:
            continue
        if not KEY_FILL:
            break

        print(f"   ✏️ {t['Team']}")
        league = ask_ai_fill(t["Team"], t["Sport"])
        time.sleep(SLEEP_TIME)

        if league:
            t["League"] = league
            t["Status"] = "AI_Filled"
            filled += 1
            changes_made = True

    if filled == 0:
        print("   ✅ Nothing to fill")

    # ------------------------------------------------------
    # PHASE 3 — VERIFY (SKIP UNKNOWN)
    # ------------------------------------------------------
    if ENABLE_VERIFICATION and KEY_VERIFY:
        print(f"\n🕵️ Phase 3: Verification")
        to_check = [
            t for t in db
            if t["League"] and t["League"] != "Unknown"
        ]

        for i in range(0, len(to_check), BATCH_SIZE):
            batch = to_check[i:i + BATCH_SIZE]
            payload = [
                {"Team": t["Team"], "League": t["League"], "Sport": t["Sport"]}
                for t in batch
            ]

            fixes = ask_ai_verify_batch(payload)
            time.sleep(SLEEP_TIME)

            for f in fixes:
                n = norm(f.get("Team"))
                if n in existing:
                    rec = existing[n]
                    if rec["League"] != f["League"]:
                        print(f"   ⚠️ Fix: {rec['Team']} → {f['League']}")
                        rec["League"] = f["League"]
                        rec["Status"] = "Verified_Modified"
                        changes_made = True

    # ------------------------------------------------------
    # SAVE
    # ------------------------------------------------------
    if changes_made:
        with open("db.json", "w") as f:
            json.dump(db, f, indent=4)
        print("\n💾 Database updated")
    else:
        print("\n💤 No changes")

if __name__ == "__main__":
    main()
