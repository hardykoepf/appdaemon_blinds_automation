# AppDaemon Blinds and Shutter Automation

This AppDaemon application provides automated control for venetian blinds and roller shutters based on sun position, brightness, and other environmental factors. It includes sophisticated state management and supports various scenarios like shadowing, dawn/dusk behavior, and ventilation.

## Features

### Common Features (Blinds & Shutters)
- Automatic positioning based on sun position and brightness
- Multiple operational states (neutral, shadow, dawn)
- Configurable delays between state changes
- Ventilation support with window sensor integration
- Lockout protection
- Solar heating functionality
- Manual override protection with automatic timeout
- State persistence across restarts
- Extensive debugging options

### Venetian Blinds Specific
- Automatic slat angle calculation based on sun elevation
- Effective slat width calculation considering sun azimuth
- Configurable slat geometry (width, distance)
- Height and angle stepping for precise control

### Roller Shutters Specific
- Height-only control optimized for roller shutters
- Light strip calculation for partial closure
- Simplified state management

### Configuration Management
- Automatic entity creation via EntityCollector
- YAML configuration generation for Home Assistant
- One-time setup of required input_boolean entities

## Installation

1. Copy the following files to your AppDaemon apps directory:
   ```
   apps/
   ├── blinds.py
   ├── shutter.py
   └── helpers/
       └── entity_collector.py
   ```

2. Configure your `apps.yaml` with the desired instances (see Configuration section)

3. Run AppDaemon - it will generate a configuration file for required entities

4. Copy the generated entity configurations to your Home Assistant `configuration.yaml`

5. Restart Home Assistant to create the entities

## Configuration

### Basic Structure
```yaml
blinds_living:
  module: blinds
  class: Blinds
  unique_id: living_blinds
  entities:
    cover: cover.living_blinds
    brightness_shadow: sensor.outdoor_brightness
    window_sensor: binary_sensor.living_window

shutter_bedroom:
  module: shutter
  class: Shutter
  unique_id: bedroom_shutter
  entities:
    cover: cover.bedroom_shutter
    brightness_shadow: sensor.outdoor_brightness
```

### Common Configuration Options

| Parameter | Description |
|-----------|-------------|
| `unique_id` | Unique identifier (used for entity names) |
| `facade.facade_angle` | Facade orientation in degrees |
| `facade.facade_offset_entry` | Sun angle when to start shadowing |
| `facade.facade_offset_exit` | Sun angle when to stop shadowing |
| `shadow_active` | Enable/disable shadow functionality |
| `dawn_active` | Enable/disable dawn functionality |

See full configuration examples in the `examples` directory.

## State Machine

Both blinds and shutters operate using a state machine with different states for various conditions:

### Blinds States
- NEUTRAL: Default position
- SHADOW: Active sun protection
- DAWN: Night/low-light position
- Various transition states with timers

### Shutter States
- NEUTRAL: Default position
- SHADOW: Sun protection position
- DAWN: Night position
- Transition states

## Entity Creation

The EntityCollector automatically generates required input_boolean entities:
- `*_blinds_locked`: Manual lock
- `*_blinds_locked_external`: Automatic lock after manual intervention
- `*_manipulation_active`: Manual mode indicator
- `*_solar_heating_active`: Solar heating mode switch
- `*_solar_heating_status`: Current solar heating status

## Contributing

Feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
