# Import only essential modules at startup
from m5stack import lcd, btnA, btnB, btnC
from m5ui import M5TextBox, M5Rect, M5Img, setScreenColor
from uiflow import wait_ms
try:
    from m5ui import rgb
except ImportError:
    try:
        import rgb
    except ImportError:
        rgb = None
import wifiCfg
import time
import ujson
import math

# Initialize RGB LED - using UIFlow rgb object
# RGB is available globally in UIFlow framework

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

# Status strings (optimized)
STATUS_STRINGS = ("Disc", "Conn", "OK", "Fail", "NoWiFi")

def status_to_string(status):
    return STATUS_STRINGS[status] if 0 <= status < len(STATUS_STRINGS) else "Unknown"

setScreenColor(0x000000)

# Screen navigation configuration
screen_navigation = {
    "status": {"A": "home", "B": "home", "C": "home"},
    "home": {"A": "forecast", "B": "history", "C": "settings"},
    "forecast": {"A": "home", "B": "history", "C": "settings"},
    "history": {"A": "home", "B": "forecast", "C": "settings"},
    "settings": {"A": "home", "B": "forecast", "C": "history"},
    "alert": {"A": "home", "B": "home", "C": "home"}
}

current_screen = "status"

# Consolidated global objects
device = {
    'env3_0': None,
    'ntp': None,
    'rtc': None,
    'mqtt_client': None,
    'weather_alert': None
}

# Connection configuration
config = {
    'wifi_ssid': "lightsaber",
    'wifi_password': "skywalker", 
    'mqtt_server': "192.168.137.1",
    'temperature_unit': "C"
}

# Consolidated status tracking
status = {
    'wifi': Status.DISCONNECTED,
    'env': Status.DISCONNECTED,
    'mqtt': Status.DISCONNECTED
}

# Consolidated sensor data
sensor = {
    'temp': None,
    'hum': None,
    'press': None,
    'last_temp': None,
    'last_hum': None,
    'last_press': None
}

# Consolidated weather data
weather = {
    'temp': 0.0,
    'condition': "",
    'icon': "unknown.png",
    'description': "",
    'wind': ""
}

# Consolidated timing
timing = {
    'wifi_check': 0,
    'env_check': 0,
    'mqtt_check': 0,
    'intervals': {
        'wifi': 60000,
        'env': 60000,
        'mqtt': 60000
    }
}

# Temperature conversion functions
def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit"""
    return (celsius * 9.0 / 5.0) + 32.0

def fahrenheit_to_celsius(fahrenheit):
    """Convert Fahrenheit to Celsius"""
    return (fahrenheit - 32.0) * 5.0 / 9.0

def format_temperature(temp_celsius, show_unit=True):
    """Format temperature according to current unit setting"""
    if config['temperature_unit'] == "F":
        temp_value = temp_celsius * 1.8 + 32.0
        if show_unit:
            return "{:.1f}°F".format(temp_value)
        else:
            return "{:.1f}".format(temp_value)
    else:
        if show_unit:
            return "{:.1f}°C".format(temp_celsius)
        else:
            return "{:.1f}".format(temp_celsius)

def get_temperature_unit_symbol():
    """Get the current temperature unit symbol"""
    return "°F" if config['temperature_unit'] == "F" else "°C"

# Use tuples for weather icon mapping (more memory efficient)
weather_icon_mapping = (
    ('01d', 'clear.png'), ('01n', 'nt_clear.png'),
    ('02d', 'mostlysunny.png'), ('02n', 'cloudy.png'),
    ('03d', 'cloudy.png'), ('03n', 'nt_cloudy.png'),
    ('04d', 'cloudy.png'), ('04n', 'nt_cloudy.png'),
    ('09d', 'rain.png'), ('09n', 'nt_rain.png'),
    ('10d', 'rain.png'), ('10n', 'nt_rain.png'),
    ('11d', 'tstorms.png'), ('11n', 'nt_tstorms.png'),
    ('13d', 'snow.png'), ('13n', 'nt_snow.png'),
    ('50d', 'fog.png'), ('50n', 'nt_fog.png')
)

def get_weather_icon(icon_code):
    """Get weather icon filename from code"""
    for code, icon in weather_icon_mapping:
        if code == icon_code:
            return icon
    return "unknown.png"

# Compact forecast data structure - array of tuples
forecast_data = [None] * 5  # (day, date, temp, humidity, icon)
history_data = [None] * 5   # (day, date, temp, humidity)

def fetch_time():
    print("Fetching NTP time...")
    try:
        # Runtime imports for time functionality
        import ntptime
        from machine import RTC
        
        device['ntp'] = ntptime.client(host='de.pool.ntp.org', timezone=2)
        device['rtc'] = RTC()
        print("NTP time fetched successfully")
    except Exception as e:
        print("Failed to fetch NTP time")

def check_wifi_connection():
    old_status = status['wifi']
    
    if not wifiCfg.wlan_sta.isconnected():
        status['wifi'] = Status.CONNECTING
        wifiCfg.doConnect(config['wifi_ssid'], config['wifi_password'])
        if wifiCfg.wlan_sta.isconnected():
            status['wifi'] = Status.CONNECTED
        else:
            status['wifi'] = Status.FAILED
    else:
        status['wifi'] = Status.CONNECTED
    
    if old_status != status['wifi']:
        print("WiFi status changed")
        if status['wifi'] == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")

def check_env_connection():
    old_status = status['env']
    
    try:
        # Runtime import for unit functionality
        import unit
        
        status['env'] = Status.CONNECTING
        if device['env3_0'] is None:
            device['env3_0'] = unit.get(unit.ENV3, unit.PORTA)
        temp = device['env3_0'].temperature
        status['env'] = Status.CONNECTED
        result = True
    except:
        status['env'] = Status.FAILED
        device['env3_0'] = None
        result = False
    
    if old_status != status['env']:
        print("ENV status changed")
        if status['env'] == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")
    
    return result

def parse_forecast_data(weather_data):
    """Parse forecast data from weather JSON and update forecast data structure"""
    try:
        if 'forecast' in weather_data:
            for i, day_data in enumerate(weather_data['forecast'][:5]):
                temp = day_data.get('temp', 0)
                humidity = day_data.get('humidity', 0)
                icon_code = day_data.get('icon', '')
                
                forecast_data[i] = (
                    day_data.get('day', '')[:3],  # Truncate day name
                    day_data.get('date', ''),
                    "{}°".format(format_temperature(temp, False)),
                    "{}%".format(humidity),
                    get_weather_icon(icon_code)
                )
    except:
        pass

def parse_history_data(weather_data):
    """Parse historical data from weather JSON and update history data structure"""
    try:
        if 'history' in weather_data:
            for i, day_data in enumerate(weather_data['history'][:5]):
                temp = day_data.get('temp', 0)
                humidity = day_data.get('humidity', 0)
                
                history_data[i] = (
                    day_data.get('day', '')[:3],  # Truncate day name
                    day_data.get('date', ''),
                    temp,
                    "{}%".format(humidity)
                )
    except:
        pass

def parse_weather_data(data):
    try:
        weather['temp'] = data.get("current_temp", 0.0)
        weather['condition'] = data.get("condition", "")
        current_icon = data.get("current_icon", "")
        wind_speed = data.get("wind_speed", "")
        wind_direction = data.get("wind_direction", "")
        current_location = data.get("location", "Unknown")

        weather['description'] = "O: {}, {}".format(format_temperature(weather['temp'], True), weather['condition'])
        weather['wind'] = "Wind: {} m/s, {}".format(wind_speed, wind_direction)

        old_icon = weather['icon']
        weather['icon'] = get_weather_icon(current_icon)
        
        # Update forecast and history data
        parse_forecast_data(data)
        parse_history_data(data)
        
        # Update UI only if on home screen
        if current_screen == "home":
            update_home_display()
    except:
        pass

def update_home_display():
    """Update home screen display elements"""
    try:
        # This will be implemented with lazy UI creation
        pass
    except:
        pass

def mqtt_callback(topic, msg):
    try:
        topic_str = topic.decode('utf-8')
        msg_str = msg.decode('utf-8')
        
        print("MQTT received topic: {}".format(topic_str))
        print("MQTT message: {}".format(msg_str))
        
        if topic_str == 'weather/data':
            weather_data = ujson.loads(msg_str)
            parse_weather_data(weather_data)
        elif topic_str == 'weather/alert_trigger':
            print("Processing weather alert...")
            device['weather_alert'] = ujson.loads(msg_str)
            print("Alert parsed: {}".format(device['weather_alert']))
            # Handle RGB alert based on level
            alert_level = device['weather_alert'].get("level", "info")
            handle_rgb_alert(alert_level)
            # Navigate to alert screen when alert is received
            print("Navigating to alert screen...")
            navigate_to_screen("alert")
    except Exception as e:
        print("MQTT callback error: {}".format(e))
        pass

def check_mqtt_connection():
    old_status = status['mqtt']
    
    if not wifiCfg.wlan_sta.isconnected():
        status['mqtt'] = Status.NO_WIFI
        result = False
    else:
        try:
            # Runtime import for MQTT functionality
            from umqtt.simple import MQTTClient
            
            status['mqtt'] = Status.CONNECTING
            
            if device['mqtt_client'] is None:
                device['mqtt_client'] = MQTTClient("m5go_env", config['mqtt_server'])
                device['mqtt_client'].set_callback(mqtt_callback)
            
            device['mqtt_client'].connect()
            device['mqtt_client'].subscribe("weather/data")
            device['mqtt_client'].subscribe("weather/alert_trigger")
            
            status['mqtt'] = Status.CONNECTED
            result = True
        except:
            status['mqtt'] = Status.FAILED
            device['mqtt_client'] = None
            result = False
    
    if old_status != status['mqtt']:
        print("MQTT status changed")
        if status['mqtt'] == Status.FAILED and current_screen != "status":
            navigate_to_screen("status")
    
    return result

def send_mqtt_data(temperature, humidity, pressure):
    if device['mqtt_client'] is None or status['mqtt'] != Status.CONNECTED:
        print("MQTT not connected, skipping data send")
        return False
    
    try:
        timestamp = get_datetime_string()
        message = '{{"timestamp":"{}","temperature":{},"humidity":{},"pressure":{}}}'.format(timestamp, temperature, humidity, pressure)
        topic = b"weather/sensor_data"
        
        device['mqtt_client'].publish(topic, message)
        print("Sent MQTT data")
        return True
    except Exception as e:
        print("Failed to send MQTT data")
        return False

def get_date_string():
    if device['ntp'] is None:
        fetch_time()
    return device['ntp'].formatDate('-') if device['ntp'] else "unknown"

def get_datetime_string():
    try:
        # Runtime import for time functionality
        from machine import RTC
        
        if device['ntp'] is None:
            fetch_time()
        device['rtc'] = RTC()
        year, month, day, _, hour, minute, second, _ = device['rtc'].datetime()
        return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(year, month, day, hour, minute, second)
    except:
        return "unknown"

# Remove SD card functionality to save memory - not needed for core weather station
# def check_sd_card(): removed

def clear_screen():
    lcd.clear()
    setScreenColor(0x111111)
    # Force garbage collection for memory optimization
    import gc
    gc.collect()

def get_page_name(screen_id):
    page_names = {
        "status": "Status",
        "home": "Home", 
        "forecast": "Forecast",
        "history": "History",
        "settings": "Settings",
        "alert": "Alert"
    }
    return page_names.get(screen_id, "--")

def get_temp_color(temp):
    """Calculate color based on dynamic temperature scale with ±3°C buffer"""
    # Convert temperature to Celsius for consistent color calculation
    temp_celsius = temp
    if config['temperature_unit'] == "F":
        temp_celsius = fahrenheit_to_celsius(temp)
    
    # Find min and max temperatures in history data
    if history_data and any(h for h in history_data if h):
        temp_values = [h[2] for h in history_data if h]
        if temp_values:
            min_temp = min(temp_values) - 3
            max_temp = max(temp_values) + 3
        else:
            min_temp, max_temp = 10, 40
    else:
        min_temp, max_temp = 10, 40
    
    # Clamp and interpolate color
    if temp_celsius <= min_temp:
        return 0x9acd32  # Yellow-green
    elif temp_celsius >= max_temp:
        return 0xff8c00  # Dark orange
    else:
        ratio = (temp_celsius - min_temp) / (max_temp - min_temp)
        red = int(154 + (255 - 154) * ratio)
        green = int(205 + (140 - 205) * ratio)
        blue = int(50 + (0 - 50) * ratio)
        return (red << 16) | (green << 8) | blue

def get_humidity_color(humidity):
    """Calculate color based on dynamic humidity scale with ±3% buffer"""
    # Find min and max humidity in history data
    if history_data and any(h for h in history_data if h):
        humidity_values = [float(h[3].rstrip('%')) for h in history_data if h and h[3] != "0%"]
        if humidity_values:
            min_humidity = max(0, min(humidity_values) - 3)
            max_humidity = min(100, max(humidity_values) + 3)
        else:
            min_humidity, max_humidity = 0, 100
    else:
        min_humidity, max_humidity = 0, 100
    
    # Clamp and interpolate color
    if humidity <= min_humidity:
        return 0x87ceeb  # Light blue
    elif humidity >= max_humidity:
        return 0x000080  # Deep blue
    else:
        ratio = (humidity - min_humidity) / (max_humidity - min_humidity)
        red = int(135 * (1 - ratio))
        green = int(206 * (1 - ratio))
        blue = int(235 * (1 - ratio) + 128 * ratio)
        return (red << 16) | (green << 8) | blue

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
        elif screen_name == "history":
            show_history_screen()
        elif screen_name == "settings":
            show_settings_screen()
        elif screen_name == "alert":
            show_alert_screen()

def get_bar_height(value, data_type="temp", max_height=40):
    """Calculate bar height based on value"""
    if data_type == "temp" and history_data:
        data_list = [h[2] for h in history_data if h]
    elif data_type == "humidity" and history_data:
        data_list = [float(h[3].rstrip('%')) for h in history_data if h and h[3] != "0%"]
    else:
        data_list = []
    
    if len(data_list) > 0:
        min_val = min(data_list)
        max_val = max(data_list)
        
        if min_val == max_val:
            return max_height // 2
        
        # Add buffer range
        if data_type == "temp":
            min_val -= 3
            max_val += 3
        else:  # humidity
            min_val = max(0, min_val - 3)
            max_val = min(100, max_val + 3)
    else:
        min_val, max_val = (10, 40) if data_type == "temp" else (0, 100)
    
    # Scale value
    if value <= min_val:
        return 5
    elif value >= max_val:
        return max_height
    else:
        ratio = (value - min_val) / (max_val - min_val)
        return int(5 + (max_height - 5) * ratio)

def update_footer():
    # With lazy UI creation, footer is created fresh each time in create_footer()
    pass

def show_header(name):
    M5Rect(0, 0, 320, 32, 0x262626, 0x262626)
    M5TextBox(8, 8, name, lcd.FONT_DejaVu18, 0xffffff, rotate=0)

def create_footer():
    M5Rect(0, 208, 320, 32, 0x262626, 0x262626)
    
    if current_screen in screen_navigation:
        nav = screen_navigation[current_screen]
        
        # Special case for status screen when navigation is blocked
        if current_screen == "status" and not can_navigate_from_status():
            footer_a = footer_b = footer_c = ""
        else:
            footer_a = get_page_name(nav.get("A", "--"))
            footer_b = get_page_name(nav.get("B", "--"))
            footer_c = get_page_name(nav.get("C", "--"))
        
        M5TextBox(32, 216, footer_a, lcd.FONT_DejaVu18, 0x888888, rotate=0)
        M5TextBox(126, 216, footer_b, lcd.FONT_DejaVu18, 0x888888, rotate=0)
        M5TextBox(222, 216, footer_c, lcd.FONT_DejaVu18, 0x888888, rotate=0)


def show_status_screen():
    show_header("System Status")

    # Lazy UI creation with current status
    wifi_color = COLOR_GREEN if status['wifi'] == Status.CONNECTED else (COLOR_YELLOW if status['wifi'] == Status.CONNECTING else COLOR_RED)
    env_color = COLOR_GREEN if status['env'] == Status.CONNECTED else (COLOR_YELLOW if status['env'] == Status.CONNECTING else COLOR_RED)
    mqtt_color = COLOR_GREEN if status['mqtt'] == Status.CONNECTED else (COLOR_YELLOW if status['mqtt'] == Status.CONNECTING else COLOR_RED)
    
    wifi_text = "WiFi: {}".format(status_to_string(status['wifi']))
    env_text = "ENV: {}".format(status_to_string(status['env']))
    mqtt_text = "MQTT: {}".format(status_to_string(status['mqtt']))
    
    M5TextBox(8, 48, wifi_text, lcd.FONT_DejaVu18, wifi_color, rotate=0)
    M5TextBox(8, 78, env_text, lcd.FONT_DejaVu18, env_color, rotate=0)
    M5TextBox(8, 108, mqtt_text, lcd.FONT_DejaVu18, mqtt_color, rotate=0)
    # Removed SD status to save memory
    
    create_footer()
    update_footer()

def show_home_screen():
    show_header("Home Screen")
    
    # Lazy UI creation - create elements inline, don't store globally
    temp_text = "Temp: {}".format(format_temperature(sensor['temp'], True)) if sensor['temp'] is not None else "Temp: --{}".format(get_temperature_unit_symbol())
    hum_text = "Humidity: {:.1f}%".format(sensor['hum']) if sensor['hum'] is not None else "Humidity: --%"
    press_text = "Pressure: {:.1f}hPa".format(sensor['press']) if sensor['press'] is not None else "Pressure: --hPa"
    
    M5TextBox(8, 48, temp_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(8, 74, hum_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(8, 100, press_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(8, 126, weather['description'], lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(8, 152, weather['wind'], lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    M5Img(248, 44, "res/{}".format(weather['icon']), True)

    create_footer()
    update_footer()

def show_forecast_screen():
    show_header("5-Day Forecast")
    
    # Add degree symbol in top right
    M5TextBox(280, 8, get_temperature_unit_symbol(), lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    # Layout for 5 days across 320px screen
    col_width = 60
    start_x = 8
    
    # Create forecast for 5 days using new data structure
    for i in range(5):
        x_pos = start_x + (i * col_width)
        
        if forecast_data[i]:
            day, date, temp, humidity, icon = forecast_data[i]
            
            # Day name
            day_text = "TOD" if day == "TOD" else day
            M5TextBox(x_pos, 48, day_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            
            # Date
            date_short = date.split('/')[0] if '/' in date else date
            M5TextBox(x_pos, 74, date_short, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            
            # Weather icon
            try:
                M5Img(x_pos, 98, "res/w32/{}".format(icon), True)
            except:
                icon_char = "?" 
                if "rain" in icon:
                    icon_char = "R"
                elif "sunny" in icon or "clear" in icon:
                    icon_char = "S"
                elif "cloud" in icon:
                    icon_char = "C"
                M5TextBox(x_pos, 106, icon_char, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            
            # Temperature and humidity
            M5TextBox(x_pos, 150, temp, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            M5TextBox(x_pos, 176, humidity, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    create_footer()
    update_footer()

def show_history_screen():
    show_header("Past 5 Days")
    
    # Add symbols in top right
    M5TextBox(260, 8, get_temperature_unit_symbol(), lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(290, 8, "%", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    # Layout for 5 time periods
    col_width = 60
    start_x = 8
    
    # Create history display using new data structure
    for i in range(5):
        x_pos = start_x + (i * col_width)
        
        if history_data[i]:
            day, date, temp, humidity = history_data[i]
            humidity_val = float(humidity.rstrip('%')) if humidity != "0%" else 0
            
            # Day abbreviation
            day_text = "TOD" if day == "TOD" else day
            M5TextBox(x_pos, 48, day_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            
            # Date
            date_short = date.split('/')[0] if '/' in date else date
            M5TextBox(x_pos, 74, date_short, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            
            # Temperature and humidity bars
            max_bar_height = 66
            temp_bar_height = get_bar_height(temp, "temp", max_bar_height)
            humidity_bar_height = get_bar_height(humidity_val, "humidity", max_bar_height)
            
            # Get colors for bars
            temp_bar_color = get_temp_color(temp)
            humidity_bar_color = get_humidity_color(humidity_val)
            
            # Temperature bar (left side)
            temp_bar_x = x_pos + 8
            temp_bar_y = 82 + (max_bar_height - temp_bar_height)
            M5Rect(temp_bar_x, temp_bar_y, 10, temp_bar_height, temp_bar_color, temp_bar_color)
            
            # Humidity bar (right side)
            humidity_bar_x = temp_bar_x + 12
            humidity_bar_y = 82 + (max_bar_height - humidity_bar_height)
            M5Rect(humidity_bar_x, humidity_bar_y, 10, humidity_bar_height, humidity_bar_color, humidity_bar_color)
            
            # Temperature and humidity values
            temp_text = "{}°".format(format_temperature(temp, False))
            M5TextBox(x_pos, 154, temp_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
            M5TextBox(x_pos, 180, humidity, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    
    create_footer()
    update_footer()

def show_settings_screen():
    show_header("Settings")
    
    # Lazy UI creation
    temp_unit_text = "Temperature Unit: {}".format(get_temperature_unit_symbol())
    M5TextBox(8, 48, temp_unit_text, lcd.FONT_DejaVu18, 0xffffff, rotate=0)
    M5TextBox(8, 70, "Double-tap C to change unit", lcd.FONT_DejaVu18, 0x888888, rotate=0)
    
    # Show simplified connection status
    wifi_text = "WiFi: {}".format(status_to_string(status['wifi']))
    env_text = "ENV: {}".format(status_to_string(status['env']))
    mqtt_text = "MQTT: {}".format(status_to_string(status['mqtt']))
    
    M5TextBox(8, 100, wifi_text, lcd.FONT_DejaVu18, 0x888888, rotate=0)
    M5TextBox(8, 125, env_text, lcd.FONT_DejaVu18, 0x888888, rotate=0)
    M5TextBox(8, 150, mqtt_text, lcd.FONT_DejaVu18, 0x888888, rotate=0)
    
    create_footer()
    update_footer()

def show_alert_screen():
    if device['weather_alert'] is None:
        show_header("Weather Alert")
        M5TextBox(10, 50, "No active alerts", lcd.FONT_DejaVu18, 0xffffff, rotate=0)
        create_footer()
        return
    
    # Get alert details
    alert_message = device['weather_alert'].get("message", "Unknown alert")
    alert_level = device['weather_alert'].get("level", "info")
    alert_timestamp = device['weather_alert'].get("timestamp", "")
    
    # Get colors based on alert level
    if alert_level == "emergency":
        bg_color = 0x8B0000
        text_color = 0xFFFFFF
    elif alert_level == "warning":
        bg_color = 0xB8860B
        text_color = 0x000000
    else:  # info or default
        bg_color = 0x000080
        text_color = 0xFFFFFF
    
    # Set background color
    setScreenColor(bg_color)
    
    # Show header
    show_header("Alert - {}".format(alert_level.upper()))
    
    # Display alert message - split into multiple lines if needed
    if len(alert_message) > 40:
        first_line = alert_message[:40]
        second_line = alert_message[40:]
        if len(second_line) > 35:
            second_line = second_line[:32] + "..."
        M5TextBox(8, 50, first_line, lcd.FONT_DejaVu18, text_color, rotate=0)
        M5TextBox(8, 75, second_line, lcd.FONT_DejaVu18, text_color, rotate=0)
        y_pos = 100
    else:
        M5TextBox(8, 50, alert_message, lcd.FONT_DejaVu18, text_color, rotate=0)
        y_pos = 75
    
    # Display timestamp if available
    if alert_timestamp:
        M5TextBox(8, y_pos, "Time: {}".format(alert_timestamp), lcd.FONT_DejaVu18, text_color, rotate=0)
    
    # Display dismiss instruction
    M5TextBox(8, 190, "Press B to dismiss", lcd.FONT_DejaVu18, text_color, rotate=0)
    
    create_footer()

# RGB alert control - using UIFlow rgb methods
def handle_rgb_alert(alert_level=None):
    """Handle RGB lighting based on alert level"""
    try:
        if rgb is None:
            return
        if alert_level == "emergency":
            rgb.setColorFrom(1, 10, 0xff0000)  # Red
            rgb.setBrightness(255)
        elif alert_level == "warning":
            rgb.setColorFrom(1, 10, 0xffff00)  # Yellow
            rgb.setBrightness(255)
        elif alert_level == "info":
            rgb.setColorFrom(1, 10, 0x0000ff)  # Blue
            rgb.setBrightness(255)
        else:
            rgb.setColorFrom(1, 10, 0x000000)  # Off
            rgb.setBrightness(0)
    except Exception as e:
        print("RGB error: {}".format(e))

def update_rgb_emergency():
    """Update RGB for emergency breathing effect"""
    try:
        if rgb is None:
            return
        if device['weather_alert'] and device['weather_alert'].get("level") == "emergency":
            current_time = time.ticks_ms()
            brightness = int(128 + 127 * math.sin(current_time / 500))
            rgb.setColorFrom(1, 10, 0xff0000)
            rgb.setBrightness(brightness)
    except Exception as e:
        print("RGB emergency update error: {}".format(e))

def can_navigate_from_status():
    return (status['wifi'] == Status.CONNECTED and 
            status['env'] == Status.CONNECTED and 
            status['mqtt'] == Status.CONNECTED)

def buttonA_wasPressed():
    global current_screen
    
    # Block navigation from alert screen (only B button dismisses)
    if current_screen == "alert":
        return
    
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "A" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["A"]
        navigate_to_screen(next_screen)

def buttonB_wasPressed():
    global current_screen
    
    # Special handling for alert screen - dismiss alert
    if current_screen == "alert":
        device['weather_alert'] = None  # Clear the alert
        handle_rgb_alert(None)  # Clear RGB alert
        navigate_to_screen("home")  # Return to home screen
        return
    
    # Normal navigation behavior for other screens
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "B" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["B"]
        navigate_to_screen(next_screen)

def buttonC_wasDoublePress():
    """Handle double-press of button C to toggle temperature unit"""
    # Toggle temperature unit
    if config['temperature_unit'] == "C":
        config['temperature_unit'] = "F"
    else:
        config['temperature_unit'] = "C"
    
    # Update the settings screen display if currently on settings
    if current_screen == "settings":
        show_settings_screen()

def buttonC_wasPressed():
    global current_screen
    
    # Block navigation from alert screen (only B button dismisses)
    if current_screen == "alert":
        return
    
    # Normal navigation behavior
    if current_screen == "status" and not can_navigate_from_status():
        return
    if current_screen in screen_navigation and "C" in screen_navigation[current_screen]:
        next_screen = screen_navigation[current_screen]["C"]
        navigate_to_screen(next_screen)

def update_sensor_labels():
    # With lazy UI creation, we just refresh the screen when on home
    if current_screen == "home":
        show_home_screen()

def has_significant_change(temp, hum, press):
    if sensor['last_temp'] is None:
        return True
    
    temp_changed = abs(temp - sensor['last_temp']) > 0.5
    hum_changed = abs(hum - sensor['last_hum']) > 1.0
    press_changed = abs(press - sensor['last_press']) > 1.0
    
    return temp_changed or hum_changed or press_changed

def update_status_labels():
    if current_screen == "status" or current_screen == "settings":
        # Refresh the entire screen with lazy UI creation
        if current_screen == "status":
            show_status_screen()
        elif current_screen == "settings":
            show_settings_screen()
        
        # Auto-navigate to home when all required connections are ready (only from status screen)
        if current_screen == "status" and can_navigate_from_status():
            navigate_to_screen("home")

print("Starting M5GO ENV III Sensor System...")

# Initialize status screen immediately to show connection progress
navigate_to_screen("status")

# Set up button callbacks
btnA.wasPressed(buttonA_wasPressed)
btnB.wasPressed(buttonB_wasPressed)
btnC.wasPressed(buttonC_wasPressed)

# Try to set up double-press callback if available
try:
    btnC.wasDoublePress(buttonC_wasDoublePress)
except:
    pass

# Start connection attempts - user can see progress on status screen
check_wifi_connection()
check_env_connection()
check_mqtt_connection()
# Removed SD card check to save memory

while True:
    current_time = time.ticks_ms()
    
    if current_time - timing['wifi_check'] >= timing['intervals']['wifi']:
        check_wifi_connection()
        timing['wifi_check'] = current_time
    
    if current_time - timing['env_check'] >= timing['intervals']['env']:
        check_env_connection()
        timing['env_check'] = current_time
    
    if current_time - timing['mqtt_check'] >= timing['intervals']['mqtt']:
        check_mqtt_connection()
        timing['mqtt_check'] = current_time
    
    # Removed SD card check to save memory
    
    if device['mqtt_client'] is not None:
        try:
            device['mqtt_client'].check_msg()
        except:
            device['mqtt_client'] = None
    
    # Update status labels
    update_status_labels()
    
    # Update sensor data and labels
    if device['env3_0'] is not None:
        try:
            temp = device['env3_0'].temperature
            humidity = device['env3_0'].humidity
            pressure = device['env3_0'].pressure
            
            # Check if values changed significantly and log if needed
            if has_significant_change(temp, humidity, pressure):
                log_env_data(temp, humidity, pressure)
                
                # Update last values
                sensor['last_temp'] = sensor['temp']
                sensor['last_hum'] = sensor['hum']
                sensor['last_press'] = sensor['press']
            
            # Update current values
            sensor['temp'] = temp
            sensor['hum'] = humidity
            sensor['press'] = pressure
            
            update_sensor_labels()
        except:
            sensor['temp'] = None
            sensor['hum'] = None
            sensor['press'] = None
            update_sensor_labels()
            device['env3_0'] = None
    else:
        sensor['temp'] = None
        sensor['hum'] = None
        sensor['press'] = None
        update_sensor_labels()
    
    # Update RGB emergency breathing effect
    update_rgb_emergency()
    
    wait_ms(1000)