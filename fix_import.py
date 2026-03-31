"""
fix_import.py — Retter timestamps og renser falske SNR/RSSI-værdier
Kør efter import_contacts.py og import_paths.py
"""
import json
import sqlite3
from datetime import datetime

DB_PATH = '/home/pi/meshcore-hub/meshcore.db'
JSON_PATH = '/home/pi/meshcore-hub/contacts.json'

with open(JSON_PATH) as f:
    data = json.load(f)

db = sqlite3.connect(DB_PATH)

# Rens alle falske værdier
db.execute("UPDATE repeaters SET last_snr=NULL, last_rssi=NULL, first_seen=NULL, last_seen=NULL WHERE seen_count IS NULL OR seen_count=0")
db.execute("UPDATE repeaters SET last_snr=NULL WHERE last_snr=-10.0")
db.execute("UPDATE repeaters SET last_rssi=NULL WHERE last_rssi=0 AND last_snr IS NULL")

fixed = 0

for contact in data['discovered_contacts']:
    pubkey = contact.get('public_key', '')
    if not pubkey or len(pubkey) < 2:
        continue

    node_id = pubkey[:2].upper()
    last_advert = contact.get('last_advert', 0)

    if last_advert and last_advert > 0:
        try:
            first_seen = datetime.fromtimestamp(last_advert).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('''
                UPDATE repeaters
                SET first_seen=?, last_seen=?
                WHERE node_id=? AND (seen_count IS NULL OR seen_count=0)
            ''', (first_seen, first_seen, node_id))
            if db.execute('SELECT changes()').fetchone()[0] > 0:
                fixed += 1
        except Exception:
            pass

db.commit()
print(f"Færdig: {fixed} noder fik korrekt timestamp og renset SNR/RSSI")
