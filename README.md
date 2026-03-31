# dk-meshcore-repeater

**MeshCore LoRa repeater nodes på Raspberry Pi — Værløse, Danmark**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Frequency](https://img.shields.io/badge/Frequency-869.618%20MHz-blue)](README.md)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red)](README.md)
[![Hardware](https://img.shields.io/badge/Core-RAK4631-green)](README.md)

Opsætning af to MeshCore repeater-noder i Værløse-området baseret på RAK4631 WisBlock og Raspberry Pi. Projektet dækker hardware-konfiguration, RF-kæde, radioparametre og netværksvisualisering via Python/Folium.

Beregnet til at kunne genbruges af andre i det danske LoRa-miljø — særligt RF-kæden og de lovlige frekvensparametre er dokumenteret grundigt.

> **Generisk opsætning:** Selvom denne opsætning bruger RAK4631 som primær hardware, er konfiguration og scripts designet til at fungere med andre MeshCore-kompatible boards. Tilpas seriel port og evt. pin-konfiguration i `config.yaml`.

### Kompatible boards

Følgende boards er bekræftet kompatible med MeshCore-firmware og kan bruges med denne opsætning. For den komplette og opdaterede liste, se [MeshCore Web Flasher](https://flasher.meshcore.co.uk).

| Board                        | MCU           | LoRa-chip | Formfaktor        | Bemærkning                            |
|------------------------------|---------------|-----------|-------------------|---------------------------------------|
| RAK4631 (WisBlock)           | nRF52840      | SX1262    | Modulært          | Bruges i dette projekt                |
| Heltec WiFi LoRa 32 V3       | ESP32-S3      | SX1262    | Dev-board m. OLED | Billigste indgang til MeshCore        |
| Heltec Wireless Tracker      | ESP32-S3      | SX1262    | Dev-board m. GPS  |                                       |
| Heltec T114                  | nRF52840      | SX1262    | Kompakt           | Lavt strømforbrug                     |
| LilyGO T-Beam (SX1262)       | ESP32         | SX1262    | Alt-i-én m. GPS   | Indbygget 18650-holder                |
| LilyGO T-Beam Supreme        | ESP32-S3      | SX1262    | Alt-i-én m. GPS   |                                       |
| LilyGO T-Deck / T-Deck Plus  | ESP32-S3      | SX1262    | Standalone m. tft | Kræver ikke smartphone                |
| LilyGO T-Pager               | ESP32-S3      | SX1262    | Standalone        |                                       |
| Seeed Studio T1000-E         | nRF52840      | LR1110    | Kompakt tracker   |                                       |
| Seeed XIAO S3 + Wio-SX1262   | ESP32-S3      | SX1262    | Meget kompakt     | Plug-and-play add-on                  |
| Seeed XIAO C3 + Wio-SX1262   | ESP32-C3      | SX1262    | Meget kompakt     |                                       |
| Station G2                   | ESP32-S3      | SX1262    | Standalone        |                                       |
| Nano G2 Ultra                | nRF52840      | SX1262    | Kompakt           |                                       |
| Waveshare RP2040 LoRa        | RP2040        | SX1262    | Dev-board         |                                       |

> **Note om LoRa-chip:** Opsætningen er primært testet med SX1262. Boards med SX1276 kan fungere, men brug da den matchende firmware-variant fra flasheren.

---

## Noder

| Node-ID       | Placering                        | Type     | Højde            |
|---------------|----------------------------------|----------|------------------|
| DK_3500_JT    | Hjemmenode, Værløse              | Repeater | Indendørs        |
| DK_3500_TT    | Udendørs rooftop, Engstedet 28   | Repeater | ~2,5 m elevation |

---

## Hardware

### RF-kæde (DK_3500_TT — udendørs node)

| Komponent       | Model                  | Spec / Note                           |
|-----------------|------------------------|---------------------------------------|
| WisBlock Core   | RAK4631                | nRF52840 + SX1262, WisBlock slot      |
| Intern connector| U.FL pigtail           | U.FL til SMA                          |
| Bandpassfilter  | BPF868M                | Undertrykkelse af støj uden for båndet|
| Kabel           | Delock 88897 RG-142    | 1 m, lavt tab                         |
| Antenne         | Delock 12504           | 8 dBi vertikal, ~2,5 m elevation      |

Rækkefølge: `RAK4631 → U.FL pigtail → BPF868M → RG-142 (1m) → 8 dBi antenne`

Bandpassfilteret sidder umiddelbart efter SMA-udgangen fra RAK4631 og reducerer interferens fra nærliggende GSM/LTE-signaler. RG-142 er valgt for lav dæmpning og mekanisk robusthed til udendørs brug.

### Raspberry Pi

Begge noder kører på Raspberry Pi (model specificeret per node i `config/`). RAK4631 tilsluttes via USB til Pi'en, som kører MeshCore-klienten og logger trafik.

---

## Radio-konfiguration

### Preset

| Parameter     | Værdi              |
|---------------|--------------------|
| Preset        | Switzerland Narrow |
| Frekvens      | 869,618 MHz        |
| Spreading Factor | SF8             |
| Båndbredde    | 62,5 kHz           |
| Sendeeffekt   | 22 dBm             |

### Lovgivningsmæssig baggrund

Frekvensen 869,618 MHz befinder sig inden for **SRD Band 7** (869,4–869,65 MHz) som defineret i ETSI EN 300 220. Gældende begrænsninger for Danmark:

- Maks. sendeeffekt: **25 mW ERP** (≈ 14 dBm ERP; bemærk at 22 dBm er EIRP fra SX1262 — kontrollér effektivt ERP med din antennes gain og kabeltab)
- Duty cycle: **maks. 10%**
- Ingen individuel licens krævet (license-exempt under Erhvervsstyrelsens bekendtgørelse om amatørradio og SRD-frekvenser)

> **Bemærk:** Kontrollér altid gældende nationale regler via [Erhvervsstyrelsen](https://www.erst.dk) og ETSI EN 300 220-3 inden deployment.

---

## Software / Raspberry Pi

### Forudsætninger

- Raspberry Pi OS (Bullseye eller nyere anbefales)
- Python 3.9+
- MeshCore-firmware flashet på RAK4631 (se [MeshCore GitHub](https://github.com/ripplebiz/MeshCore))
- Følgende Python-pakker: `folium`, `json` (stdlib)

```bash
pip install folium
```

### Installation

```bash
git clone https://github.com/dit-brugernavn/dk-meshcore-repeater.git
cd dk-meshcore-repeater
cp config/config.example.yaml config/config.yaml
# Rediger config.yaml med dine node-ID'er og seriel port
```

### Konfigurationsfil

```yaml
# config/config.yaml
node_id: "DK_3500_TT"          # Dit node-ID i MeshCore
serial_port: "/dev/ttyUSB0"    # Tilpas til din Pi
baud_rate: 115200
log_path: "logs/meshcore.log"

radio:
  frequency_mhz: 869.618
  preset: "switzerland_narrow"
  tx_power_dbm: 22
  spreading_factor: 8
  bandwidth_khz: 62.5
```

### Autostart med systemd

Opret `/etc/systemd/system/meshcore.service`:

```ini
[Unit]
Description=MeshCore Repeater Node
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/dk-meshcore-repeater/meshcore_node.py
WorkingDirectory=/home/pi/dk-meshcore-repeater
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable meshcore
sudo systemctl start meshcore
sudo systemctl status meshcore
```

---

## Netværksvisualisering

### meshcore_mapper.py

Scriptet læser en JSON-eksport fra MeshCore-klienten, auto-detekterer dit eget node-ID, estimerer GPS-positioner for noder uden GPS og genererer et interaktivt Folium-kort som HTML-fil.

**Input:** JSON-eksport fra MeshCore (typisk `mesh_export.json`)  
**Output:** `meshcore_map.html` — åbn i en browser

```bash
python3 meshcore_mapper.py --input logs/mesh_export.json --output meshcore_map.html
```

**Funktioner:**
- Auto-detektion af eget node baseret på konfigureret `node_id`
- Farvekodet visning: eget node (blå), kendte repeatere (grøn), ukendte noder (grå)
- RSSI og SNR vises i popup ved klik på node
- Estimeret position for GPS-løse noder baseret på nabonodernes position

### Eksempel-output

*(Indsæt screenshot af kortet her, eller link til en hosted HTML-version)*

---

## Målt rækkevidde og resultater

| Fra node    | Til node    | Afstand | RSSI    | Note                    |
|-------------|-------------|---------|---------|-------------------------|
| DK_3500_TT  | DK_3500_JT  | ~0,5 km | —       | Direkte LOS, intern ref |
| *(tilføj)* | *(tilføj)* | —       | —       | —                       |

*(Opdateres efterhånden som netværket udvides)*

---

## Planlagt

- [ ] Handheld Commander-node (RAK19007 + RAK12500 GPS)
- [ ] Hjemmebygget 4-sektion 868 MHz collinear antenne (~8 dBi, Aircell 7 kabel, fiberglas-hus)
- [ ] Node ved Ammekær 74, Udsholt Strand (sommer-dækning, Gilleleje-området)
- [ ] Automatisk RSSI-logging og tidsseriegraf i `meshcore_mapper.py`

---

## Projektstruktur

```
dk-meshcore-repeater/
├── config/
│   ├── config.example.yaml
│   └── config.yaml            # Ikke i git (se .gitignore)
├── logs/                      # Ikke i git
├── meshcore_node.py           # Hoved-klient
├── meshcore_mapper.py         # Kortgenerering
├── requirements.txt
└── README.md
```

`.gitignore` bør som minimum indeholde:
```
config/config.yaml
logs/
*.log
```

---

## Licens

MIT License — se [LICENSE](LICENSE)

Bidrag og erfaringsdeling fra det danske LoRa-miljø er meget velkomne.
