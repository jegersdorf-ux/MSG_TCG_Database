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
        
        # If List View worked, check parallels
        if cards:
            print("   🔍 Checking for Parallel Art variants...")
            all_with_vars = []
            for c in cards:
                all_with_vars.append(c)
                base_data = {
                    "card_no": c['card_no'],
                    "rarity": "C", 
                    "details": {}
                }
                vars = find_parallels(c['card_no'], base_data)
                all_with_vars.extend(vars)
            cards = all_with_vars

        # B. Brute Force (Fallback)
        if not cards:
            cards = brute_force_cards(s)
            
        if cards:
            # 🚨 FILTER LOGIC HERE 🚨
            # Only add to decks.json if it is a Starter Deck (Starts with "ST")
            if s['id'].startswith("ST"):
                base_cards = [c for c in cards if "_p" not in c.get('id', '')]
                decks_out[s['id']] = {
                    "name": s['name'],
                    "cards": [{"card_no": c['card_no'], "quantity": c['quantity']} for c in base_cards]
                }
                print(f"   ✅ Added {s['id']} to Deck List.")
            else:
                print(f"   ℹ️  Skipped adding {s['id']} to Deck List (Not a Starter).")
            
            # Add ALL cards to the Database (cards.json)
            for c in cards:
                uid = c.get('id', c['card_no'])
                if uid not in cards_out:
                    d = c.get('details', {})
                    cards_out[uid] = {
                        "id": uid, 
                        "card_no": c['card_no'], 
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
            print(f"   ✅ Saved {len(cards)} cards to Database.")
        else:
            print(f"   ❌ Failed to find cards for {s['id']}")

    # 3. SAVE
    with open(DECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(decks_out, f, indent=2)
    print(f"\n💾 Saved {len(decks_out)} Starter Decks to {DECKS_FILE}")

    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cards_out.values()), f, indent=2)
    print(f"💾 Saved {len(cards_out)} Total Cards to {CARDS_FILE}")

if __name__ == "__main__":
    main()
