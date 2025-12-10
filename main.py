import requests
from bs4 import BeautifulSoup
import json
import os
import time
import datetime
import cloudinary
import cloudinary.uploader
import re

# --- CONFIGURATION ---
DETAIL_URL_TEMPLATE = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch={}"
IMAGE_URL_TEMPLATE = "https://www.gundam-gcg.com/en/images/cards/card/{}.webp?251120"
JSON_FILE = "data.json" 

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

def upload_image_to_cloudinary(image_url, public_id):
    try:
        # Check if exists (Optional optimization)
        # return cloudinary.api.resource(f"gundam_cards/{public_id}")['secure_url']
        
        result = cloudinary.uploader.upload(
            image_url,
            public_id=f"gundam_cards/{public_id}",
            unique_filename=False,
            overwrite=True
        )
        return result['secure_url']
    except Exception as e:
        print(f"   ❌ Cloudinary Upload Error ({public_id}): {e}")
        return image_url

def discover_sets():
    """
    Brute-force checks for sets by probing the first card (e.g., ST01-001).
    If ST01-001 exists, we assume the set ST01 exists.
    """
    print("🔍 Brute-forcing set discovery...")
    found_sets = []
    
    # Prefixes to check
    prefixes = ["ST", "GD", "PR", "UT"] 
    
    for prefix in prefixes:
        # Check numbers 01 through 15 (Increase this limit in the future)
        for i in range(1, 15):
            set_code = f"{prefix}{i:02d}" # e.g., ST01
            test_card = f"{set_code}-001"
            url = DETAIL_URL_TEMPLATE.format(test_card)
            
            try:
                # We check the detail page for the first card of the set
                resp = requests.get(url, headers=HEADERS, timeout=3)
                
                # Check if it redirected to the main list (Soft 404) or stayed on detail
                # And ensure the page has a valid title
                if resp.status_code == 200 and "cardlist" not in resp.url:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    if soup.select_one(".cardName, h1"):
                        # Set Exists!
                        limit = 130 if prefix == "GD" else 35
                        found_sets.append({"code": set_code, "limit": limit})
                        print(f"   ✅ Found Set: {set_code}")
                    else:
                        # Empty page means set likely doesn't exist yet
                        break
                else:
                    break
            except:
                break
                
    if not found_sets:
        print("   ⚠️ No sets found via probing. Using defaults.")
        return [
            {"code": "ST01", "limit": 25}, {"code": "GD01", "limit": 105}, {"code": "GD02", "limit": 105}
        ]
        
    return found_sets

def scrape_card(card_id):
    url = DETAIL_URL_TEMPLATE.format(card_id)
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code != 200: return None 
            
        soup = BeautifulSoup(resp.content, "html.parser")
        
        name_tag = soup.select_one(".cardName, h1")
        if not name_tag: return None
        name = name_tag.text.strip()

        # STATS PARSING
        stats = {"level": "-", "cost": "-", "hp": "-", "ap": "-", "rarity": "-", "color": "N/A", "type": "UNIT"}
        
        for dt in soup.find_all("dt"):
            label = dt.text.strip().lower()
            val_tag = dt.find_next_sibling("dd")
            if not val_tag: continue
            val = val_tag.text.strip()
            
            if "lv" in label: stats["level"] = val
            elif "cost" in label: stats["cost"] = val
            elif "hp" in label: stats["hp"] = val
            elif "ap" in label or "atk" in label: stats["ap"] = val
            elif "rarity" in label: stats["rarity"] = val
            elif "color" in label: stats["color"] = val
            elif "type" in label: stats["type"] = val

        text_tag = soup.select_one(".text")
        effect_text = text_tag.text.strip().replace("<br>", "\n") if text_tag else ""
        
        traits_tag = soup.select_one(".characteristic")
        traits = traits_tag.text.strip() if traits_tag else ""

        # IMAGE HANDLING
        official_img_url = IMAGE_URL_TEMPLATE.format(card_id)
        final_image_url = upload_image_to_cloudinary(official_img_url, card_id)

        print(f"   ✅ {card_id} | {name}")

        return {
            "cardNo": card_id,
            "originalId": card_id,
            "name": name,
            "series": card_id.split("-")[0],
            "cost": int(stats["cost"]) if stats["cost"].isdigit() else 0,
            "color": stats["color"],
            "rarity": stats["rarity"],
            "apData": stats["ap"],
            "effectData": effect_text,
            "categoryData": stats["type"],
            "image": final_image_url,
            "metadata": json.dumps({ 
                "level": stats["level"],
                "hp": stats["hp"],
                "def": stats["hp"],
                "atk": stats["ap"],
                "trait": traits,
                "type": stats["type"],
                "variants": [] 
            }),
            "last_updated": str(datetime.datetime.now())
        }

    except Exception as e:
        print(f"   ❌ Error {card_id}: {e}")
        return None

def run_update():
    sets = discover_sets()
    all_cards = []
    
    print(f"\n--- STARTING SCRAPE ---")
    
    for set_info in sets:
        code = set_info['code']
        limit = set_info['limit']
        print(f"\nProcessing Set: {code}...")
        
        miss_streak = 0
        for i in range(1, limit + 1):
            card_id = f"{code}-{i:03d}"
            
            if miss_streak >= 5:
                print(f"   Stopping {code} at {i-5} (End of Set)")
                break

            card_data = scrape_card(card_id)
            
            if card_data:
                all_cards.append(card_data)
                miss_streak = 0
            else:
                miss_streak += 1
            
            time.sleep(0.1) 

    if len(all_cards) > 0:
        print(f"\nSaving {len(all_cards)} cards to {JSON_FILE}...")
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_cards, f, indent=2, ensure_ascii=False)
        print("Done.")
    else:
        print("❌ No cards found.")

if __name__ == "__main__":
    run_update()
