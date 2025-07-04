# M5GO ENV III Weather Station

A comprehensive weather monitoring system for the M5GO device with ENV III sensor unit, featuring real-time sensor data collection, weather forecasting, and MQTT connectivity.

## Features

- **Multi-Screen Interface**: Navigate between Status, Home, Forecast, History, Settings, and Alert screens
- **Real-time Sensor Data**: Temperature, humidity, and pressure monitoring via ENV III sensor
- **Weather Integration**: Display current conditions, 5-day forecast, and historical data
- **MQTT Connectivity**: Publish sensor data and receive weather updates via MQTT
- **Temperature Units**: Support for both Celsius and Fahrenheit (toggle with double-press C button)
- **Visual Indicators**: Color-coded displays and RGB LED alerts for weather conditions
- **Alert System**: Emergency, warning, and info weather alerts with visual and RGB notifications

## Hardware Requirements

- M5GO device
- ENV III sensor unit (connected to Port A)
- WiFi network connectivity
- MQTT server for data exchange

## Screen Navigation

- **Button A**: Navigate to different screens (varies by current screen)
- **Button B**: Navigate to different screens / Dismiss alerts
- **Button C**: Navigate to different screens / Double-press to toggle temperature unit
- **Status Screen**: Shows connection status for WiFi, ENV sensor, and MQTT
- **Home Screen**: Real-time sensor readings and current weather
- **Forecast Screen**: 5-day weather forecast with icons and data
- **History Screen**: Past 5 days of weather data with visual bar charts
- **Settings Screen**: Configuration options and connection status
- **Alert Screen**: Weather alerts with color-coded severity levels

## Configuration

Update the configuration section in `main.py`:

```python
config = {
    'wifi_ssid': "your_wifi_ssid",
    'wifi_password': "your_wifi_password", 
    'mqtt_server': "your_mqtt_server_ip",
    'temperature_unit': "C"  # or "F"
}
```

## MQTT Topics

- **Publish**: `weather/sensor_data` - Sensor readings from ENV III
- **Subscribe**: `weather/data` - Weather forecast and current conditions
- **Subscribe**: `weather/alert_trigger` - Weather alerts and warnings

## Weather Data Format

The system expects weather data in JSON format with the following structure:

```json
{
  "location": "LAT: XX.XXXX, LON: XX.XXXX",
  "condition": "scattered clouds",
  "current_icon": "03n",
  "current_temp": 17.62,
  "wind_speed": 1.4,
  "wind_direction": "NW",
  "forecast": [
    {
      "day": "TODAY",
      "date": "04/07",
      "temp": 28.32,
      "humidity": 39,
      "icon": "01d"
    }
  ],
  "history": [
    {
      "day": "SAT",
      "date": "28/06",
      "temp": 32.0,
      "humidity": 85
    }
  ]
}
```

## Weather Icons

The system includes weather icons for various conditions:
- Clear/Sunny (day/night variants)
- Cloudy/Partly cloudy
- Rain/Chance of rain
- Snow/Flurries
- Thunderstorms
- Fog/Haze
- And more...

Icons are stored in `img/w32/` directory in PNG format.

## Alert System

Weather alerts support three severity levels:
- **Emergency**: Red background, red RGB LED, breathing effect
- **Warning**: Yellow/gold background, yellow RGB LED
- **Info**: Blue background, blue RGB LED

## Memory Optimization

The code is optimized for M5GO's memory constraints:
- Lazy UI creation (elements created when needed)
- Runtime imports to reduce startup memory usage
- Efficient data structures using tuples
- Garbage collection at strategic points

## Installation

1. Copy all files to your M5GO device
2. Ensure `img/w32/` directory contains weather icons
3. Update configuration in `main.py`
4. Run `main.py` to start the weather station

## Dependencies

- M5Stack libraries (m5stack, m5ui, uiflow)
- MicroPython MQTT client (umqtt.simple)
- WiFi configuration (wifiCfg)
- Standard MicroPython modules (time, ujson, math)

## Usage

1. Device boots to Status screen showing connection progress
2. Once all services are connected, automatically navigates to Home screen
3. Use buttons to navigate between screens
4. Double-press C button to toggle temperature units
5. Weather alerts automatically display when received via MQTT
6. System continuously monitors sensor data and publishes changes

## Troubleshooting

- Check WiFi credentials if connection fails
- Verify MQTT server is accessible
- Ensure ENV III sensor is properly connected to Port A
- Check that weather icons are present in `img/w32/` directory
- Monitor serial output for debugging information