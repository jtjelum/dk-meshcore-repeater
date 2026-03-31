"""
webserver.py — MeshCore Hub webserver med interaktivt Folium-kort
Tilgængelig på http://<RPi-IP>:5000
"""
from flask import Flask
import folium
import sqlite3
import requests
from datetime import datetime

app = Flask(__name__)
DB_PATH = '/home/pi/meshcore-hub/meshcore.db'

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def snr_to_color(snr):
    if snr is None: return '#888888'
    if snr >= 5:   return '#00cc00'
    if snr >= 0:   return '#88cc00'
    if snr >= -5:  return '#ffaa00'
    if snr >= -10: return '#ff6600'
    return '#cc0000'

def get_elevation(lat, lon, db, node_id):
    """Hent kote fra cache eller Open-Meteo API med timeout"""
    cached = db.execute(
        "SELECT elevation FROM repeaters WHERE node_id=?", (node_id,)
    ).fetchone()
    if cached and cached[0] is not None:
        return cached[0]
    try:
        r = requests.get(
            f'https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}',
            timeout=3
        )
        if r.ok:
            elev = r.json().get('elevation', [None])[0]
            if elev is not None:
                db.execute(
                    "UPDATE repeaters SET elevation=? WHERE node_id=?",
                    (elev, node_id)
                )
                db.commit()
            return elev
    except Exception:
        pass
    return None

def build_hop_path(db, node_id, own_id):
    """Byg korrekt hop-sti: node → mellemhop → din node"""
    paths = db.execute('''
        SELECT hop_from, hop_to, hop_order
        FROM paths
        WHERE contact_id = ?
        ORDER BY hop_order ASC
    ''', (node_id,)).fetchall()

    if not paths:
        return None

    clean = []
    for p in paths:
        if not clean:
            clean.append(p['hop_from'])
        clean.append(p['hop_to'])

    seen = set()
    deduped = []
    for n in clean:
        if n not in seen:
            seen.add(n)
            deduped.append(n)

    if own_id in deduped:
        deduped.remove(own_id)
    deduped.append(own_id)

    if node_id in deduped:
        deduped.remove(node_id)
    deduped.insert(0, node_id)

    seen = set()
    final = []
    for n in deduped:
        if n not in seen:
            seen.add(n)
            final.append(n)

    named = []
    for nid in final:
        row = db.execute(
            "SELECT name FROM repeaters WHERE node_id=?", (nid,)
        ).fetchone()
        name = row['name'] if row and row['name'] else nid
        named.append((nid, name))

    hop_count = len(final) - 1
    return named, hop_count

@app.route('/')
def index():
    db = get_db()

    # Tilføj elevation kolonne hvis den ikke findes
    try:
        db.execute("ALTER TABLE repeaters ADD COLUMN elevation REAL")
        db.commit()
    except Exception:
        pass

    own_lat  = float(db.execute("SELECT value FROM node_info WHERE key='lat'").fetchone()[0])
    own_lon  = float(db.execute("SELECT value FROM node_info WHERE key='lon'").fetchone()[0])
    own_name = db.execute("SELECT value FROM node_info WHERE key='name'").fetchone()[0]
    own_id   = '59'  # Erstat med de første 2 hex-tegn af din nodes public key

    repeaters = db.execute('''
        SELECT node_id,
               CASE WHEN seen_count > 0 THEN last_snr  ELSE NULL END as last_snr,
               CASE WHEN seen_count > 0 THEN last_rssi ELSE NULL END as last_rssi,
               seen_count,
               first_seen, last_seen,
               lat, lon, name, elevation
        FROM repeaters
        WHERE lat IS NOT NULL AND lat != 0 AND lon IS NOT NULL AND lon != 0
    ''').fetchall()

    node_map = {}
    for r in repeaters:
        node_map[r['node_id']] = dict(r)

    node_map[own_id] = {
        'node_id': own_id, 'lat': own_lat, 'lon': own_lon,
        'name': own_name, 'last_snr': None, 'last_rssi': None,
        'seen_count': 0, 'first_seen': None, 'last_seen': None,
        'elevation': None
    }

    all_paths = []
    rows = db.execute('''
        SELECT p.hop_from, p.hop_to, COUNT(*) as c
        FROM paths p
        WHERE p.hop_from IN (SELECT node_id FROM repeaters WHERE lat IS NOT NULL AND lat != 0)
          AND p.hop_to   IN (SELECT node_id FROM repeaters WHERE lat IS NOT NULL AND lat != 0)
        GROUP BY p.hop_from, p.hop_to
    ''').fetchall()
    all_paths.extend(rows)

    rows_own = db.execute('''
        SELECT hop_from, ? as hop_to, COUNT(*) as c
        FROM paths WHERE hop_to=?
          AND hop_from IN (SELECT node_id FROM repeaters WHERE lat IS NOT NULL AND lat != 0)
        GROUP BY hop_from
    ''', (own_id, own_id)).fetchall()
    all_paths.extend(rows_own)

    rows_from = db.execute('''
        SELECT ? as hop_from, hop_to, COUNT(*) as c
        FROM paths WHERE hop_from=?
          AND hop_to IN (SELECT node_id FROM repeaters WHERE lat IS NOT NULL AND lat != 0)
        GROUP BY hop_to
    ''', (own_id, own_id)).fetchall()
    all_paths.extend(rows_from)

    m = folium.Map(location=[own_lat, own_lon], zoom_start=9, tiles='OpenStreetMap')

    drawn = set()
    line_count = 0
    for row in all_paths:
        hop_from = row[0]; hop_to = row[1]; count = row[2]
        fn = node_map.get(hop_from)
        tn = node_map.get(hop_to)
        if not fn or not tn:
            continue
        key = tuple(sorted([hop_from, hop_to]))
        if key in drawn:
            continue
        drawn.add(key)
        line_count += 1

        fn_name = fn['name'] or hop_from
        tn_name = tn['name'] or hop_to

        if count >= 30:   lc = '#0033cc'; w = 6
        elif count >= 15: lc = '#0066ff'; w = 5
        elif count >= 7:  lc = '#3399ff'; w = 4
        elif count >= 3:  lc = '#66bbff'; w = 3
        else:             lc = '#99ddff'; w = 2

        tip = f"<b>{fn_name} ({hop_from}) ↔ {tn_name} ({hop_to})</b><br>Forbindelser: {count}"

        folium.PolyLine(
            [[fn['lat'], fn['lon']], [tn['lat'], tn['lon']]],
            color='#ffffff', weight=20, opacity=0.001, tooltip=tip
        ).add_to(m)
        folium.PolyLine(
            [[fn['lat'], fn['lon']], [tn['lat'], tn['lon']]],
            color=lc, weight=w, opacity=0.85, tooltip=tip
        ).add_to(m)

    folium.Marker(
        location=[own_lat, own_lon],
        tooltip=f"<b>⭐ {own_name}</b><br>DIN NODE",
        icon=folium.Icon(color='black', icon='star')
    ).add_to(m)

    for node_id, node in node_map.items():
        if node_id == own_id:
            continue

        snr        = node['last_snr']
        rssi       = node['last_rssi']
        seen_count = node['seen_count'] or 0
        first_seen = node['first_seen']
        last_seen  = node['last_seen']
        name       = node['name'] or node_id
        lat        = node['lat']
        lon        = node['lon']
        elevation  = node['elevation']
        color      = snr_to_color(snr)

        if elevation is None:
            elevation = get_elevation(lat, lon, db, node_id)

        hop_result = build_hop_path(db, node_id, own_id)

        lines = [
            f"<b style='font-size:13px'>{name}</b>",
            f"ID: {node_id}"
        ]

        if snr  is not None: lines.append(f"SNR: {snr:.1f} dB")
        if rssi is not None: lines.append(f"RSSI: {rssi} dBm")
        if seen_count > 0:   lines.append(f"Pakker via din repeater: {seen_count}")
        if elevation is not None: lines.append(f"Kote: {elevation:.0f} m.o.h.")
        if lat and lon:      lines.append(f"GPS: {lat:.5f}, {lon:.5f}")

        if hop_result:
            named, hop_count = hop_result
            lines.append("<hr style='margin:4px 0'>")
            lines.append(f"<b>Rute til din node ({hop_count} hop):</b>")
            for i, (nid, nname) in enumerate(named):
                if i == 0:
                    prefix = "🔵"
                elif i == len(named) - 1:
                    prefix = "⭐"
                else:
                    prefix = "↓"
                lines.append(f"{prefix} {nname} ({nid})")

        lines.append("<hr style='margin:4px 0'>")
        if last_seen:  lines.append(f"Sidst hørt: {str(last_seen)[:16]}")
        if first_seen: lines.append(f"Første gang: {str(first_seen)[:16]}")

        tooltip_html = (
            "<div style='font-family:monospace;font-size:11px;"
            "min-width:220px;max-width:350px;line-height:1.6'>"
            + "<br>".join(lines)
            + "</div>"
        )

        if snr is None:
            icon = folium.Icon(color='gray', icon='signal', prefix='fa')
        elif snr >= 5:
            icon = folium.Icon(color='green', icon='signal', prefix='fa')
        elif snr >= 0:
            icon = folium.Icon(color='lightgreen', icon='signal', prefix='fa')
        elif snr >= -5:
            icon = folium.Icon(color='orange', icon='signal', prefix='fa')
        else:
            icon = folium.Icon(color='red', icon='signal', prefix='fa')

        folium.Marker(
            location=[lat, lon],
            tooltip=folium.Tooltip(tooltip_html, sticky=True),
            popup=folium.Popup(tooltip_html, max_width=380),
            icon=icon
        ).add_to(m)

        if snr is not None:
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:9px;color:{color};font-weight:bold;'
                         f'white-space:nowrap;margin-top:18px;margin-left:5px">'
                         f'{snr:+.1f}dB</div>',
                    icon_size=(60, 20), icon_anchor=(0, 0)
                )
            ).add_to(m)

    folium.Marker(
        location=[own_lat + 0.001, own_lon + 0.001],
        icon=folium.DivIcon(
            html=f'<div style="background:rgba(255,255,255,0.9);padding:4px 8px;'
                 f'border-radius:4px;font-size:11px;border:1px solid #ccc">'
                 f'Opdateret: {datetime.now().strftime("%H:%M:%S")} | '
                 f'{len(node_map)-1} noder | {line_count} forbindelser</div>',
            icon_size=(300, 30)
        )
    ).add_to(m)

    db.close()
    return m._repr_html_()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
