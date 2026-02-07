import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os

# --- CONFIGURATION ---
BASE_URL = "https://www.gundam-gcg.com/en/cards/index.php"
DETAIL_URL = "https://www.gundam-gcg.com/en/cards/detail.php"
IMAGE_BASE = "https://www.gundam-gcg.com/en/images/cards/card/"
HOST = "https://www.gundam-gcg.com"

# OUTPUT FILES
CARDS_FILE = "cards.json"
DECKS_FILE = "decks.json"
CONFIG_FILE = "set_config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
}

# --- INITIAL SEED ---
# "Seq" = Sequential (ST01, ST02...). "Flat" = Single List (PR, R, RP).
DEFAULT_SETS = [
    # Starters
    {"id": "ST01", "name": "Heroic Beginnings", "type": "seq", "internal_id": "616001"},
    {"id": "ST02", "name": "Wings of Advance", "type": "seq", "internal_id": "616002"},
    {"id": "ST03", "name": "Zeon's Rush", "type": "seq", "internal_id": "616003"},
    {"id": "ST04", "name": "SEED Strike", "type": "seq", "internal_id": "616004"},
    {"id": "ST05", "name": "Iron Bloom", "type": "seq", "internal_id": "616005"},
    {"id": "ST06", "name": "Clan Unity", "type": "seq", "internal_id": "616006"},
    {"id": "ST07", "name": "Turn A", "type": "seq", "internal_id": "616007"},      
    {"id": "ST08", "name": "Flash of Radiance", "type": "seq", "internal_id": "616008"},
    # Boosters
    {"id": "GD01", "name": "Legend of the MS", "type": "seq", "internal_id": "616101"},
    {"id": "GD02", "name": "Zeta of the Age", "type": "seq", "internal_id": "616102"},
    # Flat Sets (Promos, Resources)
    {"id": "PR", "name": "Promotional Cards", "type": "flat", "internal_id": ""},
    {"id": "T", "name": "Tokens", "type": "flat", "internal_id": ""},
    {"id": "EX", "name": "Extra/Basic", "type": "flat", "internal_id": ""},
    {"id": "R", "name": "Resources", "type": "flat", "internal_id": ""},
    {"id": "RP", "name": "Resource Promos", "type": "flat", "internal_id": ""}
]

def get_soup(url, params=None):
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        return BeautifulSoup(response.content, 'html.parser')
    except: return None

def load_known_sets():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return DEFAULT_SETS

def save_known_sets(sets):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(sets, f, indent=2)

def hunt_for_new_sets(current_sets):
    """Hunts for SEQUENTIAL sets (ST09, GD03) only."""
    print("🔮 Hunting for future sets (ST, GD)...")
    
    max_counts = {"ST": 0, "GD": 0}
    for s in current_sets:
        match = re.match(r'([A-Z]+)(\d+)', s['id'])
        if match:
            prefix, num = match.groups()
            if prefix in max_counts:
                max_counts[prefix] = max(max_counts[prefix], int(num))
    
    new_found = []
    
    for prefix, current_max in max_counts.items():
        misses = 0
        check_num = current_max + 1
        while misses < 2: 
            set_code = f"{prefix}{check_num:02d}"
            card_id = f"{set_code}-001"
            print(f"   ❓ Probing {set_code} ({card_id})...", end="")
            
            soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
            if soup and soup.select_one('.cardName'):
                print(f" ✅ FOUND!")
                new_entry = {"id": set_code, "name": f"Set {set_code}", "type": "seq", "internal_id": ""}
                current_sets.append(new_entry)
                new_found.append(new_entry)
                misses = 0
            else:
                print(" ❌")
                misses += 1
            check_num += 1
            time.sleep(0.3)

    if new_found: save_known_sets(current_sets)
    return current_sets

def find_parallels(base_card_id, base_data):
    """
    Checks if parallel art exists (e.g. ST01-006_p1.webp).
    This allows the App to 'stack' alternate arts.
    """
    variants = []
    
    # Check up to 3 parallel versions (_p1, _p2, _p3)
    for p in range(1, 4):
        variant_id = f"{base_data['card_no']}_p{p}" # ID for DB (unique)
        image_name = f"{base_data['card_no']}_p{p}.webp"
        image_url = f"{IMAGE_BASE}{image_name}"
        
        try:
            # Quick HEAD request to check if image exists
            resp = requests.head(image_url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                print(f"      ✨ Found Parallel Art: {image_name}")
                
                # Clone base data but update ID/Image
                var_data = base_data.copy()
                var_data['id'] = variant_id # Unique ID for DB
                var_data['image_url'] = image_url
                var_data['rarity'] = f"{base_data['rarity']} (Alt)" # Mark as alt
                variants.append(var_data)
            else:
                break # Stop if _p1 doesn't exist, _p2 likely won't either
        except:
            break
            
    return variants

def scrape_list_view(set_meta):
    """Fast scrape via filter list."""
    if not set_meta.get('internal_id'): return [] 

    print(f"   Trying List View for {set_meta['id']}...")
    soup = get_soup(BASE_URL, {'search': 'true', 'product': set_meta['internal_id'], 'view': 'text'})
    
    if not soup or (not soup.select('.cardList') and not soup.select('.list')):
        soup = get_soup(BASE_URL, {'search': 'true', 'series': set_meta['internal_id'], 'view': 'text'})

    if not soup: return []

    cards = []
    rows = soup.select('.cardList .list li') or soup.select('.cardList .item')
    
    for row in rows:
        try:
            no = row.select_one('.number, .cardNo').get_text(strip=True)
            nm = row.select_one('.cardName, .name').get_text(strip=True)
            img_tag = row.select_one('img')
            img = img_tag.get('src') if img_tag else ""
            if img.startswith('..'): img = HOST + img.replace('..', '')
            
            qty = 4 
            if "LEADER" in row.get_text().upper(): qty = 1
            if "TOKEN" in row.get_text().upper(): qty = 1
            
            cards.append({"card_no": no, "name": nm, "quantity": qty, "image_url": img})
        except: continue
        
    return cards

def brute_force_cards(set_meta):
    """Fallback: Check SetID-001...999 individually"""
    set_id = set_meta['id']
    is_flat = set_meta.get('type') == 'flat'
    
    print(f"   🔨 Brute-forcing {set_id} ({'Flat' if is_flat else 'Seq'})...")
    cards = []
    misses = 0
    
    # Range limit
    limit = 60 if is_flat else 120 
    if set_id.startswith("ST"): limit = 30 
    
    for i in range(1, limit + 1): 
        # ID Formatting (R-001 vs ST01-001)
        card_id = f"{set_id}-{i:03d}"

        soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
        
        if not soup or not soup.select_one('.cardName'):
            misses += 1
            if misses >= 5: break 
            continue
            
        name = soup.select_one('.cardName').get_text(strip=True)
        
        img_tag = soup.select_one('.cardImg img')
        img = img_tag.get('src') if img_tag else ""
        if img.startswith('..'): img = HOST + img.replace('..', '')
        
        # Stats parsing
        stats = {}
        for dt in soup.find_all("dt"):
            val = dt.find_next_sibling("dd").text.strip()
            stats[dt.text.strip().lower()] = val
            
        qty = 4
        if "LEADER" in stats.get("card type", "").upper(): qty = 1
        
        card_obj = {
            "card_no": card_id, "name": name, "quantity": qty, "image_url": img,
            "details": stats
        }
        
        cards.append(card_obj)
        
        # --- AUTO-DETECT PARALLEL ART ---
        # If Brute Force found the base card, check for _p1 variants
        parallels = find_parallels(card_id, {
            "card_no": card_id,
            "name": name,
            "image_url": img,
            "rarity": stats.get('rarity', 'C'),
            "details": stats
        })
        cards.extend(parallels) # Add parallels to the list
        
        misses = 0 
        time.sleep(0.1)
        
    return cards

def main():
    # 1. LOAD & HUNT
    known_sets = load_known_sets()
    all_sets = hunt_for_new_sets(known_sets) 
    
    decks_out = {}
    cards_out = {}

    # 2. SCRAPE
    for s in all_sets:
        print(f"\n📥 Processing {s['id']} ({s['name']})...")
        
        # A. List View (Fast - gets Base cards)
        cards = scrape_list_view(s)
        
        # If List View worked, we still need to check parallels for each card found
        if cards:
            print("   🔍 Checking for Parallel Art variants on found cards...")
            all_with_vars = []
            for c in cards:
                all_with_vars.append(c)
                # Create a temp 'details' obj for find_parallels
                base_data = {
                    "card_no": c['card_no'],
                    "rarity": "C", # Default if unknown from list view
                    "details": {}
                }
                # Check variants
                vars = find_parallels(c['card_no'], base_data)
                all_with_vars.extend(vars)
            cards = all_with_vars

        # B. Brute Force (Slow - Fallback, includes parallel check internally)
        if not cards:
            cards = brute_force_cards(s)
            
        if cards:
            # decks.json (Only include Base cards, not parallels, for starter lists)
            base_cards = [c for c in cards if "_p" not in c.get('id', '')]
            decks_out[s['id']] = {
                "name": s['name'],
                "cards": [{"card_no": c['card_no'], "quantity": c['quantity']} for c in base_cards]
            }
            
            # cards.json (Include EVERYTHING: Base + Parallels)
            for c in cards:
                # Use ID if present (variants), else card_no
                uid = c.get('id', c['card_no'])
                
                if uid not in cards_out:
                    d = c.get('details', {})
                    cards_out[uid] = {
                        "id": uid, # Unique ID (e.g. ST01-006_p1)
                        "card_no": c['card_no'], # Shared ID (e.g. ST01-006) for stacking
                        "name": c['name'], 
                        "image_url": c['image_url'],
                        "cost": int(re.sub(r'\D', '', d.get('cost', '0')) or 0),
                        "hp": int(re.sub(r'\D', '', d.get('hp', '0')) or 0),
                        "color": d.get('color', 'N/A'),
                        "type": d.get('card type', 'UNIT'),
                        "rarity": c.get('rarity', d.get('rarity', 'C')),
                        "trait": d.get('trait', ''),
                        "effect_text": d.get('text', ''),
                        "set": s['id']
                    }
            print(f"   ✅ Saved {len(cards)} cards (inc. variants).")
        else:
            print(f"   ❌ Failed to find cards for {s['id']}")

    # 3. SAVE
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(decks_out, f, indent=2)
    print(f"\n💾 Saved {len(decks_out)} sets to {DECKS_FILE}")

    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cards_out.values()), f, indent=2)
    print(f"💾 Saved {len(cards_out)} cards to {CARDS_FILE}")

if __name__ == "__main__":
    main()
