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

def safe_int(value, default=0):
    """Bezpečně převede hodnotu na int. Pokud selže, vrátí default."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_float(value, default=0.0):
    """Bezpečně převede hodnotu na float. Pokud selže, vrátí default."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def parse_bms_data(raw_data_str):
    """
    Zpracuje surový textový výstup z BMS a vrátí strukturovaná data.
    """
    # Odfiltrujeme prázdné řádky, které by mohly způsobit chybu
    lines = [line.strip() for line in raw_data_str.strip().splitlines() if line.strip()]
    
    # Zkontrolujeme, zda máme dostatek dat k parsování
    if len(lines) < 3:
        print(f"Nedostatek dat k parsování. Přijato pouze {len(lines)} řádků.")
        return None

    bms_data = {
        'summary': {},
        'cells': [],
        'footer': {}
    }
    
    # Rozdělíme řádky na hlavičku, články a patičku
    header_line = lines[0]
    cell_lines = lines[1:-2] 
    footer_lines = lines[-2:]
    
    # Zpracování hlavičky
    header_parts = [p.strip() for p in header_line.split('#')]
    if len(header_parts) >= 8:
        bms_data['summary'] = {
            'voltage_V': safe_float(header_parts[0]) / 1000.0,
            'current_A': safe_float(header_parts[1]) / 1000.0,
            'temperature_avg_C': safe_int(header_parts[2]) / 1000.0,
            'capacity_Wh': safe_int(header_parts[3]),
            'status': header_parts[4],
            'voltage_status': header_parts[5],
            'current_status': header_parts[6],
            'temp_status': header_parts[7]
        }

    # Zpracování článků
    for i, line in enumerate(cell_lines):
        cell_parts = [p.strip() for p in line.split('#')]
        if len(cell_parts) >= 4:
            bms_data['cells'].append({
                'id': i + 1,
                'voltage_V': safe_float(cell_parts[0]) / 1000.0,
                'temperature_C': safe_int(cell_parts[1]) / 1000.0,
                'status_1': cell_parts[2],
                'status_2': cell_parts[3]
            })
            
    # Zpracování patičky
    if len(footer_lines) == 2:
        bms_data['footer'] = {
            'error_code': safe_int(footer_lines[0].replace('#','')),
            'cycle_count': safe_int(footer_lines[1].replace('#',''))
        }
        
    return bms_data

# --- HLAVNÍ SMYČKA ---
try:
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=5) # Delší timeout pro jistotu
    print(f"Port {SERIAL_PORT} úspěšně otevřen.")
    
    connect_and_authorize(ser)
    
    print("\n--- Spouštím pravidelné čtení dat ---")
    while True:
        ser.write(CMD_GET_DATA)
        # Čekáme na specifický text, který označuje konec datového bloku
        response_bytes = ser.read_until(b'Command completed successfully')
        raw_output = response_bytes.decode('ascii', errors='ignore')
        
        # Očistíme surový výstup
        clean_output = raw_output.split('@')[-1] # Vezmeme text po posledním znaku '@'
        clean_output = clean_output.replace('getpwr','').strip()
        
        if '#' in clean_output:
            parsed_data = parse_bms_data(clean_output)
            if parsed_data: # Zpracujeme data, jen pokud parsování proběhlo OK
                print(f"--- Data přijata: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                print(json.dumps(parsed_data, indent=2))
        else:
            print("Přijata nekompletní data, čekám na další cyklus.")

        # Vyčistíme zbytek bufferu až po další prompt
        ser.read_until(b'pylon_debug>')
        time.sleep(10)

except Exception as e:
    print(f"Došlo k chybě: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Sériový port uzavřen.")
