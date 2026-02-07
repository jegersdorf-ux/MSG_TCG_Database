import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os

# --- CONFIGURATION ---
BASE_URL = "https://www.gundam-gcg.com/en/cards/index.php"
DETAIL_URL = "https://www.gundam-gcg.com/en/cards/detail.php"
HOST = "https://www.gundam-gcg.com"
CARDS_FILE = "cards.json"
DECKS_FILE = "decks.json"
CONFIG_FILE = "starter_decks_config.json" # stores the known decks persistently

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
}

# --- INITIAL SEED (If config file is missing) ---
DEFAULT_DECKS = [
    {"id": "ST01", "name": "Heroic Beginnings", "internal_id": "616001"},
    {"id": "ST02", "name": "Wings of Advance", "internal_id": "616002"},
    {"id": "ST03", "name": "Zeon's Rush", "internal_id": "616003"},
    {"id": "ST04", "name": "SEED Strike", "internal_id": "616004"},
    {"id": "ST05", "name": "Iron Bloom", "internal_id": "616005"},
    {"id": "ST06", "name": "Clan Unity", "internal_id": "616006"},
    {"id": "ST07", "name": "Turn A", "internal_id": "616007"},      
    {"id": "ST08", "name": "Flash of Radiance", "internal_id": "616008"},
]

def get_soup(url, params=None):
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        return BeautifulSoup(response.content, 'html.parser')
    except: return None

def load_known_decks():
    """Load decks from JSON or return default if missing"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return DEFAULT_DECKS

def save_known_decks(decks):
    """Save the updated list of decks so we remember them next time"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(decks, f, indent=2)

def hunt_for_new_decks(current_decks):
    """
    FUTURE PROOFING:
    Checks if the NEXT deck exists. 
    If we know up to ST08, this checks ST09-001. 
    If ST09 exists, it adds it and checks ST10.
    """
    print("🔮 Hunting for future decks...")
    
    # 1. Find the highest current ST number
    max_st = 0
    for d in current_decks:
        match = re.search(r'ST(\d+)', d['id'])
        if match:
            max_st = max(max_st, int(match.group(1)))
    
    new_decks_found = []
    
    # 2. Try to find the next 5 decks (e.g. ST09, ST10...)
    # We stop looking if we fail 2 in a row.
    misses = 0
    check_st = max_st + 1
    
    while misses < 2:
        deck_code = f"ST{check_st:02d}"
        card_id = f"{deck_code}-001" # Check for the Leader/First card
        print(f"   ❓ Probing {deck_code} ({card_id})...", end="")
        
        soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
        
        if soup and soup.select_one('.cardName'):
            # IT EXISTS!
            deck_name = f"Starter Deck {deck_code}" # Placeholder name
            
            # Try to find real name from Product page if possible, otherwise generic
            # For now, we accept generic name.
            
            print(f" ✅ FOUND! Adding to database.")
            new_deck_entry = {
                "id": deck_code,
                "name": deck_name, 
                "internal_id": "" # Unknown internal ID, but Brute Force will handle it
            }
            current_decks.append(new_deck_entry)
            new_decks_found.append(new_deck_entry)
            misses = 0 # Reset misses because we found one
        else:
            print(" ❌ Not found yet.")
            misses += 1
            
        check_st += 1
        time.sleep(0.5)
        
    if new_decks_found:
        print(f"✨ Future-proofing successful! Discovered {len(new_decks_found)} new decks.")
        save_known_decks(current_decks) # Save for next run
    else:
        print("   No new decks released yet.")
        
    return current_decks

def scrape_list_view(deck_meta):
    """Try to get all cards from the filter list view (Fastest)"""
    # ... (Same as before)
    if not deck_meta.get('internal_id'): return [] # Skip if we don't know internal ID

    print(f"   Trying List View for {deck_meta['id']}...")
    soup = get_soup(BASE_URL, {'search': 'true', 'product': deck_meta['internal_id'], 'view': 'text'})
    # (Rest of scrape_list_view logic from previous script...)
    # For brevity, assume standard scrape logic here.
    # If using previous script's logic, paste it here.
    return [] 

def brute_force_cards(deck_code):
    """Fallback: Check STxx-001, STxx-002... individually"""
    print(f"   🔨 Brute-forcing {deck_code}-001, 002...")
    cards = []
    misses = 0
    
    for i in range(1, 35): 
        card_id = f"{deck_code}-{i:03d}"
        soup = get_soup(DETAIL_URL, {'detailSearch': card_id})
        
        if not soup or not soup.select_one('.cardName'):
            misses += 1
            if misses >= 3: break 
            continue
            
        name = soup.select_one('.cardName').get_text(strip=True)
        img_tag = soup.select_one('.cardImg img')
        img = img_tag.get('src') if img_tag else ""
        if img.startswith('..'): img = HOST + img.replace('..', '')
        
        # Stats parsing...
        stats = {}
        for dt in soup.find_all("dt"):
            stats[dt.text.strip().lower()] = dt.find_next_sibling("dd").text.strip()
            
        qty = 4
        if "LEADER" in stats.get("card type", "").upper(): qty = 1
        elif "RARE" in stats.get("rarity", "").upper(): qty = 2
        
        cards.append({
            "card_no": card_id, "name": name, "quantity": qty, "image_url": img,
            "details": stats
        })
        misses = 0 
        time.sleep(0.1)
        
    return cards

def main():
    # 1. LOAD & HUNT
    known_decks = load_known_decks()
    all_decks = hunt_for_new_decks(known_decks) # <--- THIS IS THE MAGIC
    
    decks_out = {}
    cards_out = {}

    # 2. SCRAPE
    for deck in all_decks:
        print(f"\n📥 Processing {deck['id']}...")
        
        # Try List View (Fast) if we have an ID
        cards = []
        if deck.get('internal_id'):
             # Reuse your scrape_list_view logic here 
             # (omitted for space, paste from previous response)
             pass 
        
        # Fallback to Brute Force (Robust)
        if not cards:
            cards = brute_force_cards(deck['id'])
            
        if cards:
            decks_out[deck['id']] = {
                "name": deck['name'],
                "cards": [{"card_no": c['card_no'], "quantity": c['quantity']} for c in cards]
            }
            
            # Add to card database
            for c in cards:
                if c['card_no'] not in cards_out:
                    d = c.get('details', {})
                    cards_out[c['card_no']] = {
                        "id": c['card_no'], "card_no": c['card_no'],
                        "name": c['name'], "image_url": c['image_url'],
                        "cost": int(re.sub(r'\D', '', d.get('cost', '0')) or 0),
                        "hp": int(re.sub(r'\D', '', d.get('hp', '0')) or 0),
                        "color": d.get('color', 'N/A'),
                        "type": d.get('card type', 'UNIT'),
                        "rarity": d.get('rarity', 'C'),
                        "trait": d.get('trait', ''),
                        "effect_text": d.get('text', ''),
                        "set": deck['id']
                    }
            print(f"   ✅ Saved {len(cards)} cards.")
        else:
            print(f"   ❌ Failed to find cards for {deck['id']}")

    # 3. SAVE
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(decks_out, f, indent=2)
    print(f"\n💾 Saved {len(decks_out)} decks to {DECKS_FILE}")

    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cards_out.values()), f, indent=2)
    print(f"💾 Saved {len(cards_out)} cards to {CARDS_FILE}")

if __name__ == "__main__":
    main()
