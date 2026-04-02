"""
webserver.py — MeshCore Hub webserver med interaktivt Leaflet-kort

Tilgængelig på http://<RPi-IP>:5000

KONFIGURATION:
  Skift brugernavn og password i de to linjer herunder:
    USERNAME = 'dit_brugernavn'
    PASSWORD = 'dit_password'

  Skift own_id i index()-funktionen til de første 2 hex-tegn
  af din nodes public key (find den med: meshcli -s /dev/ttyACM0 -r → ver)
    own_id = 'XX'  ← erstat XX med dit node-ID
"""

from flask import Flask, Response, request
from functools import wraps
import sqlite3
import requests
import random
import json
from datetime import datetime

app = Flask(__name__)
DB_PATH = '/home/pi/meshcore-hub/meshcore.db'

# ─────────────────────────────────────────
# SKIFT DISSE TO LINJER TIL DIT EGET LOGIN
USERNAME = 'dit_brugernavn'
PASSWORD = 'dit_password'
# ─────────────────────────────────────────

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Login krævet', 401,
                {'WWW-Authenticate': 'Basic realm="MeshCore Hub"'}
            )
        return f(*args, **kwargs)
    return decorated

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
    """Hent kote fra cache eller Open-Meteo API — gemmes lokalt ved første opslag"""
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
                db.execute("UPDATE repeaters SET elevation=? WHERE node_id=?", (elev, node_id))
                db.commit()
            return elev
    except Exception:
        pass
    return None

def estimate_position(node_id, node_map, db):
    """
    Estimér position for noder uden GPS baseret på kommunikationspartnere.
    Bruges automatisk for nye noder der høres i pakkeloggen.
    Estimerede noder vises med grå ? markør og stiplet forbindelseslinje.
    Positionen præciseres ved næste manuelle JSON-import fra MeshCore-appen.
    """
    rows = db.execute('''
        SELECT DISTINCT CASE WHEN hop_from=? THEN hop_to ELSE hop_from END as partner
        FROM paths WHERE (hop_from=? OR hop_to=?) AND contact_id != ?
    ''', (node_id, node_id, node_id, node_id)).fetchall()
    partners = []
    for row in rows:
        partner = row['partner']
        if partner in node_map and node_map[partner].get('lat') and not node_map[partner].get('estimated'):
            partners.append((node_map[partner]['lat'], node_map[partner]['lon']))
    if not partners:
        for nid, node in node_map.items():
            if nid != node_id and node.get('lat') and not node.get('estimated'):
                partners.append((node['lat'], node['lon']))
    if not partners:
        return None, None
    lat = sum(p[0] for p in partners) / len(partners)
    lon = sum(p[1] for p in partners) / len(partners)
    random.seed(node_id)
    lat += random.uniform(-0.06, 0.06)
    lon += random.uniform(-0.06, 0.06)
    return lat, lon

def build_hop_path(db, node_id, own_id):
    """Byg korrekt hop-sti: node → mellemhop → din node"""
    paths = db.execute('''
        SELECT hop_from, hop_to, hop_order FROM paths
        WHERE contact_id=? ORDER BY hop_order ASC
    ''', (node_id,)).fetchall()
    if not paths:
        return None, 0
    clean = []
    for p in paths:
        if not clean:
            clean.append(p['hop_from'])
        clean.append(p['hop_to'])
    seen = set(); deduped = []
    for n in clean:
        if n not in seen:
            seen.add(n); deduped.append(n)
    if own_id in deduped: deduped.remove(own_id)
    deduped.append(own_id)
    if node_id in deduped: deduped.remove(node_id)
    deduped.insert(0, node_id)
    seen = set(); final = []
    for n in deduped:
        if n not in seen:
            seen.add(n); final.append(n)
    named = []
    for nid in final:
        row = db.execute("SELECT name FROM repeaters WHERE node_id=?", (nid,)).fetchone()
        named.append((nid, row['name'] if row and row['name'] else nid))
    return named, len(final) - 1

@app.route('/')
@login_required
def index():
    db = get_db()
    try:
        db.execute("ALTER TABLE repeaters ADD COLUMN elevation REAL")
        db.commit()
    except Exception:
        pass

    own_lat  = float(db.execute("SELECT value FROM node_info WHERE key='lat'").fetchone()[0])
    own_lon  = float(db.execute("SELECT value FROM node_info WHERE key='lon'").fetchone()[0])
    own_name = db.execute("SELECT value FROM node_info WHERE key='name'").fetchone()[0]

    # ─────────────────────────────────────────────────────────────────────
    # SKIFT TIL DE FØRSTE 2 HEX-TEGN AF DIN NODES PUBLIC KEY
    # Find dit node-ID: meshcli -s /dev/ttyACM0 -r → skriv 'ver'
    # Eksempel: hvis public key starter med '59b3...' så er own_id = '59'
    own_id = 'XX'
    # ─────────────────────────────────────────────────────────────────────

    repeaters = db.execute('''
        SELECT node_id,
               CASE WHEN seen_count > 0 THEN last_snr  ELSE NULL END as last_snr,
               CASE WHEN seen_count > 0 THEN last_rssi ELSE NULL END as last_rssi,
               seen_count, first_seen, last_seen, lat, lon, name, elevation
        FROM repeaters
    ''').fetchall()

    node_map = {}
    for r in repeaters:
        has_gps = bool(r['lat'] and r['lat'] != 0 and r['lon'] and r['lon'] != 0)
        node_map[r['node_id']] = {
            'node_id': r['node_id'], 'last_snr': r['last_snr'],
            'last_rssi': r['last_rssi'], 'seen_count': r['seen_count'] or 0,
            'first_seen': r['first_seen'], 'last_seen': r['last_seen'],
            'lat': r['lat'] if has_gps else None,
            'lon': r['lon'] if has_gps else None,
            'name': r['name'] or r['node_id'],
            'elevation': r['elevation'], 'estimated': False, 'has_gps': has_gps
        }

    node_map[own_id] = {
        'node_id': own_id, 'lat': own_lat, 'lon': own_lon, 'name': own_name,
        'last_snr': None, 'last_rssi': None, 'seen_count': 0,
        'first_seen': None, 'last_seen': None, 'elevation': None,
        'estimated': False, 'has_gps': True
    }

    estimated_count = 0; no_pos_count = 0
    for node_id in list(node_map.keys()):
        node = node_map[node_id]
        if not node['lat'] and node_id != own_id:
            est_lat, est_lon = estimate_position(node_id, node_map, db)
            if est_lat:
                node_map[node_id]['lat'] = est_lat
                node_map[node_id]['lon'] = est_lon
                node_map[node_id]['estimated'] = True
                estimated_count += 1
            else:
                no_pos_count += 1

    all_path_rows = []
    for row in db.execute('SELECT p.hop_from, p.hop_to, COUNT(*) as c FROM paths p GROUP BY p.hop_from, p.hop_to').fetchall():
        all_path_rows.append(row)
    for row in db.execute('SELECT hop_from, ? as hop_to, COUNT(*) as c FROM paths WHERE hop_to=? GROUP BY hop_from', (own_id, own_id)).fetchall():
        all_path_rows.append(row)
    for row in db.execute('SELECT ? as hop_from, hop_to, COUNT(*) as c FROM paths WHERE hop_from=? GROUP BY hop_to', (own_id, own_id)).fetchall():
        all_path_rows.append(row)

    lines_data = []
    drawn = set()
    for row in all_path_rows:
        hop_from = row[0]; hop_to = row[1]; count = row[2]
        fn = node_map.get(hop_from); tn = node_map.get(hop_to)
        if not fn or not tn or not fn.get('lat') or not tn.get('lat'):
            continue
        key = tuple(sorted([hop_from, hop_to]))
        if key in drawn: continue
        drawn.add(key)
        estimated_line = fn.get('estimated') or tn.get('estimated')
        if count >= 30:   lc = '#0033cc'; w = 6
        elif count >= 15: lc = '#0066ff'; w = 5
        elif count >= 7:  lc = '#3399ff'; w = 4
        elif count >= 3:  lc = '#66bbff'; w = 3
        else:             lc = '#99ddff'; w = 2
        lines_data.append({
            'from': hop_from, 'to': hop_to, 'count': count,
            'color': lc, 'weight': w, 'dashed': estimated_line,
            'from_lat': fn['lat'], 'from_lon': fn['lon'],
            'to_lat': tn['lat'], 'to_lon': tn['lon'],
            'from_name': fn['name'], 'to_name': tn['name']
        })

    nodes_data = []
    for node_id, node in node_map.items():
        if not node.get('lat'): continue
        snr = node['last_snr']; rssi = node['last_rssi']
        seen_count = node['seen_count']
        elevation = node['elevation']
        estimated = node['estimated']
        has_gps = node['has_gps']

        if not estimated and elevation is None:
            elevation = get_elevation(node['lat'], node['lon'], db, node_id)

        hop_path_html = ''
        if node_id != own_id:
            named, hop_count = build_hop_path(db, node_id, own_id)
            if named:
                hop_path_html = f"<hr style='margin:4px 0'><b>Rute til din node ({hop_count} hop):</b><br>"
                for i, (nid, nname) in enumerate(named):
                    prefix = "🔵" if i == 0 else ("⭐" if i == len(named)-1 else "↓")
                    hop_path_html += f"{prefix} {nname} ({nid})<br>"

        popup_lines = [f"<b style='font-size:13px'>{node['name']}</b>", f"ID: {node_id}"]
        if estimated: popup_lines.append("⚠️ GPS mangler — estimeret position")
        if snr  is not None: popup_lines.append(f"SNR: {snr:.1f} dB")
        if rssi is not None: popup_lines.append(f"RSSI: {rssi} dBm")
        if seen_count > 0:   popup_lines.append(f"Pakker via din repeater: {seen_count}")
        if not estimated and elevation is not None:
            popup_lines.append(f"Kote: {elevation:.0f} m.o.h.")
        if has_gps: popup_lines.append(f"GPS: {node['lat']:.5f}, {node['lon']:.5f}")

        popup_html = "<div style='font-family:monospace;font-size:11px;min-width:220px;max-width:350px;line-height:1.6'>"
        popup_html += "<br>".join(popup_lines)
        popup_html += hop_path_html
        popup_html += "<hr style='margin:4px 0'>"
        if node['last_seen']:  popup_html += f"Sidst hørt: {str(node['last_seen'])[:16]}<br>"
        if node['first_seen']: popup_html += f"Første gang: {str(node['first_seen'])[:16]}<br>"
        popup_html += "</div>"

        color = snr_to_color(snr)
        if node_id == own_id:     marker_color = 'black'
        elif estimated:           marker_color = 'gray_question'
        elif snr is None:         marker_color = 'gray'
        elif snr >= 5:            marker_color = 'green'
        elif snr >= 0:            marker_color = 'lightgreen'
        elif snr >= -5:           marker_color = 'orange'
        else:                     marker_color = 'red'

        nodes_data.append({
            'id': node_id, 'lat': node['lat'], 'lon': node['lon'],
            'name': node['name'], 'popup': popup_html,
            'color': marker_color, 'snr': snr, 'snr_color': color,
            'estimated': estimated, 'is_own': node_id == own_id
        })

    status_parts = [
        f'Opdateret: {datetime.now().strftime("%H:%M:%S")}',
        f'{len([n for n in node_map.values() if n.get("lat")])} noder',
        f'{len(drawn)} forbindelser',
    ]
    if estimated_count: status_parts.append(f'{estimated_count} estimeret pos.')
    if no_pos_count:    status_parts.append(f'{no_pos_count} uden pos.')

    db.close()

    nodes_json = json.dumps(nodes_data, ensure_ascii=False)
    lines_json = json.dumps(lines_data, ensure_ascii=False)
    status_text = ' | '.join(status_parts)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MeshCore Hub</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  body {{ margin:0; padding:0; }}
  #map {{ width:100vw; height:100vh; }}
  .status-box {{
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: rgba(255,255,255,0.92); padding: 5px 12px;
    border-radius: 5px; border: 1px solid #ccc;
    font-family: monospace; font-size: 12px; z-index: 1000;
    pointer-events: none;
  }}
  .reset-btn {{
    position: fixed; top: 10px; right: 10px;
    background: #2E5DA6; color: white; border: none;
    padding: 8px 14px; border-radius: 5px; cursor: pointer;
    font-size: 12px; z-index: 1000; display: none;
  }}
  .reset-btn:hover {{ background: #1A3A6B; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="status-box">{status_text}</div>
<button class="reset-btn" id="resetBtn" onclick="resetHighlight()">⟳ Vis alle forbindelser</button>
<script>
var map = L.map('map').setView([{own_lat}, {own_lon}], 9);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors'
}}).addTo(map);

var nodesData = {nodes_json};
var linesData = {lines_json};
var allPolylines = [];
var nodePolylines = {{}};
var selectedNode = null;

linesData.forEach(function(l) {{
    var opts = {{ color: l.color, weight: l.weight, opacity: 0.85 }};
    if (l.dashed) opts.dashArray = '8';
    var line = L.polyline([[l.from_lat, l.from_lon],[l.to_lat, l.to_lon]], opts);
    var tip = '<b>' + l.from_name + ' (' + l.from + ') ↔ ' + l.to_name + ' (' + l.to + ')</b><br>Forbindelser: ' + l.count;
    if (l.dashed) tip += '<br>⚠️ Estimeret position';
    line.bindTooltip(tip);
    line.addTo(map);
    var lineObj = {{line: line, from: l.from, to: l.to, origWeight: l.weight}};
    allPolylines.push(lineObj);
    if (!nodePolylines[l.from]) nodePolylines[l.from] = [];
    if (!nodePolylines[l.to])   nodePolylines[l.to]   = [];
    nodePolylines[l.from].push(lineObj);
    nodePolylines[l.to].push(lineObj);
}});

function highlightNode(nodeId) {{
    selectedNode = nodeId;
    document.getElementById('resetBtn').style.display = 'block';
    allPolylines.forEach(function(lo) {{
        var isRelated = nodePolylines[nodeId] && nodePolylines[nodeId].indexOf(lo) >= 0;
        if (isRelated) {{
            lo.line.setStyle({{opacity: 1, weight: lo.origWeight * 1.6}});
            lo.line.bringToFront();
        }} else {{
            lo.line.setStyle({{opacity: 0.05, weight: lo.origWeight}});
        }}
    }});
}}

function resetHighlight() {{
    selectedNode = null;
    document.getElementById('resetBtn').style.display = 'none';
    allPolylines.forEach(function(lo) {{
        lo.line.setStyle({{opacity: 0.85, weight: lo.origWeight}});
    }});
}}

nodesData.forEach(function(n) {{
    var iconHtml, iconSize;
    if (n.is_own) {{
        iconHtml = '<div style="background:#222;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 6px rgba(0,0,0,0.4)">⭐</div>';
        iconSize = [28, 28];
    }} else if (n.color === 'gray_question') {{
        iconHtml = '<div style="background:#888;border-radius:50% 50% 50% 0;transform:rotate(-45deg);width:26px;height:26px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 4px rgba(0,0,0,0.3)"><span style="transform:rotate(45deg);color:white;font-size:14px;font-weight:bold">?</span></div>';
        iconSize = [26, 26];
    }} else {{
        var colors = {{'green':'#22aa22','lightgreen':'#88cc00','orange':'#ff8800','red':'#cc2222','gray':'#888888'}};
        var bg = colors[n.color] || '#888';
        iconHtml = '<div style="background:' + bg + ';border-radius:50% 50% 50% 0;transform:rotate(-45deg);width:26px;height:26px;box-shadow:0 2px 4px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center">' +
            '<svg style="transform:rotate(45deg)" width="14" height="14" viewBox="0 0 14 14" fill="white">' +
            '<rect x="6" y="1" width="2" height="12"/><rect x="4" y="3" width="6" height="2"/>' +
            '<rect x="4" y="6" width="5" height="2"/><rect x="4" y="9" width="4" height="2"/>' +
            '</svg></div>';
        iconSize = [26, 26];
    }}

    var icon = L.divIcon({{html: iconHtml, iconSize: iconSize, iconAnchor: [iconSize[0]/2, iconSize[1]], className: ''}});
    var marker = L.marker([n.lat, n.lon], {{icon: icon}});
    marker.bindPopup(n.popup, {{maxWidth: 380}});
    marker.bindTooltip(n.name + ' (' + n.id + ')', {{sticky: false}});

    if (!n.is_own) {{
        marker.on('click', function(e) {{ highlightNode(n.id); }});
    }} else {{
        marker.on('click', function() {{ resetHighlight(); }});
    }}
    marker.addTo(map);

    if (n.snr !== null && !n.estimated) {{
        var snrLabel = L.divIcon({{
            html: '<div style="font-size:9px;color:' + n.snr_color + ';font-weight:bold;white-space:nowrap;margin-top:2px;margin-left:5px">' +
                  (n.snr >= 0 ? '+' : '') + n.snr.toFixed(1) + 'dB</div>',
            iconSize: [60, 16], iconAnchor: [0, 0], className: ''
        }});
        L.marker([n.lat, n.lon], {{icon: snrLabel, interactive: false}}).addTo(map);
    }}
}});

map.on('click', function() {{ if (selectedNode) resetHighlight(); }});
</script>
</body>
</html>"""

    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
