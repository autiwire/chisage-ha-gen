__version__ = "0.1.0"
__author__ = "Rouven Raudzus"
__company__ = "Autiwire GmbH"
__email__ = "raudzus@autiwire.de"
__copyright__ = "2025 Autiwire GmbH"
__license__ = "Apache License 2.0"
__license_url__ = "https://www.apache.org/licenses/LICENSE-2.0"
__thanks__ = "Thanks to Chisage Company for their support and high quality modbus documentation."

from dataclasses import dataclass
from typing import Optional
import yaml
import os
import argparse
import re # Import re for string replacement

# Custom class and representer for PyYAML to handle !include tags without quotes
# class IncludeTag(str):
#     pass
# 
# def represent_include_tag(dumper, data):
#     return dumper.represent_scalar('tag:yaml.org,2002:str', str(data), style='') # Plain style, no quotes
# 
# yaml.add_representer(IncludeTag, represent_include_tag)

# --- PyYAML Customization for Loading !include --- 
def include_constructor(loader, node):
    # Treat the !include tag as a plain string by returning the tag itself with its value
    # For example, if YAML is "!include foo.yaml", node.tag will be "!include"
    # and node.value will be "foo.yaml".
    # However, for unquoted tags like !include, node.value is the whole string after tag.
    # For parsing `sensors: !include path/file.yaml`
    # node will be a ScalarNode, node.tag will be u'!include', node.value is path/file.yaml
    # We want to return the literal string "!include path/file.yaml"
    return node.tag + ' ' + node.value

# Add the constructor to the SafeLoader
yaml.add_constructor('!include', include_constructor, Loader=yaml.SafeLoader)
# Also add to Dumper if we were to load and dump with complex tags, but for output we use string replacement


@dataclass
class ModbusRegister:
    name: str
    slave: int
    address: int
    data_type: str
    scale: Optional[float] = None
    unit_of_measurement: Optional[str] = None
    scan_interval: Optional[int] = None
    state_class: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "slave": self.slave,
            "address": self.address,
            "data_type": self.data_type,
        }
        if self.scale is not None:
            result["scale"] = self.scale
        if self.unit_of_measurement is not None:
            result["unit_of_measurement"] = self.unit_of_measurement
        if self.scan_interval is not None:
            result["scan_interval"] = self.scan_interval
        if self.state_class is not None:
            result["state_class"] = self.state_class
        return result

class ModbusDevice:
    name: str
    slave: int
    sensors: list[ModbusRegister]
    host: str

    def __init__(self, name: str, slave: int, host: str = "192.168.178.209", 
                 default_sensor_scan_interval: Optional[int] = 20,
                 sensors: Optional[list[ModbusRegister]] = None):
        self.name = name
        self.slave = slave
        self.host = host
        self.sensors = sensors if sensors is not None else []
        
        if default_sensor_scan_interval is not None:
            for sensor in self.sensors:
                if sensor.scan_interval is None:
                    sensor.scan_interval = default_sensor_scan_interval

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slave": self.slave,
            "sensors": [sensor.to_dict() for sensor in self.sensors],
        }

    def make_config(self, device_port_for_hub: int) -> None:
        sensor_config_list = [s.to_dict() for s in self.sensors]

        os.makedirs("chisage", exist_ok=True)
        safe_device_name_part = self.name.lower().replace(' ', '_').replace('-', '_')
        sensors_file_path = f"chisage/{safe_device_name_part}_sensors.yaml"
        
        with open(sensors_file_path, "w") as f:
            yaml.dump(sensor_config_list, f, sort_keys=False, indent=2)

        modbus_hubs_filename = "modbus_devices.yaml"
        modbus_hubs_list = [] 
        try:
            with open(modbus_hubs_filename, "r") as f:
                # Now safe_load will use our include_constructor for !include tags
                loaded_data = yaml.safe_load(f) 
                if isinstance(loaded_data, list):
                    modbus_hubs_list = loaded_data
                elif isinstance(loaded_data, dict) and "modbus" in loaded_data and isinstance(loaded_data["modbus"], list):
                    modbus_hubs_list = loaded_data["modbus"]
                elif loaded_data is not None: 
                    print(f"Warning: {modbus_hubs_filename} contains unexpected data or format. It will be overwritten.")
        except FileNotFoundError:
            pass 
        except yaml.YAMLError as e:
            # This will catch the constructor error if include_constructor is not set up right, or other YAML errors
            print(f"Warning: Error parsing {modbus_hubs_filename}: {e}. The file will be treated as empty or overwritten.")

        hub_entry = {
            "name": self.name,
            "type": "tcp",
            "host": self.host, 
            "port": device_port_for_hub, 
            "sensors": f"!include {sensors_file_path}"
        }

        found = False
        for i, entry in enumerate(modbus_hubs_list):
            if isinstance(entry, dict) and entry.get("name") == self.name:
                modbus_hubs_list[i] = hub_entry
                found = True
                break
        if not found:
            modbus_hubs_list.append(hub_entry)

        with open(modbus_hubs_filename, "w") as f:
            yaml_output_string = yaml.dump(modbus_hubs_list, sort_keys=False, indent=2, Dumper=yaml.Dumper)
            corrected_yaml_string = re.sub(r"'(!include [^']+\.yaml)'", r"\1", yaml_output_string)
            f.write(corrected_yaml_string)

class ChisageInverter(ModbusDevice):
    def __init__(self, name: str, slave: int, host: str = "192.168.178.209", default_sensor_scan_interval: int = 20):
        inverter_sensors = [
            ModbusRegister(name=f"{name} Inverter Voltage A", slave=slave, address=26, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Inverter Voltage B", slave=slave, address=27, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Inverter Voltage C", slave=slave, address=28, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Inverter Current A", slave=slave, address=29, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Inverter Current B", slave=slave, address=30, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Inverter Current C", slave=slave, address=31, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Grid Voltage A", slave=slave, address=32, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Grid Voltage B", slave=slave, address=33, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Grid Voltage C", slave=slave, address=34, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Grid Current A", slave=slave, address=35, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Grid Current B", slave=slave, address=36, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Grid Current C", slave=slave, address=37, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Load Voltage A", slave=slave, address=38, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Load Voltage B", slave=slave, address=39, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Load Voltage C", slave=slave, address=40, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Load Current A", slave=slave, address=41, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Load Current B", slave=slave, address=42, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Load Current C", slave=slave, address=43, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Diesel Generator Voltage A", slave=slave, address=44, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Diesel Generator Voltage B", slave=slave, address=45, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Diesel Generator Voltage C", slave=slave, address=46, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Diesel Generator Current A", slave=slave, address=47, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Diesel Generator Current B", slave=slave, address=48, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Diesel Generator Current C", slave=slave, address=49, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Inverter Positive Bus Voltage", slave=slave, address=50, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Negative Bus Voltage", slave=slave, address=51, data_type="uint16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Inverter Frequency", slave=slave, address=52, data_type="int16", scale=0.01, unit_of_measurement="Hz"),
            ModbusRegister(name=f"{name} Grid Frequency", slave=slave, address=53, data_type="int16", scale=0.01, unit_of_measurement="Hz"),
            ModbusRegister(name=f"{name} Diesel Generator Output Frequency", slave=slave, address=54, data_type="int16", scale=0.01, unit_of_measurement="Hz"),
            ModbusRegister(name=f"{name} Maximum Temperature", slave=slave, address=56, data_type="uint16", scale=0.1, unit_of_measurement="°C"),
            ModbusRegister(name=f"{name} Inverter Working Stage", slave=slave, address=57, data_type="uint16", unit_of_measurement=""),
            ModbusRegister(name=f"{name} External CT Power A", slave=slave, address=58, data_type="uint16", scale=0.01, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} External CT Power B", slave=slave, address=59, data_type="uint16", scale=0.01, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} External CT Power C", slave=slave, address=60, data_type="uint16", scale=0.01, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} External CT Current A", slave=slave, address=61, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} External CT Current B", slave=slave, address=62, data_type="uint16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Battery Voltage", slave=slave, address=2026, data_type="int16", scale=0.01, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Battery Current", slave=slave, address=2027, data_type="int16", scale=0.1, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Photovoltaic 1 Voltage", slave=slave, address=2028, data_type="int16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Photovoltaic 1 Current", slave=slave, address=2029, data_type="int16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Photovoltaic 2 Voltage", slave=slave, address=2030, data_type="int16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Photovoltaic 2 Current", slave=slave, address=2031, data_type="int16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} DC Bus Voltage", slave=slave, address=2032, data_type="int16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} DC Positive Bus Voltage", slave=slave, address=2033, data_type="int16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Buck Voltage", slave=slave, address=2034, data_type="int16", scale=0.1, unit_of_measurement="V"),
            ModbusRegister(name=f"{name} Buck Current", slave=slave, address=2035, data_type="int16", scale=0.01, unit_of_measurement="A"),
            ModbusRegister(name=f"{name} Battery Power", slave=slave, address=2036, data_type="int16", scale=1.0, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} Photovoltaic 1 Power", slave=slave, address=2037, data_type="int16", scale=1.0, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} Photovoltaic 2 Power", slave=slave, address=2038, data_type="int16", scale=1.0, unit_of_measurement="W", state_class="measurement"),
            ModbusRegister(name=f"{name} Battery SOC", slave=slave, address=2039, data_type="uint16", scale=1.0, unit_of_measurement="%", state_class="measurement"),
        ]
        super().__init__(name, slave, host, default_sensor_scan_interval, inverter_sensors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Chisage Inverter Modbus configurations for Home Assistant.")
    parser.add_argument("--count", type=int, required=True, 
                        help="Number of inverters to generate configurations for.")
    parser.add_argument("--slave-id", type=int, default=1, 
                        help="Modbus slave ID to use for all inverters (default: 1).")

    # IP arguments - mutually exclusive group
    ip_group = parser.add_mutually_exclusive_group(required=True)
    ip_group.add_argument("--ip-start", type=str, 
                          help="Starting IP address for incremental assignment (e.g., 192.168.1.10). Last octet will be incremented.")
    ip_group.add_argument("--ip-fixed", type=str, 
                          help="Fixed IP address to use for ALL inverters (e.g., 192.168.1.100).")

    # Port arguments - mutually exclusive group
    port_group = parser.add_mutually_exclusive_group(required=True)
    port_group.add_argument("--port-start", type=int, 
                            help="Starting port number for incremental assignment (e.g., 5001). Will be incremented.")
    port_group.add_argument("--port-fixed", type=int, 
                            help="Fixed port number to use for ALL inverters (e.g., 5000).")
    
    parser.add_argument("--generate-cards", action="store_true", 
                        help="If set, generate Lovelace card YAML configuration files for each inverter.")
    # Optional: could add --default-sensor-scan-interval if needed later

    args = parser.parse_args()

    inverter_count_num = args.count
    slave_id_val = args.slave_id

    # --- IP Address Setup ---
    ip_mode_is_start = False
    if args.ip_start:
        ip_mode_is_start = True
        ip_to_process = args.ip_start
        try:
            ip_octets = ip_to_process.split('.')
            if len(ip_octets) != 4 or not all(o.isdigit() and 0 <= int(o) <= 255 for o in ip_octets):
                raise ValueError("Invalid IP address format for --ip-start. Must be A.B.C.D with octets 0-255.")
            base_ip_prefix = ".".join(ip_octets[:3])
            last_octet_start = int(ip_octets[3])
            print(f"IP Mode: Incremental, starting from {args.ip_start}")
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)
    elif args.ip_fixed:
        ip_to_process = args.ip_fixed
        try:
            ip_octets = ip_to_process.split('.')
            if len(ip_octets) != 4 or not all(o.isdigit() and 0 <= int(o) <= 255 for o in ip_octets):
                raise ValueError("Invalid IP address format for --ip-fixed. Must be A.B.C.D with octets 0-255.")
            fixed_ip_str = ip_to_process # Store validated fixed IP
            print(f"IP Mode: Fixed, using {fixed_ip_str} for all inverters")
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)
    # Mutually exclusive group with required=True ensures one is present

    # --- Port Number Setup ---
    port_mode_is_start = False
    if args.port_start:
        port_mode_is_start = True
        port_to_process = args.port_start
        print(f"Port Mode: Incremental, starting from {port_to_process}")
    elif args.port_fixed:
        port_to_process = args.port_fixed
        print(f"Port Mode: Fixed, using {port_to_process} for all inverters")
    # Mutually exclusive group with required=True ensures one is present

    if inverter_count_num <= 0:
        print("Error: Count must be a positive integer.")
        exit(1)
        
    print(f"\nGenerating {inverter_count_num} inverter configuration(s):")
    print(f"Slave ID for all: {slave_id_val}\n")

    for i in range(inverter_count_num):
        # Determine current_host_ip
        if ip_mode_is_start:
            current_last_octet = last_octet_start + i
            if current_last_octet > 255:
                print(f"Error: IP address range overflow for --ip-start. Incrementing {args.ip_start} by {i} results in an invalid octet: {current_last_octet}.")
                print("Please check --ip-start and --count to ensure the range is valid.")
                exit(1)
            current_host_ip = f"{base_ip_prefix}.{current_last_octet}"
        else: # ip_fixed mode
            current_host_ip = fixed_ip_str

        # Determine current_port_val
        if port_mode_is_start:
            current_port_val = port_to_process + i
        else: # port_fixed mode
            current_port_val = port_to_process
            
        device_instance_name = f"Chisage {i + 1}"

        print(f"  Creating Inverter {i+1}: Name='{device_instance_name}', Host={current_host_ip}, Port={current_port_val}, SlaveID={slave_id_val}")

        inverter_device = ChisageInverter(
            name=device_instance_name,
            slave=slave_id_val,
            host=current_host_ip
        )
        
        inverter_device.make_config(device_port_for_hub=current_port_val)
        
        if args.generate_cards:
            device_identifier_for_file = device_instance_name.lower().replace(' ', '_')
            card_entities = []
            for reg in inverter_device.sensors:
                # reg.name is already like "Chisage 1 Inverter Voltage A"
                # Home Assistant's Modbus integration typically creates entity IDs like:
                # sensor.hub_name_sensor_name (all lowercase, spaces to underscores)
                # The hub name is inverter_device.name (e.g., "Chisage 1")
                # The sensor name on the hub is reg.name itself.
                
                # Sanitize hub name for entity ID part
                hub_name_sanitized = inverter_device.name.lower().replace(" ", "_")
                # Sanitize sensor name for entity ID part
                sensor_name_sanitized = reg.name.lower().replace(" ", "_")
                
                # If sensor name already contains hub name, avoid duplication for suffix
                # This logic assumes sensor names like "Chisage 1 Power" and hub name "Chisage 1"
                # We want entity id sensor.chisage_1_power
                # The Modbus integration does this: sensor.[hub_name]_[sensor_name_from_config_on_hub]
                # Our current reg.name is the full desired name, also used in sensor config

                entity_id = f"sensor.{sensor_name_sanitized}" # reg.name already has device name

                # For display name in card, try to make it cleaner by removing device prefix
                display_name_in_card = reg.name
                if display_name_in_card.startswith(inverter_device.name + " "):
                    display_name_in_card = display_name_in_card[len(inverter_device.name) + 1:]
                
                card_entities.append({
                    "entity": entity_id,
                    "name": display_name_in_card
                })

            card_config = {
                "type": "entities",
                "title": inverter_device.name, # e.g., "Chisage 1"
                "entities": card_entities
            }

            os.makedirs("chisage", exist_ok=True)
            card_filename = f"chisage/{device_identifier_for_file}_card.yaml"
            
            with open(card_filename, "w") as f_card:
                yaml.dump(card_config, f_card, sort_keys=False, indent=2)
            print(f"    Generated card: {card_filename}")
        
    print(f"\nSuccessfully generated configurations.")
    print(f"Main Modbus hub configuration updated in: modbus_devices.yaml")
    print(f"Sensor-specific configurations are in the 'chisage' directory (e.g., chisage/chisage_1_sensors.yaml).")