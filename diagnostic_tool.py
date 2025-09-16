import serial
import time
import os
from dotenv import load_dotenv

# --- Načtení konfigurace (pouze pro připojení) ---
load_dotenv()
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
BAUDRATE = int(os.getenv('BAUDRATE', 115200)) 
BMS_BARCODE = os.getenv('BMS_BARCODE')

# --- Příkazy ---
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'
CMD_GET_INFO = b'info\n'

def connect_and_authorize(ser):
    """Připojí se a autorizuje."""
    ser.read_all()
    print("Sending login command...")
    ser.write(CMD_LOGIN)
    if b'pylon_debug>' not in ser.read_until(b'pylon_debug>'):
        raise ConnectionError("Login failed.")
    print("Login successful.")
    time.sleep(0.5)
    
    print(f"Sending authorization with SN: {BMS_BARCODE}...")
    ser.write(CMD_AUTHORIZE)
    if b"pass" not in ser.read_until(b'pylon_debug>'):
        raise ConnectionError("Authorization failed!")
    print("Authorization successful.")
    time.sleep(0.5)

def get_and_print_module_info(ser):
    """Získá a vypíše mapování logického indexu na sériové číslo."""
    print("\n--- Reading Module Info (command: info) ---")
    ser.write(CMD_GET_INFO)
    response_bytes = ser.read_until(b'pylon_debug>')
    response_str = response_bytes.decode('ascii', errors='ignore')
    
    print("--- Detected Modules (Logical Order) ---")
    current_bmu_index = -1
    for line in response_str.splitlines():
        line = line.strip()
        if line.startswith('BMU'):
            try:
                current_bmu_index = int(line.split()[1])
            except (ValueError, IndexError):
                current_bmu_index = -1
        
        if line.startswith('Module:') and current_bmu_index != -1:
            try:
                barcode = line.split(':', 1)[1].strip()
                if barcode:
                    print(f"  Logical Index (BMU): {current_bmu_index} -> Barcode: {barcode}")
            except IndexError:
                continue
    print("------------------------------------------")

def main():
    """Hlavní funkce pro diagnostiku."""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=15)
        print(f"Serial port {SERIAL_PORT} opened successfully.")
        
        connect_and_authorize(ser)
        
        # Získáme a vypíšeme info o modulech
        get_and_print_module_info(ser)
        
        print("\n--- Starting periodic cell data reading (command: getpwr) ---")
        print("Now you can induce an anomaly (e.g., disconnect a balance connector).")
        
        while True:
            ser.write(CMD_GET_DATA)
            response_bytes = ser.read_until(b'pylon_debug>')
            raw_output = response_bytes.decode('ascii', errors='ignore')
            
            data_lines = [line.strip() for line in raw_output.strip().splitlines() if '#' in line]
            
            print(f"\n--- Data at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            if not data_lines:
                print("No data received.")
            else:
                for i, line in enumerate(data_lines):
                    # Vypíšeme prvních 5 článků z každého 15-článkového bloku
                    # abychom viděli anomálii, ale nezahltili terminál
                    cell_global_index = i
                    if cell_global_index % 15 < 5: # Vypíše články 0-4, 15-19, 30-34, atd.
                        print(f"  Cell {cell_global_index + 1:02d}: {line}")
            
            time.sleep(5)

    except Exception as e:
        print(f"\nA critical error occurred: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()