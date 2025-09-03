import serial
import time
import json
import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import threading

# --- Load configuration from .env file ---
load_dotenv()
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0'); BAUDRATE = int(os.getenv('BAUDRATE', 115200)); BMS_BARCODE = os.getenv('BMS_BARCODE')
MQTT_BROKER = os.getenv('MQTT_BROKER'); MQTT_PORT = int(os.getenv('MQTT_PORT', 1883)); MQTT_USER = os.getenv('MQTT_USER'); MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
HA_DISCOVERY_PREFIX = os.getenv('HA_DISCOVERY_PREFIX', 'homeassistant'); DEVICE_UNIQUE_ID = os.getenv('DEVICE_UNIQUE_ID', 'pylontech_sc0500'); DEVICE_NAME = os.getenv('DEVICE_NAME', 'Pylontech BMS SC0500')
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
if not all([BMS_BARCODE, MQTT_BROKER, MQTT_USER, MQTT_PASSWORD]): print("ERROR: One of the key values is missing in the .env file."); exit()
CMD_LOGIN = b'login debug\n'; CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii'); CMD_GET_DATA = b'getpwr\n'
connection_event = threading.Event()

def connect_and_authorize(ser):
    ser.read_all(); print("Sending login command...")
    if b'pylon_debug>' not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Login failed.")
    print("Login successful."); time.sleep(0.5)
    print(f"Sending authorization with SN: {BMS_BARCODE}..."); ser.write(CMD_AUTHORIZE)
    if b"pass" not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Authorization failed!")
    print("Authorization successful."); time.sleep(0.5)
def safe_int(v, d=0):
    try: return int(v.strip()) if v.strip() else d
    except (ValueError, TypeError): return d
def safe_float(v, d=0.0):
    try: return float(v.strip()) if v.strip() else d
    except (ValueError, TypeError): return d

# --- ZMĚNA 1: Rozšíření parsovací funkce ---
def parse_bms_data(raw_data_str):
    data_lines = [line.strip() for line in raw_data_str.strip().splitlines() if '#' in line]
    if len(data_lines) < 3: return None
    bms_data = {'summary': {}, 'cells': [], 'footer': {}}
    header_line, cell_lines, footer_lines = data_lines[0], data_lines[1:-2], data_lines[-2:]
    
    header_parts = [p.strip() for p in header_line.split('#')]
    if len(header_parts) >= 8:
        bms_data['summary'] = {
            'voltage': safe_float(header_parts[0]) / 1000.0,
            'current': safe_float(header_parts[1]) / 1000.0,
            'avg_temperature': safe_int(header_parts[2]) / 1000.0,
            'capacity': safe_int(header_parts[3]),
            'status': header_parts[4],
            'voltage_status': header_parts[5],
            'current_status': header_parts[6],
            'temperature_status': header_parts[7]
        }
    
    for i, line in enumerate(cell_lines):
        cell_parts = [p.strip() for p in line.split('#')]
        if len(cell_parts) >= 4:
            bms_data['cells'].append({
                'id': i + 1,
                'voltage': safe_float(cell_parts[0]) / 1000.0,
                'temperature': safe_int(cell_parts[1]) / 1000.0,
                'status_1': cell_parts[2],
                'status_2': cell_parts[3]
            })
            
    if len(footer_lines) == 2:
        bms_data['footer'] = {
            'error_code': safe_int(footer_lines[0].replace('#', '')),
            'cycle_count': safe_int(footer_lines[1].replace('#', ''))
        }
    return bms_data

def on_connect(client, userdata, flags, rc):
    if rc == 0: print("[MQTT] Successfully connected to broker!"); connection_event.set()
    else: print(f"[MQTT] Connection failed with code: {rc}. Check credentials and broker settings.")

# --- ZMĚNA 2: Rozšíření definice senzorů ---
def publish_ha_discovery(client):
    print("Publishing MQTT Discovery configuration (in English)...")
    device_info = {"identifiers": [DEVICE_UNIQUE_ID], "name": DEVICE_NAME, "manufacturer": "Pylontech"}
    
    # Rozšířený seznam souhrnných senzorů
    summary_sensors = {
        "voltage": {"n": "Total Voltage", "u": "V", "c": "voltage", "s": "measurement"},
        "current": {"n": "Total Current", "u": "A", "c": "current", "s": "measurement"},
        "avg_temperature": {"n": "Average Temperature", "u": "°C", "c": "temperature", "s": "measurement"},
        "capacity": {"n": "Capacity", "u": "Wh", "c": "energy", "s": "measurement"},
        "status": {"n": "Status", "i": "mdi:information-outline"},
        "voltage_status": {"n": "Voltage Status", "i": "mdi:lightning-bolt"},
        "current_status": {"n": "Current Status", "i": "mdi:current-ac"},
        "temperature_status": {"n": "Temperature Status", "i": "mdi:thermometer"},
        "cycle_count": {"n": "Cycle Count", "i": "mdi:battery-sync", "s": "total_increasing"},
        "error_code": {"n": "Error Code", "i": "mdi:alert-circle-outline"},
    }

    for key, val in summary_sensors.items():
        topic_slug = f"{DEVICE_UNIQUE_ID}_{key}"
        config_payload = {"name": f"{DEVICE_NAME} {val['n']}", "unique_id": topic_slug, "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state", "device": device_info}
        if "u" in val: config_payload["unit_of_measurement"] = val["u"]
        if "c" in val: config_payload["device_class"] = val["c"]
        if "s" in val: config_payload["state_class"] = val["s"]
        if "i" in val: config_payload["icon"] = val["i"]
        client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/config", json.dumps(config_payload), retain=True)

    # Rozšířený seznam senzorů pro každý článek
    cell_sensors = {
        "voltage": {"n": "Voltage", "u": "V", "c": "voltage", "s": "measurement"},
        "temperature": {"n": "Temperature", "u": "°C", "c": "temperature", "s": "measurement"},
        "status_1": {"n": "Status 1", "i": "mdi:list-status"},
        "status_2": {"n": "Status 2", "i": "mdi:list-status"},
    }

    for i in range(1, 76):
        for key, val in cell_sensors.items():
            topic_slug = f"{DEVICE_UNIQUE_ID}_cell_{i}_{key}"
            config_payload = {"name": f"{DEVICE_NAME} Cell {i} {val['n']}", "unique_id": topic_slug, "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/state", "device": device_info}
            if "u" in val: config_payload["unit_of_measurement"] = val["u"]
            if "c" in val: config_payload["device_class"] = val["c"]
            if "s" in val: config_payload["state_class"] = val["s"]
            if "i" in val: config_payload["icon"] = val["i"]
            client.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{topic_slug}/config", json.dumps(config_payload), retain=True)
    
    print("Configuration publishing finished.")

# --- ZMĚNA 3: Rozšíření hlavní smyčky pro odesílání ---
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
try:
    print(f"Attempting to connect to MQTT broker at {MQTT_BROKER}...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    if not connection_event.wait(timeout=10): raise ConnectionError("Timeout while waiting for MQTT broker connection.")
    publish_ha_discovery(mqtt_client)
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=5)
    print(f"Serial port {SERIAL_PORT} opened successfully at {BAUDRATE} baud.")
    connect_and_authorize(ser)
    
    print("\n--- Starting regular data reading and publishing to HA ---")
    while True:
        ser.write(CMD_GET_DATA)
        response_bytes = ser.read_until(b'pylon_debug>')
        raw_output = response_bytes.decode('ascii', errors='ignore')
        data = parse_bms_data(raw_output)
        if data and data.get('summary') and data.get('footer') and data.get('cells'):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Data received, publishing to MQTT.")
            
            # Spojíme souhrn a patičku pro snazší odeslání
            all_summary_data = {**data['summary'], **data['footer']}
            for key, value in all_summary_data.items():
                topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_{key}/state"
                mqtt_client.publish(topic, value)
                if DEBUG_MODE: print(f"  > MQTT | Topic: {topic} | Payload: {value}")

            # Publikace všech dat pro jednotlivé články
            for cell in data['cells']:
                for key, value in cell.items():
                    if key == 'id': continue
                    topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_cell_{cell['id']}_{key}/state"
                    mqtt_client.publish(topic, value)
                    if DEBUG_MODE and key == 'voltage': # Logujeme jen napětí, aby nebyl log zahlcen
                         print(f"  > MQTT | Publishing Cell {cell['id']} data...")

        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Waiting for complete data...")
        time.sleep(30)
except Exception as e:
    print(f"A critical error occurred: {e}")
finally:
    if 'ser' in locals() and ser.is_open: ser.close(); print("Serial port closed.")
    if mqtt_client.is_connected():
        mqtt_client.loop_stop(); mqtt_client.disconnect()
        print("MQTT connection closed.")
