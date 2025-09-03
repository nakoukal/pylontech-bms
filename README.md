# Pylontech SC0500 BMS to MQTT Bridge for Home Assistant

This script connects to a Pylontech **BMS SC0500** controller (used with **H48050** batteries) via a serial port, reads operational data, and publishes it to an MQTT broker for integration with Home Assistant.

Unlike common Pylontech models (like US2000/US3000), the SC0500 model uses a text-based Command Line Interface (CLI) for communication, not the standard binary protocol. This script is specifically designed for this CLI-based protocol.

## Features

-   Connects to the BMS using a text-based command protocol.
-   Parses detailed data including total voltage, current, status, cycle count, and individual cell data (voltage, temperature, status).
-   Dynamically detects the number of connected battery modules and their serial numbers.
-   Publishes data to an MQTT broker.
-   Integrates seamlessly with Home Assistant via MQTT Discovery, automatically creating and configuring all sensors.
-   Configuration is managed via an external `.env` file for security and ease of use.
-   Includes instructions for running as a persistent `systemd` service on a Raspberry Pi.

## 1. Prerequisites

### Hardware
-   Pylontech BMS SC0500 Controller
-   Pylontech H48050 Battery Modules
-   A monitoring computer (e.g., Raspberry Pi)
-   A USB to RS485/Serial adapter

### Software
-   Python 3.9+
-   An MQTT Broker (e.g., Mosquitto) accessible from the Raspberry Pi.
-   Home Assistant instance configured to use the same MQTT Broker.

## 2. Setup Instructions

These steps should be performed on your Raspberry Pi.

### Step 1: Clone the Repository or Create the Project

First, get the project files onto your Raspberry Pi.
```bash
git clone <your-repository-url>
cd <your-repository-name>
```
Or, if you are setting this up manually, create a directory and place the `bms_reader.py` script inside it.
```bash
mkdir ~/pylontech-bms
cd ~/pylontech-bms
# Now create the bms_reader.py file with the provided code
```

### Step 2: Create a Python Virtual Environment

It is best practice to run Python applications in an isolated virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```
Your terminal prompt should now be prefixed with `(.venv)`, indicating the virtual environment is active.

### Step 3: Install Dependencies

Create a file named `requirements.txt` in your project directory with the following content:

**File: `requirements.txt`**
```text
pyserial
paho-mqtt
python-dotenv
```

Now, install these libraries using pip:
```bash
pip install -r requirements.txt
```

### Step 4: Configure the Application

Create a file named `.env` in the same directory. This file will hold all your sensitive data and configuration. **Never commit this file to a public repository!**

**File: `.env`**
```ini
# Configuration for Pylontech BMS and MQTT Broker connection
# This file should NEVER be committed to a public repository.

# --- Serial Port Settings ---
SERIAL_PORT=/dev/ttyUSB0
BMS_BARCODE=YOUR_BMS_SERIAL_NUMBER_HERE

# --- MQTT Broker Settings ---
MQTT_BROKER=192.168.1.100
MQTT_PORT=1883
MQTT_USER=your_mqtt_user
MQTT_PASSWORD=your_super_secret_password

# --- Home Assistant Discovery Settings ---
HA_DISCOVERY_PREFIX=homeassistant
DEVICE_UNIQUE_ID=pylontech_sc0500
DEVICE_NAME=Pylontech BMS SC0500

# --- Debug Mode ---
# Set to "true" to enable detailed MQTT message logging to the console
DEBUG_MODE=false
```

**Important:**
-   Replace `YOUR_BMS_SERIAL_NUMBER_HERE` with the barcode of your SC0500 unit.
-   Update `MQTT_BROKER`, `MQTT_USER`, and `MQTT_PASSWORD` to match your MQTT broker's details.
-   Verify that `SERIAL_PORT` matches the device name for your USB-to-serial adapter (it's usually `/dev/ttyUSB0`). You can check with the `ls /dev/ttyUSB*` command.

### Step 5: Run the Script Manually for Testing

Before creating a service, run the script directly from your terminal to ensure everything is working correctly.

```bash
python bms_reader.py
```

You should see output indicating a successful connection to both the MQTT broker and the BMS, followed by periodic data publishing. Check your Home Assistant instance under **Settings -> Devices & Services -> Devices** to see if the "Pylontech BMS SC0500" device and its sensors have been created.

## 3. Running as a Systemd Service

To ensure the script runs automatically on boot and restarts if it fails, we will create a `systemd` service.

### Step 1: Create the Service File

Create a new service definition file using nano:
```bash
sudo nano /etc/systemd/system/pylontech-bms.service
```

### Step 2: Add the Service Configuration

Paste the following content into the file. **You must modify the paths** in the `WorkingDirectory` and `ExecStart` lines to match your system. Replace `<your_username>` with your actual username (e.g., `pi`, `radnak`).

```ini
[Unit]
Description=Pylontech BMS to MQTT Service
After=network.target

[Service]
# Replace <your_username> with your actual username
User=<your_username>
Group=<your_username>

# The full path to your project directory
WorkingDirectory=/home/<your_username>/pylontech-bms

# The full path to the python executable within your virtual environment
ExecStart=/home/<your_username>/pylontech-bms/.venv/bin/python bms_reader.py

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

-   Press `Ctrl+X` to exit.
-   Press `Y` to confirm you want to save the changes.
-   Press `Enter` to confirm the filename.

### Step 3: Enable and Start the Service

Now, tell `systemd` to reload its configuration and start your new service.

1.  **Reload the systemd daemon:**
    ```bash
    sudo systemctl daemon-reload
    ```

2.  **Enable the service to start on boot:**
    ```bash
    sudo systemctl enable pylontech-bms.service
    ```

3.  **Start the service immediately:**
    ```bash
    sudo systemctl start pylontech-bms.service
    ```

### Step 4: Check the Service Status

You can check if the service is running correctly and view its log output with the following commands:

-   **Check the status:**
    ```bash
    sudo systemctl status pylontech-bms.service
    ```
    You should see `active (running)`.

-   **View live logs:**
    ```bash
    sudo journalctl -f -u pylontech-bms.service
    ```
    This will show you the real-time console output of your script, which is extremely useful for debugging. Press `Ctrl+C` to exit the log view.

Understood. Here is a cleaned-up, English-only section that describes the communication protocol and the data structure. This can be integrated into the main `README.md` file.


## 5. Communication Protocol & Data Structure

This BMS model does not use the standard binary Pylontech protocol. Instead, it utilizes a text-based Command Line Interface (CLI) that requires a specific sequence of commands to retrieve data.

### Serial Port Parameters

| Parameter      | Value      |
| :------------- | :--------- |
| **Baudrate**   | `115200`   |
| **Data bits**  | `8`        |
| **Parity**     | `None`     |
| **Stop bits**  | `1`        |
| **Flow control** | `None`     |

### Communication Sequence

The communication process consists of three main steps. All commands are simple text strings terminated by a newline character (`\n`).

**Step 1: Login to Debug Mode**
First, access the service-level CLI.

-   **Command:** `login debug\n`
-   **Expected Response:** The BMS replies with several lines of information, ending with the `pylon_debug>` command prompt.

**Step 2: Authorize Session via Serial Number**
After a successful login, the session must be authorized by sending the BMS unit's serial number (barcode).

-   **Command:** `tbar <YOUR_BMS_SERIAL_NUMBER>\n`
-   **Example:** `tbar PPTAP01419B15082\n`
-   **Expected Response:** The BMS confirms the successful verification with a `Test result:pass` message, followed by the `pylon_debug>` prompt.

**Step 3: Read Power Data**
Once authorized, you can cyclically send the command to fetch the current operational data.

-   **Command:** `getpwr\n`
-   **Expected Response:** The BMS returns a multi-line block of text containing system and cell data. The block is terminated by a success message and the `pylon_debug>` prompt.

### Data Structure and Parsing

The response to the `getpwr` command is a multi-line text block. Only lines containing a hash symbol (`#`) contain valid data. The structure is as follows:

1.  **Header Line (1 line):** Contains summary information about the entire battery pack.
2.  **Cell Data Lines (75 lines for a 5-module system):** Contains data for each individual cell.
3.  **Footer Lines (2 lines):** Contains the error code and cycle count.

The parsed data fields for each section are:

#### Summary Data (`summary`)
| Field                | Example    | Unit | Description              |
| :------------------- | :--------- | :--- | :----------------------- |
| `voltage`            | `250.993`  | V    | Total pack voltage       |
| `current`            | `19.233`   | A    | Total pack current (charge is positive) |
| `avg_temperature`    | `36.0`     | °C   | Average pack temperature |
| `capacity`           | `11613`    | Wh   | Remaining capacity       |
| `status`             | `Charge`   | -    | Charge/Discharge/Idle status |
| `voltage_status`     | `Normal`   | -    | Overall voltage status   |
| `current_status`     | `Normal`   | -    | Overall current status   |
| `temperature_status` | `Normal`   | -    | Overall temperature status |

#### Cell Data (`cells` - repeats for each cell)
| Field         | Example  | Unit | Description      |
| :------------ | :------- | :--- | :--------------- |
| `id`          | `1`      | -    | Global cell index (1-75) |
| `voltage`     | `3.357`  | V    | Individual cell voltage |
| `temperature` | `24.0`   | °C   | Individual cell temperature |
| `status_1`    | `Normal` | -    | Cell status flag 1 |
| `status_2`    | `Normal` | -    | Cell status flag 2 |

#### Footer Data (`footer`)
| Field         | Example | Unit | Description      |
| :------------ | :------ | :--- | :--------------- |
| `error_code`  | `0`     | -    | System error code (0 = Normal) |
| `cycle_count` | `1004`  | -    | Number of full charge/discharge cycles |
