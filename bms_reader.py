import serial
import time
import json

# --- NASTAVENÍ (CONFIGURATION) ---
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 115200
BMS_BARCODE = 'PPTAP01419B15082'

# --- PŘÍKAZY (COMMANDS) ---
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'

def connect_and_authorize(ser):
    """Naváže spojení a autorizuje session."""
    ser.read_all()
    print("Posílám příkaz pro login...")
    ser.write(CMD_LOGIN)
    response = ser.read_until(b'pylon_debug>')
    if b'pylon_debug>' not in response:
        raise ConnectionError("Login se nezdařil.")
    print("Login úspěšný.")
    time.sleep(0.5)

    print(f"Posílám autorizaci s SN: {BMS_BARCODE}...")
    ser.write(CMD_AUTHORIZE)
    response = ser.read_until(b'pylon_debug>')
    if b"pass" not in response:
        raise ConnectionError("Autorizace selhala!")
    print("Autorizace úspěšná.")
    time.sleep(0.5)

def parse_bms_data(raw_data_str):
    """
    Zpracuje surový textový výstup z BMS a vrátí strukturovaná data.
    """
    lines = raw_data_str.strip().splitlines()
    
    bms_data = {
        'summary': {},
        'cells': [],
        'footer': {}
    }
    
    cell_lines = []
    footer_lines = []
    
    # Rozdělíme řádky na hlavičku, články a patičku
    header_line = lines[0]
    
    # Všechny řádky mezi hlavičkou a patičkou jsou data článků
    # Patička má 2 řádky
    cell_lines = lines[1:-2] 
    footer_lines = lines[-2:]
    
    # Zpracování hlavičky
    header_parts = [p.strip() for p in header_line.split('#') if p.strip()]
    if len(header_parts) >= 8:
        bms_data['summary'] = {
            'voltage_V': float(header_parts[0]) / 1000.0,
            'current_A': float(header_parts[1]) / 1000.0,
            'temperature_avg_C': int(header_parts[2]) / 1000.0, # Hádáme, že je to v C*1000
            'capacity_Wh': int(header_parts[3]),
            'status': header_parts[4],
            'voltage_status': header_parts[5],
            'current_status': header_parts[6],
            'temp_status': header_parts[7]
        }

    # Zpracování článků
    for i, line in enumerate(cell_lines):
        cell_parts = [p.strip() for p in line.split('#') if p.strip()]
        if len(cell_parts) >= 4:
            bms_data['cells'].append({
                'id': i + 1,
                'voltage_V': float(cell_parts[0]) / 1000.0,
                'temperature_C': int(cell_parts[1]) / 1000.0, # Hádáme, že je to v C*1000
                'status_1': cell_parts[2],
                'status_2': cell_parts[3]
            })
            
    # Zpracování patičky
    if len(footer_lines) == 2:
        bms_data['footer'] = {
            'error_code': int(footer_lines[0].replace('#','').strip()),
            'cycle_count': int(footer_lines[1].replace('#','').strip())
        }
        
    return bms_data

# --- HLAVNÍ SMYČKA ---
try:
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=2)
    print(f"Port {SERIAL_PORT} úspěšně otevřen.")
    
    connect_and_authorize(ser)
    
    print("\n--- Spouštím pravidelné čtení dat ---")
    while True:
        ser.write(CMD_GET_DATA)
        response_bytes = ser.read_until(b'Command completed successfully')
        raw_output = response_bytes.decode('ascii', errors='ignore')
        
        # Očistíme surový výstup od příkazů a promptů
        clean_output = raw_output.split('@')[-1]
        clean_output = clean_output.replace('getpwr','').strip()
        
        if '#' in clean_output:
            parsed_data = parse_bms_data(clean_output)
            # Vypíšeme data jako JSON pro snadnou čitelnost
            print(f"--- Data přijata: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            print(json.dumps(parsed_data, indent=2))
        else:
            print("Přijata nekompletní data, čekám na další cyklus.")

        # Vyčistíme zbytek bufferu až po další prompt, abychom byli synchronizovaní
        ser.read_until(b'pylon_debug>')
        time.sleep(10) # Čekáme 10 sekund

except Exception as e:
    print(f"Došlo k chybě: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Sériový port uzavřen.")
