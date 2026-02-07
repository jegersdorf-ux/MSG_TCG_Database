import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os

# --- CONFIGURATION ---
BASE_URL = "https://www.gundam-gcg.com/en/cards/index.php"
HOST = "https://www.gundam-gcg.com"
CARDS_FILE = "cards.json"
DECKS_FILE = "decks.json"

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def get_soup(url, params=None):
    """Helper to fetch page and return BeautifulSoup object"""
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

def discover_starter_decks():
    """
    Scrapes the main card page to find ALL Starter Decks automatically.
    This finds ST05, ST06, ST07, ST08, etc. without hardcoding.
    """
    print("🔍 Scanning for Starter Decks (STxx)...")
    soup = get_soup(BASE_URL)
    if not soup:
        return []

    decks = []
    
    # The filter dropdown usually has an ID like 'search_product' or 'search_series'
    # We look for all <option> tags in any <select> to be safe.
    options = soup.find_all('option')
    seen_ids = set()

    for option in options:
        text = option.get_text().strip()
        value = option.get('value')
        
        # Regex to match "Name [STxx]" format
        # Example: "Heroic Beginnings [ST01]"
        match = re.search(r'(.*?)\[(ST\d+)\]', text)
        
        if match and value and value not in seen_ids:
            deck_name = match.group(1).strip()
            deck_code = match.group(2).strip()
            
            seen_ids.add(value)
            print(f"   found: {deck_code} - {deck_name} (Filter ID: {value})")
            
            decks.append({
                "id": deck_code,      # ST01
                "name": deck_name,    # Heroic Beginnings
                "internal_id": value  # The ID used in the URL query
            })

    # Sort by ST number
    decks.sort(key=lambda x: x['id'])
    return decks

def scrape_cards_for_deck(deck_meta):
    """
    Fetches all cards for a specific deck using its internal ID.
    """
    print(f"📥 Fetching cards for {deck_meta['id']} ({deck_meta['name']})...")
    
    # Parameters to filter the list view by the specific deck
    params = {
        'search': 'true',
        'product': deck_meta['internal_id'], 
        'view': 'text' 
    }
    
    soup = get_soup(BASE_URL, params)
    
    # Fallback: If 'product' param didn't work, try 'series'
    if not soup or not soup.select('.cardList'):
        params = {'search': 'true', 'series': deck_meta['internal_id'], 'view': 'text'}
        soup = get_soup(BASE_URL, params)

    if not soup:
        return []

    cards = []
    
    # Selectors for the "Text View" of the card list
    # These classes (.list, .number, .cardName) must match the live site.
    card_rows = soup.select('.cardList .list li') 
    
    if not card_rows:
        # Fallback to Grid View selectors if Text View fails
        card_rows = soup.select('.cardList .item')

    for row in card_rows:
        try:
            # 1. Extract Card Number
            card_no_tag = row.select_one('.number') or row.select_one('.cardNo')
            if not card_no_tag: continue
            card_no = card_no_tag.get_text(strip=True)

            # 2. Extract Name
            name_tag = row.select_one('.cardName') or row.select_one('.name')
            name = name_tag.get_text(strip=True) if name_tag else "Unknown"

            # 3. Extract Image
            img_tag = row.select_one('img') or row.select_one('.cardImg img')
            img_url = ""
            if img_tag:
                src = img_tag.get('src') or img_tag.get('data-src')
                if src:
                    if src.startswith('..'):
                        img_url = HOST + src.replace('..', '')
                    elif src.startswith('/'):
                        img_url = HOST + src
                    else:
                        img_url = src

            # 4. Extract Stats (Cost, HP, etc.) if available in list view
            # Note: The text view usually has these in <dl> tags or similar
            stats = {}
            # You can add logic here to parse cost/power if needed for cards.json
            
            # 5. Determine Quantity (Heuristic)
            qty = 2 
            row_text = row.get_text().upper()
            
            if "LEADER" in row_text: qty = 1
            elif "COMMON" in row_text or "UNCOMMON" in row_text: qty = 4
            elif "RARE" in row_text: qty = 2
            if "TOKEN" in row_text: qty = 1

            cards.append({
                "card_no": card_no,
                "name": name,
                "quantity": qty,
                "image_url": img_url,
                # Add other fields for cards.json later if you want
            })
            
        except AttributeError:
            continue

    return cards

def main():
    # --- PHASE 1: DISCOVER DECKS ---
    all_decks = discover_starter_decks()
    
    if not all_decks:
        print("⚠️ No starter decks found. The website structure might have changed.")
        return

    decks_output = {}
    all_cards_flat = {}

    # --- PHASE 2: SCRAPE EACH DECK ---
    for deck in all_decks:
        cards = scrape_cards_for_deck(deck)
        
        if cards:
            # Structure for decks.json
            decks_output[deck['id']] = {
                "name": deck['name'],
                "cards": [
                    {"card_no": c['card_no'], "quantity": c['quantity']} 
                    for c in cards
                ]
            }
            
            # Add to full card database for cards.json
            for c in cards:
                if c['card_no'] not in all_cards_flat:
                    # Map to your card model structure
                    all_cards_flat[c['card_no']] = {
                        "id": c['card_no'],
                        "card_no": c['card_no'],
                        "name": c['name'],
                        "image_url": c['image_url'],
                        # Defaults for now since list view might not have full details
                        "cost": 0, "hp": 0, "ap": 0, "level": 0,
                        "color": "N/A", "type": "UNIT", "rarity": "C", 
                        "trait": "", "effect_text": "", "set": deck['id']
                    }
            
            print(f"   ✅ Processed {len(cards)} cards for {deck['id']}")
        else:
            print(f"   ⚠️ No cards found for {deck['id']}")
        
        time.sleep(1)

    # --- PHASE 3: SAVE FILES ---
    
    # Save Decks (The friendly format)
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(decks_output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved {len(decks_output)} decks to {DECKS_FILE}")

    # Save Cards (The database seed)
    # Convert dict to list
    cards_list = list(all_cards_flat.values())
    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cards_list, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved {len(cards_list)} cards to {CARDS_FILE}")

if __name__ == "__main__":
    main()
