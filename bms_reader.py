import serial
import time
import json
import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import threading

# ... (Načítání konfigurace zůstává stejné) ...
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

if not all([BMS_BARCODE, MQTT_BROKER, MQTT_USER, MQTT_PASSWORD]):
    print("CHYBA: V souboru .env chybí jedna z klíčových hodnot.")
    exit()

# ... (Všechny funkce a příkazy zůstávají stejné) ...
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'
def connect_and_authorize(ser):
    ser.read_all(); print("Posílám příkaz pro login..."); ser.write(CMD_LOGIN)
    if b'pylon_debug>' not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Login se nezdařil.")
    print("Login úspěšný."); time.sleep(0.5)
    print(f"Posílám autorizaci s SN: {BMS_BARCODE}..."); ser.write(CMD_AUTHORIZE)
    if b"pass" not in ser.read_until(b'pylon_debug>'): raise ConnectionError("Autorizace selhala!")
    print("Autorizace úspěšná."); time.sleep(0.5)
def safe_int(v, d=0): t = int; return t(v) if v else d
def safe_float(v, d=0.0): t = float; return t(v) if v else d
def parse_bms_data(s):
    lines = [l.strip() for l in s.strip().splitlines() if l.strip()]
    if len(lines) < 3: return None
    d = {'summary': {}, 'cells': [], 'footer': {}}
    h, c, f = lines[0], lines[1:-2], lines[-2:]
    hp = [p.strip() for p in h.split('#')]
    if len(hp) >= 8: d['summary'] = {'voltage': safe_float(hp[0])/1000.0, 'current': safe_float(hp[1])/1000.0, 'status': hp[4]}
    for i, l in enumerate(c):
        cp = [p.strip() for p in l.split('#')]
        if len(cp) >= 2: d['cells'].append({'id': i+1, 'voltage': safe_float(cp[0])/1000.0})
    if len(f) == 2: d['footer'] = {'error_code': safe_int(f[0].replace('#','')), 'cycle_count': safe_int(f[1].replace('#',''))}
    return d
def publish_ha_discovery(c):
    print("Publikuji MQTT Discovery konfiguraci..."); d = {"identifiers": [DEVICE_UNIQUE_ID], "name": DEVICE_NAME, "manufacturer": "Pylontech"}
    s = {"voltage": {"n": "Celkové napětí", "u": "V", "c": "voltage"}, "current": {"n": "Celkový proud", "u": "A", "c": "current"}, "status": {"n": "Stav", "i": "mdi:information-outline"}, "cycle_count": {"n": "Počet cyklů", "i": "mdi:battery-sync", "s": "total_increasing"}, "error_code": {"n": "Chybový kód", "i": "mdi:alert-circle-outline"}}
    for k, v in s.items():
        ts = f"{DEVICE_UNIQUE_ID}_{k}"; p = {"name": f"{DEVICE_NAME} {v['n']}", "unique_id": ts, "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{ts}/state", "device": d};
        if "u" in v: p["unit_of_measurement"] = v["u"]
        if "c" in v: p["device_class"] = v["c"]
        if "s" in v: p["state_class"] = v["s"]
        if "i" in v: p["icon"] = v["i"]
        c.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{ts}/config", json.dumps(p), retain=True)
    for i in range(1, 76):
        ts = f"{DEVICE_UNIQUE_ID}_cell_{i}_voltage"; p = {"name": f"{DEVICE_NAME} Článek {i} napětí", "unique_id": ts, "state_topic": f"{HA_DISCOVERY_PREFIX}/sensor/{ts}/state", "unit_of_measurement": "V", "device_class": "voltage", "state_class": "measurement", "device": d}
        c.publish(f"{HA_DISCOVERY_PREFIX}/sensor/{ts}/config", json.dumps(p), retain=True)
    print("Publikace konfigurace dokončena.")

# --- VYLEPŠENÝ HLAVNÍ KÓD S KONTROLOU MQTT ---
connection_event = threading.Event()

def on_connect(client, userdata, flags, rc):
    """Callback pro potvrzení připojení."""
    if rc == 0:
        print("[MQTT] Úspěšně připojeno k brokeru!")
        connection_event.set() # Signalizuje, že jsme připojeni
    else:
        print(f"[MQTT] Připojení selhalo, kód chyby: {rc}. Zkontrolujte jméno, heslo a nastavení brokeru.")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

try:
    print(f"Pokouším se připojit k MQTT brokeru na {MQTT_BROKER}...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    # Čekáme max 10 sekund na úspěšné připojení
    connected = connection_event.wait(timeout=10)
    if not connected:
        raise ConnectionError("Timeout při čekání na připojení k MQTT brokeru.")

    publish_ha_discovery(mqtt_client)

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
            if data and data.get('summary') and data.get('footer') and data.get('cells'):
                print(f"[{time.strftime('%Y-%m-%d %H_M_S')}] Data přijata, odesílám na MQTT.")
                
                # Publikace s kontrolou
                for key, value in data['summary'].items():
                    topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_{key}/state"
                    result = mqtt_client.publish(topic, value)
                    print(f"  > Odesílám na '{topic}': {value} -> {'OK' if result.rc == 0 else 'CHYBA'}")
                
                for key, value in data['footer'].items():
                    topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_{key}/state"
                    result = mqtt_client.publish(topic, value)
                    print(f"  > Odesílám na '{topic}': {value} -> {'OK' if result.rc == 0 else 'CHYBA'}")

                for cell in data['cells']:
                    topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_UNIQUE_ID}_cell_{cell['id']}_voltage/state"
                    result = mqtt_client.publish(topic, cell['voltage'])
                    # Tady nebudeme vypisovat všech 75 řádků, abychom nezahlcovali log
                print(f"  > Odesláno {len(data['cells'])} hodnot napětí článků.")

        ser.read_until(b'pylon_debug>')
        time.sleep(30)

except Exception as e:
    print(f"Došlo k závažné chybě: {e}")
finally:
    if mqtt_client.is_connected():
        mqtt_client.loop_stop(); mqtt_client.disconnect()
        print("MQTT spojení uzavřeno.")
    if 'ser' in locals() and ser.is_open:
        ser.close(); print("Sériový port uzavřen.")
