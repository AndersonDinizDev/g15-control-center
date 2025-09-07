#!/usr/bin/env python3

import sys
import os
import subprocess
import glob
import json
import socket
import threading
import time
import signal
import logging
import tempfile
import shutil
import select
import struct
from pathlib import Path
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
import secrets


class PowerMode(Enum):
    QUIET = ("Silencioso", "0xa3", "#4CAF50")
    BALANCED = ("Balanceado", "0xa0", "#2196F3")
    PERFORMANCE = ("Performance", "0xa1", "#FF9800")
    CUSTOM = ("Personalizado", "0xa2", "#9C27B0")


class GModeKeyListener:
    
    def __init__(self, callback=None):
        self.callback = callback
        self.running = False
        self.thread = None
        self.device_path = None
        self.logger = logging.getLogger('g15.keylistener')
        self.key_code = 148  # KEY_PROG1
        
    def find_keyboard_device(self):
        try:
            devices_info = subprocess.run(
                ['cat', '/proc/bus/input/devices'], 
                capture_output=True, text=True, check=True
            ).stdout
            
            lines = devices_info.split('\n')
            current_device = {}
            
            for line in lines:
                if line.startswith('I:'):
                    current_device = {}
                elif line.startswith('N: Name='):
                    current_device['name'] = line.split('=', 1)[1].strip('"')
                elif line.startswith('H: Handlers='):
                    handlers = line.split('=', 1)[1]
                    event_handlers = [h for h in handlers.split() if h.startswith('event')]
                    if event_handlers:
                        current_device['event'] = f"/dev/input/{event_handlers[0]}"
                        
                        if 'AT Translated Set 2 keyboard' in current_device.get('name', ''):
                            return current_device['event']
                            
        except Exception as e:
            self.logger.error(f"Error finding keyboard device: {e}")
            
        return None
    
    def read_key_events(self):
        if not self.device_path:
            return
            
        try:
            with open(self.device_path, 'rb') as device:
                while self.running:
                    ready, _, _ = select.select([device], [], [], 1.0)
                    
                    if not ready:
                        continue
                        
                    event_data = device.read(24)
                    if len(event_data) == 24:
                        tv_sec, tv_usec, type_, code, value = struct.unpack('llHHi', event_data)
                        
                        if type_ == 1 and code == self.key_code and value == 1:
                            if self.callback:
                                threading.Thread(target=self.callback, daemon=True).start()
                                
        except PermissionError:
            self.logger.error("Permission denied to read keyboard events - daemon needs root")
        except Exception as e:
            self.logger.error(f"Error reading key events: {e}")
    
    def start(self):
        if self.running:
            return
            
        self.device_path = self.find_keyboard_device()
        if not self.device_path:
            self.logger.warning("Keyboard device not found - G-Mode key capture disabled")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self.read_key_events, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


class ConfigManager:
    
    def __init__(self):
        self.config_dir = Path('/etc/g15-daemon')
        self.config_file = self.config_dir / 'config.json'
        self.backup_file = self.config_dir / 'config.json.bak'
        self.logger = logging.getLogger('g15.config')
        
        self.default_config = {
            'power_mode': 'Balanceado',
            'g_mode': False,
            'fan_profiles': {
                'cpu_fan_boost': 0,
                'gpu_fan_boost': 0
            },
            'auto_apply': True,
            'last_saved': None,
            'version': '1.0'
        }
        
        self._ensure_config_dir()
    
    def _ensure_config_dir(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.config_dir, 0o700)
            self.logger.info(f"Config directory ensured at {self.config_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create config directory: {e}")
    
    def load(self) -> dict:
        try:
            if not self.config_file.exists():
                self.logger.info("Config file not found, using defaults")
                self.save(self.default_config)
                return self.default_config.copy()
            
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            if not self._validate_config(config):
                self.logger.warning("Invalid config found, using defaults")
                return self.default_config.copy()
            
            self.logger.info(f"Config loaded: {config}")
            return config
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Config file corrupted: {e}")
            if self.backup_file.exists():
                self.logger.info("Attempting to restore from backup")
                try:
                    shutil.copy2(self.backup_file, self.config_file)
                    return self.load()
                except Exception as be:
                    self.logger.error(f"Backup restore failed: {be}")
            
            return self.default_config.copy()
        
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return self.default_config.copy()
    
    def save(self, config: dict) -> bool:
        try:
            if not self._validate_config(config):
                self.logger.error("Invalid config, not saving")
                return False
            
            config['last_saved'] = datetime.now().isoformat()
            
            if self.config_file.exists():
                shutil.copy2(self.config_file, self.backup_file)
            
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=self.config_dir,
                delete=False
            ) as tmp_file:
                json.dump(config, tmp_file, indent=2)
                tmp_path = tmp_file.name
            
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self.config_file)
            
            self.logger.info(f"Config saved: {config}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False
    
    def _validate_config(self, config: dict) -> bool:
        try:
            required_fields = ['power_mode', 'g_mode', 'fan_profiles']
            for field in required_fields:
                if field not in config:
                    self.logger.error(f"Missing required field: {field}")
                    return False
            
            valid_modes = ['Silencioso', 'Balanceado', 'Performance', 'Personalizado']
            if config['power_mode'] not in valid_modes:
                self.logger.error(f"Invalid power_mode: {config['power_mode']}")
                return False
            
            if not isinstance(config['g_mode'], bool):
                self.logger.error(f"Invalid g_mode type: {type(config['g_mode'])}")
                return False
            
            fan_profiles = config.get('fan_profiles', {})
            for fan in ['cpu_fan_boost', 'gpu_fan_boost']:
                if fan in fan_profiles:
                    boost = fan_profiles[fan]
                    if not isinstance(boost, int) or not (0 <= boost <= 100):
                        self.logger.error(f"Invalid {fan} value: {boost}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Config validation error: {e}")
            return False


class G15HardwareController:
    def __init__(self):
        self.acpi_call_path = "/proc/acpi/call"
        self.acpi_base = r"\_SB.AMWW.WMAX"
        self.current_mode = PowerMode.BALANCED
        self.g_mode_active = False
        self.manual_mode = False
        self.current_fan_boosts = {1: 0, 2: 0}
        self.manual_fan_control = {1: False, 2: False}
        self.pre_gmode_state = None

        self.hwmon_path = None
        self.hwmon_fans = {}
        self.hwmon_temps = {}

        self.logger = logging.getLogger('g15.hardware')
        self.config_manager = ConfigManager()

        self._validate_security()
        self._check_acpi_availability()
        self._detect_hwmon_sensors()
        self._detect_model()
        self._load_and_apply_config()

    def _validate_security(self):
        if os.geteuid() != 0:
            self.logger.critical("SECURITY: Daemon must run as root")
            sys.exit(1)

        critical_paths = ["/proc/acpi", "/sys/class/hwmon"]
        for path in critical_paths:
            if not os.path.exists(path):
                self.logger.warning(f"SECURITY: Critical path missing: {path}")

        self.logger.info("SECURITY: Initial validation passed")

    def _check_acpi_availability(self):
        if not os.path.exists(self.acpi_call_path):
            self.logger.error("ACPI path not found. Dell G15 hardware not detected.")
            sys.exit(1)

        try:
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            if 'acpi_call' not in result.stdout:
                self.logger.info("Loading acpi_call module...")
                result = subprocess.run(['modprobe', 'acpi_call'], capture_output=True, text=True)
                if result.returncode != 0:
                    self.logger.error("Failed to load acpi_call module.")
                    sys.exit(1)
        except Exception as e:
            self.logger.error(f"Failed to check/load acpi_call module: {e}")
            sys.exit(1)

        try:
            with open(self.acpi_call_path, 'w') as f:
                f.write("test")
            self.logger.info("ACPI interface is accessible")
        except Exception as e:
            self.logger.error(f"Cannot write to ACPI interface: {e}")
            sys.exit(1)

    def _detect_hwmon_sensors(self):
        dell_hwmon_names = ['dell_smm', 'dell_ddv']

        for hwmon_dir in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                name_file = os.path.join(hwmon_dir, 'name')
                if os.path.exists(name_file):
                    with open(name_file, 'r') as f:
                        hwmon_name = f.read().strip()

                    if hwmon_name in dell_hwmon_names:
                        self.hwmon_path = hwmon_dir
                        self.logger.info(f"Found Dell hwmon: {hwmon_name} at {hwmon_dir}")

                        for temp_file in glob.glob(os.path.join(hwmon_dir, 'temp*_input')):
                            temp_num = temp_file.split('temp')[1].split('_')[0]
                            self.hwmon_temps[int(temp_num)] = temp_file

                        for fan_file in glob.glob(os.path.join(hwmon_dir, 'fan*_input')):
                            fan_num = fan_file.split('fan')[1].split('_')[0]
                            self.hwmon_fans[int(fan_num)] = fan_file

                        self.logger.info(f"Detected temperatures: {list(self.hwmon_temps.keys())}")
                        self.logger.info(f"Detected fans: {list(self.hwmon_fans.keys())}")
                        return
            except Exception as e:
                self.logger.warning(f"Error checking hwmon {hwmon_dir}: {e}")
                continue

        self.logger.warning("No Dell hwmon sensors found, using ACPI only")

    def _detect_model(self):
        try:
            result = self._acpi_call_real("0x1a", ["0x02", "0x02"])
            if result and result != "0x0":
                model_map = {
                    "0x1": "5511", "0x2": "5515", "0x3": "5520",
                    "0x4": "5525", "0x5": "5530", "0x6": "5535"
                }
                self.model = model_map.get(result, "Unknown")
                self.logger.info(f"Detected Dell G15 {self.model}")
            else:
                self.model = "Unknown"
        except Exception as e:
            self.logger.warning(f"Model detection failed: {e}")
            self.model = "Unknown"
    
    def _load_and_apply_config(self):
        try:
            config = self.config_manager.load()
            
            if not config.get('auto_apply', True):
                self.logger.info("Auto-apply disabled, using default settings")
                return
            
            self.logger.info("Applying saved configuration...")
            
            mode_name = config.get('power_mode', 'Balanceado')
            for mode in PowerMode:
                if mode.value[0] == mode_name:
                    self.set_power_mode(mode, save_config=False)
                    break
            
            g_mode = config.get('g_mode', False)
            if g_mode:
                self.enable_g_mode(save_config=False)
            
            if mode_name == 'Personalizado':
                fan_profiles = config.get('fan_profiles', {})
                for fan_id in [1, 2]:
                    fan_key = f'{"cpu" if fan_id == 1 else "gpu"}_fan_boost'
                    manual_key = f'{"cpu" if fan_id == 1 else "gpu"}_manual'
                    
                    if fan_profiles.get(manual_key, False):
                        self.manual_fan_control[fan_id] = True
                        self.set_fan_boost(fan_id, fan_profiles.get(fan_key, 0), save_config=False)
            
            self.logger.info("Configuration applied successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to apply saved config: {e}")
            self.logger.info("Using default configuration")
    
    def _save_current_config(self):
        try:
            config = {
                'power_mode': self.current_mode.value[0],
                'g_mode': self.g_mode_active,
                'fan_profiles': {
                    'cpu_fan_boost': self.current_fan_boosts.get(1, 0),
                    'gpu_fan_boost': self.current_fan_boosts.get(2, 0),
                    'cpu_manual': self.manual_fan_control.get(1, False),
                    'gpu_manual': self.manual_fan_control.get(2, False)
                },
                'auto_apply': True,
                'version': '1.0'
            }
            
            self.config_manager.save(config)
            
        except Exception as e:
            self.logger.error(f"Config save failed: {e}")

    def _read_hwmon_sensor(self, sensor_path: str) -> int:
        try:
            if not sensor_path.startswith('/sys/class/hwmon/'):
                self.logger.error(f"SECURITY: Invalid sensor path: {sensor_path}")
                return 0

            with open(sensor_path, 'r') as f:
                value = int(f.read().strip())
                return value
        except Exception as e:
            self.logger.error(f"Error reading hwmon sensor {sensor_path}: {e}")
            return 0

    def _acpi_call_real(self, wmi_code: str, args: list = None) -> str:
        if args is None:
            args = []

        if not wmi_code.startswith('0x'):
            self.logger.error(f"SECURITY: Invalid WMI code format: {wmi_code}")
            return "0x0"

        for arg in args:
            if not str(arg).startswith('0x'):
                self.logger.error(f"SECURITY: Invalid argument format: {arg}")
                return "0x0"

        while len(args) < 4:
            args.append("0x00")

        args_str = ', '.join(str(a) for a in args)
        command = f"{self.acpi_base} 0 {wmi_code} {{{args_str}}}"

        try:
            with open(self.acpi_call_path, 'w') as f:
                f.write(command)

            with open(self.acpi_call_path, 'r') as f:
                result = f.read().strip()

            if result.startswith("{"):
                result = result.strip("{}").split(",")[0].strip()

            self.logger.debug(f"ACPI call: {command} -> {result}")
            return result if result else "0x0"
        except Exception as e:
            self.logger.error(f"ACPI call error: {e}")
            return "0x0"

    def get_cpu_temp(self) -> int:
        if self.hwmon_path and 1 in self.hwmon_temps:
            temp_millidegrees = self._read_hwmon_sensor(self.hwmon_temps[1])
            if temp_millidegrees > 0:
                temp_celsius = temp_millidegrees // 1000
                if 0 <= temp_celsius <= 120:
                    return temp_celsius

        result = self._acpi_call_real("0x14", ["0x04", "0x01"])
        try:
            temp = int(result, 16)
            if 0 <= temp <= 120:
                return temp
        except:
            pass

        return 45

    def get_gpu_temp(self) -> int:
        if self.hwmon_path and 2 in self.hwmon_temps:
            temp_millidegrees = self._read_hwmon_sensor(self.hwmon_temps[2])
            if temp_millidegrees > 0:
                temp_celsius = temp_millidegrees // 1000
                if 0 <= temp_celsius <= 120:
                    return temp_celsius

        result = self._acpi_call_real("0x14", ["0x04", "0x02"])
        try:
            temp = int(result, 16)
            if 0 <= temp <= 120:
                return temp
        except:
            pass

        return 50

    def get_fan_rpm(self, fan_id: int) -> int:
        if not isinstance(fan_id, int) or fan_id not in [1, 2]:
            self.logger.error(f"SECURITY: Invalid fan_id: {fan_id}")
            return 0

        if self.hwmon_path and fan_id in self.hwmon_fans:
            rpm = self._read_hwmon_sensor(self.hwmon_fans[fan_id])
            if 0 <= rpm <= 10000:
                return rpm

        sensor_id = f"0x{0x32 + fan_id - 1:02X}"
        result = self._acpi_call_real("0x14", ["0x05", sensor_id])
        try:
            rpm = int(result, 16)
            if 0 <= rpm <= 10000:
                return rpm
        except:
            pass

        return 2500 if fan_id == 1 else 2300

    def get_fan_boost(self, fan_id: int) -> int:
        if not isinstance(fan_id, int) or fan_id not in [1, 2]:
            self.logger.error(f"SECURITY: Invalid fan_id: {fan_id}")
            return 0
        
        return self.current_fan_boosts.get(fan_id, 0)

    def get_power_mode(self) -> PowerMode:
        return self.current_mode

    def get_g_mode_status(self) -> bool:
        result = self._acpi_call_real("0x25", ["0x02"])
        return result == "0x1"

    def set_power_mode(self, mode: PowerMode, save_config: bool = True) -> bool:
        if not isinstance(mode, PowerMode):
            self.logger.error(f"SECURITY: Invalid power mode type: {type(mode)}")
            return False

        self.logger.info(f"CONTROL: Setting power mode to {mode.value[0]}")

        self.current_mode = mode
        if mode == PowerMode.CUSTOM:
            self.manual_mode = True
        else:
            self.manual_mode = False
            self._acpi_call_real("0x15", ["0x01", mode.value[1]])
            self.current_fan_boosts = {1: 0, 2: 0}
            self.manual_fan_control = {1: False, 2: False}

        if save_config:
            self._save_current_config()

        return True

    def set_fan_boost(self, fan_id: int, percentage: int, save_config: bool = True, is_manual: bool = True) -> bool:
        if not isinstance(fan_id, int) or fan_id not in [1, 2]:
            self.logger.error(f"SECURITY: Invalid fan_id: {fan_id}")
            return False

        if not isinstance(percentage, int) or not (0 <= percentage <= 100):
            self.logger.error(f"SECURITY: Invalid percentage: {percentage}")
            return False

        self.logger.info(f"CONTROL: Setting fan {fan_id} boost to {percentage}%")

        sensor_id = f"0x{0x32 + fan_id - 1:02X}"
        hex_value = f"0x{percentage:02X}"
        self._acpi_call_real("0x15", ["0x02", sensor_id, hex_value])
        
        self.current_fan_boosts[fan_id] = percentage
        if is_manual:
            self.manual_fan_control[fan_id] = (percentage > 0)
        
        if save_config:
            self._save_current_config()

        return True

    def enable_g_mode(self, save_config: bool = True) -> bool:
        self.logger.info("CONTROL: Enabling G-Mode")
        
        if not self.g_mode_active:
            self.pre_gmode_state = {
                'mode': self.current_mode,
                'fan_boosts': self.current_fan_boosts.copy(),
                'manual_control': self.manual_fan_control.copy()
            }
        
        self.g_mode_active = True
        
        self._acpi_call_real("0x25", ["0x01", "0x01"])
        time.sleep(0.05)
        self._acpi_call_real("0x15", ["0x01", "0xab"])
        
        if save_config:
            self._save_current_config()
        
        return True

    def disable_g_mode(self, save_config: bool = True) -> bool:
        self.logger.info("CONTROL: Disabling G-Mode")
        self.g_mode_active = False
        
        self._acpi_call_real("0x25", ["0x01", "0x00"])
        time.sleep(0.1)
        
        if self.pre_gmode_state:
            mode = self.pre_gmode_state['mode']
            fan_boosts = self.pre_gmode_state['fan_boosts']
            manual_control = self.pre_gmode_state['manual_control']
            
            self._acpi_call_real("0x15", ["0x01", PowerMode.BALANCED.value[1]])
            time.sleep(0.1)
            
            if mode == PowerMode.CUSTOM:
                self.set_power_mode(mode, save_config=False)
                
                for fan_id in [1, 2]:
                    if manual_control.get(fan_id, False):
                        self.set_fan_boost(fan_id, fan_boosts.get(fan_id, 0), save_config=False, is_manual=True)
            else:
                self.set_power_mode(mode, save_config=False)
            
            self.pre_gmode_state = None
        else:
            self._acpi_call_real("0x15", ["0x01", self.current_mode.value[1]])
        
        if save_config:
            self._save_current_config()
        
        return True

    def toggle_g_mode(self) -> bool:
        if self.g_mode_active:
            return self.disable_g_mode()
        else:
            return self.enable_g_mode()


class G15DaemonServer:
    def __init__(self):
        self.socket_path = "/tmp/g15-daemon.sock"
        self.hardware = G15HardwareController()
        self.running = False
        self.server_socket = None

        self.active_sessions = {}

        self.setup_logging()

        self.client_requests = {}

        self.logger = logging.getLogger('g15.daemon')
        
        self.gmode_listener = GModeKeyListener(callback=self._on_gmode_key_pressed)
    
    def _on_gmode_key_pressed(self):
        try:
            self.hardware.toggle_g_mode()
        except Exception as e:
            self.logger.error(f"Error handling G-Mode key press: {e}")

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/g15-daemon.log'),
                logging.StreamHandler()
            ]
        )

    def generate_session_token(self) -> str:
        return secrets.token_hex(16)

    def validate_request(self, client_addr: str, request_data: dict) -> bool:
        now = time.time()
        if client_addr not in self.client_requests:
            self.client_requests[client_addr] = []

        self.client_requests[client_addr] = [
            req_time for req_time in self.client_requests[client_addr]
            if now - req_time < 10
        ]

        if len(self.client_requests[client_addr]) > 50:
            self.logger.warning(f"SECURITY: Rate limit exceeded for {client_addr}")
            return False

        self.client_requests[client_addr].append(now)

        required_fields = ['action']
        for field in required_fields:
            if field not in request_data:
                self.logger.error(f"SECURITY: Missing required field: {field}")
                return False

        return True

    def process_request(self, request_data: dict) -> dict:
        action = request_data.get('action', '')

        allowed_actions = [
            'get_status', 'get_temps', 'get_fans', 'get_power_mode', 'get_all_data',
            'set_power_mode', 'set_fan_boost', 'toggle_g_mode',
            'authenticate'
        ]

        if action not in allowed_actions:
            self.logger.error(f"SECURITY: Unauthorized action: {action}")
            return {"status": "error", "message": "Unauthorized action"}

        try:
            if action == 'authenticate':
                token = self.generate_session_token()
                self.active_sessions[token] = time.time()
                return {"status": "success", "token": token}

            elif action == 'get_status':
                return {
                    "status": "success",
                    "data": {
                        "model": self.hardware.model,
                        "hwmon_available": self.hardware.hwmon_path is not None,
                        "g_mode_active": self.hardware.g_mode_active
                    }
                }

            elif action == 'get_temps':
                return {
                    "status": "success",
                    "data": {
                        "cpu_temp": self.hardware.get_cpu_temp(),
                        "gpu_temp": self.hardware.get_gpu_temp()
                    }
                }

            elif action == 'get_fans':
                return {
                    "status": "success",
                    "data": {
                        "fan1_rpm": self.hardware.get_fan_rpm(1),
                        "fan2_rpm": self.hardware.get_fan_rpm(2),
                        "fan1_boost": self.hardware.get_fan_boost(1),
                        "fan2_boost": self.hardware.get_fan_boost(2),
                        "fan1_manual": self.hardware.manual_fan_control.get(1, False),
                        "fan2_manual": self.hardware.manual_fan_control.get(2, False)
                    }
                }

            elif action == 'get_power_mode':
                mode = self.hardware.get_power_mode()
                return {
                    "status": "success",
                    "data": {
                        "current_mode": mode.value[0],
                        "g_mode": self.hardware.g_mode_active
                    }
                }

            elif action == 'set_power_mode':
                mode_name = request_data.get('mode', '')
                mode_map = {mode.value[0]: mode for mode in PowerMode}

                if mode_name not in mode_map:
                    return {"status": "error", "message": "Invalid power mode"}

                success = self.hardware.set_power_mode(mode_map[mode_name])
                return {"status": "success" if success else "error"}

            elif action == 'set_fan_boost':
                fan_id = request_data.get('fan_id')
                percentage = request_data.get('percentage')

                if not isinstance(fan_id, int) or not isinstance(percentage, int):
                    return {"status": "error", "message": "Invalid parameters"}

                success = self.hardware.set_fan_boost(fan_id, percentage)
                return {"status": "success" if success else "error"}

            elif action == 'get_all_data':
                return {
                    "status": "success",
                    "data": {
                        "temps": {
                            "cpu_temp": self.hardware.get_cpu_temp(),
                            "gpu_temp": self.hardware.get_gpu_temp()
                        },
                        "fans": {
                            "fan1_rpm": self.hardware.get_fan_rpm(1),
                            "fan2_rpm": self.hardware.get_fan_rpm(2),
                            "fan1_boost": self.hardware.get_fan_boost(1),
                            "fan2_boost": self.hardware.get_fan_boost(2),
                            "fan1_manual": self.hardware.manual_fan_control.get(1, False),
                            "fan2_manual": self.hardware.manual_fan_control.get(2, False)
                        },
                        "power": {
                            "current_mode": self.hardware.get_power_mode().value[0],
                            "g_mode": self.hardware.g_mode_active
                        },
                        "status": {
                            "model": self.hardware.model,
                            "hwmon_available": self.hardware.hwmon_path is not None,
                            "g_mode_active": self.hardware.g_mode_active
                        }
                    }
                }

            elif action == 'toggle_g_mode':
                success = self.hardware.toggle_g_mode()
                return {"status": "success" if success else "error"}

        except Exception as e:
            self.logger.error(f"Error processing request: {e}")
            return {"status": "error", "message": "Internal server error"}

        return {"status": "error", "message": "Unknown error"}

    def handle_client(self, client_socket, client_addr):
        try:
            data = client_socket.recv(4096)
            if not data:
                return

            request_data = json.loads(data.decode('utf-8'))

            if not self.validate_request(str(client_addr), request_data):
                response = {"status": "error", "message": "Request validation failed"}
            else:
                response = self.process_request(request_data)

            response_json = json.dumps(response)
            client_socket.send(response_json.encode('utf-8'))

        except json.JSONDecodeError:
            self.logger.error(f"SECURITY: Invalid JSON from {client_addr}")
            error_response = {"status": "error", "message": "Invalid JSON"}
            client_socket.send(json.dumps(error_response).encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Error handling client {client_addr}: {e}")
        finally:
            client_socket.close()

    def start_server(self):
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)

            os.chmod(self.socket_path, 0o666)

            try:
                import grp
                users_gid = grp.getgrnam('users').gr_gid
                os.chown(self.socket_path, -1, users_gid)
                os.chmod(self.socket_path, 0o660)
                self.logger.info("Socket permissions set for 'users' group")
            except (KeyError, OSError):
                os.chmod(self.socket_path, 0o666)
                self.logger.warning("Using fallback permissions (666) for socket")

            self.server_socket.listen(5)
            self.running = True

            self.gmode_listener.start()

            self.logger.info(f"G15 Daemon started on {self.socket_path}")

            while self.running:
                try:
                    client_socket, client_addr = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                except socket.error as e:
                    if self.running:
                        self.logger.error(f"Socket error: {e}")
                    break

        except Exception as e:
            self.logger.error(f"Failed to start daemon: {e}")
            sys.exit(1)

    def stop_server(self):
        self.logger.info("Stopping G15 Daemon...")
        self.running = False

        if hasattr(self, 'gmode_listener'):
            self.gmode_listener.stop()

        if self.server_socket:
            self.server_socket.close()

        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self.logger.info("G15 Daemon stopped")


def signal_handler(signum, frame):
    global daemon_server
    if daemon_server:
        daemon_server.stop_server()
    sys.exit(0)


def main():
    print("Starting Dell G15 Control Center Daemon...")
    print("WARNING: This daemon runs with root privileges")
    print("All operations are logged for security audit")
    print("Configuration will be saved to /etc/g15-daemon/config.json")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    global daemon_server
    daemon_server = G15DaemonServer()

    try:
        daemon_server.start_server()
    except KeyboardInterrupt:
        daemon_server.stop_server()
    except Exception as e:
        logging.error(f"Daemon crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()