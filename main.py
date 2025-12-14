import requests
from requests.exceptions import Timeout, ConnectionError, RequestException
from bs4 import BeautifulSoup
import json
import os
import time
import datetime
import cloudinary
import cloudinary.uploader
import cloudinary.api
import re

# --- CONFIGURATION ---
FULL_CHECK = True  # True = Audit all cards. False = Only find new cards.

# Files
JSON_FILE = "cards.json"
DECKS_FILE = "decks.json"

# URL Templates
DETAIL_URL_TEMPLATE = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch={}"
IMAGE_URL_TEMPLATE = "https://www.gundam-gcg.com/en/images/cards/card/{}.webp?251120"

# DECK SOURCES: Map Deck Code -> Strategy Page URL
DECK_SOURCES = {
    "ST01": "https://www.gundam-gcg.com/en/decks/deck-004.php",
    "ST02": "https://www.gundam-gcg.com/en/decks/deck-005.php",
    "ST03": "https://www.gundam-gcg.com/en/decks/deck-006.php",
    "ST04": "https://www.gundam-gcg.com/en/decks/deck-007.php",
    # Add future decks here (e.g., ST05, ST06)
}

# ARCHITECTURAL NOTE: 
# Add new set prefixes here to ensure they are discovered by the prober.
KNOWN_SET_PREFIXES = ["ST", "GD", "PR", "UT", "EXRP", "EXB", "EXR", "EXBP"]

# Cloudinary Setup
cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET'),
    secure = True
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

RATE_LIMIT_HIT = False

# --- UTILITY FUNCTIONS ---

def safe_int(val):
    if not val: return 0
    try:
        clean_val = re.sub(r'[^\d-]', '', str(val))
        if not clean_val: return 0
        return int(clean_val)
    except:
        return 0

def has_changed(old, new):
    """Generic diff checker for dicts."""
    if not old: return True
    # For cards, we ignore timestamps. For decks, straight comparison is fine.
    o = old.copy()
    n = new.copy()
    o.pop('last_updated', None)
    n.pop('last_updated', None)
    # Sort keys to ensure reliable string comparison
    return json.dumps(o, sort_keys=True) != json.dumps(n, sort_keys=True)

# --- PHASE 1: DECK SCRAPING LOGIC ---

def scrape_deck_strategy(url):
    """
    Scrapes a strategy page for card counts using Regex.
    Returns: { "ST01-001": 2, "ST01-002": 4 }
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        
        soup = BeautifulSoup(resp.content, "html.parser")
        text_content = soup.get_text()

        # Regex: Looks for "2x CardName (ST01-001)"
        pattern = re.compile(r'(\d+)x\s+.*?\((ST\d+-\d+)\)')
        matches = pattern.findall(text_content)
        
        if not matches: return None

        deck_dict = {}
        for count, card_id in matches:
            deck_dict[card_id.strip()] = int(count)
            
        return deck_dict
    except Exception:
        return None

def sync_decks():
    """
    Manages the Deck DB. Follows the '3 Failures' and 'Update Only Changes' rules.
    """
    print("\n--- PHASE 1: SYNCING DECKS ---")
    
    # 1. Load Existing
    master_decks = {}
    if os.path.exists(DECKS_FILE):
        try:
            with open(DECKS_FILE, 'r', encoding='utf-8') as f:
                master_decks = json.load(f)
        except:
            print("    ⚠️ Error reading decks.json. Starting fresh.")
    
    updates_made = False
    
    for deck_code, url in DECK_SOURCES.items():
        print(f"    Processing {deck_code}...", end="")
        
        # Retry Logic (3 Failures Rule)
        max_retries = 3
        scraped_data = None
        
        for attempt in range(1, max_retries + 1):
            scraped_data = scrape_deck_strategy(url)
            if scraped_data:
                break # Success
            else:
                if attempt < max_retries:
                    time.sleep(1) # Brief cooldown
                else:
                    print(f" ❌ Failed after {max_retries} attempts. Skipping.")
        
        if not scraped_data:
            continue
            
        # Diff Check (Update Only Changes)
        existing_data = master_decks.get(deck_code)
        if has_changed(existing_data, scraped_data):
            status = "UPDATE" if existing_data else "NEW"
            print(f" 📝 {status}")
            master_decks[deck_code] = scraped_data
            updates_made = True
        else:
            print(" ✅ No Changes")
            
        time.sleep(0.5) # Be polite

    if updates_made:
        print(f"    💾 Saving updated decks to {DECKS_FILE}...")
        with open(DECKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(master_decks, f, indent=2)
    else:
        print("    ✨ Decks are up to date.")

    # Convert to Inverted Index for Card Scraper
    # { "ST01-001": {"ST01": 2}, ... }
    inverted_map = {}
    for deck_id, cards in master_decks.items():
        for card_id, count in cards.items():
            if card_id not in inverted_map: inverted_map[card_id] = {}
            inverted_map[card_id][deck_id] = count
            
    return inverted_map

# --- PHASE 2: CARD SCRAPING LOGIC ---

def upload_image_to_cloudinary(image_url, public_id):
    global RATE_LIMIT_HIT
    if RATE_LIMIT_HIT: return image_url

    try:
        result = cloudinary.uploader.upload(
            image_url,
            public_id=f"gundam_cards/{public_id}",
            unique_filename=False,
            overwrite=True
        )
        return result['secure_url']
    except Exception as e:
        error_msg = str(e)
        if "420" in error_msg or "Rate Limit" in error_msg:
            print(f"    🛑 RATE LIMIT REACHED. Switching to pass-through mode.")
            RATE_LIMIT_HIT = True
        return image_url

def discover_sets():
    print("\n--- PHASE 2: SET DISCOVERY ---")
    found_sets = []
    PROBE_TIMEOUT = 5
    
    for prefix in KNOWN_SET_PREFIXES:
        print(f"    Checking {prefix} series...", end="")
        set_miss_streak = 0
        
        for i in range(1, 10):
            set_code = f"{prefix}{i:02d}"
            test_card = f"{set_code}-001"
            url = DETAIL_URL_TEMPLATE.format(test_card)
            
            exists = False
            try:
                resp = requests.get(url, headers=HEADERS, timeout=PROBE_TIMEOUT) 
                if resp.status_code == 200 and "cardlist" not in resp.url:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    if soup.select_one(".cardName, h1"):
                        exists = True
            except:
                pass

            if exists:
                found_sets.append({"code": set_code, "limit": 200})
                set_miss_streak = 0
            else:
                set_miss_streak += 1
                if set_miss_streak >= 2: 
                    break 
        print(" Done.")
            
    if not found_sets:
        return [{"code": "ST01", "limit": 30}]
    return found_sets

def scrape_card(card_id, deck_info_map, existing_card=None):
    url = DETAIL_URL_TEMPLATE.format(card_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10) 
        if resp.status_code != 200 or "cardlist" in resp.url: return None
        
        soup = BeautifulSoup(resp.content, "html.parser")
        name_tag = soup.select_one(".cardName, h1")
        if not name_tag: return None
        name = name_tag.text.strip()

        raw_stats = {
            "level": "0", "cost": "0", "hp": "0", "ap": "0", "rarity": "-", 
            "color": "N/A", "type": "UNIT", "zone": "-", "trait": "-", 
            "link": "-", "source": "-", "release": "-"
        }

        for dt in soup.find_all("dt"):
            label = dt.text.strip().lower()
            val_tag = dt.find_next_sibling("dd")
            if not val_tag: continue
            val = val_tag.text.strip()

            if "lv" in label: raw_stats["level"] = val
            elif "cost" in label: raw_stats["cost"] = val
            elif "hp" in label: raw_stats["hp"] = val
            elif "ap" in label or "atk" in label: raw_stats["ap"] = val
            elif "color" in label: raw_stats["color"] = val
            elif "type" in label: raw_stats["type"] = val
            elif "zone" in label: raw_stats["zone"] = val
            elif "trait" in label: raw_stats["trait"] = val
            elif "link" in label: raw_stats["link"] = val
            elif "source" in label: raw_stats["source"] = val
            elif "where" in label: raw_stats["release"] = val

        rarity_tag = soup.select_one(".rarity")
        if rarity_tag: raw_stats["rarity"] = rarity_tag.text.strip()

        block_icon_tag = soup.select_one(".blockIcon")
        block_icon = safe_int(block_icon_tag.text.strip()) if block_icon_tag else 0

        effect_tag = soup.select_one(".cardDataRow.overview .dataTxt")
        effect_text = effect_tag.text.strip().replace("<br>", "\n") if effect_tag else ""
        
        # Image Handling
        final_image_url = ""
        has_valid_existing = (existing_card and "image_url" in existing_card and "cloudinary.com" in existing_card["image_url"])
        if has_valid_existing:
            final_image_url = existing_card["image_url"]
        else:
            final_image_url = upload_image_to_cloudinary(IMAGE_URL_TEMPLATE.format(card_id), card_id)

        # Deck Enrichment
        deck_quantities = deck_info_map.get(card_id, {})

        return {
            "id": card_id,                
            "card_no": card_id,           
            "name": name,
            "series": card_id.split("-")[0],
            "cost": safe_int(raw_stats["cost"]),
            "hp": safe_int(raw_stats["hp"]),
            "ap": safe_int(raw_stats["ap"]),
            "level": safe_int(raw_stats["level"]),
            "color": raw_stats["color"],
            "rarity": raw_stats["rarity"],
            "type": raw_stats["type"],
            "block_icon": block_icon, 
            "trait": raw_stats["trait"],        
            "zone": raw_stats["zone"],
            "link": raw_stats["link"],
            "effect_text": effect_text,
            "source_title": raw_stats["source"],
            "image_url": final_image_url,
            "release_pack": raw_stats["release"],
            "deck_quantities": deck_quantities, # Auto-Populated Column
            "last_updated": int(time.time()) 
        }
    except Exception as e:
        print(f"    ❌ Error {card_id}: {e}")
        return None

def save_db(db):
    if len(db) > 0:
        data_list = list(db.values())
        print(f"    💾 Checkpoint: Saving {len(data_list)} total cards...")
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2, ensure_ascii=False)

def run_update():
    # 1. Sync Decks First
    deck_map = sync_decks()

    # 2. Load Card DB
    master_db = {}
    if os.path.exists(JSON_FILE):
        print(f"📂 Loading existing {JSON_FILE}...")
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
                for c in data_list:
                    key = c.get('id', c.get('cardNo'))
                    if key: master_db[key] = c
        except:
            print("    ⚠️ Error reading existing JSON. Starting fresh.")
    
    if not all([os.getenv('CLOUDINARY_CLOUD_NAME'), os.getenv('CLOUDINARY_API_KEY')]):
        print("\n    🛑 WARNING: Cloudinary credentials missing.")

    sets = discover_sets()
    
    print(f"\n--- PHASE 3: CARD AUDIT ({'FULL' if FULL_CHECK else 'INCREMENTAL'}) ---")
    
    for set_info in sets:
        code = set_info['code']
        limit = set_info['limit']
        print(f"\nProcessing Set: {code} (Limit {limit})...")
        
        miss_streak = 0
        max_misses = 3
        
        for i in range(1, limit + 1):
            card_id = f"{code}-{i:03d}"
            
            # Logic: If not FULL_CHECK, we skip existing. 
            # BUT, if we have new deck data for this card, we force an update to inject it.
            existing_card = master_db.get(card_id)
            force_deck_update = False
            
            if existing_card:
                old_decks = existing_card.get("deck_quantities", {})
                new_decks = deck_map.get(card_id, {})
                if str(old_decks) != str(new_decks):
                    force_deck_update = True

            if not FULL_CHECK and existing_card and not force_deck_update:
                miss_streak = 0
                continue
                
            new_card_data = scrape_card(card_id, deck_map, existing_card=existing_card)
            
            if new_card_data:
                if has_changed(existing_card, new_card_data):
                    status = "UPDATE" if existing_card else "NEW"
                    print(f"    📝 {status}: {card_id}")      
                    master_db[card_id] = new_card_data
                miss_streak = 0
            else:
                miss_streak += 1
                if miss_streak <= max_misses:
                    print(f"    . {card_id} not found (Miss {miss_streak}/{max_misses})")
                else:
                    print(f"    🛑 Max misses reached for {code}. Moving to next set.")
                    break # The "3 Failures Move On" Rule for Sets
            
            time.sleep(0.1) 
            if i % 200 == 0: save_db(master_db) 
                 
        save_db(master_db)

    print("\n✅ Update Complete.")

if __name__ == "__main__":
    run_update()
