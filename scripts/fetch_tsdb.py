import os
import requests
import urllib.parse
import re
import time
import json
from PIL import Image
from io import BytesIO

# ==========================================
# 1. CONFIGURATION
# ==========================================
API_KEY = "123"
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"
SAVE_DIR = "assets/logos/tsdb"
LEAGUE_MAP_FILE = "assets/data/league_map.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

# Supported Leagues
LEAGUES = {
    "English Premier League": "English Premier League",
    "English League Championship": "English League Championship",
    "Scottish Premiership": "Scottish Premiership",
    "Spanish La Liga": "Spanish La Liga",
    "German Bundesliga": "German Bundesliga",
    "Italian Serie A": "Italian Serie A",
    "French Ligue 1": "French Ligue 1",
    "Dutch Eredivisie": "Dutch Eredivisie",
    "Portuguese Primeira Liga": "Portuguese Primeira Liga",
    "UEFA Champions League": "UEFA Champions League",
    "UEFA Europa League": "UEFA Europa League",
    "American Major League Soccer": "American Major League Soccer",
    "Saudi Pro League": "Saudi Arabian Pro League",
    "Belgian Pro League": "Belgian Pro League",
    "NBA": "NBA",
    "NFL": "NFL",
    "NHL": "NHL",
    "MLB": "MLB",
    "F1": "Formula 1",
    "UFC": "UFC",
    "Australian Big Bash League": "Australian Big Bash League",
    "United Rugby Championship": "United Rugby Championship"
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
            
            # 1. Convert to RGBA (Preserve Transparency)
            if img.mode != 'RGBA': 
                img = img.convert('RGBA')
            
            # 2. High Quality Resize to 60x60
            img = img.resize((60, 60), Image.Resampling.LANCZOS)
            
            # 3. Save as WebP (Optimized)
            img.save(save_path, "WEBP", quality=90, method=6)
            return True
    except: 
        pass
    return False

# ==========================================
# 3. MAIN EXECUTION
# ==========================================
def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    # 1. Create folder for data and Initialize Map
    os.makedirs(os.path.dirname(LEAGUE_MAP_FILE), exist_ok=True)
    league_map = {} 

    print("--- Starting TSDB Harvester (60x60 Optimized) ---")

    for display_name, tsdb_name in LEAGUES.items():
        print(f" > Checking: {display_name}")
        encoded = urllib.parse.quote(tsdb_name)
        url = f"{BASE_URL}/search_all_teams.php?l={encoded}"
        
        try:
            data = requests.get(url, headers=HEADERS, timeout=10).json()
            if data and data.get('teams'):
                count = 0
                for t in data['teams']:
                    name = t.get('strTeam')
                    
                    # 2. Map Team to League
                    if name:
                        team_key = slugify(name)
                        if team_key:
                            league_map[team_key] = display_name

                    # 3. Process Images
                    badge = t.get('strTeamBadge') or t.get('strBadge')
                    
                    if name and badge:
                        slug = slugify(name)
                        path = os.path.join(SAVE_DIR, f"{slug}.webp")
                        if save_image_optimized(badge, path):
                            count += 1
                
                if count > 0: print(f"   [+] Saved {count} new logos.")
            else:
                print(f"   [-] No teams found.")
                
        except Exception as e:
            print(f"   [!] Error: {e}")
        
        time.sleep(1.5) # Rate limit safety

    # 4. Save the Map (OUTSIDE the loop)
    with open(LEAGUE_MAP_FILE, 'w') as f:
        json.dump(league_map, f, indent=2)
    
    print(f"--- League Map Saved ({len(league_map)} teams) ---")

if __name__ == "__main__":
    main()
