#!/usr/bin/env python3
"""Dell G15 Control Center daemon — hardware control via alienware_wmi."""

from __future__ import annotations

import json
import logging
import os
import select
import shutil
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import NamedTuple, Optional


PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
ALIENWARE_THERMAL_MODE = Path("/sys/devices/platform/alienware-wmi/thermal_mode")
PRODUCT_NAME = Path("/sys/class/dmi/id/product_name")
HWMON_DIR = Path("/sys/class/hwmon")
INPUT_DEVICES = Path("/proc/bus/input/devices")

CONFIG_DIR = Path("/etc/g15-daemon")
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_BACKUP = CONFIG_DIR / "config.json.bak"

SOCKET_PATH = "/tmp/g15-daemon.sock"

KEYBOARD_NAME = "AT Translated Set 2 keyboard"
KEY_PROG1 = 148
EV_KEY = 1

THERMAL_MODE_GMODE = "0xab"
THERMAL_MODE_OFF = "0x00"

VALID_PROFILES = {"quiet", "balanced", "performance"}


class PowerInfo(NamedTuple):
    label: str
    profile: str
    color: str


class PowerMode(Enum):
    QUIET = PowerInfo("Silencioso", "quiet", "#4CAF50")
    BALANCED = PowerInfo("Balanceado", "balanced", "#2196F3")
    PERFORMANCE = PowerInfo("Performance", "performance", "#FF9800")
    CUSTOM = PowerInfo("Personalizado", "inherit", "#9C27B0")


class GModeKeyListener:
    def __init__(self, callback):
        self.callback = callback
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.device_path: Optional[str] = None
        self.logger = logging.getLogger("g15.keylistener")

    def _find_keyboard(self) -> Optional[str]:
        try:
            content = INPUT_DEVICES.read_text()
        except OSError as e:
            self.logger.error(f"Cannot read {INPUT_DEVICES}: {e}")
            return None

        current_name = ""
        for line in content.splitlines():
            if line.startswith("N: Name="):
                current_name = line.split("=", 1)[1].strip('"')
            elif line.startswith("H: Handlers=") and KEYBOARD_NAME in current_name:
                for handler in line.split("=", 1)[1].split():
                    if handler.startswith("event"):
                        return f"/dev/input/{handler}"
        return None

    def _read_loop(self):
        try:
            with open(self.device_path, "rb") as device:
                while self.running:
                    ready, _, _ = select.select([device], [], [], 1.0)
                    if not ready:
                        continue
                    data = device.read(24)
                    if len(data) != 24:
                        continue
                    _, _, etype, code, value = struct.unpack("llHHi", data)
                    if etype == EV_KEY and code == KEY_PROG1 and value == 1:
                        threading.Thread(target=self.callback, daemon=True).start()
        except PermissionError:
            self.logger.error("Permission denied reading keyboard events")
        except Exception as e:
            self.logger.error(f"Error reading key events: {e}")

    def start(self):
        if self.running:
            return
        self.device_path = self._find_keyboard()
        if not self.device_path:
            self.logger.warning("Keyboard not found — G-Mode key disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


class ConfigManager:
    DEFAULT = {
        "power_mode": PowerMode.BALANCED.value.label,
        "g_mode": False,
        "fan_profiles": {"cpu_fan_boost": 0, "gpu_fan_boost": 0},
        "auto_apply": True,
        "version": "1.0",
    }

    def __init__(self):
        self.logger = logging.getLogger("g15.config")
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_DIR.chmod(0o700)
        except OSError as e:
            self.logger.error(f"Cannot create {CONFIG_DIR}: {e}")

    def load(self) -> dict:
        if not CONFIG_FILE.exists():
            self.save(self.DEFAULT)
            return self.DEFAULT.copy()

        try:
            config = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError as e:
            self.logger.error(f"Config corrupted: {e}")
            if CONFIG_BACKUP.exists():
                shutil.copy2(CONFIG_BACKUP, CONFIG_FILE)
                return self.load()
            return self.DEFAULT.copy()
        except OSError as e:
            self.logger.error(f"Cannot read config: {e}")
            return self.DEFAULT.copy()

        if not self._is_valid(config):
            self.logger.warning("Invalid config; using defaults")
            return self.DEFAULT.copy()
        return config

    def save(self, config: dict) -> bool:
        if not self._is_valid(config):
            self.logger.error("Refusing to save invalid config")
            return False

        config["last_saved"] = datetime.now().isoformat()
        tmp_path: Optional[str] = None
        try:
            if CONFIG_FILE.exists():
                shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=CONFIG_DIR, delete=False
            ) as tmp:
                json.dump(config, tmp, indent=2)
                tmp_path = tmp.name
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, CONFIG_FILE)
            return True
        except OSError as e:
            self.logger.error(f"Failed to save config: {e}")
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False

    @staticmethod
    def _is_valid(config: dict) -> bool:
        if not all(k in config for k in ("power_mode", "g_mode", "fan_profiles")):
            return False
        if config["power_mode"] not in {m.value.label for m in PowerMode}:
            return False
        if not isinstance(config["g_mode"], bool):
            return False
        for key in ("cpu_fan_boost", "gpu_fan_boost"):
            v = config["fan_profiles"].get(key)
            if v is not None and (not isinstance(v, int) or not 0 <= v <= 100):
                return False
        return True


class HardwareController:
    """Reads sensors and drives Dell G15 hardware via alienware_wmi."""

    def __init__(self):
        self.logger = logging.getLogger("g15.hardware")
        self.config_manager = ConfigManager()

        self.current_mode: PowerMode = PowerMode.BALANCED
        self.g_mode_active: bool = False
        self.current_fan_boosts: dict = {1: 0, 2: 0}
        self.manual_fan_control: dict = {1: False, 2: False}
        self.pre_gmode_state: Optional[dict] = None

        self.hwmon_temps: dict = {}
        self.hwmon_fans: dict = {}
        self.hwmon_fan_boosts: dict = {}

        if os.geteuid() != 0:
            self.logger.critical("Daemon must run as root")
            sys.exit(1)

        self._detect_hwmon()
        self.model = self._detect_model()
        self._load_and_apply_config()

    def _detect_hwmon(self):
        # alienware_wmi is the canonical interface for G15: writable fanN_boost
        # plus labeled CPU/GPU sensors. dell_smm/dell_ddv kept as sensor-only
        # fallback when alienware_wmi isn't loaded.
        sensor_fallbacks = ("dell_smm", "dell_ddv")

        for hwmon in sorted(HWMON_DIR.glob("hwmon*")):
            name_file = hwmon / "name"
            try:
                name = name_file.read_text().strip()
            except OSError:
                continue

            if name == "alienware_wmi":
                self._index_hwmon(hwmon, with_boost=True)
            elif name in sensor_fallbacks and not self.hwmon_temps:
                self._index_hwmon(hwmon, with_boost=False)

        if not self.hwmon_fan_boosts:
            self.logger.warning(
                "alienware_wmi fan boost controls not found — "
                "fan control will be unavailable"
            )

    def _index_hwmon(self, hwmon: Path, with_boost: bool):
        for path in hwmon.glob("temp*_input"):
            try:
                idx = int(path.name[4:].split("_", 1)[0])
            except ValueError:
                continue
            self.hwmon_temps.setdefault(idx, path)

        for path in hwmon.glob("fan*_input"):
            try:
                idx = int(path.name[3:].split("_", 1)[0])
            except ValueError:
                continue
            self.hwmon_fans.setdefault(idx, path)
            if with_boost:
                boost = hwmon / f"fan{idx}_boost"
                if boost.exists():
                    self.hwmon_fan_boosts.setdefault(idx, boost)

    @staticmethod
    def _detect_model() -> str:
        try:
            return PRODUCT_NAME.read_text().strip()
        except OSError:
            return "Unknown"

    @staticmethod
    def _read_sysfs(path: Path) -> str:
        try:
            return path.read_text().strip()
        except OSError:
            return ""

    def _write_sysfs(self, path: Path, value: str) -> bool:
        try:
            path.write_text(value)
            return True
        except OSError as e:
            self.logger.error(f"Write {path}={value} failed: {e}")
            return False

    @staticmethod
    def _read_int(path: Path) -> int:
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return 0

    def _load_and_apply_config(self):
        config = self.config_manager.load()
        if not config.get("auto_apply", True):
            return

        label = config.get("power_mode", PowerMode.BALANCED.value.label)
        for mode in PowerMode:
            if mode.value.label == label:
                self.set_power_mode(mode, save_config=False)
                break

        if config.get("g_mode"):
            self.enable_g_mode(save_config=False)

        if label == PowerMode.CUSTOM.value.label:
            fan_profiles = config.get("fan_profiles", {})
            for fan_id in (1, 2):
                key = "cpu" if fan_id == 1 else "gpu"
                if fan_profiles.get(f"{key}_manual"):
                    self.set_fan_boost(
                        fan_id,
                        fan_profiles.get(f"{key}_fan_boost", 0),
                        save_config=False,
                    )

    def _save_config(self):
        self.config_manager.save({
            "power_mode": self.current_mode.value.label,
            "g_mode": self.g_mode_active,
            "fan_profiles": {
                "cpu_fan_boost": self.current_fan_boosts.get(1, 0),
                "gpu_fan_boost": self.current_fan_boosts.get(2, 0),
                "cpu_manual": self.manual_fan_control.get(1, False),
                "gpu_manual": self.manual_fan_control.get(2, False),
            },
            "auto_apply": True,
            "version": "1.0",
        })

    def get_cpu_temp(self) -> int:
        if 1 not in self.hwmon_temps:
            return 0
        return self._read_int(self.hwmon_temps[1]) // 1000

    def get_gpu_temp(self) -> int:
        if 2 not in self.hwmon_temps:
            return 0
        return self._read_int(self.hwmon_temps[2]) // 1000

    def get_fan_rpm(self, fan_id: int) -> int:
        if fan_id not in (1, 2) or fan_id not in self.hwmon_fans:
            return 0
        return self._read_int(self.hwmon_fans[fan_id])

    def get_fan_boost(self, fan_id: int) -> int:
        return self.current_fan_boosts.get(fan_id, 0)

    def get_power_mode(self) -> PowerMode:
        # CUSTOM has no sysfs representation — trust in-memory state.
        if self.current_mode == PowerMode.CUSTOM:
            return PowerMode.CUSTOM
        current = self._read_sysfs(PLATFORM_PROFILE)
        for mode in PowerMode:
            if mode == PowerMode.CUSTOM:
                continue
            if mode.value.profile == current:
                self.current_mode = mode
                return mode
        return self.current_mode

    def set_power_mode(self, mode: PowerMode, save_config: bool = True) -> bool:
        if mode == PowerMode.CUSTOM:
            current = self._read_sysfs(PLATFORM_PROFILE)
            profile = current if current in VALID_PROFILES else "balanced"
        else:
            profile = mode.value.profile

        self.logger.info(f"Setting power mode to {mode.value.label} ({profile})")

        # Re-applying the same profile can cause some Dell ECs to re-init the
        # thermal table and clobber fan boosts — skip when no-op.
        if self._read_sysfs(PLATFORM_PROFILE) == profile:
            success = True
        else:
            success = self._write_sysfs(PLATFORM_PROFILE, profile)

        if success:
            self.current_mode = mode
            if mode != PowerMode.CUSTOM:
                for fid in (1, 2):
                    if fid in self.hwmon_fan_boosts:
                        self._write_sysfs(self.hwmon_fan_boosts[fid], "0")
                self.current_fan_boosts = {1: 0, 2: 0}
                self.manual_fan_control = {1: False, 2: False}

        if save_config:
            self._save_config()
        return success

    def set_fan_boost(self, fan_id: int, percentage: int, save_config: bool = True) -> bool:
        if fan_id not in (1, 2):
            return False
        if not isinstance(percentage, int) or not 0 <= percentage <= 100:
            return False
        if fan_id not in self.hwmon_fan_boosts:
            self.logger.error("alienware_wmi fan boost not available")
            return False

        self.logger.info(f"Setting fan {fan_id} boost to {percentage}%")
        success = self._write_sysfs(self.hwmon_fan_boosts[fan_id], str(percentage))

        self.current_fan_boosts[fan_id] = percentage
        self.manual_fan_control[fan_id] = percentage > 0

        if save_config:
            self._save_config()
        return success

    def enable_g_mode(self, save_config: bool = True) -> bool:
        self.logger.info("Enabling G-Mode")
        if not self.g_mode_active:
            self.pre_gmode_state = {
                "mode": self.current_mode,
                "fan_boosts": self.current_fan_boosts.copy(),
                "manual_control": self.manual_fan_control.copy(),
            }
        self.g_mode_active = True

        if ALIENWARE_THERMAL_MODE.exists():
            self._write_sysfs(ALIENWARE_THERMAL_MODE, THERMAL_MODE_GMODE)
        success = self._write_sysfs(PLATFORM_PROFILE, "performance")

        if save_config:
            self._save_config()
        return success

    def disable_g_mode(self, save_config: bool = True) -> bool:
        self.logger.info("Disabling G-Mode")
        self.g_mode_active = False

        if ALIENWARE_THERMAL_MODE.exists():
            self._write_sysfs(ALIENWARE_THERMAL_MODE, THERMAL_MODE_OFF)

        pre, self.pre_gmode_state = self.pre_gmode_state, None
        if pre:
            mode = pre["mode"]
            self.set_power_mode(mode, save_config=False)
            if mode == PowerMode.CUSTOM:
                saved_boosts = pre.get("fan_boosts", {})
                for fid in (1, 2):
                    self.set_fan_boost(
                        fid, saved_boosts.get(fid, 0), save_config=False
                    )
        else:
            self.set_power_mode(PowerMode.BALANCED, save_config=False)

        if save_config:
            self._save_config()
        return True

    def toggle_g_mode(self) -> bool:
        return self.disable_g_mode() if self.g_mode_active else self.enable_g_mode()


class DaemonServer:
    RATE_LIMIT_WINDOW = 10.0
    RATE_LIMIT_MAX = 50

    def __init__(self):
        self.logger = logging.getLogger("g15.daemon")
        self.hardware = HardwareController()
        self.running = False
        self.server_socket: Optional[socket.socket] = None
        self.client_requests: dict = {}
        self.gmode_listener = GModeKeyListener(self._on_gmode_key)

    def _on_gmode_key(self):
        try:
            self.hardware.toggle_g_mode()
        except Exception as e:
            self.logger.error(f"G-Mode key handler failed: {e}")

    def _rate_limit_ok(self, addr: str) -> bool:
        now = time.time()
        history = self.client_requests.setdefault(addr, [])
        history[:] = [t for t in history if now - t < self.RATE_LIMIT_WINDOW]
        if len(history) >= self.RATE_LIMIT_MAX:
            self.logger.warning(f"Rate limit exceeded: {addr}")
            return False
        history.append(now)
        return True

    def _status_data(self) -> dict:
        return {
            "model": self.hardware.model,
            "hwmon_available": bool(self.hardware.hwmon_fan_boosts),
            "g_mode_active": self.hardware.g_mode_active,
        }

    def _temp_data(self) -> dict:
        return {
            "cpu_temp": self.hardware.get_cpu_temp(),
            "gpu_temp": self.hardware.get_gpu_temp(),
        }

    def _fan_data(self) -> dict:
        hw = self.hardware
        return {
            "fan1_rpm": hw.get_fan_rpm(1),
            "fan2_rpm": hw.get_fan_rpm(2),
            "fan1_boost": hw.get_fan_boost(1),
            "fan2_boost": hw.get_fan_boost(2),
            "fan1_manual": hw.manual_fan_control.get(1, False),
            "fan2_manual": hw.manual_fan_control.get(2, False),
        }

    def _power_data(self) -> dict:
        return {
            "current_mode": self.hardware.get_power_mode().value.label,
            "g_mode": self.hardware.g_mode_active,
        }

    def _process(self, request: dict) -> dict:
        action = request.get("action")
        hw = self.hardware

        if action == "get_status":
            return {"status": "success", "data": self._status_data()}
        if action == "get_temps":
            return {"status": "success", "data": self._temp_data()}
        if action == "get_fans":
            return {"status": "success", "data": self._fan_data()}
        if action == "get_power_mode":
            return {"status": "success", "data": self._power_data()}
        if action == "get_all_data":
            return {
                "status": "success",
                "data": {
                    "temps": self._temp_data(),
                    "fans": self._fan_data(),
                    "power": self._power_data(),
                    "status": self._status_data(),
                },
            }
        if action == "set_power_mode":
            mode_map = {m.value.label: m for m in PowerMode}
            mode = mode_map.get(request.get("mode"))
            if mode is None:
                return {"status": "error", "message": "Invalid power mode"}
            return {"status": "success" if hw.set_power_mode(mode) else "error"}
        if action == "set_fan_boost":
            fan_id = request.get("fan_id")
            pct = request.get("percentage")
            if not isinstance(fan_id, int) or not isinstance(pct, int):
                return {"status": "error", "message": "Invalid parameters"}
            return {"status": "success" if hw.set_fan_boost(fan_id, pct) else "error"}
        if action == "toggle_g_mode":
            return {"status": "success" if hw.toggle_g_mode() else "error"}

        return {"status": "error", "message": "Unauthorized action"}

    def _handle_client(self, client_socket: socket.socket, addr):
        try:
            data = client_socket.recv(4096)
            if not data:
                return
            try:
                request = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                response = {"status": "error", "message": "Invalid JSON"}
            else:
                if not isinstance(request, dict) or "action" not in request:
                    response = {"status": "error", "message": "Missing action"}
                elif not self._rate_limit_ok(str(addr)):
                    response = {"status": "error", "message": "Rate limit exceeded"}
                else:
                    response = self._process(request)
            client_socket.send(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.logger.error(f"Client handling failed: {e}")
        finally:
            client_socket.close()

    def start(self):
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        self.server_socket.listen(5)
        self.running = True

        self.gmode_listener.start()
        self.logger.info(f"G15 Daemon listening on {SOCKET_PATH}")

        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
            except OSError:
                if self.running:
                    self.logger.error("Accept failed", exc_info=True)
                break
            threading.Thread(
                target=self._handle_client,
                args=(client_socket, addr),
                daemon=True,
            ).start()

    def stop(self):
        self.logger.info("Stopping G15 Daemon")
        self.running = False
        self.gmode_listener.stop()
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )


def main():
    setup_logging()
    logger = logging.getLogger("g15.daemon")
    logger.info("Starting Dell G15 Control Center daemon")

    server = DaemonServer()

    def shutdown(_signum, _frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    except Exception as e:
        logger.exception(f"Daemon crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
