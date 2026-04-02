# MeshCore Hub

**MeshCore Hub** er et Raspberry Pi-baseret system til automatisk dataindsamling og visualisering af et MeshCore LoRa-netværk.

![MeshCore Hub kort](screenshot.jpg)

---

## Hvad systemet gør

```
RAK4631 / Heltec / LilyGO (MeshCore Repeater firmware)
        │ USB serial
        ▼
Raspberry Pi
  ├── meshcore_hub.py   — Indsamler pakkedata hvert 5. minut → SQLite
  └── webserver.py      — Leaflet-kort tilgængeligt i browser på port 5000
```

### Funktioner

- **Automatisk dataindsamling** fra RAK4631 (og andre boards) via USB serial hvert 5. minut
- **SQLite-database** der vokser over tid med historisk data
- **Interaktivt Leaflet-kort** med login (Basic Auth)
- **Alle repeatere vises** — nye noder dukker automatisk op med estimeret position (grå `?`)
- **Hop-stier** visualiseret geografisk med korrekt rækkefølge
- **Forbindelseslinjer** med tykkelse baseret på aktivitet
- **Fremhævning** ved klik på enkelt repeater — kun dens forbindelser vises
- **Kote (m.o.h.)** hentet automatisk fra Open-Meteo og cachet lokalt
- **SNR/RSSI** farvekodet på markører
- **Estimeret position** for nye noder uden GPS — præciseres ved næste manuelle import
- **Autostart** ved RPi-opstart via systemd

---

## Understøttede boards

| Board | USB port | USB-chip | Ændring i meshcore_hub.py |
|---|---|---|---|
| RAK19007 + RAK4631 | `/dev/ttyACM0` | Native USB | Ingen (standard) |
| Heltec V4 | `/dev/ttyACM0` | Native USB-OTG | Ingen (standard) |
| Heltec V3 | `/dev/ttyUSB0` | CH340 | `SERIAL_PORT = '/dev/ttyUSB0'` |
| Heltec V2 | `/dev/ttyUSB0` | CP2102 | `SERIAL_PORT = '/dev/ttyUSB0'` |
| LilyGO T-Beam | `/dev/ttyUSB0` | CP2102 | `SERIAL_PORT = '/dev/ttyUSB0'` |
| LilyGO T3-S3 | `/dev/ttyUSB0` | CP2102 | `SERIAL_PORT = '/dev/ttyUSB0'` |
| Seeed T1000-E | `/dev/ttyACM0` | Native USB | Ingen (standard) |

---

## Krav

- Raspberry Pi 3 eller nyere
- MicroSD-kort 16 GB+
- USB-strømforsyning 5V/2A
- MeshCore Repeater firmware v1.12+ på dit board
- Python 3.10+

---

## Installation

### 1. Flash Raspberry Pi OS Lite (64-bit)

Brug [Raspberry Pi Imager](https://raspberrypi.com/software) og konfigurér:
- Hostname: `meshcore-hub`
- SSH aktiveret
- WiFi konfigureret

### 2. Installer afhængigheder

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv sqlite3 -y
sudo usermod -a -G dialout pi
sudo reboot
```

### 3. Opret projektmappe og virtuelt miljø

```bash
mkdir ~/meshcore-hub
cd ~/meshcore-hub
python3 -m venv venv
source venv/bin/activate
pip install pyserial flask flask-httpauth folium requests meshcore-cli
```

### 4. Kopiér scripts

```bash
# Fra Windows — kør i PowerShell:
scp meshcore_hub.py pi@meshcore-hub.local:/home/pi/meshcore-hub/
scp webserver.py pi@meshcore-hub.local:/home/pi/meshcore-hub/
scp import_contacts.py pi@meshcore-hub.local:/home/pi/meshcore-hub/
scp import_paths.py pi@meshcore-hub.local:/home/pi/meshcore-hub/
scp fix_import.py pi@meshcore-hub.local:/home/pi/meshcore-hub/
scp meshcore-hub.service pi@meshcore-hub.local:/tmp/
scp meshcore-web.service pi@meshcore-hub.local:/tmp/
```

### 5. Konfigurér scripts

**meshcore_hub.py** — skift port hvis du ikke bruger RAK4631:
```python
SERIAL_PORT = '/dev/ttyACM0'  # Heltec/LilyGO: '/dev/ttyUSB0'
```

**webserver.py** — skift login og node-ID:
```python
USERNAME = 'dit_brugernavn'   # ← skift til dit eget
PASSWORD = 'dit_password'     # ← skift til dit eget
```
Og i `index()`-funktionen:
```python
own_id = 'XX'   # ← de første 2 hex-tegn af din nodes public key
                # Find det med: meshcli -s /dev/ttyACM0 -r → ver
```

### 6. Gem koordinater og start services

```bash
# Gem din nodes GPS-koordinater
sqlite3 ~/meshcore-hub/meshcore.db "INSERT OR REPLACE INTO node_info (key, value) VALUES ('lat', '55.XXXXX');"
sqlite3 ~/meshcore-hub/meshcore.db "INSERT OR REPLACE INTO node_info (key, value) VALUES ('lon', '12.XXXXX');"

# Installér og aktivér services
sudo mv /tmp/meshcore-hub.service /etc/systemd/system/
sudo mv /tmp/meshcore-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable meshcore-hub meshcore-web
sudo systemctl start meshcore-hub meshcore-web
```

Kortet er nu tilgængeligt på: `http://meshcore-hub.local:5000`

---

## Importer kontakter fra MeshCore-appen

For at få præcise GPS-koordinater og hop-stier eksporteres kontaktlisten fra appen:

1. MeshCore-app → Contacts → Eksportér JSON
2. Kopiér til RPi:
```bash
scp "meshcore_discovered_contacts.json" pi@meshcore-hub.local:/home/pi/meshcore-hub/contacts.json
```
3. Kør import:
```bash
cd ~/meshcore-hub && source venv/bin/activate
python3 import_contacts.py
python3 import_paths.py
python3 fix_import.py
sudo systemctl restart meshcore-web
```

> **Tip:** Gentag importen månedligt for at holde koordinater og hop-stier opdaterede.

---

## Kortets markører

| Markør | Betydning |
|---|---|
| ⭐ Sort | Din egen node |
| 🟢 Grøn | SNR ≥ 5 dB |
| 🟡 Gulgrøn | SNR 0–5 dB |
| 🟠 Orange | SNR −5–0 dB |
| 🔴 Rød | SNR < −5 dB |
| ⬜ Grå signal | Ingen SNR-data |
| ❔ Grå ? | Ny node — GPS mangler, estimeret position |

Forbindelseslinjer:
- **Tyk blå** = mange forbindelser
- **Tynd lyseblå** = få forbindelser
- **Stiplet** = en eller begge noder har estimeret position

---

## Nyttige kommandoer

```bash
# Se logs
sudo journalctl -u meshcore-hub -f
sudo journalctl -u meshcore-web -f

# Tjek database
sqlite3 ~/meshcore-hub/meshcore.db "SELECT node_id, name, last_snr, seen_count FROM repeaters ORDER BY seen_count DESC LIMIT 20;"

# Genstart
sudo systemctl restart meshcore-hub meshcore-web
```

---

## Filstruktur

| Fil | Funktion |
|---|---|
| `meshcore_hub.py` | Hoved-script — indsamler pakkedata og gemmer i SQLite |
| `webserver.py` | Flask/Leaflet webserver |
| `import_contacts.py` | Importerer GPS-koordinater fra app-eksport |
| `import_paths.py` | Importerer hop-stier fra app-eksport |
| `fix_import.py` | Retter timestamps og renser falske SNR-værdier |
| `meshcore-hub.service` | systemd service til meshcore_hub.py |
| `meshcore-web.service` | systemd service til webserver.py |

---

## Bemærkninger

**GPS-koordinater** hentes fra manuel eksport af MeshCore-appens kontaktliste. Nye noder der høres i pakkeloggen vises automatisk med estimeret position (grå `?`) indtil næste import.

**Pakkeloggen** fra MeshCore repeater-firmware indeholder ikke GPS-koordinater i tekstformat — koordinater er embedded i binære advert-pakker og kræver manuel import fra appen.

**MeshCore Repeater firmware** understøtter ikke `meshcore_py` (kun companion-firmware). Dataindsamling sker via serial CLI (`log`, `neighbors`, `get`-kommandoer).

---

## Licens

MIT — brug og tilpas frit.
