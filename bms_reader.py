import serial
import time
import json
import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Načte konfigurační proměnné ze souboru .env
load_dotenv()

# --- NAČTENÍ KONFIGURACE Z .env ---
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
BAUDRATE = int(os.getenv('BAUDRATE', 115200)) # <--- OPRAVA: Načtení baudrate
BMS_BARCODE = os.getenv('BMS_BARCODE')

MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')

HA_DISCOVERY_PREFIX = os.getenv('HA_DISCOVERY_PREFIX', 'homeassistant')
DEVICE_UNIQUE_ID = os.getenv('DEVICE_UNIQUE_ID', 'pylontech_sc0500')
DEVICE_NAME = os.getenv('DEVICE_NAME', 'Pylontech BMS SC0500')

# --- KONTROLA ZÁKLADNÍ KONFIGURACE ---
if not all([BMS_BARCODE, MQTT_BROKER, MQTT_USER, MQTT_PASSWORD]):
    print("CHYBA: V souboru .env chybí jedna z klíčových hodnot (BMS_BARCODE, MQTT_BROKER, MQTT_USER, MQTT_PASSWORD).")
    exit()

# --- PŘÍKAZY PRO BMS ---
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'


def connect_and_authorize(ser):
    """Naváže spojení s BMS a autorizuje session."""
    ser.read_all()
    print("Posílám příkaz pro login...")
    ser.write(CMD_LOGIN)
    response = ser.read_until(b'pylon_debug>')
    if b'pylon_debug>' not in response: raise ConnectionError("Login se nezdařil.")
    print("Login úspěšný.")
    time.sleep(0.5)

    print(f"Posílám autorizaci s SN: {BMS_BARCODE}...")
    ser.write(CMD_AUTHORIZE)
    response = ser.read_until(b'pylon_debug>')
    if b"pass" not in response: raise ConnectionError("Autorizace selhala!")
    print("Autorizace úspěšná.")
    time.sleep(0.5)

def safe_int(value, default=0):
    try: return int(value)
    except (ValueError, TypeError): return default

def safe_float(value, default=0.0):
    try: return float(value)
    except (ValueError, TypeError): return default

def parse_bms_data(raw_data_str):
    """Zpracuje surový textový výstup z BMS a vrátí strukturovaná data."""
    lines = [line.strip() for line in raw_data_str.strip().splitlines() if line.strip()]
    if len(lines) < 3: return None
    bms_data = {'summary': {}, 'cells': [], 'footer': {}}
    
    header_line, cell_lines, footer_lines = lines[0], lines[1:-2], lines[-2:]
    
    header_parts = [p.strip() for p in header_line.split('#')]
    if len(header_parts) >= 8:
        bms_data['summary'] = {
            'voltage': safe_float(header_parts[0]) / 1000.0,
            'current': safe_float(header_parts[1]) / 1000.0,
            'status': header_parts[4],
        }
    
    for i, line in enumerate(cell_lines):
        cell_parts = [p.strip() for p in line.split('#')]
        if len(cell_parts) >= 2:
            bms_data['cells'].append({ 'id': i + 1, 'voltage': safe_float(cell_parts[0]) / 1000.0 })
            
    if len(footer_lines) == 2:
        bms_data['footer'] = {
            'error_code': safe_int(footer_lines[0].replace('#','')),
            'cycle_count': safe_int(footer_lines[1].replace('#',''))
        }
    return bms_data

def publish_ha_discovery(client):
    """Publikuje konfigurační data pro automatické vytvoření senzorů v HA."""
    print("Publikuji MQTT Discovery konfiguraci pro Home Assistant...")
    
    device_info = {
        "identifiers": [DEVICE_UNIQUE_ID],
        "name": DEVICE_NAME,
        "manufacturer": "Pylontech"
    }

    sensors = {
        "voltage": {"name": "Celkové napětí", "unit": "V", "class": "voltage", "state_class": "measurement"},
        "current": {"name": "Celkový proud", "unit": "A", "class": "current", "state_class": "measurement"},
        "status": {"name": "Stav", "icon": "mdi:information-outline"},
        "cycle_count": {"name": "Počet cyklů", "icon": "mdi:battery-sync", "state_class": "total_increasing"},
        "error_code": {"name": "Chybový kód", "icon": "mdi:alert-circle-outline"},
    }

    # Konfigurace pro souhrnné senzory
    for key, val in sensors.items():
        topic_slug = f"{DEVICE_UNIQUE_ID}_{key}"
        config_payload = {
            "name": f"{DEVICE_NAME} {val['name']}",
            "unique_id": topic_slug,
            "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state",
            "device": device_info
        }
        if "unit" in val: config_payload["unit_of_measurement"] = val["unit"]
        if "class" in val: config_payload["device_class"] = val["class"]
        if "state_class" in val: config_payload["state_class"] = val["state_class"]
        if "icon" in val: config_payload["icon"] = val["icon"]
        
        client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/config", json.dumps(config_payload), retain=True)

    # Konfigurace pro napětí jednotlivých článků
    for i in range(1, 76):
        topic_slug = f"{DEVICE_UNIQUE_ID}_cell_{i}_voltage"
        config_payload = {
            "name": f"{DEVICE_NAME} Článek {i} napětí",
            "unique_id": topic_slug,
            "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state",
            "unit_of_measurement": "V",
            "device_class": "voltage",
            "state_class": "measurement",
            "device": device_info
        }
        client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/config", json.dumps(config_payload), retain=True)

    print("Publikace konfigurace dokončena.")

# --- HLAVNÍ KÓD ---
# OPRAVA: Přidán parametr pro odstranění DeprecationWarning
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

try:
    print(f"Připojuji se k MQTT brokeru na {MQTT_BROKER}...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    publish_ha_discovery(mqtt_client)

    # Hodnota BAUDRATE je nyní správně načtena z .env souboru
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=5)
    print(f"Port {SERIAL_PORT} úspěšně otevřen s rychlostí {BAUDRATE}.")
    
    connect_and_authorize(ser)
    
    print("\n--- Spouštím pravidelné čtení dat a odesílání do HA ---")
    while True:
        ser.write(CMD_GET_DATA)
        response_bytes = ser.read_until(b'Command completed successfully')
        raw_output = response_bytes.decode('ascii', errors='ignore')
        
        clean_output = raw_output.split('@')[-1].replace('getpwr','').strip()
        
        if '#' in clean_output:
            data = parse_bms_data(clean_output)
            if data and data['summary'] and data['footer'] and data['cells']:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Data přijata, odesílám na MQTT.")
                
                # Publikace souhrnných dat
                mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_voltage/state", data['summary']['voltage'])
                mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_current/state", data['summary']['current'])
                mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_status/state", data['summary']['status'])
                
                # Publikace dat z patičky
                mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_cycle_count/state", data['footer']['cycle_count'])
                mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_error_code/state", data['footer']['error_code'])
                
                # Publikace dat jednotlivých článků
                for cell in data['cells']:
                    mqtt_client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_cell_{cell['id']}_voltage/state", cell['voltage'])

        ser.read_until(b'pylon_debug>')
        time.sleep(30)

except Exception as e:
    print(f"Došlo k závažné chybě: {e}")
finally:
    if mqtt_client.is_connected():
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("MQTT spojení uzavřeno.")
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Sériový port uzavřen.")
