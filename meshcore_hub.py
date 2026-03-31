import serial
import sqlite3
import time
import threading
import re
from datetime import datetime

SERIAL_PORT = '/dev/ttyACM0'
BAUD = 115200
DB_PATH = '/home/pi/meshcore-hub/meshcore.db'
POLL_INTERVAL = 300  # sekunder mellem log-dumps

LOG_PATTERN = re.compile(
    r'(\d+:\d+:\d+)\s*[–-]\s*(\S+)\s+\S+\s+(RX|TX),.*?'
    r'SNR=([-\d]+)\s+RSSI=([-\d]+)\s+score=(\d+)\s+\[([0-9A-Fa-f]+)\s*->\s*([0-9A-Fa-f]+)\]'
)

def init_db(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS node_info (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS neighbors (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id   TEXT NOT NULL,
            timestamp TEXT,
            snr       REAL,
            seen_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS repeaters (
            node_id    TEXT PRIMARY KEY,
            last_snr   REAL,
            last_rssi  INTEGER,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen  DATETIME DEFAULT CURRENT_TIMESTAMP,
            seen_count INTEGER DEFAULT 0,
            lat        REAL,
            lon        REAL,
            name       TEXT,
            location   TEXT,
            elevation  REAL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS packets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            log_time    TEXT,
            log_date    TEXT,
            direction   TEXT,
            snr         REAL,
            rssi        INTEGER,
            score       INTEGER,
            from_node   TEXT,
            to_node     TEXT,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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
    db.commit()

def send_cmd(ser, cmd, wait=0.5):
    ser.write((cmd + '\r').encode())
    time.sleep(wait)

def read_until_prompt(ser, timeout=10):
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                lines.append(line)
        else:
            time.sleep(0.1)
    return lines

def parse_and_store_log(lines, db):
    new_nodes = 0
    new_packets = 0
    for line in lines:
        m = LOG_PATTERN.search(line)
        if not m:
            continue
        log_time, log_date, direction, snr, rssi, score, from_node, to_node = m.groups()
        snr = float(snr)
        rssi = int(rssi)
        score = int(score)

        db.execute('''
            INSERT INTO packets (log_time, log_date, direction, snr, rssi, score, from_node, to_node)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (log_time, log_date, direction, snr, rssi, score, from_node, to_node))
        new_packets += 1

        for node_id in set([from_node, to_node]):
            existing = db.execute(
                'SELECT seen_count FROM repeaters WHERE node_id=?', (node_id,)
            ).fetchone()
            if existing:
                db.execute('''
                    UPDATE repeaters
                    SET last_snr=?, last_rssi=?, last_seen=?, seen_count=seen_count+1
                    WHERE node_id=?
                ''', (snr, rssi, datetime.now(), node_id))
            else:
                db.execute('''
                    INSERT INTO repeaters (node_id, last_snr, last_rssi, seen_count)
                    VALUES (?,?,?,1)
                ''', (node_id, snr, rssi))
                new_nodes += 1
                print(f"  → Ny node: {node_id} SNR={snr}dB RSSI={rssi}dBm")

    db.commit()
    if new_packets > 0:
        print(f"  → {new_packets} pakker parset, {new_nodes} nye noder")

def main():
    db = sqlite3.connect(DB_PATH)
    init_db(db)
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=2)
    time.sleep(2)

    # Gem node-info ved opstart
    for key in ['name', 'freq']:
        send_cmd(ser, f'get {key}', wait=1.0)
        time.sleep(1)
        lines = []
        while ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                lines.append(line)
        for line in lines:
            if line.startswith('-> > '):
                value = line[5:]
                db.execute(
                    'INSERT OR REPLACE INTO node_info (key, value, updated_at) VALUES (?,?,?)',
                    (key, value, datetime.now())
                )
                db.commit()
                print(f"Node {key}: {value}")

    send_cmd(ser, 'log start', wait=1.0)
    print("Hub kører — dumper log hvert 5. minut...")

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Henter log fra RAK4631...")
        send_cmd(ser, 'log', wait=0.5)
        lines = read_until_prompt(ser, timeout=10)
        print(f"  → {len(lines)} linjer modtaget")
        parse_and_store_log(lines, db)

        n_lines_raw = []
        send_cmd(ser, 'neighbors', wait=1.0)
        time.sleep(1)
        while ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                n_lines_raw.append(line)

        for line in n_lines_raw:
            if line.startswith('-> ') and ':' in line:
                data = line[3:]
                if data != '-none-':
                    parts = data.split(':')
                    if len(parts) == 3:
                        node_id, ts, snr_x4 = parts
                        snr = int(snr_x4) / 4.0
                        db.execute(
                            'INSERT INTO neighbors (node_id, timestamp, snr) VALUES (?,?,?)',
                            (node_id, ts, snr)
                        )
                        db.commit()

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
