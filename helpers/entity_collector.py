import os
from pathlib import Path

class EntityCollector:
    """
    Singleton class to collect input_boolean configurations from blinds and shutter instances.
    Generates YAML configuration for Home Assistant's configuration.yaml
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EntityCollector, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'input_booleans'):
            self.input_booleans = {}
    
    def add_boolean(self, entity_id: str, friendly_name: str, icon: str = None):
        """
        Add an input_boolean configuration.
        
        Args:
            entity_id: The entity ID without the input_boolean. prefix
            friendly_name: Display name for the input_boolean
            icon: Optional MDI icon string
        """
        config = {
            "name": friendly_name
        }
        if icon:
            config["icon"] = icon
            
        self.input_booleans[entity_id] = config
    
    def get_yaml_config(self) -> str:
        """
        Generate YAML configuration for input_booleans.
        
        Returns:
            String containing YAML configuration ready to paste into configuration.yaml
        """
        if not self.input_booleans:
            return "# No input_booleans configured"
            
        yaml_lines = []
        for entity_id, config in sorted(self.input_booleans.items()):
            yaml_lines.append(f"  {entity_id}:")
            for key, value in config.items():
                yaml_lines.append(f"    {key}: {value}")
                
        return "\n".join(yaml_lines) + "\n"

    def write_yaml_config(self, directory_path: str) -> str | None:
        """
        Write YAML configuration to a file in the specified directory.
        
        Args:
            directory_path: Path where the file should be created
            
        Returns:
            str: Full filepath if file was written successfully
            None: If writing failed
        """
        try:
            # Create directory if it doesn't exist
            Path(directory_path).mkdir(parents=True, exist_ok=True)
            
            # Fixed filename
            filename = "entities.config"
            filepath = os.path.join(directory_path, filename)
            
            # Get YAML configuration
            yaml_content = self.get_yaml_config()
            
            # Write configuration to file
            if os.path.exists(filepath):
                append_write = 'a' # append if already exists
            else:
                append_write = 'w' # make a new file if not
                # When new file add first line "input_boolean:"
                yaml_content = "input_boolean:\n" + yaml_content
            with open(filepath, append_write, encoding='utf-8') as f:
                f.write(yaml_content)
            
            # Clear variable when already written
            self.input_booleans = {}

            return filepath
            
        except Exception as e:
            raise e
