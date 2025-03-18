import network
import urequests
import time
import machine
from machine import Pin, ADC
from dht import DHT11
from dht import InvalidChecksum

# WiFi Credentials
WIFI_SSID = "Redmagic"
WIFI_PASSWORD = "22222222"

# Firebase Database URL
FIREBASE_URL = "https://predictive-18aaa-default-rtdb.firebaseio.com/sensor_data.json"

# Initialize sensors
dht_pin = Pin(28, Pin.OUT, Pin.PULL_DOWN)  # DHT11 on GPIO28
sensor = DHT11(dht_pin)
vibration_sensor = ADC(Pin(26))  # Vibration on ADC0 (GPIO26)
current_sensor = ADC(Pin(27))  # ACS712 Current Sensor on ADC1 (GPIO27)

# Constants for ACS712
ACS712_SENSITIVITY = 185  # 185mV/A for ACS712-5A (use 100 for 20A, 66 for 30A)
VOLTAGE_REF = 3.3  # Reference voltage for Raspberry Pi Pico ADC
ADC_RESOLUTION = 65535  # 16-bit ADC max value
OFFSET_VOLTAGE = 2500  # 2.5V (2500mV) offset for ACS712

# Function to connect to WiFi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    print("Connecting to WiFi...")
    while not wlan.isconnected():
        time.sleep(1)
    
    print("Connected to WiFi:", wlan.ifconfig())

# Function to read DHT11 sensor with retries
def read_dht11():
    for _ in range(5):  # Retry up to 5 times
        try:
            sensor.measure()
            return sensor.temperature, sensor.humidity
        except (InvalidChecksum, OSError) as e:
            print("DHT11 Read Error:", e)
            time.sleep(2)  # Wait before retrying
    return None, None  # Return None if all retries fail

# Function to read current sensor with multiple samples
def read_current():
    readings = []
    for _ in range(10):  # Take 10 samples for accuracy
        adc_value = current_sensor.read_u16()  # Read ADC value (0-65535)
        voltage_mv = (adc_value / ADC_RESOLUTION) * 3300  # Convert ADC to millivolts
        current = (voltage_mv - OFFSET_VOLTAGE) / ACS712_SENSITIVITY  # Calculate current in Amps
        readings.append(current)
        time.sleep(0.01)  # Small delay

    avg_current = sum(readings) / len(readings)  # Get average current
    return round(avg_current, 3)  # Round to 3 decimal places

# Function to read vibration sensor with averaging
def read_vibration():
    samples = 10
    total = 0
    for _ in range(samples):
        total += vibration_sensor.read_u16()
        time.sleep_ms(5)
    return int(total / samples)  # Cast to integer to remove decimal


# Function to get the timestamp
def get_timestamp():
    local_time = time.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        local_time[0], local_time[1], local_time[2], 
        local_time[3], local_time[4], local_time[5]
    )

# Function to send data to Firebase
def send_data_to_firebase(data):
    try:
        response = urequests.post(FIREBASE_URL, json=data)
        response.close()
        print("Data logged:", data['timestamp'], data['Temperature'], data['Humidity'], data['VibrationLevel'], data['Current'])
    except Exception as e:
        print("Error sending data:", e)
        connect_wifi()  # Try reconnecting if there's an issue

# Main loop to collect and send sensor data
def main():
    connect_wifi()

    while True:
        try:
            # Read DHT11 sensor
            temperature, humidity = read_dht11()
            if temperature is None or humidity is None:
                print("Failed to read DHT11 sensor.")
                continue

            # Read vibration sensor
            vibration_level = read_vibration()

            # Read current sensor
            current = read_current()

            # Get timestamp
            timestamp = get_timestamp()

            # Prepare data in JSON format
            data = {
                "timestamp": timestamp,
                "Temperature": temperature,
                "Humidity": humidity,
                "VibrationLevel": vibration_level,
                "Current": current
            }

            # Send data to Firebase
            send_data_to_firebase(data)

        except Exception as e:
            print("Error:", e)

        time.sleep(0.1)  # Log data every 5 seconds

# Start main loop
main()

