# pylontech-bms
bms pylontech home assistant 
Samozřejmě, s velkou radostí. Je skvělé, že chcete tyto cenné informace zdokumentovat pro ostatní. Vytvořil jsem `README.md` soubor v Markdown formátu, který můžete použít na GitHubu nebo kdekoliv jinde.

Dokument je psán dvojjazyčně (Česky a Anglicky v komentářích), aby byl co nejužitečnější pro širší komunitu.

---

# Komunikace s Pylontech BMS SC0500 (Textový Protokol)
## Communication with Pylontech BMS SC0500 (Text-based Protocol)

Tento dokument popisuje metodu komunikace s řídicí jednotkou Pylontech **BMS SC0500** ve spojení s bateriemi **H48050**.

Na rozdíl od běžnějších modelů (jako US2000/US3000), tato BMS **nepoužívá** standardní binární Pylontech protokol. Místo toho komunikuje pomocí textové příkazové řádky (CLI - Command Line Interface) přes sériový port. Knihovny jako `python-pylontech` proto s tímto modelem **nefungují**.

*This document describes the communication method for the Pylontech **BMS SC0500** controller used with **H48050** batteries.*

*Unlike more common models (like the US2000/US3000), this BMS **does not use** the standard binary Pylontech protocol. Instead, it communicates using a text-based Command Line Interface (CLI) over the serial port. Therefore, libraries like `python-pylontech` **will not work** with this model.*

## 1. Požadavky (Requirements)

### Hardware
*   Řídicí jednotka Pylontech BMS SC0500
*   Bateriové moduly Pylontech H48050
*   Počítač pro monitoring (např. Raspberry Pi, PC)
*   Převodník USB na RS485 / Sériový port

### Software
*   Python 3
*   Knihovna `pyserial` (`pip install pyserial`)
*   Jakýkoliv terminálový program pro sériovou komunikaci (Minicom, PuTTY, etc.)

## 2. Parametry Sériové Komunikace (Serial Communication Parameters)

| Parametr | Hodnota |
| :--- | :--- |
| **Přenosová rychlost (Baudrate)** | `115200` |
| **Datové bity (Data bits)** | `8` |
| **Parita (Parity)** | `None` |
| **Stop bity (Stop bits)** | `1` |
| **Řízení toku (Flow control)** | `None` |

## 3. Komunikační Protokol (Communication Protocol)

Komunikace probíhá ve třech hlavních krocích. Všechny příkazy jsou textové řetězce ukončené znakem nového řádku (`\n`, `0x0A`).

*The communication consists of three main steps. All commands are text strings terminated by a newline character (`\n`, `0x0A`).*

### Krok 1: Přihlášení do Debug Režimu (Login to Debug Mode)
Nejprve je nutné se přihlásit do servisního režimu.

*First, you must log into the service mode.*

- **Příkaz (Command):**
  ```
  login debug\n
  ```
- **Očekávaná odpověď (Expected Response):**
  BMS odpoví sérií informací a skončí promptem `pylon_debug>`.
  *(The BMS will reply with a series of informational lines, ending with the `pylon_debug>` prompt.)*

### Krok 2: Autorizace pomocí Sériového Čísla (Authorization via Serial Number)
Po úspěšném přihlášení je nutné autorizovat session odesláním sériového čísla (čárového kódu) vaší BMS.

*After a successful login, the session must be authorized by sending the serial number (barcode) of your BMS unit.*

- **Příkaz (Command):**
  ```
  tbar <VASE_SERIOVE_CISLO>\n
  ```
  *Příklad (Example):*
  ```
  tbar PPTAP01419B15082\n
  ```
- **Očekávaná odpověď (Expected Response):**
  BMS potvrdí úspěšné ověření.
  *(The BMS will confirm successful verification.)*
  ```
  Test result:pass
  Barcode:PPTAP01419B15082
  ...
  pylon_debug>
  ```

### Krok 3: Čtení Dat (Reading Data)
Po autorizaci je možné cyklicky posílat příkaz pro vyčtení aktuálních provozních dat.

*Once authorized, you can cyclically send the command to read current operational data.*

- **Příkaz (Command):**
  ```
  getpwr\n
  ```
- **Odpověď (Response):**
  BMS vrátí jeden dlouhý řádek dat, kde jsou jednotlivé hodnoty oddělené znakem mřížky (`#`). Řádek končí znaky `\r\n`.
  *(The BMS returns a single long line of data, where individual values are separated by a hash symbol (`#`). The line is terminated by `\r\n`.)*
  *Příklad (Example):*
  ```
  246031#      0#  36000#  10558# Idle# Normal# Normal# Normal# ...
  ```

## 4. Zpracování Dat (Parsing the Data)

Odpověď na příkaz `getpwr` je potřeba rozdělit podle oddělovače `#`. Na základě analýzy logů z aplikace Battery View odpovídají jednotlivé sloupce následujícím hodnotám:

*The response to the `getpwr` command needs to be split by the `#` delimiter. Based on an analysis of logs from the Battery View application, the columns correspond to the following values:*

| Index | Popis (Description) | Příklad (Example) | Jednotka (Unit) |
|:---|:---|:---|:---|
| 0 | Napětí (Voltage) | `246159` | mV |
| 1 | Proud (Current) | `0` | mA |
| 2 | Teplota (Temperature) | `36` | ? (pravděpodobně °C) |
| 3 | Kapacita (Capacity) | `10569` | ? (pravděpodobně Wh) |
| 4 | Základní stav (Basic Status) | `Idle` | - |
| 5 | Stav napětí (Voltage Status) | `Normal` | - |
| 6 | Stav proudu (Current Status) | `Normal` | - |
| 7 | Stav teploty (Temp Status) | `Normal` | - |
| 8 | Nejnižší teplota (Lowest Temp) | `26` | °C |
| 9 | ID buňky s nejnižší T (Lowest T Cell ID) | `50 51 52 53` | - |
| 10 | Nejvyšší teplota (Highest Temp) | `26` | °C |
| 11 | ID buňky s nejvyšší T (Highest T Cell ID)| `55 56` | - |
| 12 | Nejnižší napětí (Lowest Cell Volt) | `3295` | mV |
| 13 | ID buňky s nejnižším V (Lowest V Cell ID)| `24` | - |
| 14 | Nejvyšší napětí (Highest Cell Volt) | `3293` | mV |
| 15 | ID buňky s nejvyšším V (Highest V Cell ID)| `2400` (?) | - |
| 16 | Chybový kód (Error Code) | `0` | - |
| 17 | Počet cyklů (Cycle Count) | `1004` | - |

## 5. Příklad v Pythonu (Python Example Script)

Následující skript demonstruje kompletní proces připojení, autorizace a cyklického čtení dat.

*The following script demonstrates the complete process of connecting, authorizing, and cyclically reading the data.*

```python
import serial
import time

# --- NASTAVENÍ (CONFIGURATION) ---
SERIAL_PORT = '/dev/ttyUSB0'  # Upravte podle vašeho systému (např. 'COM3' pro Windows)
BAUDRATE = 115200
# ZDE ZADEJTE VAŠE SÉRIOVÉ ČÍSLO!
# ENTER YOUR SERIAL NUMBER HERE!
BMS_BARCODE = 'PPTAP01419B15082' 

# --- PŘÍKAZY (COMMANDS) ---
CMD_LOGIN = b'login debug\n'
CMD_AUTHORIZE = f'tbar {BMS_BARCODE}\n'.encode('ascii')
CMD_GET_DATA = b'getpwr\n'

def read_until_prompt(ser, prompt=b'pylon_debug>'):
    """Čte data ze sériového portu, dokud nenarazí na prompt."""
    line = b''
    # Ochrana proti nekonečné smyčce
    start_time = time.time()
    while not line.endswith(prompt):
        if time.time() - start_time > 5: # 5 sekund timeout
            raise TimeoutError("Timeout při čekání na prompt.")
        line += ser.read(1)
    return line.decode('ascii', errors='ignore')

try:
    # 1. Otevření sériového portu
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=2)
    print(f"Port {SERIAL_PORT} úspěšně otevřen.")
    ser.read_all() # Vyčistit buffer

    # 2. Přihlášení
    print("Posílám příkaz pro login...")
    ser.write(CMD_LOGIN)
    response = read_until_prompt(ser)
    print("Odpověď na login přijata.")
    if "pylon_debug>" not in response:
        raise ConnectionError("Login se nezdařil, prompt nenalezen.")
    print("Login úspěšný.")
    time.sleep(0.5)

    # 3. Autorizace
    print(f"Posílám autorizaci s SN: {BMS_BARCODE}...")
    ser.write(CMD_AUTHORIZE)
    response = read_until_prompt(ser)
    if "pass" not in response:
        raise ConnectionError("Autorizace selhala! Zkontrolujte sériové číslo.")
    print("Autorizace úspěšná.")
    time.sleep(0.5)

    # 4. Smyčka pro čtení dat
    print("\n--- Spouštím pravidelné čtení dat (každých 10 sekund) ---")
    while True:
        ser.write(CMD_GET_DATA)
        response_bytes = ser.read_until(b'pylon_debug>') 
        response_str = response_bytes.decode('ascii', errors='ignore')
        
        # Očištění a parsování dat
        clean_response = response_str.replace('getpwr', '').replace('@', '').strip()
        data_lines = [line for line in clean_response.splitlines() if '#' in line]

        if data_lines:
            data_values = data_lines[0].split('#')
            voltage_mv = int(data_values[0])
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Napětí: {voltage_mv / 1000.0:.3f} V")
        
        time.sleep(10)

except serial.SerialException as e:
    print(f"CHYBA: {e}")
except (ConnectionError, TimeoutError) as e:
    print(f"CHYBA PŘIPOJENÍ: {e}")
except KeyboardInterrupt:
    print("\nUkončuji program.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Sériový port uzavřen.")
```
