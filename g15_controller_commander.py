#!/usr/bin/env python3

import sys
import os
import subprocess
import random
import time
import glob
from enum import Enum
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QSlider, QPushButton,
    QSystemTrayIcon, QMenu, QMessageBox, QFrame, QProgressBar,
    QGraphicsDropShadowEffect, QTabWidget
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSettings,
    QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QFont, QAction, QColor,
    QBrush, QPen, QLinearGradient, QRadialGradient
)


class PowerMode(Enum):
    QUIET = ("Quiet", "0xa3", "#4CAF50")
    BALANCED = ("Balanced", "0xa0", "#2196F3")
    PERFORMANCE = ("Performance", "0xa1", "#FF9800")
    CUSTOM = ("Custom", "0xa2", "#9C27B0")




class ACPIController:
    def __init__(self):
        self.acpi_call_path = "/proc/acpi/call"
        self.acpi_base = r"\_SB.AMWW.WMAX"
        self.current_mode = PowerMode.BALANCED
        self.g_mode_active = False
        self.manual_mode = False
        
        # Caminhos dos sensores hwmon (serão detectados automaticamente)
        self.hwmon_path = None
        self.hwmon_fans = {}
        self.hwmon_temps = {}

        # Verifica disponibilidade ACPI - obrigatório
        self._check_acpi_availability()
        
        # Detecta sensores hwmon Dell
        self._detect_hwmon_sensors()
        
        print("=== ACPI Mode: REAL HARDWARE ===")
        self._detect_model()

    def _check_acpi_availability(self):
        """Verifica se ACPI está disponível e temos permissão - obrigatório"""
        if not os.path.exists(self.acpi_call_path):
            print("ERROR: ACPI path not found. Dell G15 hardware not detected.")
            print("This application requires Dell G15 hardware with ACPI support.")
            sys.exit(1)

        if os.geteuid() != 0:
            print("ERROR: This application requires root privileges.")
            print("Please run with: sudo python3 g15_controller_commander.py")
            sys.exit(1)

        # Tenta carregar módulo
        try:
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            if 'acpi_call' not in result.stdout:
                print("Loading acpi_call module...")
                result = subprocess.run(['modprobe', 'acpi_call'], capture_output=True, text=True)
                if result.returncode != 0:
                    print("ERROR: Failed to load acpi_call module.")
                    print("Please install acpi_call-dkms package.")
                    sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to check/load acpi_call module: {e}")
            sys.exit(1)

        # Testa escrita
        try:
            with open(self.acpi_call_path, 'w') as f:
                f.write("test")
            print("ACPI interface is accessible")
        except Exception as e:
            print(f"ERROR: Cannot write to ACPI interface: {e}")
            print("Please ensure you have root privileges and acpi_call module is loaded.")
            sys.exit(1)

    def _detect_hwmon_sensors(self):
        """Detecta automaticamente sensores hwmon Dell"""
        dell_hwmon_names = ['dell_smm', 'dell_ddv']
        
        for hwmon_dir in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                name_file = os.path.join(hwmon_dir, 'name')
                if os.path.exists(name_file):
                    with open(name_file, 'r') as f:
                        hwmon_name = f.read().strip()
                    
                    if hwmon_name in dell_hwmon_names:
                        self.hwmon_path = hwmon_dir
                        print(f"Found Dell hwmon: {hwmon_name} at {hwmon_dir}")
                        
                        # Detecta sensores de temperatura disponíveis
                        for temp_file in glob.glob(os.path.join(hwmon_dir, 'temp*_input')):
                            temp_num = temp_file.split('temp')[1].split('_')[0]
                            self.hwmon_temps[int(temp_num)] = temp_file
                        
                        # Detecta sensores de ventoinha disponíveis  
                        for fan_file in glob.glob(os.path.join(hwmon_dir, 'fan*_input')):
                            fan_num = fan_file.split('fan')[1].split('_')[0]
                            self.hwmon_fans[int(fan_num)] = fan_file
                            
                        print(f"Detected temperatures: {list(self.hwmon_temps.keys())}")
                        print(f"Detected fans: {list(self.hwmon_fans.keys())}")
                        return
            except Exception as e:
                continue
        
        print("WARNING: No Dell hwmon sensors found, using ACPI only")
    
    def _detect_model(self):
        try:
            result = self._acpi_call_real("0x1a", ["0x02", "0x02"])
            if result and result != "0x0":
                model_map = {
                    "0x1": "5511", "0x2": "5515", "0x3": "5520",
                    "0x4": "5525", "0x5": "5530", "0x6": "5535"
                }
                self.model = model_map.get(result, "Unknown")
                print(f"Detected Dell G15 {self.model}")
            else:
                self.model = "Unknown"
        except:
            self.model = "Unknown"

    def _read_hwmon_sensor(self, sensor_path: str) -> int:
        """Lê valor de um sensor hwmon"""
        try:
            with open(sensor_path, 'r') as f:
                value = int(f.read().strip())
                return value
        except Exception as e:
            print(f"Error reading hwmon sensor {sensor_path}: {e}")
            return 0
    
    def _acpi_call_real(self, wmi_code: str, args: list = None) -> str:
        """Chamada ACPI real para hardware"""
        if args is None:
            args = []

        while len(args) < 4:
            args.append("0x00")

        args_str = ', '.join(str(a) for a in args)
        command = f"{self.acpi_base} 0 {wmi_code} {{{args_str}}}"

        try:
            with open(self.acpi_call_path, 'w') as f:
                f.write(command)

            with open(self.acpi_call_path, 'r') as f:
                result = f.read().strip()

            # Parse result
            if result.startswith("{"):
                result = result.strip("{}").split(",")[0].strip()

            return result if result else "0x0"
        except Exception as e:
            print(f"ACPI error: {e}")
            return "0x0"

    def get_cpu_temp(self) -> int:
        # Primeiro tenta hwmon (mais confiável)
        if self.hwmon_path and 1 in self.hwmon_temps:
            temp_millidegrees = self._read_hwmon_sensor(self.hwmon_temps[1])
            if temp_millidegrees > 0:
                temp_celsius = temp_millidegrees // 1000
                if 0 <= temp_celsius <= 120:
                    return temp_celsius
        
        # Fallback para ACPI
        result = self._acpi_call_real("0x14", ["0x04", "0x01"])
        try:
            temp = int(result, 16)
            if 0 <= temp <= 120:
                return temp
        except:
            pass
        
        return 45

    def get_gpu_temp(self) -> int:
        # Primeiro tenta hwmon (mais confiável)
        if self.hwmon_path and 2 in self.hwmon_temps:
            temp_millidegrees = self._read_hwmon_sensor(self.hwmon_temps[2])
            if temp_millidegrees > 0:
                temp_celsius = temp_millidegrees // 1000
                if 0 <= temp_celsius <= 120:
                    return temp_celsius
        
        # Fallback para ACPI
        result = self._acpi_call_real("0x14", ["0x04", "0x02"])
        try:
            temp = int(result, 16)
            if 0 <= temp <= 120:
                return temp
        except:
            pass
        
        return 50

    def get_fan_rpm(self, fan_id: int) -> int:
        # Primeiro tenta hwmon (mais confiável)
        if self.hwmon_path and fan_id in self.hwmon_fans:
            rpm = self._read_hwmon_sensor(self.hwmon_fans[fan_id])
            if 0 <= rpm <= 10000:
                return rpm
        
        # Fallback para ACPI
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
        self.current_mode = mode
        if mode == PowerMode.CUSTOM:
            self.manual_mode = True
        else:
            self.manual_mode = False
            self._acpi_call_real("0x15", ["0x01", mode.value[1]])
        print(f"Power mode set to: {mode.value[0]}")
        return True

    def set_fan_boost(self, fan_id: int, percentage: int) -> bool:
        sensor_id = f"0x{0x32 + fan_id - 1:02X}"
        hex_value = f"0x{percentage:02X}"
        self._acpi_call_real("0x15", ["0x02", sensor_id, hex_value])
        print(f"Fan {fan_id} boost set to {percentage}%")
        return True

    def enable_g_mode(self) -> bool:
        self.g_mode_active = True
        self._acpi_call_real("0x15", ["0x01", "0xab"])
        self._acpi_call_real("0x25", ["0x01", "0x01"])
        print("G-Mode ENABLED")
        return True

    def disable_g_mode(self) -> bool:
        self.g_mode_active = False
        self._acpi_call_real("0x15", ["0x01", self.current_mode.value[1]])
        self._acpi_call_real("0x25", ["0x01", "0x00"])
        print("G-Mode DISABLED")
        return True

    def toggle_g_mode(self) -> bool:
        if self.g_mode_active:
            return self.disable_g_mode()
        else:
            return self.enable_g_mode()


class SensorMonitor(QThread):
    data_updated = pyqtSignal(dict)

    def __init__(self, acpi_controller):
        super().__init__()
        self.acpi = acpi_controller
        self.running = True

    def run(self):
        update_count = 0
        while self.running:
            try:
                update_count += 1

                data = {
                    'cpu_temp': self.acpi.get_cpu_temp(),
                    'gpu_temp': self.acpi.get_gpu_temp(),
                    'fan1_rpm': self.acpi.get_fan_rpm(1),
                    'fan2_rpm': self.acpi.get_fan_rpm(2),
                    'fan1_boost': self.acpi.get_fan_boost(1),
                    'fan2_boost': self.acpi.get_fan_boost(2),
                    'power_mode': self.acpi.get_power_mode(),
                    'g_mode': self.acpi.g_mode_active
                }

                self.data_updated.emit(data)

                print(f"[{update_count:04d}] CPU={data['cpu_temp']}°C, GPU={data['gpu_temp']}°C, "
                      f"Fan1={data['fan1_rpm']} RPM, Fan2={data['fan2_rpm']} RPM, "
                      f"G-Mode={'ON' if data['g_mode'] else 'OFF'}")

            except Exception as e:
                print(f"Monitor error: {e}")

            self.msleep(1000)

    def stop(self):
        self.running = False
        self.wait()


class ThermalCard(QFrame):
    def __init__(self, title: str, unit: str = "°C", max_value: int = 100):
        super().__init__()
        self.title = title
        self.unit = unit
        self.max_value = max_value
        self.current_value = 0
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 2px solid #E0E0E0;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel(self.title)
        title_label.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #666666;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel(f"--{self.unit}")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setStyleSheet("""
            font-size: 36px;
            font-weight: bold;
            color: #2196F3;
            padding: 5px;
        """)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.max_value)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E0E0E0;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:0.5 #FFC107, stop:1 #F44336);
                border-radius: 3px;
            }
        """)

        self.status_label = QLabel("--")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 11px;
            font-weight: 500;
            color: #4CAF50;
            padding: 3px 8px;
            background: #E8F5E9;
            border-radius: 8px;
        """)

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)

    def update_value(self, value: int):
        self.current_value = value
        self.value_label.setText(f"{value}{self.unit}")
        self.progress_bar.setValue(value)

        color, status, bg = self.get_status_style(value)
        self.value_label.setStyleSheet(f"""
            font-size: 36px;
            font-weight: bold;
            color: {color};
            padding: 5px;
        """)
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 500;
            color: {color};
            padding: 3px 8px;
            background: {bg};
            border-radius: 8px;
        """)

    def get_status_style(self, value):
        if self.unit == "°C":
            if value < 50:
                return "#4CAF50", "Cool", "#E8F5E9"
            elif value < 70:
                return "#FFC107", "Normal", "#FFF8E1"
            elif value < 85:
                return "#FF9800", "Warm", "#FFF3E0"
            else:
                return "#F44336", "Hot", "#FFEBEE"
        else:
            if value < 2000:
                return "#2196F3", "Low", "#E3F2FD"
            elif value < 4000:
                return "#4CAF50", "Normal", "#E8F5E9"
            else:
                return "#FF9800", "High", "#FFF3E0"


class FanControlCard(QFrame):
    boost_changed = pyqtSignal(int, int)

    def __init__(self, fan_id: int, title: str):
        super().__init__()
        self.fan_id = fan_id
        self.title = title
        self.manual_enabled = False
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 2px solid #E0E0E0;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        header_layout = QHBoxLayout()

        title_label = QLabel(self.title)
        title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #333333;
        """)

        self.rpm_label = QLabel("0 RPM")
        self.rpm_label.setStyleSheet("""
            font-size: 12px;
            font-weight: 500;
            color: #666666;
            padding: 3px 8px;
            background: #F5F5F5;
            border-radius: 6px;
        """)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.rpm_label)

        self.manual_toggle = QPushButton("Manual OFF")
        self.manual_toggle.setCheckable(True)
        self.manual_toggle.setFixedHeight(32)
        self.manual_toggle.clicked.connect(self.toggle_manual)
        self.update_manual_button_style(False)

        control_widget = QWidget()
        control_widget.setStyleSheet("""
            QWidget {
                background: #F8F9FA;
                border-radius: 8px;
            }
        """)
        control_layout = QVBoxLayout(control_widget)
        control_layout.setContentsMargins(12, 12, 12, 12)
        control_layout.setSpacing(8)

        slider_layout = QHBoxLayout()

        self.boost_slider = QSlider(Qt.Orientation.Horizontal)
        self.boost_slider.setRange(0, 100)
        self.boost_slider.setValue(0)
        self.boost_slider.setEnabled(False)
        self.boost_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #E0E0E0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                background: white;
                border: 2px solid #2196F3;
                border-radius: 8px;
                margin: -5px 0;
            }
            QSlider::sub-page:horizontal {
                background: #2196F3;
                border-radius: 3px;
            }
            QSlider::handle:horizontal:disabled {
                background: #F0F0F0;
                border: 2px solid #CCCCCC;
            }
        """)
        self.boost_slider.valueChanged.connect(self.update_boost_label)
        self.boost_slider.sliderReleased.connect(self.apply_boost)

        self.boost_label = QLabel("0%")
        self.boost_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.boost_label.setFixedWidth(50)
        self.boost_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #2196F3;
            background: white;
            padding: 5px;
            border: 1px solid #E0E0E0;
            border-radius: 6px;
        """)

        slider_layout.addWidget(self.boost_slider)
        slider_layout.addWidget(self.boost_label)

        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)

        for value in [0, 25, 50, 75, 100]:
            btn = QPushButton(f"{value}%")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, v=value: self.set_preset(v))
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    font-weight: 500;
                    background: white;
                    color: #666666;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #2196F3;
                    color: white;
                    border: 1px solid #2196F3;
                }
            """)
            preset_layout.addWidget(btn)

        control_layout.addLayout(slider_layout)
        control_layout.addLayout(preset_layout)

        layout.addLayout(header_layout)
        layout.addWidget(self.manual_toggle)
        layout.addWidget(control_widget)

    def update_manual_button_style(self, enabled):
        if enabled:
            self.manual_toggle.setStyleSheet("""
                QPushButton {
                    font-size: 12px;
                    font-weight: 600;
                    background: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #1976D2;
                }
            """)
        else:
            self.manual_toggle.setStyleSheet("""
                QPushButton {
                    font-size: 12px;
                    font-weight: 500;
                    background: white;
                    color: #666666;
                    border: 2px solid #E0E0E0;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #F5F5F5;
                    border: 2px solid #2196F3;
                    color: #2196F3;
                }
            """)

    def toggle_manual(self):
        self.manual_enabled = self.manual_toggle.isChecked()
        self.manual_toggle.setText("Manual ON" if self.manual_enabled else "Manual OFF")
        self.update_manual_button_style(self.manual_enabled)
        self.boost_slider.setEnabled(self.manual_enabled)

        if not self.manual_enabled:
            self.boost_slider.setValue(0)
            self.boost_changed.emit(self.fan_id, 0)

    def update_boost_label(self, value):
        self.boost_label.setText(f"{value}%")

    def apply_boost(self):
        if self.manual_enabled:
            value = self.boost_slider.value()
            self.boost_changed.emit(self.fan_id, value)

    def set_preset(self, value):
        if self.manual_enabled:
            self.boost_slider.setValue(value)
            self.apply_boost()

    def update_rpm(self, rpm: int):
        self.rpm_label.setText(f"{rpm:,} RPM")

    def update_boost(self, boost: int):
        if not self.manual_enabled:
            self.boost_slider.setValue(boost)


class GModeButton(QPushButton):
    toggled_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__("G-MODE OFF")
        self.setCheckable(True)
        self.setFixedSize(180, 50)
        self.is_on = False
        self.update_style(False)
        self.clicked.connect(self.on_click)

    def on_click(self):
        self.is_on = not self.is_on
        self.update_display()
        self.toggled_signal.emit(self.is_on)

    def update_display(self):
        self.setText("G-MODE ON" if self.is_on else "G-MODE OFF")
        self.update_style(self.is_on)

    def set_state(self, is_on):
        if self.is_on != is_on:
            self.is_on = is_on
            self.setChecked(is_on)
            self.update_display()

    def update_style(self, is_on):
        if is_on:
            self.setStyleSheet("""
                QPushButton {
                    font-size: 16px;
                    font-weight: bold;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #FF4444, stop:1 #CC0000);
                    color: white;
                    border: none;
                    border-radius: 25px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #FF6666, stop:1 #FF0000);
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    font-size: 16px;
                    font-weight: bold;
                    background: white;
                    color: #666666;
                    border: 3px solid #E0E0E0;
                    border-radius: 25px;
                }
                QPushButton:hover {
                    background: #F5F5F5;
                    border: 3px solid #FF4444;
                    color: #FF4444;
                }
            """)


class PowerModeSelector(QFrame):
    mode_changed = pyqtSignal(PowerMode)

    def __init__(self):
        super().__init__()
        self.mode_buttons = {}
        self.current_mode = PowerMode.BALANCED
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 2px solid #E0E0E0;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("Power Mode")
        title.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            color: #333333;
            padding-bottom: 8px;
        """)
        layout.addWidget(title)

        for mode in PowerMode:
            btn = QPushButton(f"  {mode.value[0]}")
            btn.setCheckable(True)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda checked, m=mode: self.select_mode(m))
            self.mode_buttons[mode] = btn
            self.update_button_style(btn, mode, False)
            layout.addWidget(btn)

    def update_button_style(self, btn, mode, selected):
        color = mode.value[2]
        if selected:
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 13px;
                    font-weight: 600;
                    text-align: left;
                    padding-left: 15px;
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: 6px;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 13px;
                    font-weight: 500;
                    text-align: left;
                    padding-left: 15px;
                    background: white;
                    color: #666666;
                    border: 2px solid #E0E0E0;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background: #F5F5F5;
                    color: {color};
                    border: 2px solid {color};
                }}
            """)

    def select_mode(self, mode: PowerMode):
        self.current_mode = mode
        for m, btn in self.mode_buttons.items():
            selected = (m == mode)
            btn.setChecked(selected)
            self.update_button_style(btn, m, selected)
        self.mode_changed.emit(mode)

    def set_mode(self, mode: PowerMode):
        if mode in self.mode_buttons:
            for m, btn in self.mode_buttons.items():
                selected = (m == mode)
                btn.setChecked(selected)
                self.update_button_style(btn, m, selected)
            self.current_mode = mode


class SystemTrayIcon(QSystemTrayIcon):
    toggle_g_mode = pyqtSignal()
    show_window = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.g_mode_active = False
        self.cpu_temp = 0
        self.gpu_temp = 0
        self.create_icon()
        self.create_menu()

    def create_icon(self):
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = size // 2
        radius = 20

        if self.g_mode_active:
            gradient = QRadialGradient(center, center, radius)
            gradient.setColorAt(0, QColor("#FF6666"))
            gradient.setColorAt(1, QColor("#CC0000"))
            painter.setBrush(QBrush(gradient))
        else:
            gradient = QRadialGradient(center, center, radius)
            gradient.setColorAt(0, QColor("#6699FF"))
            gradient.setColorAt(1, QColor("#3366CC"))
            painter.setBrush(QBrush(gradient))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.setFont(QFont("Arial", 14 if self.g_mode_active else 11, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "G" if self.g_mode_active else "FAN")

        if self.g_mode_active:
            painter.setBrush(Qt.GlobalColor.white)
            painter.setPen(Qt.PenStyle.NoPen)
            dot_size = 6
            positions = [
                (8, 8), (size - 8 - dot_size, 8),
                (8, size - 8 - dot_size), (size - 8 - dot_size, size - 8 - dot_size)
            ]
            for x, y in positions:
                painter.drawEllipse(x, y, dot_size, dot_size)

        painter.end()
        self.setIcon(QIcon(pixmap))

    def create_menu(self):
        menu = QMenu()

        self.g_mode_action = QAction("Toggle G-Mode", self)
        self.g_mode_action.triggered.connect(self.toggle_g_mode.emit)
        menu.addAction(self.g_mode_action)

        menu.addSeparator()

        self.temp_action = QAction("CPU: --°C | GPU: --°C", self)
        self.temp_action.setEnabled(False)
        menu.addAction(self.temp_action)

        menu.addSeparator()

        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_window.emit)
        menu.addAction(show_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def update_status(self, g_mode: bool, cpu_temp: int, gpu_temp: int):
        self.g_mode_active = g_mode
        self.cpu_temp = cpu_temp
        self.gpu_temp = gpu_temp

        self.create_icon()

        status = "ACTIVE" if g_mode else "INACTIVE"
        self.setToolTip(f"Dell G15 Controller\nG-Mode: {status}\nCPU: {cpu_temp}°C | GPU: {gpu_temp}°C")

        self.temp_action.setText(f"CPU: {cpu_temp}°C | GPU: {gpu_temp}°C")
        self.g_mode_action.setText(f"Disable G-Mode" if g_mode else "Enable G-Mode")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Força tema consistente
        QApplication.setStyle('Fusion')

        self.acpi = ACPIController()
        self.settings = None  # Desabilita QSettings para evitar diferenças visuais
        self.custom_message_shown = False

        self.setup_ui()
        self.setup_monitoring()
        self.setup_tray()
        self.check_privileges()

    def setup_ui(self):
        self.setWindowTitle("Dell G15 Control Center")
        self.setFixedSize(1000, 600)

        self.setStyleSheet("""
            QMainWindow {
                background: #F5F6FA;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        title = QLabel("Dell G15 Control Center")
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2C3E50;
        """)

        model_label = QLabel(f"Model: {self.acpi.model}")
        model_label.setStyleSheet("""
            font-size: 12px;
            color: #666666;
            padding: 4px 10px;
            background: white;
            border: 1px solid #E0E0E0;
            border-radius: 12px;
        """)

        mode_label = QLabel("REAL HARDWARE")
        color = "#27AE60"
        mode_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: bold;
            color: {color};
            padding: 4px 10px;
            background: white;
            border: 2px solid {color};
            border-radius: 12px;
        """)

        self.g_mode_button = GModeButton()
        self.g_mode_button.toggled_signal.connect(self.toggle_g_mode)

        header_layout.addWidget(title)
        header_layout.addWidget(model_label)
        header_layout.addWidget(mode_label)
        header_layout.addStretch()
        header_layout.addWidget(self.g_mode_button)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                background: transparent;
                border: none;
            }
            QTabBar::tab {
                background: white;
                color: #666666;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                color: #2C3E50;
                border-bottom: 2px solid #2196F3;
            }
        """)

        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        monitor_layout.setSpacing(15)

        thermal_section = QFrame()
        thermal_section.setStyleSheet("QFrame { background: transparent; }")
        thermal_layout = QHBoxLayout(thermal_section)
        thermal_layout.setSpacing(15)

        self.cpu_thermal = ThermalCard("CPU Temperature", "°C", 100)
        self.gpu_thermal = ThermalCard("GPU Temperature", "°C", 100)
        self.fan1_rpm = ThermalCard("CPU Fan Speed", " RPM", 6000)
        self.fan2_rpm = ThermalCard("GPU Fan Speed", " RPM", 6000)

        thermal_layout.addWidget(self.cpu_thermal)
        thermal_layout.addWidget(self.gpu_thermal)
        thermal_layout.addWidget(self.fan1_rpm)
        thermal_layout.addWidget(self.fan2_rpm)

        fan_section = QFrame()
        fan_section.setStyleSheet("QFrame { background: transparent; }")
        fan_layout = QHBoxLayout(fan_section)
        fan_layout.setSpacing(15)

        self.fan1_control = FanControlCard(1, "CPU Fan Control")
        self.fan2_control = FanControlCard(2, "GPU Fan Control")

        self.fan1_control.boost_changed.connect(self.on_fan_boost_changed)
        self.fan2_control.boost_changed.connect(self.on_fan_boost_changed)

        fan_layout.addWidget(self.fan1_control)
        fan_layout.addWidget(self.fan2_control)
        fan_layout.addStretch()

        monitor_layout.addWidget(thermal_section)
        monitor_layout.addWidget(fan_section)
        monitor_layout.addStretch()

        settings_tab = QWidget()
        settings_layout = QHBoxLayout(settings_tab)
        settings_layout.setSpacing(15)

        self.power_selector = PowerModeSelector()
        self.power_selector.mode_changed.connect(self.on_mode_changed)

        info_panel = QFrame()
        info_panel.setStyleSheet("""
            QFrame {
                background: white;
                border: 2px solid #E0E0E0;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        info_layout = QVBoxLayout(info_panel)

        info_text = QLabel("""
<b>Instructions:</b><br><br>
• <b>G-Mode:</b> Toggle for maximum cooling<br>
• <b>Power Modes:</b> Choose your thermal profile<br>
• <b>Manual Control:</b> Select Custom mode first<br>
• <b>System Tray:</b> Double-click to show/hide<br><br>
<b>Status:</b> Real Hardware""")

        info_text.setStyleSheet("""
            font-size: 12px;
            color: #666666;
            line-height: 1.5;
        """)
        info_text.setWordWrap(True)

        info_layout.addWidget(info_text)
        info_layout.addStretch()

        settings_layout.addWidget(self.power_selector)
        settings_layout.addWidget(info_panel, 1)

        tabs.addTab(monitor_tab, "Monitor")
        tabs.addTab(settings_tab, "Settings")

        main_layout.addLayout(header_layout)
        main_layout.addWidget(tabs)

    def setup_monitoring(self):
        self.monitor = SensorMonitor(self.acpi)
        self.monitor.data_updated.connect(self.update_sensor_data)
        self.monitor.start()

    def setup_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = SystemTrayIcon()
            self.tray.toggle_g_mode.connect(self.toggle_g_mode)
            self.tray.show_window.connect(self.show_and_raise)
            self.tray.quit_app.connect(self.quit_application)
            self.tray.activated.connect(self.on_tray_activated)
            self.tray.show()

    def check_privileges(self):
        pass

    def update_sensor_data(self, data):
        self.cpu_thermal.update_value(data['cpu_temp'])
        self.gpu_thermal.update_value(data['gpu_temp'])
        self.fan1_rpm.update_value(data['fan1_rpm'])
        self.fan2_rpm.update_value(data['fan2_rpm'])

        self.fan1_control.update_rpm(data['fan1_rpm'])
        self.fan2_control.update_rpm(data['fan2_rpm'])
        self.fan1_control.update_boost(data['fan1_boost'])
        self.fan2_control.update_boost(data['fan2_boost'])

        self.power_selector.set_mode(data['power_mode'])
        self.g_mode_button.set_state(data['g_mode'])

        if hasattr(self, 'tray'):
            self.tray.update_status(data['g_mode'], data['cpu_temp'], data['gpu_temp'])

    def toggle_g_mode(self, state=None):
        self.acpi.toggle_g_mode()

    def on_mode_changed(self, mode: PowerMode):
        self.acpi.set_power_mode(mode)

        if mode == PowerMode.CUSTOM:
            if not self.custom_message_shown:
                self.custom_message_shown = True
                QMessageBox.information(self, "Custom Mode",
                    "Custom mode activated.\nEnable Manual control in fan cards.")
        else:
            self.fan1_control.manual_toggle.setChecked(False)
            self.fan1_control.toggle_manual()
            self.fan2_control.manual_toggle.setChecked(False)
            self.fan2_control.toggle_manual()

    def on_fan_boost_changed(self, fan_id: int, boost: int):
        if self.acpi.current_mode != PowerMode.CUSTOM:
            QMessageBox.warning(self, "Mode Warning",
                "Please select Custom mode first.")
            return

        self.acpi.set_fan_boost(fan_id, boost)

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_raise()

    def quit_application(self):
        if self.monitor:
            self.monitor.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if hasattr(self, 'tray') and self.tray.isVisible():
            self.hide()
            self.tray.showMessage(
                "Dell G15 Controller",
                "Minimized to system tray",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()
        else:
            if self.monitor:
                self.monitor.stop()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Força tema consistente
    app.setStyle('Fusion')

    # Fonte padrão
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    print("=" * 60)
    print(" Dell G15 Control Center - v3.0 FINAL")
    print("=" * 60)
    print("Mode: REAL HARDWARE")
    print("Root: YES")
    print("Model: " + window.acpi.model)
    print("=" * 60)
    print("Monitoring started - values should update every second...")
    print("=" * 60)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()