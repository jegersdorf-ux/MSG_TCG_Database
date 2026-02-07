import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re

# --- CONFIGURATION ---
FULL_CHECK = False 
MAX_MISSES = 3 

# Output Files
JSON_FILE = "cards.json"
DECKS_FILE = "decks.json" # This will now be the "Friendly" file

# URLs
DETAIL_URL_TEMPLATE = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch={}"
IMAGE_URL_TEMPLATE = "https://www.gundam-gcg.com/en/images/cards/card/{}.webp" 
PRODUCT_URL_TEMPLATE = "https://www.gundam-gcg.com/en/products/{}.html"
LAUNCH_NEWS_URL = "https://www.gundam-gcg.com/en/news/02_82.html"

# Prefixes
KNOWN_SET_PREFIXES = ["ST", "GD", "PR", "UT", "EXRP", "EXB", "EXR", "EXBP", "EX", "T"]

# Special Assets (Tokens, etc)
SPECIAL_ASSETS = [
    "EX01-001", "EX01-002", "EX01-003", 
    "T01-001", "T01-002",               
    "EX-001",                           
]

# Raw Seed Data (Still used for fallback)
SEED_DECKS_RAW = {
    "ST01": { "ST01-001": 2, "ST01-002": 4, "ST01-003": 4, "ST01-004": 2, "ST01-005": 4, "ST01-006": 2, "ST01-007": 4, "ST01-008": 2, "ST01-009": 4, "ST01-010": 4, "ST01-011": 4, "ST01-012": 4, "ST01-013": 2, "ST01-014": 4, "ST01-015": 2, "ST01-016": 2 },
    "ST02": { "ST02-001": 2, "ST02-002": 4, "ST02-003": 4, "ST02-004": 2, "ST02-005": 4, "ST02-006": 2, "ST02-007": 4, "ST02-008": 2, "ST02-009": 4, "ST02-010": 4, "ST02-011": 4, "ST02-012": 4, "ST02-013": 2, "ST02-014": 4, "ST02-015": 2, "ST02-016": 2 },
    "ST03": { "ST03-001": 2, "ST03-002": 4, "ST03-003": 4, "ST03-004": 4, "ST03-005": 2, "ST03-006": 2, "ST03-007": 4, "ST03-008": 4, "ST03-009": 2, "ST03-010": 4, "ST03-011": 4, "ST03-012": 4, "ST03-013": 2, "ST03-014": 4, "ST03-015": 2, "ST03-016": 2 },
    "ST04": { "ST04-001": 2, "ST04-002": 4, "ST04-003": 4, "ST04-004": 2, "ST04-005": 4, "ST04-006": 2, "ST04-007": 4, "ST04-008": 2, "ST04-009": 4, "ST04-010": 4, "ST04-011": 4, "ST04-012": 4, "ST04-013": 2, "ST04-014": 4, "ST04-015": 2, "ST04-016": 2 }
}

HEADERS = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' }

# --- UTILS ---
def safe_int(val):
    if not val: return 0
    try: return int(re.sub(r'[^\d-]', '', str(val)))
    except: return 0

def check_url_exists(url):
    try: return requests.head(url, headers=HEADERS, timeout=3).status_code == 200
    except: return False

def extract_rarities(rarity_text):
    if not rarity_text: return ["-"]
    return [p.strip() for p in re.split(r'[・/,\.\|\u30FB]', rarity_text) if p.strip()]

# --- DECK LOGIC ---

def scrape_launch_news():
    print(f"📡 Scraping Launch News for deck lists...")
    decks = {}
    try:
        resp = requests.get(LAUNCH_NEWS_URL, headers=HEADERS, timeout=10)
        if resp.status_code != 200: return {}
        soup = BeautifulSoup(resp.content, "html.parser")
        matches = re.findall(r'(ST\d{2}-\d{3})', soup.get_text())
        if len(matches) < 10: return {}
        for card_id in matches:
            deck_code = card_id.split('-')[0]
            if deck_code not in decks: decks[deck_code] = {}
            # Assume 2 copies if scraping from text unless specified
            decks[deck_code][card_id] = 2 
        return decks
    except: return {}

def hunt_products():
    print(f"    🕵️ Getting Deck Names...")
    found_decks = {}
    miss_streak = 0
    for i in range(1, 21):
        code = f"ST{i:02d}"
        url = PRODUCT_URL_TEMPLATE.format(code.lower())
        try:
            resp = requests.get(url, headers=HEADERS, timeout=2)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                title = soup.select_one("h1.ttl, .productName, h1, title")
                raw = title.text.strip() if title else f"Starter Deck {code}"
                clean = raw.split('[')[0].replace("GUNDAM CARD GAME", "").strip()
                found_decks[code] = clean
                print(f"        Found: {code} -> {clean}")
                miss_streak = 0
            else:
                miss_streak += 1
            if miss_streak >= MAX_MISSES: break
        except: 
            miss_streak += 1
            if miss_streak >= MAX_MISSES: break
    return found_decks

def generate_friendly_deck_json():
    print("\n--- PHASE 1: GENERATING FRIENDLY DECK JSON ---")
    
    # 1. Merge Raw Lists
    raw_decks = SEED_DECKS_RAW.copy()
    news_data = scrape_launch_news()
    for k, v in news_data.items():
        if k not in raw_decks: raw_decks[k] = v

    # 2. Get Names
    names = hunt_products()

    # 3. Transform to Friendly Format
    friendly_output = {}
    
    for deck_code, card_map in raw_decks.items():
        deck_name = names.get(deck_code, f"Starter Deck {deck_code}")
        
        # Create the array of objects
        card_list = []
        for card_no, quantity in card_map.items():
            card_list.append({
                "card_no": card_no,
                "quantity": quantity
            })
            
        friendly_output[deck_code] = {
            "name": deck_name,
            "cards": card_list
        }

    print(f"    💾 Saving friendly structure to {DECKS_FILE}...")
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(friendly_output, f, indent=2)
    
    # Return a simple map for the card scraper to use later
    # (Card scraper just needs to know which cards belong to which deck ID)
    simple_map = {}
    for d_code, data in friendly_output.items():
        for c in data['cards']:
            cid = c['card_no']
            if cid not in simple_map: simple_map[cid] = {}
            simple_map[cid][d_code] = c['quantity']
            
    return simple_map

# --- CARD LOGIC ---

def discover_sets():
    print("\n--- PHASE 2: SET DISCOVERY ---")
    found_sets = []
    for prefix in KNOWN_SET_PREFIXES:
        print(f"    Checking {prefix}...", end="")
        miss = 0
        for i in range(1, 10):
            scode = f"{prefix}{i:02d}"
            try:
                if requests.head(DETAIL_URL_TEMPLATE.format(f"{scode}-001"), headers=HEADERS, timeout=2).status_code == 200:
                    found_sets.append({"code": scode, "limit": 200})
                    miss = 0
                else: miss += 1
            except: miss += 1
            if miss >= 2: break
        print(" Done.")
    if not found_sets: return [{"code": "ST01", "limit": 30}]
    return found_sets

def scrape_card(card_id, deck_map):
    url = DETAIL_URL_TEMPLATE.format(card_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200 or "cardlist" in resp.url: return []
        soup = BeautifulSoup(resp.content, "html.parser")
        
        name = soup.select_one(".cardName, h1").text.strip()
        if not name: return []

        stats = {k: "0" for k in ["cost", "hp", "ap", "level"]}
        meta = {k: "-" for k in ["color", "type", "trait", "rarity", "link"]}
        
        for dt in soup.find_all("dt"):
            lbl = dt.text.strip().lower()
            val = dt.find_next_sibling("dd").text.strip() if dt.find_next_sibling("dd") else ""
            if "cost" in lbl: stats["cost"] = val
            elif "hp" in lbl: stats["hp"] = val
            elif "ap" in lbl or "atk" in lbl: stats["ap"] = val
            elif "level" in lbl: stats["level"] = val
            elif "color" in lbl: meta["color"] = val
            elif "type" in lbl: meta["type"] = val
            elif "trait" in lbl: meta["trait"] = val
            elif "rarity" in lbl: meta["rarity"] = val
            elif "link" in lbl: meta["link"] = val

        rarities = extract_rarities(soup.select_one(".rarity").text.strip()) if soup.select_one(".rarity") else [meta["rarity"]]
        effect = soup.select_one(".cardDataRow.overview .dataTxt").text.strip().replace("<br>", "\n") if soup.select_one(".cardDataRow.overview .dataTxt") else ""

        base_data = {
            "card_no": card_id, "name": name, "series": card_id.split("-")[0],
            "cost": safe_int(stats["cost"]), "hp": safe_int(stats["hp"]), 
            "ap": safe_int(stats["ap"]), "level": safe_int(stats["level"]),
            "color": meta["color"], "type": meta["type"], "trait": meta["trait"],
            "rarity": meta["rarity"], "link": meta["link"], "effect_text": effect,
            "deck_quantities": deck_map.get(card_id, {}), "last_updated": int(time.time())
        }

        # Variants
        cards = []
        idx = 0
        while True:
            suffix = "" if idx == 0 else f"_p{idx}"
            cid = f"{card_id}{suffix}"
            img = IMAGE_URL_TEMPLATE.format(cid)
            if not check_url_exists(img):
                if idx == 0: return []
                break
            
            c = base_data.copy()
            c["id"] = cid
            c["image_url"] = img
            c["rarity"] = rarities[idx] if idx < len(rarities) else f"{rarities[-1]}+"
            cards.append(c)
            idx += 1
            if idx > 15: break
            
        return cards
    except: return []

def run_update():
    # 1. Generate Friendly Deck JSON
    deck_map = generate_friendly_deck_json()
    
    # 2. Load Existing
    db = {}
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                for c in json.load(f): db[c['id']] = c
        except: pass

    # 3. Scrape Cards
    print("\n--- PHASE 3: CARD SCRAPING ---")
    
    # Special Assets
    for aid in SPECIAL_ASSETS:
        for c in scrape_card(aid, deck_map):
            db[c['id']] = c
            print(f"    💎 Special: {c['id']}")

    # Regular Sets
    for s in discover_sets():
        print(f"\nProcessing {s['code']}...")
        miss = 0
        for i in range(1, s['limit']+1):
            cid = f"{s['code']}-{i:03d}"
            res = scrape_card(cid, deck_map)
            if res:
                miss = 0
                for c in res:
                    if c['id'] not in db: print(f"    New: {c['id']}")
                    db[c['id']] = c
            else:
                miss += 1
                if miss > MAX_MISSES: break
            time.sleep(0.1)
            if i % 20 == 0: 
                with open(JSON_FILE, 'w', encoding='utf-8') as f: json.dump(list(db.values()), f, indent=2)

    # 4. Save Final
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(db.values()), f, indent=2)
    print("\n✅ All Done!")

if __name__ == "__main__":
    run_update()
