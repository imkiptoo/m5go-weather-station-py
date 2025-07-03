from m5stack import *
from m5ui import *
from uiflow import *
import unit
import wifiCfg
import time
from umqtt.simple import MQTTClient
import ujson
import machine
import utime
import os
from hardware import sdcard
import ntptime
from machine import RTC

# Log level constants
LOG_INFO = "INFO"
LOG_WARNING = "WARNING"
LOG_ERROR = "ERROR"

setScreenColor(0x111111)

title0 = M5Title(title="ENV III Sensor", x=3, fgcolor=0xffffff, bgcolor=0x0000ff)

env3_0 = None
ntp = None

label_temp = M5TextBox(10, 50, "Temp: --°C", lcd.FONT_Default, 0xffffff, rotate=0)
label_hum = M5TextBox(10, 70, "Humidity: --%", lcd.FONT_Default, 0xffffff, rotate=0)
label_press = M5TextBox(10, 90, "Pressure: --hPa", lcd.FONT_Default, 0xffffff, rotate=0)
label_wifi = M5TextBox(10, 110, "WiFi: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
label_env = M5TextBox(10, 130, "ENV: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
label_mqtt = M5TextBox(10, 150, "MQTT: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
label_sd = M5TextBox(10, 170, "SD: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)

wifi_ssid = "lightsaber"
wifi_password = "skywalker"
last_wifi_check = 0
last_env_check = 0
last_mqtt_check = 0
last_sd_check = 0

mqtt_server = "192.168.137.1"
mqtt_client = None
weather_data = {}
weather_alert = None

# Status tracking for console logging
wifi_status = "Disconnected"
env_status = "Disconnected" 
mqtt_status = "Disconnected"
sd_status = "Disconnected"
sd_mounted = False
last_temp = None
last_hum = None
last_press = None

def fetch_time():
    global ntp
    global rtc
    print("Fetching NTP time...")
    try:
        ntp = ntptime.client(host='de.pool.ntp.org', timezone=2)
        rtc = RTC()
        print("NTP time fetched successfully")
    except Exception as e:
        print("Failed to fetch NTP time: {}".format(e))

def check_wifi_connection():
    global wifi_status
    old_status = wifi_status
    
    if not wifiCfg.wlan_sta.isconnected():
        wifi_status = "Connecting"
        label_wifi.setText("WiFi: Connecting...")
        label_wifi.setColor(0xffff00)
        wifiCfg.doConnect(wifi_ssid, wifi_password)
        if wifiCfg.wlan_sta.isconnected():
            wifi_status = "Connected"
            label_wifi.setText("WiFi: Connected")
            label_wifi.setColor(0x00ff00)
        else:
            wifi_status = "Failed"
            label_wifi.setText("WiFi: Failed")
            label_wifi.setColor(0xff0000)
    else:
        wifi_status = "Connected"
        label_wifi.setText("WiFi: Connected")
        label_wifi.setColor(0x00ff00)
    
    if old_status != wifi_status:
        log_message(LOG_INFO, "WiFi status changed: {} -> {}".format(old_status, wifi_status))

def check_env_connection():
    global env3_0, env_status
    old_status = env_status
    
    try:
        env_status = "Connecting"
        label_env.setText("ENV: Connecting...")
        label_env.setColor(0xffff00)
        if env3_0 is None:
            env3_0 = unit.get(unit.ENV3, unit.PORTA)
        temp = env3_0.temperature
        env_status = "Connected"
        label_env.setText("ENV: Connected")
        label_env.setColor(0x00ff00)
        result = True
    except:
        env_status = "Failed"
        label_env.setText("ENV: Failed")
        label_env.setColor(0xff0000)
        env3_0 = None
        result = False
    
    if old_status != env_status:
        log_message(LOG_INFO, "ENV status changed: {} -> {}".format(old_status, env_status))
    
    return result

def mqtt_callback(topic, msg):
    global weather_data, weather_alert
    try:
        topic_str = topic.decode('utf-8')
        msg_str = msg.decode('utf-8')
        
        if topic_str == 'weather/data':
            weather_data = ujson.loads(msg_str)
        elif topic_str == 'weather/alert_trigger':
            weather_alert = ujson.loads(msg_str)
    except:
        pass

def check_mqtt_connection():
    global mqtt_client, mqtt_status
    old_status = mqtt_status
    
    if not wifiCfg.wlan_sta.isconnected():
        mqtt_status = "No WiFi"
        label_mqtt.setText("MQTT: No WiFi")
        label_mqtt.setColor(0xff0000)
        result = False
    else:
        try:
            mqtt_status = "Connecting"
            label_mqtt.setText("MQTT: Connecting...")
            label_mqtt.setColor(0xffff00)
            
            if mqtt_client is None:
                mqtt_client = MQTTClient("m5go_env", mqtt_server)
                mqtt_client.set_callback(mqtt_callback)
            
            mqtt_client.connect()
            mqtt_client.subscribe("weather/data")
            mqtt_client.subscribe("weather/alert_trigger")
            
            mqtt_status = "Connected"
            label_mqtt.setText("MQTT: Connected")
            label_mqtt.setColor(0x00ff00)
            result = True
        except:
            mqtt_status = "Failed"
            label_mqtt.setText("MQTT: Failed")
            label_mqtt.setColor(0xff0000)
            mqtt_client = None
            result = False
    
    if old_status != mqtt_status:
        log_message(LOG_INFO, "MQTT status changed: {} -> {}".format(old_status, mqtt_status))
    
    return result

def log_message(level, message):
    """Log structured messages with timestamp and level"""
    try:
        timestamp = get_datetime_string()
        
        # Determine storage path - prefer SD card if available
        if sd_mounted and sd_status == "Connected":
            base_dir = "/sd"
        else:
            base_dir = "/flash"
        
        # Ensure logs directory exists
        logs_dir = "{}/logs".format(base_dir)
        try:
            os.mkdir(logs_dir)
        except:
            pass
        
        log_file = "{}/{}.log".format(logs_dir, get_date_string())
        log_entry = "{}  {:10} m5go: {}".format(timestamp, level, message)
        
        with open(log_file, "a+") as fs:
            fs.write(log_entry + "\n")
        
        # Also print to console
        print(log_entry)
        
    except Exception as e:
        print("Failed to write log: {}".format(e))

def send_mqtt_data(temperature, humidity, pressure):
    global mqtt_client, mqtt_status
    
    if mqtt_client is None or mqtt_status != "Connected":
        log_message(LOG_WARNING, "MQTT not connected, skipping data send")
        return False
    
    try:
        timestamp = get_datetime_string()
        
        message = '{"timestamp":"' + str(timestamp) + '","temperature":' + str(temperature) + ',"humidity":' + str(humidity) + ',"pressure":' + str(pressure) + '}'
        topic = b"weather/sensor_data"
        
        mqtt_client.publish(topic, message)
        log_message(LOG_INFO, "Sent MQTT data: T={:.1f}°C H={:.1f}% P={:.1f}hPa at {}".format(temperature, humidity, pressure, timestamp))
        return True
    except Exception as e:
        log_message(LOG_ERROR, "Failed to send MQTT data: {}".format(e))
        return False

def get_date_string():
    if ntp is None:
        fetch_time()
    return ntp.formatDate('-')

def get_datetime_string():
    if ntp is None:
        fetch_time()
    year, month, day, _, hour, minute, second, _ = rtc.datetime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(year, month, day, hour, minute, second)

def check_sd_card():
    global sd_status, sd_mounted
    old_status = sd_status
    
    try:
        if not sd_mounted:
            sd_status = "Connecting"
            label_sd.setText("SD: Connecting...")
            label_sd.setColor(0xffff00)
            
            # Try different mount points
            try:
                if os.listdir("/sd"):
                    sd_mounted = True
                    sd_status = "Connected"
            except:
                try:
                    sd_mounted = True
                    sd_status = "Connected"
                except:
                    sd_status = "Failed"
        else:
            # Check if still mounted
            try:
                os.listdir("/sd")
                sd_status = "Connected"
            except:
                sd_mounted = False
                sd_status = "Failed"
        
        if sd_status == "Connected":
            label_sd.setText("SD: Connected")
            label_sd.setColor(0x00ff00)
        else:
            label_sd.setText("SD: Failed")
            label_sd.setColor(0xff0000)
            
    except Exception as e:
        sd_status = "Failed"
        label_sd.setText("SD: Failed")
        label_sd.setColor(0xff0000)
        sd_mounted = False
    
    if old_status != sd_status:
        log_message(LOG_INFO, "SD status changed: {} -> {}".format(old_status, sd_status))
    
    return sd_mounted

def log_env_data(temperature, humidity, pressure):
    try:
        check_sd_card()
        
        # Determine storage path - prefer SD card if available
        if sd_mounted and sd_status == "Connected":
            base_dir = "/sd"
            storage_type = "SD"
        else:
            base_dir = "/flash"
            storage_type = "Flash"
        
        # Ensure directories exist
        logs_dir = "{}/logs".format(base_dir)
        measurements_dir = "{}/measurements".format(base_dir)
        
        try:
            os.mkdir(logs_dir)
        except:
            pass
        
        try:
            os.mkdir(measurements_dir)
        except:
            pass

        timestamp = get_datetime_string()
        
        # Save JSON measurements to measurements folder
        measurements_file = "{}/{}.json".format(measurements_dir, get_date_string())
        measurement_entry = '{"timestamp":"' + str(timestamp) + '","temperature":' + str(temperature) + ',"humidity":' + str(humidity) + ',"pressure":' + str(pressure) + '}'
        
        with open(measurements_file, "a+") as fs:
            fs.write(measurement_entry + "\n")
        
        # Log human-readable message using log_message function
        log_message(LOG_INFO, "Logged ENV data to {}: T={:.1f}°C H={:.1f}% P={:.1f}hPa at {}".format(storage_type, temperature, humidity, pressure, timestamp))
        
        # Send data via MQTT
        send_mqtt_data(temperature, humidity, pressure)
    except Exception as e:
        log_message(LOG_ERROR, "Failed to log data: {}".format(e))

print("Starting M5GO ENV III Sensor System...")
print("WiFi: {}, ENV: {}, MQTT: {}, SD: {}".format(wifi_status, env_status, mqtt_status, sd_status))

check_wifi_connection()
check_env_connection()
check_mqtt_connection()
check_sd_card()
fetch_time()

while True:
    current_time = time.ticks_ms()
    
    if time.ticks_diff(current_time, last_wifi_check) >= 60000:
        check_wifi_connection()
        last_wifi_check = current_time
    
    if time.ticks_diff(current_time, last_env_check) >= 60000:
        check_env_connection()
        last_env_check = current_time
    
    if time.ticks_diff(current_time, last_mqtt_check) >= 60000:
        check_mqtt_connection()
        last_mqtt_check = current_time
    
    if time.ticks_diff(current_time, last_sd_check) >= 60000:
        check_sd_card()
        last_sd_check = current_time
    
    if mqtt_client is not None:
        try:
            mqtt_client.check_msg()
        except:
            mqtt_client = None
    
    if env3_0 is not None:
        try:
            temp = env3_0.temperature
            humidity = env3_0.humidity
            pressure = env3_0.pressure
            
            # Check if values changed significantly
            '''
            temp_changed = last_temp is None or abs(temp - last_temp) > 0.5
            hum_changed = last_hum is None or abs(humidity - last_hum) > 1.0
            press_changed = last_press is None or abs(pressure - last_press) > 1.0
            
            if temp_changed or hum_changed or press_changed:
            '''
            
            if True:
                log_env_data(temp, humidity, pressure)
                last_temp = temp
                last_hum = humidity
                last_press = pressure
            
            label_temp.setText("Temp: {:.1f}°C".format(temp))
            label_hum.setText("Humidity: {:.1f}%".format(humidity))
            label_press.setText("Pressure: {:.1f}hPa".format(pressure))
        except:
            label_temp.setText("Temp: --°C")
            label_hum.setText("Humidity: --%")
            label_press.setText("Pressure: --hPa")
            env3_0 = None
    else:
        label_temp.setText("Temp: --°C")
        label_hum.setText("Humidity: --%")
        label_press.setText("Pressure: --hPa")
    
    wait_ms(1000)