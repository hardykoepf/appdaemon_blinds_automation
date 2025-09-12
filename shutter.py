"""Individual shutter logic."""
import os.path
import math
import time
import json
from datetime import datetime, timedelta
from time import time
# from decimal import Decimal, ROUND_HALF_EVEN
from appdaemon.plugins.hass.hassapi import Hass
from helpers.entity_collector import EntityCollector

# Constants
STATE_ON = 'on'
STATE_OFF = 'off'
WINDOW_OPEN = 'on'
WINDOW_CLOSED = 'off'
UNAVAILABLE = 'unavailable'
UNKNOWN = 'unknown'

class Shutter(Hass):
    """Represents a single shutter with its configuration and state."""

    # States
    STATE_SHADOW_TO_NEUTRAL_TIMER = 3
    STATE_SHADOW = 2
    STATE_NEUTRAL_TO_SHADOW_TIMER = 1
    STATE_NEUTRAL = 0
    STATE_NEUTRAL_TO_DAWN_TIMER = -1
    STATE_DAWN = -2
    STATE_DAWN_TO_NEUTRAL_TIMER = -3

    # Default config values
    DEFAULT_CONFIG = {
        "unique_id": None,
        "facade": {
            "facade_offset_entry": -90,
            "facade_offset_exit": 90,
            "min_elevation": 0,
            "max_elevation": 90,
        },
        "move_constraints": {
            "min_height": 0,
            "max_height": 100,
            "height_step": 5,
            "height_tolerance": 5
        },
        "neutral": {
            "neutral_height": 100,
        },
        "shadow_active": True,
        "shadow": {
            "shadow_brightness_threshold": 50000,
            "total_height": 2000,
            "light_strip": 500
        },
        "dawn_active": True,
        "dawn": {
            "dawn_height": 0,
            "dawn_brightness_threshold": 10,
            "dawn_prevent_move_up_after_dusk": True,
        },
        "delays": {
            "neutral_to_shadow_delay": 165,
            "neutral_to_dawn_delay": 315,
            "shadow_to_neutral_delay": 615,
            "dawn_to_neutral_delay": 915,
        },
        "ventilation_active": False,
        "ventilation": {
            "ventilation_height": 0,
        },
        "lockout_protection_active": False,
        "shutter_locked_external_for_min": 30,
        "save_states": False,
        "DEBUG": False
    }

    def initialize(self):
        """Setup listeners and scheduling."""

        self.log(f"Initializing ...")

        # Merge default config with provided args (apps.yaml)
        self.params = self.deep_merge_config(self.DEFAULT_CONFIG, self.args)

        # Attribute if blinds is moving
        self.moving = False

        # Add new variables for tracking automated changes
        self.automated_change_counter = -1
        self.max_automated_change_counter = 5  # Number of change position events after a automated change can happen (normally 2 - one event when height was arrived and one when also tilt was set)
        self.expected_height = None

        # Validate config
        self.validate_config()

        # Initialize States beginning from Neutral
        self.shutter_state = self.STATE_NEUTRAL
        self.debug(f"Initialized state: {self.shutter_state}")
        self.shutter_locked_external_till = None
        self.timer = None
        if self.params.get('solar_heating_available'):
            self.hysterese_reached = False

        # Check if we can load a previous stored state
        self.load_state_from_file()

        # Read actual values on initilization
        self.current_height = self.get_state(self.params['entities']['cover'], attribute='current_position')
        self.expected_height = self.current_height
        self.debug(f"Current height: {self.current_height}")
        
        # Read configured sensors.
        # Try to read entities twice, when first time issues occur. This could happen when HASS was restarted, but maybe sensors are not ready yet.
        # Happens for example when using KNX integration which has to be read from Bus first
        try:
            self.read_entity_values()
        except ValueError:
            # Retry some seconds later - maybe integrations are not completely up and running
            time.sleep(10)
            self.read_entity_values()

        # Initialize sun attributes
        sun_state = self.get_state("sun.sun", attribute="all")
        self.on_sun_change(entity="manual_start", attribute={}, old="", new=sun_state, kwargs={})

        # Self generated Entities create and get actual state
        self.create_internal_entities()

        self.shutter_locked = self.get_state(self.name_shutter_locked)
        self.shutter_locked_external = self.get_state(self.name_shutter_locked_external)
        # Reset external lock when initializing
        if self.shutter_locked_external == STATE_ON:
            self.set_state(entity_id=self.name_shutter_locked_external, state=STATE_OFF)
            self.shutter_locked_external_till = None

        self.manipulation_active = self.get_state(self.name_manipulation_active)
        if self.params.get('solar_heating_available'):
            self.solar_heating_active = self.get_state(self.name_solar_heating_active)
            # Initialize variable
            self.solar_heating_state = STATE_OFF

        # Setup listen events
        #Listen to the created boolean entities
        self.listen_state(self.on_state_change, self.name_shutter_locked)
        self.listen_state(self.on_state_change, self.name_shutter_locked_external)
        self.listen_state(self.on_state_change, self.name_manipulation_active)
        if self.params.get('solar_heating_available'):
            self.listen_state(self.on_state_change, self.name_solar_heating_active)


        # Listen to changes of sun position
        self.listen_state(self.on_sun_change, 'sun.sun', attribute = "all")

        # Listen to brightness sensor
        self.listen_state(self.on_brightness_shadow_change, self.params['entities']['brightness_shadow'])
        if self.params['entities'].get("brightness_dawn"):
            self.listen_state(self.on_brightness_dawn_change, self.params['entities']['brightness_dawn'])

        # Listen to Sunshine Brightness Threshold Sensor if configured
        if self.params['shadow'].get('shadow_brightness_threshold_entity'):
            self.listen_state(self.on_sunshine_brightness_threshold_change, self.params['shadow'].get('shadow_brightness_threshold_entity'))

        # Listen to window sensor when lockout protection is activated
        if self.params.get("lockout_protection_active") or self.params.get("ventilation_active"):
            self.listen_state(self.on_window_change, self.params['entities']['window_sensor'])

        # Listen to current temperature
        if self.params['entities'].get('climate'):
            self.listen_state(self.on_temperature_change, self.params['entities']['climate'], attribute='current_temperature')

        # Listen to cover changes to detect manual changes
        self.listen_state(self.on_cover_change, self.params['entities']['cover'], attribute='all')

        # shedule main in 30 seconds
        self.schedule_main()

        # Save state
        self.save_states_to_file()
        
        self.log(f"shutter initialized.")

    def deep_merge_config(self, default: dict, override: dict) -> dict:
        """Recursively merge two dictionaries, preserving nested structures."""
        result = default.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge_config(result[key], value)
            else:
                result[key] = value
                
        return result

    def read_entity_values(self):
        self.brightness_shadow = int(float(self.get_state(self.params['entities']['brightness_shadow'])))
        if self.params.get('entities', {}).get("brightness_dawn"):
            self.brightness_dawn = int(float(self.get_state(self.params['entities']['brightness_dawn'])))
        if self.params.get('entities', {}).get("window_sensor"):
            self.window_open = self.get_state(self.params['entities']['window_sensor'])
        if self.params['entities'].get('climate'):
            self.current_temperature = self.get_state(self.params['entities'].get('climate'), attribute="current_temperature")
        if self.params['shadow'].get('shadow_brightness_threshold_entity'):
            self.sunshine_brightness_threshold = int(float(self.get_state(self.params['shadow'].get('shadow_brightness_threshold_entity'))))

    def validate_config(self):
        """Validate configuration and log missing entries."""
        valid = True

        if not self.params.get('unique_id'):
            self.log(f"Configuration: Missing mandatory 'unique_id' (without spaces)")

        if not self.params.get('entities'):
            self.log(f"Configuration: Missing mandatory 'entities' settings.")
        else:
            if not self.params['entities'].get('cover'):
                self.log(f"Missing mandatory configuration: entities.cover")
                result = False
            elif not self.entity_exists(self.params['entities']['cover']):
                self.log(f"Configuration entity entities.cover: {self.params['entities']['cover']} could not be found in HASS")
                result = False
                
            if not self.params['entities'].get('brightness_shadow'):
                self.log(f"Missing mandatory configuration: entities.brightness_shadow")
                valid = False
            elif not self.entity_exists(self.params['entities']['brightness_shadow']):
                self.log(f"Configuration entity entities.brightness_shadow: {self.params['entities']['brightness_shadow']} could not be found in HASS")
                valid = False

            if self.params['entities'].get('brightness_dawn'):
                if not self.entity_exists(self.params.get('entities', {}).get('brightness_dawn')):
                    self.log(f"Configuration entity entities.brightness_dawn: {self.params.get('entities', {}).get('brightness_dawn')} could not be found in HASS")
                    valid = False

            if self.params.get('lockout_protection_active') or self.params.get('ventilation_active'):
                if not self.entity_exists(self.params.get('entities', {}).get('window_sensor')):
                    self.log(f"Configuration entity entities.window_sensor: {self.params.get('entities', {}).get('window_sensor')} could not be found in HASS")
                    valid = False

            if self.params.get('solar_heating_available'):
                if not self.entity_exists(self.params.get('entities', {}).get('climate')):
                    self.log(f"Configuration entity entities.climate: {self.params.get('entities', {}).get('climate')} could not be found in HASS")
                    valid = False

        if self.params['facade']['min_elevation'] >= self.params['facade']['max_elevation']:
            self.log("Configuration error min_elevation is greater or equal max_elevation. Makes no sense.")
            valid = False

        if not self.params.get('facade'):
            self.log(f"Configuration: Missing mandatory 'facade' settings.")
        else:
            if self.params.get('facade', {}).get('facade_angle') is None:
                self.log("Config entry facade.facade_angle is missing")
            elif not type(self.params['facade']['facade_angle']) == int:
                self.log("facade.facade_angle has to of type int")

            if self.params.get('facade', {}).get('facade_offset_entry') is None:
                self.log("Config entry facade.facade_offset_entry is missing")
                valid = False
            elif not type(self.params['facade']['facade_offset_entry']) == int:
                self.log("facade.facade_offset_entry has to of type int")
                valid = False
            else:
                offset_entry = self.params['facade']['facade_offset_entry']

            if self.params.get('facade', {}).get('facade_offset_exit') is None:
                self.log("Config entry facade.facade_offset_exit is missing")
                valid = False
            elif not type(self.params['facade']['facade_offset_exit']) == int:
                self.log("facade.facade_offset_exit has to of type int")
                valid = False
            else:
                if offset_entry and offset_entry >= self.params['facade']['facade_offset_exit']:
                    self.log("facade.facade_offset_entry has to be lower than facade.facade_offset_exit")
                    valid = False

        if self.params.get("ventilation_active"):
            if self.params['entities'].get('window_sensor') is None:
                self.log("Ventilation configured, but entities.window_sensor missing")
                valid = False
            if self.params['ventilation'].get('ventilation_height'):
                if not type(self.params.get('ventilation', {}).get('ventilation_height')) == int:
                    self.log("ventilation.ventilation_height has to be False or of type int")
                    valid = False

        if self.params.get("lockout_protection_active"):
            if self.params['entities'].get('window_sensor') is None:
                self.log("Ventilation configured, but entities.window_sensor missing")
                valid = False

        if self.params.get('solar_heating_available'):
            if self.params['entities'].get('climate') is None:
                self.log("Solar heating configured, but entities.climate missing")
                valid = False
            if not self.params.get('solar_heating'):
                self.log("solar_heating branch has to be defined in config when solar_heating_available is True")
                valid = False
            if self.params['solar_heating'].get('solar_heating_temperature'):
                if not (type(self.params['solar_heating'].get('solar_heating_temperature')) == float or
                    type(self.params['solar_heating'].get('solar_heating_temperature')) == int):
                    self.log("solar_heating.solar_heating_temperature has to be of type float or int")
                    valid = False
            if not type(self.params['solar_heating'].get('solar_heating_height')) == int:
                self.log("solar_heating.solar_heating_height has to be of type int")
                valid = False

        if valid:
            self.debug("Configuration validation successful")
        else:
            raise ValueError("Configuration validation failed. Check error log.")


    def debug(self, text):
        if self.params['DEBUG']:
            self.log(text)

    def create_internal_entities(self):
        # Get collector instance
        collector = EntityCollector()

        # List with all generated entities
        self.input_booleans = []

        # Generate
        entities_missing = False
        self.name_shutter_locked = "input_boolean." + self.params['unique_id'] + "_shutter_locked"
        if not self.entity_exists(self.name_shutter_locked):
            name = f"Shutter {self.params['name']} shutter locked"
            collector.add_boolean(
                f"{self.params['unique_id']}_shutter_locked",
                name,
                "mdi:lock"
            )
            entities_missing = True
        else:
            self.input_booleans.append(self.name_shutter_locked)

        self.name_shutter_locked_external = "input_boolean." + self.params['unique_id'] + "_shutter_locked_external"
        if not self.entity_exists(self.name_shutter_locked_external):
            name = f"Shutter {self.params['name']} shutter locked external"
            collector.add_boolean(
                f"{self.params['unique_id']}_shutter_locked_external",
                name,
                "mdi:timer-lock"
            )
            entities_missing = True
        else:
            self.input_booleans.append(self.name_shutter_locked_external)

        self.name_manipulation_active = "input_boolean." + self.params['unique_id'] + "_manipulation_active"
        if not self.entity_exists(self.name_manipulation_active):
            name = f"Shutter {self.params['name']} manipulation active"
            collector.add_boolean(
                f"{self.params['unique_id']}_manipulation_active",
                name,
                "mdi:arrow-all"
            )
            entities_missing = True
        else:
            self.input_booleans.append(self.name_manipulation_active)

        self.name_solar_heating_active = "input_boolean." + self.params['unique_id'] + "_solar_heating_active"
        self.name_solar_heating_status = "input_boolean." + self.params['unique_id'] + "_solar_heating_status"
        if self.params.get('solar_heating_available'):
            # Solar heating configured
            if not self.entity_exists(self.name_solar_heating_active):
                name = f"Shutter {self.params['name']} solar heating active"
                collector.add_boolean(
                    f"{self.params['unique_id']}_solar_heating_active",
                    name,
                    "mdi:sun-thermometer"
                )
                entities_missing = True
            else:
                self.input_booleans.append(self.name_solar_heating_active)

            if not self.entity_exists(self.name_solar_heating_status):
                name = f"Shutter {self.params['name']} solar heating status"
                collector.add_boolean(
                    f"{self.params['unique_id']}_solar_heating_status",
                    name,
                    "mdi:sun-thermometer"
                )
                entities_missing = True
            else:
                self.input_booleans.append(self.name_solar_heating_status)

        # When entities are missing, create (overwrite configuration template file)
        if entities_missing:
            config_path = str(self.app_dir)  # This is the directory where the app is running
            try:
                filepath = collector.write_yaml_config(config_path)
            except Exception as e:
                self.error(f"Failed to write configuration {e}")
            self.log(f"IMPORTANT: You have to create entities in HASS.")
            self.log(f"IMPORTANT: copy lines in file {filepath} to your HASS configuration.yaml and reload configuration")
            self.log(f"IMPORTANT: Stopping logic")
            raise EnvironmentError(f"Exiting logic. Copy lines in file {filepath} to your HASS configuration.yaml first")

        # Register callback for getting state changes from HA
        self.listen_event(self.listen_internal_entities, event = "call_service")

    def listen_internal_entities(self, event_name, data, kwargs):
        if data['domain'] == "input_boolean" and (data['service'] == "turn_off" or data['service'] == "turn_on"):
            # BooleansService data could have a list of entity_ids or just one single string (either called by service or manually switching)
            # Handling list first
            if type(data['service_data']['entity_id']) == list:
                for entity_id in  data['service_data']['entity_id']:
                    if entity_id in self.input_booleans:
                        if entity_id == self.name_solar_heating_status:
                            # This boolean hould not be modified from outside. So overwrite with actual state
                            self.set_state(entity_id=entity_id, state=self.solar_heating_status)
                        elif data['service'] == "turn_off":
                            self.log(f"{entity_id} switched off")
                            self.set_state(entity_id=entity_id, state=STATE_OFF)
                        elif data['service'] == "turn_on":
                            self.log(f"{entity_id} switched on")
                            self.set_state(entity_id=entity_id, state=STATE_ON)
            elif type(data['service_data']['entity_id']) == str:
                if data['service_data']['entity_id'] in self.input_booleans:
                    if data['service_data']['entity_id'] == self.name_solar_heating_status:
                        # This boolean hould not be modified from outside. So overwrite with actual state
                        self.set_state(entity_id=data['service_data']['entity_id'], state=self.solar_heating_status)
                    elif data['service'] == "turn_off":
                        entity_id = data['service_data']['entity_id']
                        self.log(f"{data['service_data']['entity_id']} switched off")
                        self.set_state(entity_id=data['service_data']['entity_id'], state=STATE_OFF)
                    elif data['service'] == "turn_on":
                        entity_id = data['service_data']['entity_id']
                        self.log(f"{data['service_data']['entity_id']} switched on")
                        self.set_state(entity_id=data['service_data']['entity_id'], state=STATE_ON)
            else:
                self.error(f"Couldn't handle service call for input_boolean: {data['service_data']['entity_id']}")

    def schedule_main(self):
        # schedule main in 30 seconds
        current = datetime.now()
        if current.second < 30:
            run_at = current.replace(second=30, microsecond=0)
        else:
            run_at = current.replace(second=0, microsecond=0) + timedelta(minutes=1)
        self.handle = self.run_every(self.main, run_at, interval=30)
        self.log("Scheduled main funtion every 30 Seconds")

    def main(self, *args):
        self.debug("Starting main logic...")
        # This is the function where everything is put together

        # Check if an maybe existing external lock could be released
        self.check_external_lock()

        # Log if shutter is locked
        if self.shutter_locked == STATE_ON:
            self.debug(f"shutter is locked.")
        elif self.shutter_locked_external == STATE_ON:
            self.debug(f"shutter is locked due to external change till: {self.shutter_locked_external_till}")
        elif self.manipulation_active == STATE_ON:
            self.debug(f"shutter is locked due to manipulation change.")

        # Check state
        self.debug(f"Current state main: {self.shutter_state}")
        match self.shutter_state:
            case self.STATE_SHADOW_TO_NEUTRAL_TIMER :
                self.shutter_state = self.handle_state_shadow_to_neutral_timer()
            case self.STATE_SHADOW:
                self.shutter_state = self.handle_state_shadow()
            case self.STATE_NEUTRAL_TO_SHADOW_TIMER:
                self.shutter_state = self.handle_state_neutral_to_shadow_timer()
            case self.STATE_NEUTRAL:
                self.shutter_state = self.handle_state_neutral()
            case self.STATE_NEUTRAL_TO_DAWN_TIMER:
                self.shutter_state = self.handle_state_neutral_to_dawn_timer()
            case self.STATE_DAWN:
                self.shutter_state = self.handle_state_dawn()
            case self.STATE_DAWN_TO_NEUTRAL_TIMER:
                self.shutter_state = self.handle_state_dawn_to_neutral_timer()
        self.debug(f"Current state main after check: {self.shutter_state}")

        # Get height and angle without any constraints
        self.calculated_height = self.handle_states()
        self.new_height = self.calculated_height
        
        # Check constraints respecting priority of each constraint (lowest prio first)
        # ventilation
        if self.params.get("ventilation_active"):
            if self.window_open == WINDOW_OPEN:
                if  type(self.params['ventilation'].get("ventilation_height")) == int:
                    if self.current_height < self.params['ventilation'].get("ventilation_height"):
                        # Only open shutter when its more closed than ventialtion height
                        self.debug(f"Ventilation activated: Current height: {self.current_height} ventialtion height: {self.params['ventilation'].get('ventilation_height')}")
                        self.new_height = self.params['ventilation'].get("ventilation_height")

        # Solar heat | for comparison of two floats the comparison issue is fine and we don't care about small differences
        if self.params.get("solar_heating_available"):
            if self.solar_heating_active == STATE_ON:
                if self.current_temperature > self.params['solar_heating']['solar_heating_temperature']:
                    # Current Temperature above wanted temperature -> No more solar heating
                    self.hysterese_reached = True
                    # Update status
                    if self.solar_heating_state == STATE_ON:
                        self.solar_heating_state = STATE_OFF
                        self.set_state(self.name_solar_heating_status, STATE_OFF)
                        self.debug("Temperature reached and above threshold. Solar heating status OFF.")
                else:
                    # Current Temperature below wanted temperature
                    if self.hysterese_reached:
                        # check if current_temperature again below hysterese
                        if  self.current_temperature < (self.params['solar_heating']['solar_heating_temperature'] - float(self.params['solar_heating']['solar_heating_hysterese'])):
                            # Current temperature below hysterese -> Heat again
                            self.hysterese_reached = False
                            self.new_height = self.params['solar_heating']['solar_heating_height']
                            if self.solar_heating_state == STATE_OFF:
                                self.solar_heating_state = STATE_ON
                                self.set_state(self.name_solar_heating_status, STATE_ON)
                                self.debug("Temperature below threshold. Solar heating status ON.")
                    else:
                        # Hysterese not reached, so do solar heating
                        self.new_height = self.params['solar_heating']['solar_heating_height']
                        if self.solar_heating_state == STATE_OFF:
                            self.solar_heating_state = STATE_ON
                            self.set_state(self.name_solar_heating_status, STATE_ON)
                            self.debug("Temperature below threshold. Solar heating status ON.")
            else:
                # chack that status boolean has state off
                if self.solar_heating_state == STATE_ON:
                    self.solar_heating_state = STATE_OFF
                    self.set_state(self.name_solar_heating_status, STATE_OFF)
                    self.debug("Solar heating not active. Solar heating status OFF.")


        # When after dusk, prevent from moving shutter up if configured
        if self.params['dawn'].get("dawn_prevent_move_up_after_dusk"):
            if 'next_dusk' in dir(self) and self.next_dusk.replace(tzinfo=None) < datetime.now().replace(tzinfo=None):
                # After dusk, don't move up shutter
                if self.current_height < self.new_height:
                    self.debug(f"Prevent from moving shutter up after dusk. Current height: {self.current_height}")
                    self.new_height = self.current_height

        # lockout protection - also when window sensor is unavailable activate lockout protection
        if self.params.get("lockout_protection_active") and (self.window_open == WINDOW_OPEN or self.window_open == UNAVAILABLE):
            if self.current_height > self.new_height:
                # When new height is lower than actual height, do not change height
                self.new_height = self.current_height
                self.debug(f"Lockout protection active. Taking over current height. Current height: {self.current_height}")

        self.debug(f"New calculated height: {self.new_height}")

        # When everything was checked, move shutter - when not already moving
        if self.moving:
            self.debug("Shutter already moving - don't set new position")
        else:
            self.set_position(self.new_height)

        # Save state
        self.save_states_to_file()

    def set_position(self, height):
        """Set cover position."""
        if not isinstance(height, (int, float)) or height < 0 or height > 100:
            self.error(f"Invalid height value: {height}")
            return
        
        self.debug(f"set_position called with: {height}")

        if self.moving:
            self.debug("Shutter already moving - don't set new position")
            return
        
        # Automated change counter reflects how many state changes happened since last blinds change
        # When this value equals 0, the logic changed position but no feedback from device has arrived till now (blinds still moving)
        # Only when last change was finished, a new change should be sent
        if self.automated_change_counter != 0:

            # Only write changes to cover entity when not locked in any way
            if (self.shutter_locked == STATE_OFF
                and self.shutter_locked_external == STATE_OFF
                and self.manipulation_active == STATE_OFF):
                # Check if height changed to actual shutter height respecting tolerance
                self.debug(f"Current positions: height: {self.current_height}")
                tolerance_height = self.params['move_constraints']['height_tolerance']
                if not (self.current_height <= min((height + tolerance_height), 100) and self.current_height >= max((height - tolerance_height), 0)):
                    result = self.call_service("cover/set_cover_position",
                                    entity_id=self.params['entities']['cover'],
                                    position=height)
                    self.debug(f"Changing height to: {height}. Result: {result}")
                    if not result['success']:
                        self.error(f"Could not set position to height: {height}")
                    else:
                        self.debug(f"Set shutter to height: {height}")
                        self.automated_change_counter = 0
                        self.expected_height = height

        else:
            self.debug(f"Last position change still ongoing.")

        self.debug("set_position finish")

            
    def is_timer_finished(self):
        if self.timer is None:
            return True
        elif self.timer < datetime.now():
            return True
        else:
            return False
    
    def get_dawn_brightness(self):
        # Dawn brightness could either be a separate entity - or as fallback use shadow brightness entity
        if self.params['entities'].get("brightness_dawn"):
            return self.brightness_dawn
        else:
            return self.brightness_shadow

    def calculate_sun_deviation(self):
        # Normalize the difference between sun and facade angle to -180...+180
        angle_diff = round((self.azimuth - self.params['facade']['facade_angle']) % 360, 2)
        if angle_diff > 180:
            angle_diff = round(angle_diff - 360, 2)
        return angle_diff

    def in_sun(self):
        """Calculate if facade is in sun."""
        # Calculate absolute deviation between sun azimuth and facade angle
        angle_diff = self.calculate_sun_deviation()
        
        # Check if sun is in configured range
        sun_entry = self.params['facade']['facade_offset_entry']
        sun_exit = self.params['facade']['facade_offset_exit']
        
        # Check elevation
        if not (self.params['facade']['min_elevation'] <= self.elevation <= self.params['facade']['max_elevation']):
            return False

        self.debug(f"Sun angle relative to facade: {angle_diff} (Entry: {sun_entry}, Exit: {sun_exit})")
        
        return sun_entry <= angle_diff <= sun_exit

    def calculate_height(self):
        """Calculate shutter height for light strip."""
        if not self.params.get('shadow', {}).get('light_strip'):
            return 0
        if self.params['shadow']['light_strip'] == 0:
            return 0 # Fully closed when no light strip is defined
            
        height = round(self.params['shadow']['light_strip'] * math.tan(math.radians(self.elevation)))
        height_pct = 100 - round(height * 100 / self.params['shadow']['total_height'])

        # Apply min/max constraints from config
        if height_pct < self.params['move_constraints']['min_height']:
            height_pct = self.params['move_constraints']['min_height']
        elif height_pct > self.params['move_constraints']['max_height']:
            height_pct = self.params['move_constraints']['max_height']
        
        # Apply stepping
        return round(height_pct / self.params['move_constraints']['height_step']) * self.params['move_constraints']['height_step']

    def check_external_lock(self):
        if self.shutter_locked_external == STATE_ON:
            # sanity check if shutter locked external on but no Timestamp, set back to off
            if self.shutter_locked_external_till is None:
                self.debug("Method check_external_lock no time found. Setting to off")
                self.set_state(entity_id=self.name_shutter_locked_external, state=STATE_OFF)
                # Read entity to be in sync with HASS
                self.blinds_locked_external = self.get_state(entity_id=self.name_shutter_locked_external)
            elif datetime.now() > self.shutter_locked_external_till:
                # reset lock
                self.debug("Method check_external_lock time is up. Setting to off")
                self.set_state(entity_id=self.name_shutter_locked_external, state=STATE_OFF)
                # Read entity to be in sync with HASS
                self.blinds_locked_external = self.get_state(entity_id=self.name_shutter_locked_external)
                self.shutter_locked_external_till = None

    def get_shadow_brightness_threshold(self):
        # shadow brightness threshold will be read from shadow_brightness_threshold_entity when configured
        # and if not from shadow_brightness_threshold
        if self.params['shadow'].get('shadow_brightness_threshold_entity'):
            return self.sunshine_brightness_threshold
        else:
            return self.params['shadow']['shadow_brightness_threshold']

    def calc_stepping_height(self, height):
        """ calculate height fitting step width """
        if self.params['move_constraints']['height_step'] != 0 and (height % self.params['move_constraints']['height_step']) != 0:
            return height - self.params['move_constraints']['height_step'] + (height % self.params['move_constraints']['height_step'])

    def handle_state_shadow_to_neutral_timer(self):
        if self.in_sun() and self.params['shadow_active']:
            if self.brightness_shadow > self.get_shadow_brightness_threshold():
                # Brightness again above threshold - move back to shadow
                self.debug("Brightness above threshold. Switching from SHADOW_TO HORIZONTAL_TIMER back to SHADOW")
                self.timer = None
                return self.STATE_SHADOW
            elif self.is_timer_finished():
                # Timer is over, move to neutral
                self.debug("Timer finished switching from SHADOW_TO_NEUTRAL_TIMER to NEUTRAL")
                return self.STATE_NEUTRAL
            else:
                # nothing to change
                return self.shutter_state
        else:
            # When facade no longer in sun change to neutral
            self.debug("Facade no longer in sun. Switching to NEUTRAL")
            self.timer = None
            return self.STATE_NEUTRAL

    def handle_state_shadow(self):
        if self.in_sun() and self.params['shadow_active']:
            if self.brightness_shadow < self.get_shadow_brightness_threshold():
                # Brightness below threshold - start timer for moving to horizontal
                self.debug("Brightness below threshold. Switching from SHADOW to SHADOW_TO_NEUTRAL_TIMER")
                self.timer = datetime.now() + timedelta(seconds = int(self.params['delays']['shadow_to_neutral_delay']))
                self.debug(f"Timer finish at: {self.timer}")
                return self.STATE_SHADOW_TO_NEUTRAL_TIMER
            else:
                return self.STATE_SHADOW
        else:
            # When facade no longer in sun change to neutral
            self.debug("Facade no longer in sun. Switching to NEUTRAL")
            return self.STATE_NEUTRAL

    def handle_state_neutral_to_shadow_timer(self):
        if self.in_sun() and self.params['shadow_active']:
            if self.brightness_shadow < self.get_shadow_brightness_threshold():
                # Brightness below threshold - go back to neutral
                self.debug("Brightness below threshold. Switching from NEUTRAL_TO_SHADOW_TIMER back to NEUTRAL")
                self.timer = None
                return self.STATE_NEUTRAL
            elif self.is_timer_finished():
                self.debug("Timer finished. Switching from NEUTRAL_TO_SHADOW_TIMER to SHADOW")
                self.timer = None
                return self.STATE_SHADOW
            else:
                # nothing to change
                return self.shutter_state
        else:
            # When facade no longer in sun change to neutral
            self.debug("Facade no longer in sun. Switching to NEUTRAL")
            self.timer = None
            return self.STATE_NEUTRAL
    
    def handle_state_neutral(self):
        if self.params['dawn_active'] and (self.get_dawn_brightness() < self.params['dawn']['dawn_brightness_threshold']):
            # Separate dawn object and brightness below threshold - start neutral to dawn timer
            self.debug("Brightness below dawn threshold. Switching from NEUTRAL to NEUTRAL_TO_DAWN_TIMER")
            self.timer = datetime.now() + timedelta(seconds = int(self.params['delays']['neutral_to_dawn_delay']))
            self.debug(f"Timer finish at: {self.timer}")
            return self.STATE_NEUTRAL_TO_DAWN_TIMER
        elif self.in_sun() and self.params['shadow_active']:
            if self.brightness_shadow > self.get_shadow_brightness_threshold():
                # Brightness above threshold - start timer for moving to horizontal
                self.debug("Brightness above threshold. Switching from NEUTRAL to NEUTRAL_TO_SHADOW_TIMER")
                self.timer = datetime.now() + timedelta(seconds = self.params['delays']['neutral_to_shadow_delay'])
                self.debug(f"Timer finish at: {self.timer}")
                return self.STATE_NEUTRAL_TO_SHADOW_TIMER
            else:
                # nothing to change
                return self.shutter_state
        else:
            # nothing to change
            return self.shutter_state
            
    def handle_state_neutral_to_dawn_timer(self):
        if self.params['dawn_active']:
            if self.get_dawn_brightness() > self.params['dawn'].get("dawn_brightness_threshold"):
                # Brightness again avove threshold - back to neutral
                self.debug("Brightness above threshold. Switching from NEUTRAL_TO_DAWN_TIMER back to NEUTRAL")
                self.timer = None
                self.shutter_state = self.STATE_NEUTRAL
            elif self.is_timer_finished():
                self.debug("Timer NEUTRAL_TO_DAWN_TIMER finished. Switching to DAWN")
                self.timer = None
                return self.STATE_DAWN
            else:
                # nothing to change
                return self.shutter_state
        else:
            self.debug("Dawn handling no longer active. Switching to NEUTRAL")
            self.timer = None
            return self.STATE_NEUTRAL

    def handle_state_dawn(self):
        if self.params['dawn_active']:
            if self.get_dawn_brightness() > self.params['dawn']['dawn_brightness_threshold']:
                # Brightness below threshold - start timer for moving to horizontal
                self.debug("Brightness above threshold. Switching from DAWN to DAWN_TO_NEUTRAL_TIMER")
                self.timer = datetime.now() + timedelta(seconds = int(self.params['delays']['dawn_to_neutral_delay']))
                self.debug(f"Timer finish at: {self.timer}")
                return self.STATE_DAWN_TO_NEUTRAL_TIMER
            else:
                # nothing to change
                return self.shutter_state
        else:
            # When dawn not active change to neutral
            self.debug("Dawn handling no longer active. Switching to NEUTRAL")
            return self.STATE_NEUTRAL

    def handle_state_dawn_to_neutral_timer(self):
        if self.params['dawn_active']:
            if self.get_dawn_brightness() < self.params['dawn']['dawn_brightness_threshold']:
                # Brightness again below threshold - move back to dawn
                self.debug("Brightness below threshold. Switching from DAWN_TO_NEUTRAL_TIMER back to DAWN")
                self.timer = None
                return self.STATE_DAWN
            elif self.is_timer_finished():
                # Timer is over, move to neutral
                self.debug("Timer DAWN_TO_NEUTRAL_TIMER finished. Switching to NEUTRAL")
                return self.STATE_NEUTRAL
            else:
                # nothing to change
                return self.shutter_state
        else:
            # When facade no longer in sun change to neutral
            self.debug("Dawn handling no longer active. Switching to NEUTRAL")
            self.timer = None
            return self.STATE_NEUTRAL
        
    def handle_states(self):
        """ Method to handle height based on actual state """
        # calculate/determine height based on state
        match self.shutter_state:
            case self.STATE_SHADOW_TO_NEUTRAL_TIMER:
                height = self.calculate_height()
                self.debug(f"handle_states: Calculated new height: {height}")
                return height
            case self.STATE_DAWN_TO_NEUTRAL_TIMER:
                self.debug(f"handle_states: Calculated new height: {self.params['dawn']['dawn_height']}")
                return self.params['dawn']['dawn_height']
            case self.STATE_SHADOW:
                height = self.calculate_height()
                self.debug(f"handle_states: Calculated new height: {height}")
                return height
            case self.STATE_NEUTRAL_TO_SHADOW_TIMER | self.STATE_NEUTRAL | self.STATE_NEUTRAL_TO_DAWN_TIMER:
                self.debug(f"handle_states: Calculated new height: {self.params['neutral']['neutral_height']}")
                return self.params['neutral']['neutral_height']
            case self.STATE_DAWN:
                self.debug(f"handle_states: Calculated new height: {self.params['dawn']['dawn_height']}")
                return self.params['dawn']['dawn_height']
            case _:
                self.error(f"handle_states: Unknown state: {self.shutter_state}")

    def on_sun_change(self, entity, attribute, old, new, kwargs):
        """Stores changes in instance variable."""
        self.debug(f"Sun change triggered: {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        
        self.azimuth = new['attributes']['azimuth']
        self.elevation  = new['attributes']['elevation']
        self.next_dusk  = datetime.fromisoformat(new['attributes']['next_dusk'])
        if self.in_sun():
            self.debug(f"Facade is in sun")
        else:
            self.debug(f"Facade is NOT in sun")

    def on_state_change(self, entity, attribute, old, new, kwargs):
        if new is None:
            return
        self.debug(f"input_boolean {entity} changed: {new}")
        if entity == self.name_shutter_locked:
            self.shutter_locked = new
        elif entity == self.name_shutter_locked_external:
            self.shutter_locked_external = new
            if new == STATE_OFF:
                self.shutter_locked_external_till = None
            else:
                if self.shutter_locked_external_till is None:
                    self.shutter_locked_external_till = datetime.now() + timedelta(minutes=self.params['shutter_locked_external_for_min'])
        elif entity == self.name_manipulation_active:
            self.manipulation_active = new
        elif entity == self.name_solar_heating_active:
            self.solar_heating_active = new
        # Call main to change immediately
        self.main()

    def on_brightness_shadow_change(self, entity, attribute, old, new, kwargs):
        """Handle changes in brightness."""
        self.debug(f"Brightness shadow change triggered: {entity=}, {old=}, {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        self.brightness_shadow = int(float(new))

    def on_sunshine_brightness_threshold_change(self, entity, attribute, old, new, kwargs):
        """Handle change of Sunshine Brightness Threshold Sensor Change"""
        self.debug(f"Sunshine Brightness Threshold Sensor change triggered: {entity=}, {old=}, {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        self.debug(f"Updating internal sunshine_brightness_threshold to: {new}")
        self.sunshine_brightness_threshold = int(float(new))

    def on_brightness_dawn_change(self, entity, attribute, old, new, kwargs):
        """Handle changes in brightness."""
        self.debug(f"Brightness dawn change triggered: {entity=}, {old=}, {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        self.brightness_dawn = int(float(new))


    def on_window_change(self, entity, attribute, old, new, kwargs):
        """Handle changes for window."""
        self.debug(f"Window change triggered: {entity=}, {old=}, {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        self.window_open = new
        # Update positions immediately
        self.main()

    def on_temperature_change(self, entity, attribute, old, new, kwargs):
        """Handle changes on temperature."""
        self.debug(f"Current temperature change triggered: {entity=}, {old=}, {new=}")
        if new in [None, UNKNOWN, UNAVAILABLE]:
            return
        else:
            self.current_temperature = float(new)

    def on_cover_change(self, entity, attribute, old, new, kwargs):
        # logic for handling changes
        # self.debug(f"Cover change triggered: {entity=}, {attribute=}, {old=}, {new=}")
        if new is None or new['state'] in ["opening", "closing", UNKNOWN, UNAVAILABLE]:
            # Filtering these states. Maybe it's a manual trigger or triggered by this logic
            self.moving = True
            return
        else:
            self.moving = False
            self.debug(f"Cover changed: {entity=}, {attribute=}, {old=}, {new=}")
            # Raise self.automated_change_counter by one
            self.automated_change_counter += 1
            self.debug(f"Automated Change Counter: {self.automated_change_counter}")

            # Set new values to variables
            self.current_height = new['attributes']['current_position']

            # Check position
            tolerance_height = self.params['move_constraints']['height_tolerance']

            # Check height/position
            height_matches = (self.expected_height is None or 
                                (self.current_height <= min((self.expected_height + tolerance_height), 100) and 
                                self.current_height >= max((self.expected_height - tolerance_height), 0)))

            if height_matches:
                self.debug("Change matches expected automated change")
                # Check if the curent event could be related to an automated cover change
                if self.automated_change_counter <= self.max_automated_change_counter:
                    # Reset external lock timer
                    self.shutter_locked_external_till = None
                    # Check if an maybe existing external lock could be released
                    self.check_external_lock()
            else:
                self.debug("Change doesn't match expected automated change - set external lock")
                # Logic when manual change detected - when aleady locked by any other lock no external lock detection
                if self.manipulation_active == STATE_OFF and self.shutter_locked == STATE_OFF:
                    # When not already locked due to external change, lock it and set timer
                    if self.shutter_locked_external == STATE_OFF:
                        # Set lock directly - communication with HASS maybe take some time and lead to issues
                        self.shutter_locked_external = STATE_ON
                        # Update timer
                        self.shutter_locked_external_till = datetime.now() + timedelta(minutes=self.params['shutter_locked_external_for_min'])
                        # AFTER timer update, also change state of input_boolean
                        self.set_state(entity_id=self.name_shutter_locked_external, state=STATE_ON)
                        # Sync State with HASS
                        self.shutter_locked_external = self.get_state(entity_id=self.name_shutter_locked_external)
                        
                        self.debug(f"External lock set to: {self.shutter_locked_external} timer set to: {self.shutter_locked_external_till}")
                    else:
                        self.debug(f"Already locked by external change till: {self.shutter_locked_external_till}")

    def save_states_to_file(self):
        """Save current states to JSON file with timestamp."""
        if not self.params['save_states']:
            # Don't save states
            return
        if not self.params['unique_id']:
            self.debug("No file suffix defined. Not saving state.")
            return

        state_data = {
            "timestamp": datetime.now().isoformat(),
            "state": self.shutter_state,
            "timer": self.timer.isoformat() if self.timer else None
        }
        
        try:
            filename = f"states_{self.params['unique_id']}.json"
            filepath = os.path.join(self.app_dir, filename)
            with open(filepath, 'w') as f:
                json.dump(state_data, f, indent=2)
            self.debug(f"Saved state to {filename}")
        except Exception as e:
            self.error(f"Failed to save state: {e}")

    def load_state_from_file(self):
        """Load states from JSON file if not older than 1 hour."""
        if not self.params['unique_id']:
            self.debug("No file suffix defined. No saved states.")
            return
        try:
            filename = f"states_{self.params['unique_id']}.json"
            filepath = os.path.join(self.app_dir, filename)
            
            if not os.path.exists(filepath):
                self.debug(f"No state file found for {self.params['unique_id']}")
                return False
                
            with open(filepath, 'r') as f:
                state_data = json.load(f)
                
            # Check timestamp
            saved_time = datetime.fromisoformat(state_data['timestamp'])
            if datetime.now() - saved_time > timedelta(minutes=60):
                self.debug(f"State file too old ({saved_time}), not loading")
                return False
                
            # Restore states
            self.shutter_state = state_data['state']
            self.timer = datetime.fromisoformat(state_data['timer']) if state_data['timer'] else None
            
            self.debug(f"Loaded state from {filename} (saved at {saved_time})")
            return True
            
        except Exception as e:
            self.error(f"Failed to load state: {e}")
            return False