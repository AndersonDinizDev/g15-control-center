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
from pathlib import Path
from enum import Enum
from typing import Dict, Any, Optional
import secrets


class PowerMode(Enum):
    QUIET = ("Quiet", "0xa3", "#4CAF50")
    BALANCED = ("Balanced", "0xa0", "#2196F3")
    PERFORMANCE = ("Performance", "0xa1", "#FF9800")
    CUSTOM = ("Custom", "0xa2", "#9C27B0")


class G15HardwareController:
    def __init__(self):
        self.acpi_call_path = "/proc/acpi/call"
        self.acpi_base = r"\_SB.AMWW.WMAX"
        self.current_mode = PowerMode.BALANCED
        self.g_mode_active = False
        self.manual_mode = False

        self.hwmon_path = None
        self.hwmon_fans = {}
        self.hwmon_temps = {}

        self.logger = logging.getLogger('g15.hardware')

        self._validate_security()
        self._check_acpi_availability()
        self._detect_hwmon_sensors()
        self._detect_model()

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

        sensor_id = f"0x{0x32 + fan_id - 1:02X}"
        result = self._acpi_call_real("0x14", ["0x0c", sensor_id])
        try:
            return max(0, min(100, int(result, 16)))
        except:
            return 0

    def get_power_mode(self) -> PowerMode:
        if self.manual_mode:
            return PowerMode.CUSTOM

        result = self._acpi_call_real("0x14", ["0x0b"])
        for mode in PowerMode:
            if mode.value[1] == result:
                return mode
        return PowerMode.BALANCED

    def get_g_mode_status(self) -> bool:
        result = self._acpi_call_real("0x25", ["0x02"])
        return result == "0x1"

    def set_power_mode(self, mode: PowerMode) -> bool:
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

        return True

    def set_fan_boost(self, fan_id: int, percentage: int) -> bool:
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

        return True

    def enable_g_mode(self) -> bool:
        self.logger.info("CONTROL: Enabling G-Mode")
        self.g_mode_active = True
        self._acpi_call_real("0x15", ["0x01", "0xab"])
        self._acpi_call_real("0x25", ["0x01", "0x01"])
        return True

    def disable_g_mode(self) -> bool:
        self.logger.info("CONTROL: Disabling G-Mode")
        self.g_mode_active = False
        self._acpi_call_real("0x15", ["0x01", self.current_mode.value[1]])
        self._acpi_call_real("0x25", ["0x01", "0x00"])
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
                        "fan2_boost": self.hardware.get_fan_boost(2)
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
                            "fan2_boost": self.hardware.get_fan_boost(2)
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
    print("Starting Dell G15 Controller Daemon...")
    print("⚠️  WARNING: This daemon runs with root privileges")
    print("⚠️  All operations are logged for security audit")

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