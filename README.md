# AppDaemon Blinds Automation

An advanced AppDaemon application for Home Assistant that provides sophisticated blind control based on sun position, brightness levels, and various other conditions.

## Features

- Automatic blind positioning based on sun position relative to facade
- Smart shadow protection with configurable thresholds
- Dawn/dusk handling with separate brightness detection
- Solar heating functionality
- Ventilation mode support
- Window lockout protection
- Manual override detection with automatic return to automation
- State persistence across restarts
- Configurable transition delays
- Support for slat geometry calculations
- Automated angle calculations for optimal shading

## Requirements

- Home Assistant with AppDaemon 4.x
- Cover entity with support for position and tilt control (0-100%)
- Brightness sensor(s)
- Optional: Window contact sensor
- Optional: Climate entity for solar heating

## Installation

1. Copy `blinds.py` to your AppDaemon `apps` directory
2. Add your configuration to `apps.yaml`
3. Restart AppDaemon

## Configuration

Example configuration:

```yaml
living_room_blinds:
  module: blinds
  class: Blinds
  
  unique_id: living_room  # Required: Unique identifier (no spaces)
  
  entities:
    cover: cover.living_room_blinds        # Required: Your cover entity
    brightness_shadow: sensor.brightness    # Required: Brightness sensor
    brightness_dawn: sensor.brightness_2    # Optional: Separate dawn sensor
    window_sensor: binary_sensor.window    # Optional: Window contact
    climate: climate.living_room           # Optional: For solar heating
  
  facade:
    facade_angle: 253          # Direction the facade faces (degrees)
    facade_offset_entry: -50   # When sun starts hitting facade
    facade_offset_exit: 50     # When sun stops hitting facade
    min_elevation: 0          # Min sun elevation for shadow handling
    max_elevation: 90         # Max sun elevation for shadow handling
```

See `apps.example.yaml` for full configuration options.

## States and Transitions

The app manages several states for smooth transitions:

1. NEUTRAL - Default state
2. SHADOW - Active sun protection
3. DAWN - Dawn/dusk handling
4. Various transition states with configurable delays

## Features in Detail

### Shadow Protection
- Calculates optimal slat angles based on sun position
- Considers slat geometry for precise shading
- Configurable brightness thresholds
- Support for dynamic brightness thresholds

### Dawn/Dusk Handling
- Separate dawn mode with configurable positions
- Optional prevention of upward movement after dusk
- Separate brightness thresholds for dawn detection

### Solar Heating
- Temperature-based blind control
- Configurable target temperature and hysteresis
- Separate position settings for solar heating mode

### Safety Features
- Window lockout protection
- Ventilation mode
- Manual override detection
- External lock timer

### Physical Constraints
- Minimum/maximum angle limits
- Step-based movement
- Movement tolerance settings
- Slat geometry configuration

## Generated Entities

The app creates several helper entities in Home Assistant:

- `input_boolean.[unique_id]_blinds_locked` - Manual lock
- `input_boolean.[unique_id]_blinds_locked_external` - External control lock (Lock will be activated when Blinds are moved outside of this App. You can configure for how long it will be locked till it switches back to automated mode)
- `input_boolean.[unique_id]_manipulation_active` - Manual override active (Should be used, when Blinds are moved by a Home Assistant Automation. Blinds are locked till the lock is released again)
- `input_boolean.[unique_id]_solar_heating_active` - Solar heating status
- `input_boolean.[unique_id]_solar_heating_status` - Current solar heating state

## Debugging

Enable debug logging by setting `DEBUG: true` in your configuration to get detailed logging information.

## Notes

- All angles are in degrees (0-360)
- All positions are in percentages (0-100)
- 0% tilt = fully closed, 100% tilt = fully open
- 0% height = fully closed, 100% height = fully open

## License

This project is licensed under the MIT License - see the LICENSE file for details.
