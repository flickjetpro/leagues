import os
import requests
import re
import time
from PIL import Image
from io import BytesIO

# ==========================================
# 1. CONFIGURATION
# ==========================================
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes?country=us"
STREAMED_BASE = "https://streamed.pk/api/images/badge/"

TSDB_DIR = "assets/logos/tsdb"
STREAMED_DIR = "assets/logos/streamed"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ==========================================
# 2. UTILS
# ==========================================
def slugify(name):
    if not name: return None
    clean = str(name).lower()
    clean = re.sub(r"[^\w\s-]", "", clean)
    clean = re.sub(r"\s+", "-", clean)
    return clean.strip("-")

def save_image_optimized(url, save_path):
    """
    Downloads image, Resizes to 60x60, Converts to WEBP
    """
    if os.path.exists(save_path): return False
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content))
            
            # 1. Convert to RGBA
            if img.mode != 'RGBA': 
                img = img.convert('RGBA')
            
            # 2. High Quality Resize to 60x60
            img = img.resize((60, 60), Image.Resampling.LANCZOS)
            
            # 3. Save as WebP
            img.save(save_path, "WEBP", quality=90, method=6)
            return True
    except: 
        pass
    return False

# ==========================================
# 3. MAIN EXECUTION
# ==========================================
def main():
    os.makedirs(STREAMED_DIR, exist_ok=True)
    print("--- Starting Gap-Filler Harvester (60x60 Optimized) ---")
    
    try:
        data = requests.get(BACKEND_URL, headers=HEADERS).json()
        matches = data.get('matches', [])
    except:
        print("CRITICAL: Backend unavailable")
        return

    # Gather needed teams
    tasks = {}
    for m in matches:
        if m.get('team_a') and m.get('team_a_logo'):
            tasks[m['team_a']] = m['team_a_logo']
        if m.get('team_b') and m.get('team_b_logo'):
            tasks[m['team_b']] = m['team_b_logo']

    count = 0
    for team_name, badge_id in tasks.items():
        slug = slugify(team_name)
        if not slug: continue

        # 1. CHECK TSDB (Priority 1) - If we have high quality logo, skip.
        tsdb_path = os.path.join(TSDB_DIR, f"{slug}.webp")
        if os.path.exists(tsdb_path):
            continue 

        # 2. CHECK STREAMED (Priority 2) - If we already saved it, skip.
        streamed_path = os.path.join(STREAMED_DIR, f"{slug}.webp")
        if os.path.exists(streamed_path):
            continue

        # 3. DOWNLOAD & RESIZE
        if "http" in badge_id:
            src_url = badge_id
        else:
            src_url = f"{STREAMED_BASE}{badge_id}.webp"
            
        if save_image_optimized(src_url, streamed_path):
            print(f"   [+] Filled Gap: {slug}.webp")
            count += 1
            time.sleep(0.2)

    print(f"--- Done. Filled {count} missing logos. ---")

if __name__ == "__main__":
    main()
