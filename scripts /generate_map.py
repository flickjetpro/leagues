import os
import json
import requests
from difflib import get_close_matches

# CONFIG
BACKEND_URL = "https://vercelapi-olive.vercel.app/api/sync-nodes?country=us"
DIRS = {
    'tsdb': 'assets/logos/tsdb',
    'streamed': 'assets/logos/streamed'
}
OUTPUT_FILE = 'assets/data/image_map.json'

def normalize(name):
    if not name: return ""
    return "".join([c for c in name.lower() if c.isalnum()])

def main():
    # 1. Load Local Files
    logos = {} # { "slug": "full_path" }
    
    # Load TSDB first (Highest Priority)
    if os.path.exists(DIRS['tsdb']):
        for f in os.listdir(DIRS['tsdb']):
            if f.endswith('.webp'):
                logos[f.replace('.webp', '')] = f"/{DIRS['tsdb']}/{f}"

    # Load Streamed second (Gap fillers)
    if os.path.exists(DIRS['streamed']):
        for f in os.listdir(DIRS['streamed']):
            if f.endswith('.webp'):
                slug = f.replace('.webp', '')
                if slug not in logos: # Don't overwrite TSDB
                    logos[slug] = f"/{DIRS['streamed']}/{f}"

    print(f"--- Map Generator: Found {len(logos)} unique logos ---")

    # 2. Fetch Backend
    try:
        data = requests.get(BACKEND_URL).json()
        matches = data.get('matches', [])
    except:
        return

    # 3. Create Map
    team_map = {}
    available_slugs = list(logos.keys())

    for m in matches:
        for t_key in ['team_a', 'team_b']:
            team_name = m.get(t_key)
            if not team_name: continue
            
            # Target Slug
            target_slug = "".join([c for c in team_name.lower() if c.isalnum() or c == '-']).strip('-')
            
            match_found = None
            
            # 1. Exact Check
            if target_slug in logos:
                match_found = logos[target_slug]
            
            # 2. Fuzzy Check (High confidence only)
            else:
                norm_search = normalize(team_name)
                matches_fuzzy = get_close_matches(norm_search, available_slugs, n=1, cutoff=0.7)
                if matches_fuzzy:
                    match_found = logos[matches_fuzzy[0]]

            if match_found:
                team_map[team_name] = match_found

    # 4. Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Format for Frontend: { "teams": { "Arsenal": "/path/to/logo.webp" } }
    final_json = { "teams": team_map }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_json, f, indent=2)
        
    print(f"--- Map Saved with {len(team_map)} teams ---")

if __name__ == "__main__":
    main()
