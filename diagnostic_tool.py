import serial
import time
import os
from dotenv import load_dotenv

# --- Load configuration from .env file ---
load_dotenv()
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
BAUDRATE = int(os.getenv('BAUDRATE', 115200)) 
BMS_BARCODE = os.getenv('BMS_BARCODE')

# --- BMS Commands ---
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'
CMD_GET_INFO = b'info\n'

def connect_and_authorize(ser):
    """Establishes connection with the BMS and authorizes the session."""
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
    """Gets and prints the mapping of logical index to serial number."""
    print("\n--- Reading Module Info (command: info) ---")
    ser.write(CMD_GET_INFO)
    response_bytes = ser.read_until(b'pylon_debug>')
    response_str = response_bytes.decode('ascii', errors='ignore')
    
    print("--- Detected Modules (Logical Order from BMS) ---")
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
    print("-------------------------------------------------")

def main():
    """Main function for diagnostics."""
    ser = None
    try:
        # Nastavíme delší timeout, aby měl příkaz 'info' dostatek času
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=15)
        print(f"Serial port {SERIAL_PORT} opened successfully at {BAUDRATE} baud.")
        
        connect_and_authorize(ser)
        
        get_and_print_module_info(ser)
        
        print("\n--- Starting periodic cell data reading (command: getpwr) ---")
        print("Now you can induce an anomaly (e.g., disconnect a module's balance connector).")
        print("Watch the output to see which group of cells (1-15, 16-30, etc.) shows an error.")
        
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
                    cell_global_index = i + 1
                    # Vypisujeme data pro každý článek, aby byla anomálie jasně vidět
                    print(f"  Cell {cell_global_index:02d}: {line}")
            
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nExiting diagnostic tool.")
    except Exception as e:
        print(f"\nA critical error occurred: {e}")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()
