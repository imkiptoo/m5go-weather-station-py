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

# Color constants
COLOR_GREEN = 0x00ff00
COLOR_RED = 0xff0000
COLOR_YELLOW = 0xffff00

# Status enum
class Status:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    FAILED = 3
    NO_WIFI = 4

def status_to_string(status):
    if status == Status.DISCONNECTED:
        return "Disconnected"
    elif status == Status.CONNECTING:
        return "Connecting"
    elif status == Status.CONNECTED:
        return "Connected"
    elif status == Status.FAILED:
        return "Failed"
    elif status == Status.NO_WIFI:
        return "No WiFi"
    else:
        return "Unknown"

setScreenColor(0x000000)

# Screen navigation configuration
screen_navigation = {
    "status": {"A": "home", "B": "home", "C": "home"},
    "home": {"A": "forecast", "B": "temp_history", "C": "settings"},
    "forecast": {"A": "home", "B": "temp_history", "C": "settings"},
    "temp_history": {"A": "home", "B": "humidity_history", "C": "settings"},
    "humidity_history": {"A": "home", "B": "temp_history", "C": "settings"},
    "settings": {"A": "home", "B": "forecast", "C": "temp_history"},
    "alert": {"A": "home", "B": "home", "C": "home"}
}

current_screen = "status"
title0 = M5Title(title="ENV III Sensor", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)

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

# Minimal weather data - just basic values
weather_temp = 0.0
weather_condition = ""

# Simplified sensor data - use global variables
current_sensor_temp = None
current_sensor_hum = None
current_sensor_press = None
last_sensor_temp = None
last_sensor_hum = None
last_sensor_press = None

# Status tracking for console logging
wifi_status = Status.DISCONNECTED
env_status = Status.DISCONNECTED
mqtt_status = Status.DISCONNECTED
sd_status = Status.DISCONNECTED
sd_mounted = False

# Removed status tracking to save memory

# Footer button labels
footer_a = None
footer_b = None
footer_c = None

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
    global wifi_status, current_screen
    old_status = wifi_status
    
    if not wifiCfg.wlan_sta.isconnected():
        wifi_status = Status.CONNECTING
        wifiCfg.doConnect(wifi_ssid, wifi_password)
        if wifiCfg.wlan_sta.isconnected():
            wifi_status = Status.CONNECTED
        else:
            wifi_status = Status.FAILED
    else:
        wifi_status = Status.CONNECTED
    
    if old_status != wifi_status:
        log_message(LOG_INFO, "WiFi status changed: {} -> {}".format(status_to_string(old_status), status_to_string(wifi_status)))
        if wifi_status == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")

def check_env_connection():
    global env3_0, env_status, current_screen
    old_status = env_status
    
    try:
        env_status = Status.CONNECTING
        if env3_0 is None:
            env3_0 = unit.get(unit.ENV3, unit.PORTA)
        temp = env3_0.temperature
        env_status = Status.CONNECTED
        result = True
    except:
        env_status = Status.FAILED
        env3_0 = None
        result = False
    
    if old_status != env_status:
        log_message(LOG_INFO, "ENV status changed: {} -> {}".format(status_to_string(old_status), status_to_string(env_status)))
        if env_status == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")
    
    return result

def parse_weather_data(data):
    global weather_temp, weather_condition
    try:
        weather_temp = data.get("current_temp", 0.0)
        weather_condition = data.get("condition", "")
        print("Weather: {:.1f}C {}".format(weather_temp, weather_condition))
    except:
        pass

def mqtt_callback(topic, msg):
    global weather_data, weather_alert
    try:
        topic_str = topic.decode('utf-8')
        msg_str = msg.decode('utf-8')
        
        if topic_str == 'weather/data':
            weather_data = ujson.loads(msg_str)
            parse_weather_data(weather_data)
        elif topic_str == 'weather/alert_trigger':
            weather_alert = ujson.loads(msg_str)
    except Exception as e:
        print("MQTT callback error: {}".format(e))

def check_mqtt_connection():
    global mqtt_client, mqtt_status, current_screen
    old_status = mqtt_status
    
    if not wifiCfg.wlan_sta.isconnected():
        mqtt_status = Status.NO_WIFI
        result = False
    else:
        try:
            mqtt_status = Status.CONNECTING
            
            if mqtt_client is None:
                mqtt_client = MQTTClient("m5go_env", mqtt_server)
                mqtt_client.set_callback(mqtt_callback)
            
            mqtt_client.connect()
            mqtt_client.subscribe("weather/data")
            mqtt_client.subscribe("weather/alert_trigger")
            
            mqtt_status = Status.CONNECTED
            result = True
        except:
            mqtt_status = Status.FAILED
            mqtt_client = None
            result = False
    
    if old_status != mqtt_status:
        log_message(LOG_INFO, "MQTT status changed: {} -> {}".format(status_to_string(old_status), status_to_string(mqtt_status)))
        if mqtt_status == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")
    
    return result

def log_message(level, message):
    try:
        print("{}: {}".format(level, message))
    except:
        pass

def send_mqtt_data(temperature, humidity, pressure):
    global mqtt_client, mqtt_status
    
    if mqtt_client is None or mqtt_status != Status.CONNECTED:
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
    return "2025-07-03"

def get_datetime_string():
    return "2025-07-03T15:30:00"

def check_sd_card():
    global sd_status, sd_mounted
    old_status = sd_status
    
    try:
        if not sd_mounted:
            sd_status = Status.CONNECTING
            
            # Try different mount points
            try:
                if os.listdir("/sd"):
                    sd_mounted = True
                    sd_status = Status.CONNECTED
            except:
                try:
                    sd_mounted = True
                    sd_status = Status.CONNECTED
                except:
                    sd_status = Status.FAILED
        else:
            # Check if still mounted
            try:
                os.listdir("/sd")
                sd_status = Status.CONNECTED
            except:
                sd_mounted = False
                sd_status = Status.FAILED
                
    except Exception as e:
        sd_status = Status.FAILED
        sd_mounted = False
    
    if old_status != sd_status:
        log_message(LOG_INFO, "SD status changed: {} -> {}".format(status_to_string(old_status), status_to_string(sd_status)))
    
    return sd_mounted

def log_env_data(temperature, humidity, pressure):
    try:
        send_mqtt_data(temperature, humidity, pressure)
    except:
        pass

def navigate_to_screen(screen_name):
    global current_screen
    if screen_name in screen_navigation:
        current_screen = screen_name
        clear_screen()
        if screen_name == "status":
            show_status_screen()
        elif screen_name == "home":
            show_home_screen()
        elif screen_name == "forecast":
            show_forecast_screen()
        elif screen_name == "temp_history":
            show_temp_history_screen()
        elif screen_name == "humidity_history":
            show_humidity_history_screen()
        elif screen_name == "settings":
            show_settings_screen()
        elif screen_name == "alert":
            show_alert_screen()

def clear_screen():
    lcd.clear()
    setScreenColor(0x111111)

def create_footer():
    global footer_a, footer_b, footer_c
    footer_a = M5TextBox(10, 220, "A:", lcd.FONT_Default, 0x888888, rotate=0)
    footer_b = M5TextBox(120, 220, "B:", lcd.FONT_Default, 0x888888, rotate=0)
    footer_c = M5TextBox(230, 220, "C:", lcd.FONT_Default, 0x888888, rotate=0)

def get_page_name(screen_id):
    if screen_id == "status":
        return "Status"
    elif screen_id == "home":
        return "Home"
    elif screen_id == "forecast":
        return "Forecast"
    elif screen_id == "temp_history":
        return "Temp"
    elif screen_id == "humidity_history":
        return "Humidity"
    elif screen_id == "settings":
        return "Settings"
    elif screen_id == "alert":
        return "Alert"
    else:
        return "--"

def update_footer():
    global current_screen, footer_a, footer_b, footer_c
    if current_screen in screen_navigation:
        nav = screen_navigation[current_screen]
        
        # Special case for status screen when navigation is blocked
        if current_screen == "status" and not can_navigate_from_status():
            footer_a.setText("")
            footer_b.setText("")
            footer_c.setText("")
        else:
            footer_a.setText(get_page_name(nav.get("A", "--")))
            footer_b.setText(get_page_name(nav.get("B", "--")))
            footer_c.setText(get_page_name(nav.get("C", "--")))

def show_status_screen():
    global title0, label_wifi, label_env, label_mqtt, label_sd
    title0 = M5Title(title="System Status", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    label_wifi = M5TextBox(10, 50, "WiFi: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
    label_env = M5TextBox(10, 70, "ENV: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
    label_mqtt = M5TextBox(10, 90, "MQTT: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
    label_sd = M5TextBox(10, 110, "SD: Disconnected", lcd.FONT_Default, 0xff0000, rotate=0)
    create_footer()
    update_footer()

def show_home_screen():
    global title_text, title_background, label_temp, label_hum, label_press
    # title0 = M5Title(title="ENV III Sensor", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    title_background = M5Rect(0, 0, 320, 32, 0xff00ff, 0xff00ff)
    title_text = M5TextBox(8, 8, "ENV III Sensor", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    label_temp = M5TextBox(0, 50, "Temp: --°C", lcd.FONT_Default, 0xffffff, rotate=0)
    label_hum = M5TextBox(10, 70, "Humidity: --%", lcd.FONT_Default, 0xffffff, rotate=0)
    label_press = M5TextBox(10, 90, "Pressure: --hPa", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_forecast_screen():
    M5Title(title="Weather Forecast", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    M5TextBox(10, 50, "Forecast data will be displayed here", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_temp_history_screen():
    M5Title(title="Temperature History", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    M5TextBox(10, 50, "Temperature history will be displayed here", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_humidity_history_screen():
    M5Title(title="Humidity History", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    M5TextBox(10, 50, "Humidity history will be displayed here", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_settings_screen():
    M5Title(title="Settings", x=8, fgcolor=0xffffff, bgcolor=0x0000ff, h=32)
    M5TextBox(10, 50, "Settings will be displayed here", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_alert_screen():
    M5Title(title="Alert", x=8, fgcolor=0xffffff, bgcolor=0xff0000, h=32)
    M5TextBox(10, 50, "Alert information will be displayed here", lcd.FONT_Default, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def can_navigate_from_status():
    return (wifi_status == Status.CONNECTED and 
            env_status == Status.CONNECTED and 
            mqtt_status == Status.CONNECTED)

def buttonA_wasPressed():
    global current_screen
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "A" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["A"]
        navigate_to_screen(next_screen)

def buttonB_wasPressed():
    global current_screen
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "B" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["B"]
        navigate_to_screen(next_screen)

def buttonC_wasPressed():
    global current_screen
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "C" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["C"]
        navigate_to_screen(next_screen)

def update_sensor_labels():
    global current_screen, current_sensor_temp, current_sensor_hum, current_sensor_press
    if current_screen == "home":
        if current_sensor_temp is not None:
            label_temp.setText("Temp: {:.1f}°C".format(current_sensor_temp))
            label_hum.setText("Humidity: {:.1f}%".format(current_sensor_hum))
            label_press.setText("Pressure: {:.1f}hPa".format(current_sensor_press))
        else:
            label_temp.setText("Temp: --°C")
            label_hum.setText("Humidity: --%")
            label_press.setText("Pressure: --hPa")

def has_significant_change(temp, hum, press):
    global last_sensor_temp, last_sensor_hum, last_sensor_press
    if last_sensor_temp is None:
        return True
    
    temp_changed = abs(temp - last_sensor_temp) > 0.5
    hum_changed = abs(hum - last_sensor_hum) > 1.0
    press_changed = abs(press - last_sensor_press) > 1.0
    
    return temp_changed or hum_changed or press_changed

def update_status_labels():
    global current_screen
    if current_screen == "status":
        # Always update all status labels
        if wifi_status == Status.CONNECTED:
            label_wifi.setText("WiFi: Connected")
            label_wifi.setColor(COLOR_GREEN)
        elif wifi_status == Status.CONNECTING:
            label_wifi.setText("WiFi: Connecting...")
            label_wifi.setColor(COLOR_YELLOW)
        else:
            label_wifi.setText("WiFi: {}".format(status_to_string(wifi_status)))
            label_wifi.setColor(COLOR_RED)
        
        if env_status == Status.CONNECTED:
            label_env.setText("ENV: Connected")
            label_env.setColor(COLOR_GREEN)
        elif env_status == Status.CONNECTING:
            label_env.setText("ENV: Connecting...")
            label_env.setColor(COLOR_YELLOW)
        else:
            label_env.setText("ENV: {}".format(status_to_string(env_status)))
            label_env.setColor(COLOR_RED)
        
        if mqtt_status == Status.CONNECTED:
            label_mqtt.setText("MQTT: Connected")
            label_mqtt.setColor(COLOR_GREEN)
        elif mqtt_status == Status.CONNECTING:
            label_mqtt.setText("MQTT: Connecting...")
            label_mqtt.setColor(COLOR_YELLOW)
        else:
            label_mqtt.setText("MQTT: {}".format(status_to_string(mqtt_status)))
            label_mqtt.setColor(COLOR_RED)
        
        if sd_status == Status.CONNECTED:
            label_sd.setText("SD: Connected")
            label_sd.setColor(COLOR_GREEN)
        elif sd_status == Status.CONNECTING:
            label_sd.setText("SD: Connecting...")
            label_sd.setColor(COLOR_YELLOW)
        else:
            label_sd.setText("SD: {}".format(status_to_string(sd_status)))
            label_sd.setColor(COLOR_RED)
        
        update_footer()
        
        # Auto-navigate to home when all required connections are ready
        if can_navigate_from_status():
            navigate_to_screen("home")

print("Starting M5GO ENV III Sensor System...")
print("WiFi: {}, ENV: {}, MQTT: {}, SD: {}".format(status_to_string(wifi_status), status_to_string(env_status), status_to_string(mqtt_status), status_to_string(sd_status)))

# Initialize status screen immediately to show connection progress
navigate_to_screen("status")

# Set up button callbacks
btnA.wasPressed(buttonA_wasPressed)
btnB.wasPressed(buttonB_wasPressed)
btnC.wasPressed(buttonC_wasPressed)

# Start connection attempts - user can see progress on status screen
check_wifi_connection()
check_env_connection()
check_mqtt_connection()
check_sd_card()

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
    
    # Update status labels
    update_status_labels()
    
    # Update sensor data and labels
    if env3_0 is not None:
        try:
            temp = env3_0.temperature
            humidity = env3_0.humidity
            pressure = env3_0.pressure
            
            # Check if values changed significantly and log if needed
            if has_significant_change(temp, humidity, pressure):
                log_env_data(temp, humidity, pressure)
                print("Sensor: {:.1f}°C, {:.1f}%, {:.1f}hPa".format(temp, humidity, pressure))
                
                # Update last values
                last_sensor_temp = current_sensor_temp
                last_sensor_hum = current_sensor_hum
                last_sensor_press = current_sensor_press
            
            # Update current values
            current_sensor_temp = temp
            current_sensor_hum = humidity
            current_sensor_press = pressure
            
            update_sensor_labels()
        except:
            current_sensor_temp = None
            current_sensor_hum = None
            current_sensor_press = None
            update_sensor_labels()
            env3_0 = None
    else:
        current_sensor_temp = None
        current_sensor_hum = None
        current_sensor_press = None
        update_sensor_labels()
    
    wait_ms(1000)