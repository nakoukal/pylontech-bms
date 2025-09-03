import serial
import time
import json
import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import threading

# --- Načtení konfigurace ---
load_dotenv()
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
BAUDRATE = int(os.getenv('BAUDRATE', 115200)) 
BMS_BARCODE = os.getenv('BMS_BARCODE')
MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
HA_DISCOVERY_PREFIX = os.getenv('HA_DISCOVERY_PREFIX', 'homeassistant')
DEVICE_UNIQUE_ID = os.getenv('DEVICE_UNIQUE_ID', 'pylontech_sc0500')
DEVICE_NAME = os.getenv('DEVICE_NAME', 'Pylontech BMS SC0500')
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'

# ... (Všechny funkce kromě publish_ha_discovery zůstávají stejné) ...
if not all([BMS_BARCODE, MQTT_BROKER, MQTT_USER, MQTT_PASSWORD]):
    print("CHYBA: V souboru .env chybí jedna z klíčových hodnot.")
    exit()
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'
connection_event = threading.Event()
def connect_and_authorize(ser):
    ser.read_all(); print("Posílám příkaz pro login..."); ser.write(CMD_LOGIN)
    if b'pylon_debug>' not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Login se nezdařil.")
    print("Login úspěšný."); time.sleep(0.5)
    print(f"Posílám autorizaci s SN: {BMS_BARCODE}..."); ser.write(CMD_AUTHORIZE)
    if b"pass" not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Autorizace selhala!")
    print("Autorizace úspěšná."); time.sleep(0.5)
def safe_int(v, d=0):
    try: return int(v.strip()) if v.strip() else d
    except (ValueError, TypeError): return d
def safe_float(v, d=0.0):
    try: return float(v.strip()) if v.strip() else d
    except (ValueError, TypeError): return d
def parse_bms_data(raw_data_str):
    data_lines = [line.strip() for line in raw_data_str.strip().splitlines() if '#' in line]
    if len(data_lines) < 3:
        if DEBUG_MODE: print(f"[PARSER] Nedostatek datových řádků k parsování. Nalezeno: {len(data_lines)}")
        return None
    bms_data = {'summary': {}, 'cells': [], 'footer': {}}
    header_line, cell_lines, footer_lines = data_lines[0], data_lines[1:-2], data_lines[-2:]
    header_parts = [p.strip() for p in header_line.split('#')]
    if len(header_parts) >= 8:
        bms_data['summary'] = {'voltage': safe_float(header_parts[0])/1000.0, 'current': safe_float(header_parts[1])/1000.0, 'status': header_parts[4]}
    for i, line in enumerate(cell_lines):
        cell_parts = [p.strip() for p in line.split('#')]
        if len(cell_parts) >= 2:
            bms_data['cells'].append({'id': i+1, 'voltage': safe_float(cell_parts[0])/1000.0})
    if len(footer_lines) == 2:
        bms_data['footer'] = {'error_code': safe_int(footer_lines[0].replace('#','')), 'cycle_count': safe_int(footer_lines[1].replace('#',''))}
    return bms_data
def on_connect(client, userdata, flags, rc):
    if rc == 0: print("[MQTT] Úspěšně připojeno k brokeru!"); connection_event.set()
    else: print(f"[MQTT] Připojení selhalo, kód chyby: {rc}.")

# --- UPRAVENÁ FUNKCE S ANGLICKÝMI NÁZVY ---
def publish_ha_discovery(c):
    """Publikuje konfigurační data pro automatické vytvoření senzorů v HA."""
    print("Publikuji MQTT Discovery konfiguraci (v angličtině)..."); 
    device_info = {"identifiers": [DEVICE_UNIQUE_ID], "name": DEVICE_NAME, "manufacturer": "Pylontech"}
    
    # Anglické názvy pro senzory
    sensors = {
        "voltage": {"n": "Total Voltage", "u": "V", "c": "voltage", "s": "measurement"},
        "current": {"n": "Total Current", "u": "A", "c": "current", "s": "measurement"},
        "status": {"n": "Status", "i": "mdi:information-outline"},
        "cycle_count": {"n": "Cycle Count", "i": "mdi:battery-sync", "s": "total_increasing"},
        "error_code": {"n": "Error Code", "i": "mdi:alert-circle-outline"},
    }

    # Konfigurace pro souhrnné senzory
    for key, val in sensors.items():
        topic_slug = f"{DEVICE_UNIQUE_ID}_{key}"
        config_payload = {
            "name": f"{DEVICE_NAME} {val['n']}", # Použití anglického názvu
            "unique_id": topic_slug,
            "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state",
            "device": device_info
        }
        if "u" in val: config_payload["unit_of_measurement"] = val["u"] 
        if "c" in val: config_payload["device_class"] = val["c"]
        if "s" in val: config_payload["state_class"] = val["s"]
        if "i" in val: config_payload["icon"] = val["i"]
        c.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{ts}/config", json.dumps(p), retain=True)

    # Konfigurace pro napětí jednotlivých článků
    for i in range(1, 76):
        topic_slug = f"{DEVICE_UNIQUE_ID}_cell_{i}_voltage"
        config_payload = {
            "name": f"{DEVICE_NAME} Cell {i} Voltage", # Použití anglického názvu
            "unique_id": topic_slug,
            "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state",
            "unit_of_measurement": "V",
            "device_class": "voltage",
            "state_class": "measurement",
            "device": device_info
        }
        c.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/config", json.dumps(config_payload), retain=True)
    
    print("Publikace konfigurace dokončena.")

# --- HLAVNÍ KÓD (beze změny) ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
try:
    print(f"Pokouším se připojit k MQTT brokeru na {MQTT_BROKER}...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    if not connection_event.wait(timeout=10): raise ConnectionError("Timeout při čekání na připojení k MQTT brokeru.")
    publish_ha_discovery(mqtt_client)
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=5)
    print(f"Port {SERIAL_PORT} úspěšně otevřen s rychlostí {BAUDRATE}.")
    connect_and_authorize(ser)
    print("\n--- Spouštím pravidelné čtení dat a odesílání do HA ---")
    while True:
        ser.write(CMD_GET_DATA)
        response_bytes = ser.read_until(b'pylon_debug>')
        raw_output = response_bytes.decode('ascii', errors='ignore')
        data = parse_bms_data(raw_output)
        if data and data.get('summary') and data.get('footer') and data.get('cells'):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Data přijata, odesílám na MQTT.")
            for key, value in data['summary'].items():
                topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_{key}/state"
                mqtt_client.publish(topic, value)
                if DEBUG_MODE: print(f"  > MQTT | Téma: {topic} | Data: {value}")
            for key, value in data['footer'].items():
                topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_{key}/state"
                mqtt_client.publish(topic, value)
                if DEBUG_MODE: print(f"  > MQTT | Téma: {topic} | Data: {value}")
            for cell in data['cells']:
                topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_cell_{cell['id']}_voltage/state"
                mqtt_client.publish(topic, cell['voltage'])
                if DEBUG_MODE: print(f"  > MQTT | Téma: {topic} | Data: {cell['voltage']}")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Čekám na kompletní data...")
        time.sleep(30)
except Exception as e:
    print(f"Došlo k závažné chybě: {e}")
finally:
    if 'ser' in locals() and ser.is_open: ser.close(); print("Sériový port uzavřen.")
    if mqtt_client.is_connected():
        mqtt_client.loop_stop(); mqtt_client.disconnect()
        print("MQTT spojení uzavřeno.")
