import requests
from requests.exceptions import Timeout, ConnectionError, RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import json
import os
import time
import datetime
import re
import hashlib
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- CONFIGURATION ---
FULL_CHECK = False  # False = Use Rolling Audit (Specific sets on specific days). True = Audit ALL now.
FORCE_REFRESH_DAYS = 7 

# Safety Timer
MAX_RUNTIME_SECONDS = 5.5 * 60 * 60 
START_TIME = time.time()

# Files
JSON_FILE = "cards.json"
DECKS_FILE = "decks.json"
METADATA_FILE = "deck_metadata.json"

# Scanning Range
SCAN_START_ID = 4
SCAN_END_ID = 30 

# URL Templates
DETAIL_URL_TEMPLATE = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch={}"
IMAGE_URL_TEMPLATE = "https://www.gundam-gcg.com/en/images/cards/card/{}.webp?251120"
STRATEGY_URL_TEMPLATE = "https://www.gundam-gcg.com/en/decks/deck-{:03d}.php"
PRODUCT_URL_TEMPLATE = "https://www.gundam-gcg.com/en/products/{}.html"

# Known Set Prefixes
KNOWN_SET_PREFIXES = ["ST", "GD", "PR", "UT", "EXRP", "EXB", "EXR", "EXBP"]

# Cloudinary Setup
cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET'),
    secure = True
)

# Initialize Session
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

RATE_LIMIT_HIT = False

# --- UTILITY FUNCTIONS ---

def get_scheduled_day(set_code):
    """
    Deterministically assigns a Set Code to a day of the month (1-28).
    This ensures the schedule is stable (ST01 always checks on the same day).
    We use 28 to ensure it runs even in February.
    """
    # Create a hash of the set code to get a consistent number
    hash_val = int(hashlib.md5(set_code.encode()).hexdigest(), 16)
    # Map that number to 1-28
    return (hash_val % 28) + 1

def check_runtime():
    elapsed = time.time() - START_TIME
    if elapsed > MAX_RUNTIME_SECONDS:
        print(f"\n⏰ TIME LIMIT REACHED ({elapsed/3600:.2f} hrs). Stopping to save progress.")
        return False
    return True

def safe_int(val):
    if not val: return 0
    try:
        clean_val = re.sub(r'[^\d-]', '', str(val))
        return int(clean_val) if clean_val else 0
    except:
        return 0

def has_changed(old, new):
    if not old: return True
    o = old.copy()
    n = new.copy()
    o.pop('last_updated', None)
    n.pop('last_updated', None)
    return json.dumps(o, sort_keys=True) != json.dumps(n, sort_keys=True)

# --- PHASE 1: DECK DISCOVERY ---
# (Stays mostly the same, compressed for brevity)

def get_product_name(deck_code):
    try:
        resp = session.get(PRODUCT_URL_TEMPLATE.format(deck_code.lower()), timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            h1 = soup.select_one("h1.ttl, .productName, h1")
            return h1.text.strip() if h1 else f"Starter Deck {deck_code}"
    except: pass
    return f"Starter Deck {deck_code}"

def hunt_decks():
    print(f"\n🕵️ Hunting for Decks (IDs {SCAN_START_ID}-{SCAN_END_ID})...")
    found_decks = {}
    for i in range(SCAN_START_ID, SCAN_END_ID + 1):
        if not check_runtime(): break
        try:
            resp = session.get(STRATEGY_URL_TEMPLATE.format(i), timeout=3)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                title = soup.title.text.strip() if soup.title else ""
                match = re.search(r'(ST\d+)', title, re.IGNORECASE)
                if match:
                    code = match.group(1).upper()
                    print(f"    ✅ HIT: Found {code} at ID {i:03d}")
                    found_decks[code] = {"strategy_url": STRATEGY_URL_TEMPLATE.format(i), "name": get_product_name(code)}
                    time.sleep(0.1)
        except: pass
    return found_decks

def scrape_deck_counts(url):
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200: return None
        soup = BeautifulSoup(resp.content, "html.parser")
        matches = re.findall(r'(\d+)x\s+.*?\((ST\d+-\d+)\)', soup.get_text())
        return {card_id.strip(): int(count) for count, card_id in matches}
    except: return None

def sync_decks():
    print("\n--- PHASE 1: SYNCING DECKS ---")
    discovered_sources = hunt_decks()
    master_decks = {}
    master_metadata = {}
    
    if os.path.exists(DECKS_FILE):
        try:
            with open(DECKS_FILE, 'r') as f: master_decks = json.load(f)
        except: pass
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f: master_metadata = json.load(f)
        except: pass

    updates_made = False
    for code, info in discovered_sources.items():
        if not check_runtime(): break
        url = info['strategy_url']
        if code not in master_metadata:
            master_metadata[code] = {"name": info['name'], "strategy_url": url, "product_url": PRODUCT_URL_TEMPLATE.format(code.lower())}
            updates_made = True
            
        if code in master_decks and not FULL_CHECK: continue # Skip scrape if cached and not Full Check

        print(f"    Processing {code}...", end="")
        data = scrape_deck_counts(url)
        if data:
            if has_changed(master_decks.get(code), data):
                master_decks[code] = data
                updates_made = True
                print(" Updated")
            else: print(" No Changes")
        else: print(" Failed")
        time.sleep(0.5)

    if updates_made:
        with open(DECKS_FILE, 'w') as f: json.dump(master_decks, f, indent=2)
        with open(METADATA_FILE, 'w') as f: json.dump(master_metadata, f, indent=2)

    inverted_map = {}
    for d, cards in master_decks.items():
        for c, q in cards.items():
            if c not in inverted_map: inverted_map[c] = {}
            inverted_map[c][d] = q
    return inverted_map

# --- PHASE 2: CARD SCRAPING ---

def upload_image_to_cloudinary(image_url, public_id):
    global RATE_LIMIT_HIT
    if RATE_LIMIT_HIT: return image_url
    try:
        result = cloudinary.uploader.upload(image_url, public_id=f"gundam_cards/{public_id}", overwrite=True)
        return result['secure_url']
    except Exception as e:
        if "420" in str(e) or "Rate Limit" in str(e):
            print(f"    🛑 RATE LIMIT. Pass-through mode.")
            RATE_LIMIT_HIT = True
        return image_url

def discover_sets():
    print("\n--- PHASE 2: SET DISCOVERY ---")
    found_sets = []
    for prefix in KNOWN_SET_PREFIXES:
        if not check_runtime(): break
        print(f"    Checking {prefix}...", end="")
        for i in range(1, 10):
            set_code = f"{prefix}{i:02d}"
            try:
                if session.head(DETAIL_URL_TEMPLATE.format(f"{set_code}-001"), timeout=5).status_code == 200:
                    found_sets.append({"code": set_code, "limit": 200})
            except: pass
        print(" Done.")
    if not found_sets: return [{"code": "ST01", "limit": 30}]
    return found_sets

def scrape_card(card_id, deck_info_map, existing_card=None):
    try:
        resp = session.get(DETAIL_URL_TEMPLATE.format(card_id), timeout=10)
        if resp.status_code != 200 or "cardlist" in resp.url: return None
        soup = BeautifulSoup(resp.content, "html.parser")
        
        name_tag = soup.select_one(".cardName, h1")
        if not name_tag: return None
        
        # Stats Extraction
        raw = {k: "0" for k in ["level", "cost", "hp", "ap"]}
        raw.update({k: "-" for k in ["rarity", "zone", "trait", "link", "source", "release"]})
        raw.update({"color": "N/A", "type": "UNIT"})

        for dt in soup.find_all("dt"):
            lbl = dt.text.lower()
            val = dt.find_next_sibling("dd").text.strip() if dt.find_next_sibling("dd") else ""
            if "lv" in lbl: raw["level"] = val
            elif "cost" in lbl: raw["cost"] = val
            elif "hp" in lbl: raw["hp"] = val
            elif "ap" in lbl: raw["ap"] = val
            elif "color" in lbl: raw["color"] = val
            elif "type" in lbl: raw["type"] = val
            elif "zone" in lbl: raw["zone"] = val
            elif "trait" in lbl: raw["trait"] = val
            elif "link" in lbl: raw["link"] = val
            elif "source" in lbl: raw["source"] = val
            elif "where" in lbl: raw["release"] = val

        rarity = soup.select_one(".rarity").text.strip() if soup.select_one(".rarity") else "-"
        blk = safe_int(soup.select_one(".blockIcon").text) if soup.select_one(".blockIcon") else 0
        eff = soup.select_one(".cardDataRow.overview .dataTxt").text.strip().replace("<br>", "\n") if soup.select_one(".cardDataRow.overview .dataTxt") else ""
        
        # Image Handling
        img_url = ""
        if existing_card and "cloudinary.com" in existing_card.get("image_url", ""):
            img_url = existing_card["image_url"]
        else:
            img_url = upload_image_to_cloudinary(IMAGE_URL_TEMPLATE.format(card_id), card_id)

        return {
            "id": card_id, "card_no": card_id, "name": name_tag.text.strip(),
            "series": card_id.split("-")[0],
            "cost": safe_int(raw["cost"]), "hp": safe_int(raw["hp"]), "ap": safe_int(raw["ap"]),
            "level": safe_int(raw["level"]), "color": raw["color"], "rarity": rarity,
            "type": raw["type"], "block_icon": blk, "trait": raw["trait"], "zone": raw["zone"],
            "link": raw["link"], "effect_text": eff, "source_title": raw["source"],
            "image_url": img_url, "release_pack": raw["release"],
            "deck_quantities": deck_info_map.get(card_id, {}),
            "last_updated": int(time.time())
        }
    except Exception as e:
        print(f"Error {card_id}: {e}")
        return None

def save_db(db):
    if db:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(db.values()), f, indent=2, ensure_ascii=False)

def run_update():
    deck_map = sync_decks()
    master_db = {}
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r') as f:
                for c in json.load(f):
                    master_db[c.get('id', c.get('cardNo'))] = c
        except: pass
    
    sets = discover_sets()
    
    # --- SCHEDULE LOGIC ---
    today_day = datetime.datetime.now().day
    print(f"\n📅 Today is Day {today_day} of the month.")
    print("--- PHASE 3: ROLLING AUDIT ---")
    
    for set_info in sets:
        if not check_runtime(): break

        code = set_info['code']
        limit = set_info['limit']
        
        # Calculate if this set runs today
        scheduled_day = get_scheduled_day(code)
        is_scheduled_run = (today_day == scheduled_day)
        
        # Determine Audit Mode for this specific set
        do_full_audit = FULL_CHECK or is_scheduled_run
        
        schedule_status = "📅 SCHEDULED FULL AUDIT" if is_scheduled_run else f"(Scheduled for Day {scheduled_day})"
        mode_label = "FULL CHECK" if do_full_audit else "INCREMENTAL (New/Changes Only)"
        
        print(f"\nProcessing Set: {code} | {mode_label} | {schedule_status}")
        
        miss_streak = 0
        for i in range(1, limit + 1):
            if not check_runtime(): break

            card_id = f"{code}-{i:03d}"
            existing_card = master_db.get(card_id)
            force_deck_update = False
            
            if existing_card:
                if str(existing_card.get("deck_quantities", {})) != str(deck_map.get(card_id, {})):
                    force_deck_update = True

            # DECISION: Should we scrape?
            should_scan = False
            if not existing_card: should_scan = True       # Always scan new cards
            elif force_deck_update: should_scan = True     # Always scan if deck counts changed
            elif do_full_audit: should_scan = True         # Scan if global flag OR today is scheduled day

            if not should_scan:
                miss_streak = 0
                continue
                
            new_data = scrape_card(card_id, deck_map, existing_card)
            
            if new_data:
                if has_changed(existing_card, new_data):
                    print(f"    📝 UPDATE: {card_id}")
                    master_db[card_id] = new_data
                miss_streak = 0
            else:
                miss_streak += 1
                if miss_streak > 3:
                    print(f"    🛑 Max misses for {code}. Next set.")
                    break 
            
            if i % 50 == 0: save_db(master_db)
                  
        save_db(master_db)

    print("\n✅ Update Complete.")

if __name__ == "__main__":
    run_update()
