"""
import_paths.py — Importer hop-stier fra MeshCore app-eksport
Kør efter import_contacts.py
"""
import json
import sqlite3

DB_PATH = '/home/pi/meshcore-hub/meshcore.db'
JSON_PATH = '/home/pi/meshcore-hub/contacts.json'

with open(JSON_PATH) as f:
    data = json.load(f)

db = sqlite3.connect(DB_PATH)

db.execute('''
    CREATE TABLE IF NOT EXISTS paths (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id  TEXT,
        hop_from    TEXT,
        hop_to      TEXT,
        hop_order   INTEGER,
        recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
db.execute('DELETE FROM paths')
imported = 0

for contact in data['discovered_contacts']:
    pubkey = contact.get('public_key', '')
    path_str = contact.get('advert_path_list', '')
    if not pubkey or not path_str:
        continue

    contact_id = pubkey[:2].upper()
    hops = [h.strip()[:2].upper() for h in path_str.split(',') if h.strip()]

    if len(hops) < 2:
        continue

    for i in range(len(hops) - 1):
        db.execute('''
            INSERT INTO paths (contact_id, hop_from, hop_to, hop_order)
            VALUES (?, ?, ?, ?)
        ''', (contact_id, hops[i], hops[i+1], i))
        imported += 1

db.commit()
print(f"Færdig: {imported} hop-forbindelser importeret")
