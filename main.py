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
                    
                    # Integers (will be null for Tokens)
                    "cost": safe_int('cost'),
                    "hp": safe_int('hp'),
                    "ap": safe_int('ap'),
                    "level": safe_int('level'),
                    
                    # Strings (will be null if "-")
                    "color": safe_str('color'),
                    "type": c['type'],
                    "rarity": c['rarity'],
                    "trait": safe_str('trait'),
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
