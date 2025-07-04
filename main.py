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
title0 = M5Title(title="ENV III Sensor", x=8, fgcolor=0x000000, bgcolor=0x000000, h=32)

env3_0 = None
ntp = None

label_temp = None
label_hum = None
label_press = None
label_condition = None
label_wind = None
label_location = None
image_condition = None

label_wifi = None
label_env = None
label_mqtt = None
label_sd = None

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
current_icon_file = "unknown.png"
weather_condition_description = ""
current_wind = ""
current_location = ""

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

weather_icon_mapping = {
    # Clear sky
    '01d': 'clear.png',
    '01n': 'nt_clear.png',
    
    # Few clouds
    '02d': 'mostlysunny.png',
    '02n': 'nt_mostlycloudy.png',
    
    # Scattered clouds
    '03d': 'mostlycloudy.png', 
    '03n': 'mostlycloudy.png',
    
    # Broken clouds
    '04d': 'cloudy.png',
    '04n': 'nt_cloudy.png',
    
    # Shower rain
    '09d': 'sleet.png',
    '09n': 'nt_sleet.png',
    
    # Rain
    '10d': 'rain.png',
    '10n': 'nt_rain.png',
    
    # Thunderstorm
    '11d': 'tstorms.png',
    '11n': 'nt_tstorms.png',
    
    # Snow
    '13d': 'snow.png',
    '13n': 'nt_snow.png',
    
    # Mist
    '50d': 'fog.png',
    '50n': 'nt_fog.png'
}

# Global variables for forecast display (5 days for better screen layout)
forecast_days = ["TODAY", "MON", "TUE", "WED", "THU"]
forecast_dates = ["11/5", "12/5", "13/5", "14/5", "15/5"]  
forecast_temps = ["22°", "20°", "19°", "18°", "18°"]
forecast_humidity = ["74%", "70%", "78%", "85%", "82%"]
forecast_icons = ["sunny.png", "cloudy.png", "rain.png", "cloudy.png", "rain.png"]

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

def parse_forecast_data(weather_data):
    """Parse forecast data from weather JSON and update forecast display variables"""
    global forecast_days, forecast_dates, forecast_temps, forecast_humidity, forecast_icons
    
    try:
        if 'forecast' in weather_data:
            forecast_list = weather_data['forecast']
            
            # Process up to 5 days from MQTT data
            for i, day_data in enumerate(forecast_list[:5]):  
                if i < len(forecast_days):
                    # Update day names and dates
                    forecast_days[i] = day_data.get('day', forecast_days[i])
                    forecast_dates[i] = day_data.get('date', forecast_dates[i])
                    
                    # Update temperatures
                    temp = day_data.get('temp', 0)
                    forecast_temps[i] = "{:.0f}°".format(temp)
                    
                    # Update humidity
                    humidity = day_data.get('humidity', 0)
                    forecast_humidity[i] = "{}%".format(humidity)
                    
                    # Update weather icons
                    icon_code = day_data.get('icon', '')
                    if icon_code in weather_icon_mapping:
                        forecast_icons[i] = weather_icon_mapping[icon_code]
                    else:
                        forecast_icons[i] = "unknown.png"
                        
            print("Forecast data updated successfully")
    except Exception as e:
        print("Error parsing forecast data: {}".format(e))

def parse_weather_data(data):
    global weather_temp, weather_condition, current_icon_file, weather_condition_description, current_wind, current_location
    try:
        weather_temp = data.get("current_temp", 0.0)
        weather_condition = data.get("condition", "")
        current_icon = data.get("current_icon", "")
        wind_speed = data.get("wind_speed", "")
        wind_direction = data.get("wind_direction", "")
        current_location = data.get("location", "Unknown")

        weather_condition_description = "Outside: {:.1f}C, {}".format(weather_temp, weather_condition)
        current_wind = "Wind: {} m/s, {}".format(wind_speed, wind_direction)

        old_icon_file = current_icon_file

        print(current_screen)

        if current_icon in weather_icon_mapping:
                current_icon_file = weather_icon_mapping[current_icon]
        else:
            current_icon_file = "unknown.png"
        
        # Update forecast data as well
        parse_forecast_data(data)
        
        if current_screen == "home":            
            label_condition.setText(weather_condition_description)
            label_wind.setText(current_wind)
            #label_location.setText(label_location)
            if current_icon_file != old_icon_file:
                image_condition.hide()
                image_condition.changeImg("res/{}".format(current_icon_file))
                image_condition.show()

        print("Weather: {:.1f}C {} Icon: {}".format(weather_temp, weather_condition, current_icon))
    except:
        pass

def mqtt_callback(topic, msg):
    global weather_data, weather_alert
    try:
        topic_str = topic.decode('utf-8')
        msg_str = msg.decode('utf-8')
        
        if topic_str == 'weather/data':
            print("Received weather data on topic '{}': {}".format(topic_str, msg_str))
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

def get_page_name(screen_id):
    if screen_id == "status":
        return "Status"
    elif screen_id == "home":
        return "Home"
    elif screen_id == "forecast":
        return "Forecast"
    elif screen_id == "temp_history":
        return "History"
    elif screen_id == "humidity_history":
        return "Humid"
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

def show_header(name):
    global title_text, title_background
    title_background = M5Rect(0, 0, 320, 32, 0x262626, 0x262626)
    title_text = M5TextBox(8, 8, name, lcd.FONT_DejaVu18, 0xffffff, rotate=0)

def create_footer():
    global footer_background, footer_a, footer_b, footer_c
    footer_background = M5Rect(0, 208, 320, 32, 0x262626, 0x262626)
    footer_a = M5TextBox(32, 216, "", lcd.FONT_DejaVu18, 0x888888, rotate=0)
    footer_b = M5TextBox(126, 216, "", lcd.FONT_DejaVu18, 0x888888, rotate=0)
    footer_c = M5TextBox(222, 216, "", lcd.FONT_DejaVu18, 0x888888, rotate=0)


def show_status_screen():
    show_header("System Status")

    global label_wifi, label_env, label_mqtt, label_sd
    
    label_wifi = M5TextBox(8, 48, "WiFi: Disconnected", lcd.FONT_DejaVu18, 0xff0000, rotate=0)
    label_env = M5TextBox(8, 78, "ENV: Disconnected", lcd.FONT_DejaVu18, 0xff0000, rotate=0)
    label_mqtt = M5TextBox(8, 108, "MQTT: Disconnected", lcd.FONT_DejaVu18, 0xff0000, rotate=0)
    label_sd = M5TextBox(8, 138, "SD: Disconnected", lcd.FONT_DejaVu18, 0xff0000, rotate=0)
    create_footer()
    update_footer()

def show_home_screen():
    show_header("Home Screen")
    
    global label_temp, label_hum, label_press, label_condition, image_condition, label_wind, label_location
    
    label_temp = M5TextBox(8, 48, "Temp: --°C", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    label_hum = M5TextBox(8, 74, "Humidity: --%", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    label_press = M5TextBox(8, 100, "Pressure: --hPa", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    label_condition = M5TextBox(8, 126, weather_condition_description, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    label_wind = M5TextBox(8, 152, current_wind, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    # label_location = M5TextBox(8, 178, current_location, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    image_condition = M5Img(248, 44, "res/" + current_icon_file, True)

    update_sensor_labels()

    create_footer()
    update_footer()

def show_forecast_screen():
    global forecast_days, forecast_dates, forecast_temps, forecast_humidity, forecast_icons
    
    show_header("5-Day Forecast")
    
    # Debug: print forecast data to console
    print("Forecast data:")
    print("Days:", forecast_days)
    print("Dates:", forecast_dates)
    print("Temps:", forecast_temps)
    print("Humidity:", forecast_humidity)
    print("Icons:", forecast_icons)
    
    # Add degree symbol in top right
    temp_unit = M5TextBox(280, 8, "°C", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    # Layout for 5 days across 320px screen with some margin
    col_width = 60  # Slightly smaller to add margins
    start_x = 8   # Start with small margin from left edge
    
    # Create forecast for all 5 days
    for i in range(5):
        x_pos = start_x + (i * col_width)
        
        # Day name - use full names for better readability
        if forecast_days[i] == "TODAY":
            day_text = "TOD"  # Shortened to fit
        else:
            day_text = forecast_days[i][:3]  # MON, TUE, etc.
        M5TextBox(x_pos, 48, day_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
        
        # Date (remove month, just day)
        date_short = forecast_dates[i].split('/')[1] if '/' in forecast_dates[i] else forecast_dates[i]
        M5TextBox(x_pos, 74, date_short, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
        
        # Weather icon (try image first, fallback to text)
        try:
            M5Img(x_pos, 98, "res/w32/{}".format(forecast_icons[i]), True)
        except:
            # Fallback weather icons - use single characters
            if "rain" in forecast_icons[i]:
                icon_char = "R"
            elif "sunny" in forecast_icons[i] or "clear" in forecast_icons[i]:
                icon_char = "S"
            elif "cloud" in forecast_icons[i]:
                icon_char = "C"
            elif "snow" in forecast_icons[i]:
                icon_char = "N"
            else:
                icon_char = "?"
            M5TextBox(x_pos, 106, icon_char, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
        
        # Temperature 
        temp_text = forecast_temps[i]
        M5TextBox(x_pos, 150, temp_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
        
        # Humidity
        humid_text = forecast_humidity[i]
        M5TextBox(x_pos, 176, humid_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    create_footer()
    update_footer()

def show_temp_history_screen():
    show_header("Temperature History")
    
    M5TextBox(10, 50, "Temperature history will be displayed here", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_humidity_history_screen():
    show_header("Humidity History")
    
    M5TextBox(10, 50, "Humidity history will be displayed here", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_settings_screen():
    show_header("Settings")
    
    M5TextBox(10, 50, "Settings will be displayed here", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    create_footer()
    update_footer()

def show_alert_screen():
    show_header("Weather Alert")
    
    M5TextBox(10, 50, "Alert information will be displayed here", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
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