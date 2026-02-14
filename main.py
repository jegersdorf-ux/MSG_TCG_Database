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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- 🛡️ SOURCE OF TRUTH: VERIFIED QUANTITIES ---
STARTER_COUNTS = {
    "ST01": {
        "ST01-001": 2, "ST01-006": 2, "ST01-014": 2, 
        "ST01-004": 3, "ST01-005": 3, "ST01-008": 3, "ST01-009": 3, "ST01-012": 3, "ST01-013": 3, "ST01-015": 3, "ST01-016": 3
    },
    "ST02": {
        "ST02-001": 2, "ST02-006": 2, "ST02-014": 2,
        "ST02-004": 3, "ST02-005": 3, "ST02-008": 3, "ST02-009": 3, "ST02-012": 3, "ST02-013": 3, "ST02-015": 3, "ST02-016": 3
    },
    "ST03": {
        "ST03-001": 2, "ST03-006": 2, "ST03-014": 2,
        "ST03-004": 3, "ST03-005": 3, "ST03-007": 3, "ST03-009": 3, "ST03-012": 3, "ST03-013": 3, "ST03-015": 3, "ST03-016": 3
    },
    "ST04": {
        "ST04-001": 2, "ST04-006": 2, "ST04-014": 2,
        "ST04-004": 3, "ST04-005": 3, "ST04-008": 3, "ST04-009": 3, "ST04-012": 3, "ST04-013": 3, "ST04-015": 3, "ST04-016": 3
    },
    "ST05": {
        "ST05-001": 2, "ST05-005": 2, "ST05-014": 2,
        "ST05-004": 3, "ST05-007": 3, "ST05-008": 3, "ST05-011": 3, "ST05-012": 3, "ST05-013": 3, "ST05-015": 3
    },
    "ST06": {
        "ST06-001": 2, "ST06-006": 2, "ST06-013": 2,
        "ST06-003": 3, "ST06-004": 3, "ST06-008": 3, "ST06-009": 3, "ST06-012": 3, "ST06-014": 3, "ST06-015": 3
    },
    "ST07": {
        "ST07-001": 2, "ST07-005": 2, "ST07-013": 2,
        "ST07-003": 3, "ST07-004": 3, "ST07-008": 3, "ST07-009": 3, "ST07-012": 3, "ST07-014": 3, "ST07-015": 3
    },
    "ST08": {
        "ST08-001": 2, "ST08-006": 2, "ST08-012": 2,
        "ST08-003": 3, "ST08-004": 3, "ST08-008": 3, "ST08-009": 3, "ST08-011": 3, "ST08-013": 3, "ST08-014": 3, "ST08-015": 3
    }
}

# --- INITIAL SEED ---
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
    {"id": "GD03", "name": "Steel Requiem", "type": "seq", "internal_id": "616103"},
    # Flat Sets
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
    except Exception as e: 
        print(f"Error fetching {url}: {e}")
        return None

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
        check_num = current_max + 1
        for i in range(3): 
            set_code = f"{prefix}{check_num:02d}"
            card_id = f"{set_code}-001"
            print(f"   ❓ Probing {set_code} ({card_id})...", end="")
            
            soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
            if soup and soup.select_one('.cardName'):
                print(f" ✅ FOUND!")
                new_entry = {"id": set_code, "name": f"Set {set_code}", "type": "seq", "internal_id": ""}
                current_sets.append(new_entry)
                new_found.append(new_entry)
            else:
                print(" ❌")
                break 
            check_num += 1
            time.sleep(0.3)

    if new_found: save_known_sets(current_sets)
    return current_sets

def extract_rarities(rarity_text):
    """Splits rarity string into a clean list."""
    if not rarity_text: return ["-"]
    parts = re.split(r'[・/,\.\|\u30FB]', rarity_text) 
    return [p.strip() for p in parts if p.strip()]

def scrape_details(card_id):
    """
    Fetches stats with smart Key Mapping and FAQ extraction.
    Matches the logic used in the successful JS console test.
    """
    soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
    if not soup: return {}
    
    stats = {}
    faq_list = []
    
    # --- KEY MAPPER ---
    # Maps raw site labels to clean JSON keys
    KEY_MAP = {
        "cost": "cost",
        "hp": "hp",
        "ap": "ap",
        "color": "color",
        "type": "type",
        "card type": "type",
        "trait": "trait",
        "link": "link",
        "zone": "zone",
        "lv.": "level",
        "source title": "source",
        "where to get it": "product_name"
    }

    # 1. Scrape all DT/DD pairs
    for dt in soup.find_all("dt"):
        raw_label = dt.get_text(strip=True).lower()
        
        dd = dt.find_next_sibling("dd")
        val = dd.get_text(strip=True) if dd else ""
        
        # LOGIC: Is it a Stat or an FAQ?
        if raw_label in KEY_MAP:
            # It is a known stat
            stats[KEY_MAP[raw_label]] = val
        elif raw_label:
            # It is NOT a known stat -> Treat as FAQ Question
            # Storing as {Question, Answer} pair
            faq_list.append({
                "question": dt.get_text(strip=True),
                "answer": val
            })
            
    # 2. Scrape Rarity (Explicit Selector)
    rarity_tag = soup.select_one(".rarity")
    if rarity_tag:
        raw_rarity = rarity_tag.get_text(strip=True)
        stats['rarity_raw'] = raw_rarity
        stats['rarity_list'] = extract_rarities(raw_rarity)
        stats['rarity'] = stats['rarity_list'][0]
    else:
        stats['rarity'] = stats.get('rarity', 'C')
        stats['rarity_list'] = [stats['rarity']]

    # 3. Scrape Effect Text (Explicit Selector)
    text_tag = soup.select_one(".cardDataRow.overview .dataTxt")
    if text_tag:
        # get_text with separator handles <br> tags as newlines
        stats['text'] = text_tag.get_text("\n").strip()
    else:
        stats['text'] = ""

    # 4. Attach FAQ
    stats['faq'] = faq_list

    return stats

def find_parallels(base_card_id, base_data):
    variants = []
    rarity_list = base_data.get('details', {}).get('rarity_list', [])
    
    for p in range(1, 5):
        variant_id = f"{base_data['card_no']}_p{p}"
        image_name = f"{base_data['card_no']}_p{p}.webp"
        image_url = f"{IMAGE_BASE}{image_name}"
        
        try:
            resp = requests.head(image_url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                print(f"      ✨ Found Parallel: {variant_id}")
                var_data = base_data.copy()
                var_data['id'] = variant_id
                var_data['image_url'] = image_url
                
                if p < len(rarity_list):
                    var_data['rarity'] = rarity_list[p]
                else:
                    var_data['rarity'] = f"{rarity_list[-1]} (Alt)"
                    
                variants.append(var_data)
            else:
                break
        except: break
    return variants

def process_set(set_meta):
    set_id = set_meta['id']
    print(f"\n📥 Processing {set_id} ({set_meta['name']})...")
    
    cards = []
    
    # 1. Try List View first
    if set_meta.get('internal_id'):
        print(f"   Using List View...")
        soup = get_soup(BASE_URL, {'search': 'true', 'product': set_meta['internal_id'], 'view': 'text'})
        if soup:
            rows = soup.select('.cardList .list li') or soup.select('.cardList .item')
            for row in rows:
                try:
                    no = row.select_one('.number, .cardNo').get_text(strip=True)
                    nm = row.select_one('.cardName, .name').get_text(strip=True)
                    
                    # --- FIX: Construct URL manually instead of scraping broken relative paths ---
                    img = f"{IMAGE_BASE}{no}.webp"
                    
                    cards.append({"card_no": no, "name": nm, "image_url": img})
                except: continue

    # 2. Brute Force Fallback
    if not cards:
        print(f"   ⚠️ List view failed. Brute-forcing...")
        limit = 30 if set_id.startswith("ST") else 120
        for i in range(1, limit + 1):
            try:
                card_id = f"{set_id}-{i:03d}"
                soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
                if soup and soup.select_one('.cardName'):
                    nm = soup.select_one('.cardName').get_text(strip=True)
                    
                    # --- FIX: Construct URL manually ---
                    img = f"{IMAGE_BASE}{card_id}.webp"
                    
                    cards.append({"card_no": card_id, "name": nm, "image_url": img})
                time.sleep(0.1)
            except: continue

    # 3. Enrich Data
    final_cards = []
    print(f"   🔍 Enriching {len(cards)} cards...")
    
    for c in cards:
        details = scrape_details(c['card_no'])
        c['details'] = details
        c['rarity'] = details.get('rarity', 'C').strip()
        c['type'] = details.get("type", "UNIT").strip().upper()
        
        # Quantity Logic
        qty = 4 
        if "LEADER" in c['type'] or "TOKEN" in c['type']: 
            qty = 1
        elif set_id in STARTER_COUNTS and c['card_no'] in STARTER_COUNTS[set_id]:
            qty = STARTER_COUNTS[set_id][c['card_no']]
        elif set_id.startswith("ST") and set_id not in STARTER_COUNTS:
            rarity_clean = c['rarity'].replace('+', '').upper()
            if rarity_clean in ['SR', 'R']:
                qty = 2
        
        c['quantity'] = qty
        final_cards.append(c)
        
        # Parallels
        vars = find_parallels(c['card_no'], c)
        final_cards.extend(vars)
        time.sleep(0.1) 

    return final_cards

def main():
    known_sets = load_known_sets()
    all_sets = hunt_for_new_sets(known_sets)
    
    decks_out = {}
    cards_out = {}

    for s in all_sets:
        cards = process_set(s)
        
        if cards:
            # Build Deck Objects
            if s['id'].startswith("ST"):
                base_cards = [c for c in cards if "_p" not in c.get('id', c['card_no'])]
                decks_out[s['id']] = {
                    "name": s['name'],
                    "cards": [{"card_no": c['card_no'], "quantity": c['quantity']} for c in base_cards]
                }
            
            # Build Card Objects
            for c in cards:
                uid = c.get('id', c['card_no'])
                d = c.get('details', {})
                
                # --- HELPER: Returns Int or None (null) ---
                def safe_int(key):
                    val = d.get(key, '-')
                    # If it's a placeholder or empty, return None (null)
                    if not val or val == '-' or val == 'N/A':
                        return None
                    
                    # Clean the string (remove non-digits)
                    clean = re.sub(r'\D', '', str(val))
                    return int(clean) if clean else None

                # --- HELPER: Returns String or None (null) ---
                def safe_str(key, default='-'):
                    val = d.get(key, default)
                    if not val or val == '-' or val == 'N/A':
                        return None
                    return val.strip()

                # --- FINAL JSON MAPPING ---
                cards_out[uid] = {
                    "id": uid, 
                    "card_no": c['card_no'], 
                    "name": c['name'], 
                    "image_url": c['image_url'],
                    
                    # Integers (will be null for Tokens/Events)
                    "cost": safe_int('cost'),
                    "hp": safe_int('hp'),
                    "ap": safe_int('ap'),
                    "level": safe_int('level'),
                    
                    # Strings (will be null if "-")
                    "color": safe_str('color'),
                    "type": c['type'],
                    "rarity": c['rarity'],
                    "trait": safe_str('trait'),
                    "link": safe_str('link'),  # <--- NEW FIELD ADDED HERE
                    "effect_text": safe_str('text', ''),
                    
                    # Extended Fields
                    "zone": safe_str('zone'),
                    "source": safe_str('source'),
                    "product": safe_str('product_name'),
                    "faq": d.get('faq', []), # Keep empty array if no FAQ
                    
                    "set": s['id']
                }
    
    print(f"\n💾 Overwriting {CARDS_FILE} with fresh data...")
    print(f"   - Saved {len(decks_out)} Decks")
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(decks_out, f, indent=2)

    print(f"   - Saved {len(cards_out)} Cards")
    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cards_out.values()), f, indent=2)

if __name__ == "__main__":
    main()
