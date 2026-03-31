"""
import_contacts.py — Importer alle kontakter fra MeshCore app-eksport
Kør efter at du har kopieret din contacts.json til /home/pi/meshcore-hub/contacts.json
"""
import json
import sqlite3

DB_PATH = '/home/pi/meshcore-hub/meshcore.db'
JSON_PATH = '/home/pi/meshcore-hub/contacts.json'

with open(JSON_PATH) as f:
    data = json.load(f)

db = sqlite3.connect(DB_PATH)
inserted = 0
updated = 0
skipped = 0

for contact in data['discovered_contacts']:
    pubkey = contact.get('public_key', '')
    if not pubkey or len(pubkey) < 2:
        continue

    node_id = pubkey[:2].upper()
    lat = float(contact.get('latitude', 0))
    lon = float(contact.get('longitude', 0))
    name = contact.get('name', '')

    if lat == 0.0 and lon == 0.0:
        skipped += 1
        continue

    existing = db.execute('SELECT node_id FROM repeaters WHERE node_id=?', (node_id,)).fetchone()
    if existing:
        db.execute('''
            UPDATE repeaters SET lat=?, lon=?, name=?
            WHERE node_id=?
        ''', (lat, lon, name, node_id))
        updated += 1
    else:
        db.execute('''
            INSERT INTO repeaters (node_id, lat, lon, name, last_snr, last_rssi, seen_count)
            VALUES (?, ?, ?, ?, NULL, NULL, 0)
        ''', (node_id, lat, lon, name))
        inserted += 1
        print(f"➕ {node_id} → {name} ({lat:.4f}, {lon:.4f})")

db.commit()
print(f"\nFærdig: {inserted} nye, {updated} opdateret, {skipped} uden GPS")
