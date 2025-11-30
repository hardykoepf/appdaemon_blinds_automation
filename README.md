# Blinds AppDaemon App

This AppDaemon app is designed to manage blinds in a smart home environment. It provides advanced functionality for controlling blinds based on various parameters such as sun position, temperature, and user-defined constraints. The app is highly customizable and can be tailored to individual needs.

## Features

- **Dawn and Shadow Handling**: Manages blinds during dawn and shadow periods.
- **Sun Position Tracking**: Adjusts blinds for shadow handling based on the sun's azimuth and elevation.
- **Solar Heating**: Activates solar heating mode when conditions are met and shadow handling is active in general.
- **Ventilation Support**: Adjusts blinds when window/door is open.
- **Lockout Protection**: Prevents blinds from moving under certain conditions when window/door is open.
- **State Persistence**: Saves and restores states to/from a file.
- **Debugging**: Provides detailed debug logs for troubleshooting.


## Minimal Configuration

Below is an example of the minimal configuration required to use this app. Note that either **dawn handling** or **shadow handling** should be configured at a minimum for the app to function effectively. Without these, the app will not manage blinds dynamically based on environmental conditions.
See also "Default configuration values". Mybe there are values already defined which is fine and you don't have to explicitly define by your own.

```yaml
Living Room Blinds:
  unique_id: "living_room_blinds"
  module: blinds
  class: Blinds
  entities:
    cover: cover.living_room # Cover from Home Assistant to be managed
    brightness_shadow: sensor.helligkeit_gesamt # Brightness Sensor delivering the LUX value of sky
  facade:
    facade_angle: 180
    facade_offset_entry: -30
    facade_offset_exit: 30
    min_elevation: 10
    max_elevation: 80
  blinds:
    slat_width: 25 # Width of slat
    slat_distance: 20 # Distance between two slats
    height_tolerance: 5 # That slats are not moving too often you should define a tolerance. Only when calculated height differs more than tolerance from current height, the blinds is moved.
    angle_tolerance: 5 # Same like above but for angle
    height_step: 5 # Stepping for height
    angle_step: 5 # Stepping for angle
  move_constraints: # With this you can restrict the angle when shadowing is active
    min_angle: 0
    max_angle: 100
  shadow_active: True
  shadow:
    shadow_horizontal_angle: 100 # Angle -> maybe additionally restricted by move_constraints
    shadow_brightness_threshold_entity: sensor.sunshine_threshold # HASS sensor which defines the actual threshold when shadowing should be active. Could also be set as fixed value by shadow_brightness_threshold 
    shadow_height: 0 # Height position of blinds which should be set when shadowing is active. In HASS 0 means fully closed and 100 fully opened.
  delays:
    neutral_to_shadow_delay: 165 # When brightness is above defined (fixed or variable) threshold how many seconds wait before activate shadowing
    shadow_to_horizontal_delay: 315 # When shadowing is active and brightness switches below defined threshold, how many seconds to wait for setting angle to "shadow_horizontal_angle"
    horizontal_to_neutral_delay: 915 # When in horizontal position, how many seconds to wait to go back to neutral setting
```

### Description of Minimal Configuration

- **unique_id**: A unique identifier for the blinds.
- **name**: A human-readable name for the blinds.
- **entities**: Entities from HASS needed. At least cover and brighness_sensor is needed
- **facade**: Defines the facade's orientation and sun-related parameters.
- **blinds**: Specifies the physical properties of the blinds, tolerance and stepping.
- **move_constraints**: Sets the minimum and maximum angles for the blinds.
- **dawn**: Configures dawn-specific behavior. At least one of **dawn** or **shadow** must be configured.

## Maximal Configuration

Below is an example of a maximal configuration with all features enabled, including the "active" options for better control:

```yaml
Living Room Blinds:
  unique_id: "living_room_blinds"
  name: "Living Room Blinds"
  entities:
    cover: cover.living_room
    brightness_shadow: sensor.brightness
    window_sensor: binary_sensor.living_room_window_sensor
    climate: climate.living_room_climate
  facade:
    facade_angle: 180
    facade_offset_entry: -30
    facade_offset_exit: 30
    min_elevation: 10
    max_elevation: 80
  blinds:
    slat_width: 25
    slat_distance: 20
    height_tolerance: 5
    angle_tolerance: 5
    angle_step: 5
    height_step: 5
  move_constraints:
    min_angle: 0
    max_angle: 100
  dawn_active: True
  dawn:
    dawn_brightness_threshold: 200 # When brightness below this parameter, the timer for switching to dawn setting will start
    dawn_height: 0
    dawn_angle: 0
    dawn_prevent_move_up_after_dusk: True # When time is after dusk (defined by sun.sun integration) and blinds are closed, they will not move up because they have to close in a short
  shadow_active: True
  shadow:
    shadow_brightness_threshold: 300
    shadow_height: 70
    shadow_angle: 45
    shadow_active: True
  solar_heating_available: True
  solar_heating:
    solar_heating_available: True
    solar_heating_angle: 20
    solar_heating_height: 80
    solar_heating_temperature: 22
    solar_heating_hysterese: 2
  ventilation_active: True
  ventilation:
    ventilation_height: 10
    ventilation_angle: 90
  delays:
    neutral_to_shadow_delay: 165
    neutral_to_dawn_delay: 315
    shadow_to_horizontal_delay: 315
    horizontal_to_neutral_delay: 915
    dawn_to_horizontal_delay: 75
    dawn_horizontal_to_neutral_delay: 915
  save_states: True
  blinds_locked_external_for_min: 15 # When blinds was changed by an external command (e.g. in HASS) the blind will be locked for this duration till it will return to be managed by the logic
  DEBUG: True # Set debug output option
```

### Description of Maximal Configuration

- **dawn**: Configures dawn-specific behavior.
- **shadow**: Configures shadow-specific behavior.
- **solar_heating**: Enables and configures solar heating functionality. Includes an "active" option to enable or disable solar heating.
- **ventilation**: Configures behavior when windows are open. Includes an "active" option to enable or disable ventilation handling.
- **delays**: Sets delays for state transitions.
- **save_states**: Enables saving and restoring states.
- **blinds_locked_external_for_min**: Sets the duration for external lock.

## Features explained

### Sun Position Tracking

You have to activate sun.sum integration in Home Assistant.
The azimuth and elevation of this integration is used by this app.

For every blinds where you want to use shadowing (otherwise sun position tracking makes no sense) you have to define following settings:
- **facade_angle**: The facade angle is the direction of the facade in a 360 degree definition. 0 degree means the blind of this facade is exactly facing to north. 180 degree means the facade is exactly oriented to south etc.
- **facade_offset_entry**: When there is a natural shadowing to this facade bcause of for example a tree, wall etc. The blinds don't have to activate shadowing till sun passes this point. Therefore the offset entry could be set to something different than '-90'. But -90 means the shadowing will be active as far as the azimuth of sun reaches a position where sun is facing facade. So shadowing will be started when azimuth is above "facade_angle - facade_offset_entry"
- **facade_offset_exit**: Same as before but natural shadowing by wall or tree is on the other side - before sun leaves the facade. Means shadowing will be stopped when azimuth of sun is above "facade_angle + facade_offset_exit".
- **min_elevation**: Shadowing starting when elevation of sun is above this threshold.
- **max_elevation**: Shadowing stopping when elevation of sun is above this threshold.

### Solar Heating

Solar heating means, that you use the sun for heating up your rooms. So makes sense to activate this feature in winter for facades facing position of sun.
For activating this feature the following configuration options has to be set. 
```yaml
  solar_heating_available: True
  solar_heating:
    solar_heating_temperature: 23 # Temperature to which the sun should heat up the room (needs climate sensor in "entities" section)
    solar_heating_hysterese: 0.5 # The hysterese defines how much temperature has to drop till solar heating is again active. It prevents from moving blinds too often
    solar_heating_height: 100 # height to which the blinds should be set when solar heating status is on
    solar_heating_angle: 100 # angle to which the blinds should be set when solar heating status is on
```

When you activate this feature, two input booleans has to be created in HASS:
- **solar_heating_active**: With this boolean you can de/activate solar heating for specific blinds in general. Normally you will activate in winter and turn off in summer.
- **solar_heating_status**: This is only set by App the app and could NOT be changed by HASS. For visualization in Dashboard you can use this to display if the blinds is actually in solar heating position.

### Ventilation Support

Prerequisites: For ventialtion support you need a window sensor to detect window open/close status which the blinds belongs to.

When window is opened, the blinds will move to a defined position. Normally the blinds is move to horizontal position so that air exchange can happen.

The configuration of this feature:
```yaml
  entities:
    window_sensor: binary_sensor.window_living_room # In entities section a window sensor (should be a binary sensor) has to be defined
  ventilation_active: True
  ventilation:
    ventilation_height: False # Height position to which the blinds should be moved when window was opened. When set to False, nothing will be changed on this parameter
    ventilation_angle: 100 # Angle position to which the blinds should be moved when window was opened. When set to False, nothing will be changed on this parameter
```

### Lockout Protection

Prerequisites: For lockout protection you need a window/door sensor to detect window/door open/close status which the blinds belongs to.

When window/door is opened, the blinds will only move up and no longer will move down.

The configuration of this feature:
```yaml
  entities:
    window_sensor: binary_sensor.door_living_room # In entities section a window sensor (should be a binary sensor) has to be defined
  lockout_protection_active: True # All you have to do besides defining a window sensor is to set this parameter to True
```

## State Persistance

With every run, the actual state will be stored in a file in app directory. This is done that the logic can resume work when appdaemon has to be restarted.
When appdaemon is longer than 1 hour "offline", the state will not be taken from the saved file. Then logic will begin to run with state neutral.

Recommendation is to activate this feature by default.
```yaml
  save_states: True
```

## Possible States

Related on shadow handling or dawn handling following sates exists.

### For shadow handling

- **Neutral**: State when the brighness is above dawn and below shadow handling.
- **Neutral to Shadow timer**: Timer is running when brightness is switching above defined shadowing brightness threshold. In delay config block "neutral_to_shadow_delay" is defining the duration of this timer. If brightness switches below threshold while timer is running, the timer is cancelled and state is switching back to "Neutral".
- **Shadow**: When "Neutral to Shadow timer" has finished (and brightness didn't switch below threshold while timer was running) shadowing will be activated. This means, Blinds are positioned to defined shadow height and angle is calculated based on sun position. While timer is running, the blinds are still processing like in state Shadow.
- **Shadow to shadow horizontal timer**: When brightness switches below defined shadowing threshold, the timer will run. If brightness switches above threshold while timer is running, the timer is cancelled and state is going back to "Shadow" again. The duration of timer is defined in delay config block called "shadow_to_horizontal_delay".
- **Shadow horizontal to neutral timer**: After "Shadow to horizontal" timer has finished while brightness still below defined shadowing threshold, the angle of the blinds is set to defined position by "shadow_horizontal_angle" in shadow config block and the timer for going back to neutral state will be startet. This timer is using  duration from delay config block "horizontal_to_neutral_delay".

### For dawn handling

- **Neutral**: State when the brighness is above dawn and below shadow handling.
- **Neutral to Dawn timer**: Timer is running when brightness is switching below defined dawn brightness threshold (dawn_brightness_threshold). In delay config block "neutral_to_dawn_delay" is defining the duration of this timer. If brightness switches above threshold while timer is running, the timer is cancelled and state is switching back to "Neutral".
- **Dawn**: When "Neutral to Dawn timer" has finished (and brightness didn't switch above threshold while timer was running) dawn state will be activated. This means, Blinds are positioned to defined dawn height and angle in dawn config block (dawn_height; dawn_angle).
- **Dawn to dawn horizontal timer**: When brightness switches above defined dawn threshold (e.g. next morning), the timer will start running. If brightness switches below threshold while timer is running, the timer is cancelled and state is going back to "Dawn" again. The duration of timer is defined in delay config block called "dawn_to_horizontal_delay". While timer is running, the blinds are still processing like in state Dawn.
- **Dawn horizontal to neutral timer**: After "Dawn to horizontal timer" has finished while brightness still above defined dawn threshold, the angle of the blinds is set to defined position by "dawn_horizontal_angle" in dawn config block and the timer for going back to neutral state will be startet. This timer is using duration from delay config block "dawn_horizontal_to_neutral_delay".

### Delay config block

The delay config block should look like this when Shadowing and Dawn is activated.
When nothing is defined in config, these values are also the default values:
```yaml
  delays:
    neutral_to_shadow_delay: 165
    neutral_to_dawn_delay: 315
    shadow_to_horizontal_delay: 315
    horizontal_to_neutral_delay: 915
    dawn_to_horizontal_delay: 75
    dawn_horizontal_to_neutral_delay: 915
```

## Adding Missing Input Booleans

The app uses `EntityCollector` to generate missing input booleans. If any input booleans are missing, the app will log an error and create a file with the necessary configuration lines. Follow these steps to add the missing entities to HASS:

1. Check the AppDaemon logs for a message indicating missing entities.
2. Locate the file created by the app (`entities.config`). The file will be in app directory of blinds app.
3. Copy the lines from the file into your Home Assistant `configuration.yaml`.
4. Reload the Home Assistant configuration.
5. Restart Appdaemon

### Example of Generated Input Booleans

```yaml
input_boolean:
  living_room_blinds_locked:
    name: "Blinds Locked"
    icon: "mdi:lock"
  living_room_debug_active:
    name: "Debug Active"
    icon: "mdi:bug"
```

## Default configuration values

You don't have to define every configuration option. If not defined but option was activated is defaults with the values you find below.
When configuration is missed, an exception is raised and the instance of the blinds couldn't be started. This you will see in error log of Appdaemon.

```yaml
  "facade": {
      "facade_offset_entry": -90,
      "facade_offset_exit": 90,
      "min_elevation": 0,
      "max_elevation": 90,
  },
  "move_constraints": {
      "min_angle": 0,
      "max_angle": 100
  },
  "blinds": {
      "slat_width": 90,
      "slat_distance": 80,
      "angle_offset": 0,
      "angle_step": 5,
      "height_step": 5,
      "angle_tolerance": 5,
      "height_tolerance": 5
  },
  "neutral": {
      "neutral_height": 100,
      "neutral_angle": 100,
  },
  "shadow_active": True,
  "shadow": {
      "shadow_horizontal_angle": 100,
      "shadow_brightness_threshold": 50000,
      "shadow_height": 0
  },
  "dawn_active": True,
  "dawn": {
      "dawn_height": 0,
      "dawn_angle": 0,
      "dawn_horizontal_angle": 0,
      "dawn_brightness_threshold": 10,
      "dawn_prevent_move_up_after_dusk": True,
  },
  "delays": {
      "neutral_to_shadow_delay": 165,
      "neutral_to_dawn_delay": 315,
      "shadow_to_horizontal_delay": 615,
      "horizontal_to_neutral_delay": 915,
      "dawn_to_horizontal_delay": 75,
      "dawn_horizontal_to_neutral_delay": 915
  },
  "ventilation_active": False,
  "lockout_protection_active": False,
  "blinds_locked_external_for_min": 30,
  "save_states": False,
  "DEBUG": False
```


## Customization

To customize the app for your needs:

1. Modify the configuration file to match your setup.
2. Adjust parameters such as facade angle, slat dimensions, and delays.
3. Enable or disable features like solar heating and ventilation as needed.

## Debugging

There are two ways of enable debugging.
Either enable in general via configuration. Therefore set the option `DEBUG` to True -> see Maximal Configuration
Or enable debugging in HASS by setting the corresponding input boolean to `on`. This input boolean is named "<unique_id>_debug_active" in HASS.
This will provide detailed logs to help troubleshoot issues.

## Notes

- Ensure all required input booleans are created in Home Assistant.
- Test the configuration in a controlled environment before deploying it to production.

For further assistance, refer to the AppDaemon documentation or contact the developer.