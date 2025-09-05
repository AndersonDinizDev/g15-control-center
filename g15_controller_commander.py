#!/usr/bin/env python3

import sys
import os
import subprocess
import random
import time
import glob
import json
import socket
import argparse
from pathlib import Path
from enum import Enum
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QSlider, QPushButton,
    QSystemTrayIcon, QMenu, QMessageBox, QFrame, QProgressBar,
    QGraphicsDropShadowEffect, QTabWidget, QCheckBox
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
    QUIET = ("Silencioso", "0xa3", "#4CAF50")
    BALANCED = ("Balanceado", "0xa0", "#2196F3")
    PERFORMANCE = ("Performance", "0xa1", "#FF9800")
    CUSTOM = ("Personalizado", "0xa2", "#9C27B0")


class G15DaemonClient:
    def __init__(self):
        self.socket_path = "/tmp/g15-daemon.sock"
        self.daemon_available = self._check_daemon()
        self.session_token = None
        self._cached_data = None
        self._last_update = 0
        self._cache_timeout = 1.0

        if self.daemon_available:
            self._authenticate()
            print("=== G15 Client Mode: Connected to Daemon ===")
        else:
            print("=== G15 Client Mode: Daemon not available ===")

    def _check_daemon(self) -> bool:
        try:
            if not os.path.exists(self.socket_path):
                return False

            try:
                stat_info = os.stat(self.socket_path)
            except Exception as e:
                return False

            test_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            test_socket.settimeout(1.0)
            test_socket.connect(self.socket_path)
            test_socket.close()
            return True
        except Exception as e:
            return False

    def _authenticate(self):
        try:
            response = self._send_request({"action": "authenticate"})
            if response.get("status") == "success":
                self.session_token = response.get("token")
        except:
            self.daemon_available = False

    def _send_request(self, request_data: dict) -> dict:
        if not self.daemon_available:
            return {"status": "error", "message": "Daemon not available"}

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            client_socket.connect(self.socket_path)

            if self.session_token and "token" not in request_data:
                request_data["token"] = self.session_token

            request_json = json.dumps(request_data)
            client_socket.send(request_json.encode('utf-8'))

            response_data = client_socket.recv(4096)
            client_socket.close()

            return json.loads(response_data.decode('utf-8'))

        except Exception as e:
            print(f"Error communicating with daemon: {e}")
            self.daemon_available = False
            return {"status": "error", "message": str(e)}

    def _get_all_data(self) -> dict:
        import time

        current_time = time.time()
        if (self._cached_data is None or
            current_time - self._last_update > self._cache_timeout):

            response = self._send_request({"action": "get_all_data"})
            if response.get("status") == "success":
                self._cached_data = response.get("data", {})
                self._last_update = current_time
            else:
                self._cached_data = {
                    "temps": {"cpu_temp": 45, "gpu_temp": 50},
                    "fans": {"fan1_rpm": 2500, "fan2_rpm": 2300, "fan1_boost": 0, "fan2_boost": 0},
                    "power": {"current_mode": "Balanceado", "g_mode": False},
                    "status": {"model": "Unknown", "hwmon_available": False, "g_mode_active": False}
                }

        return self._cached_data

    def get_cpu_temp(self) -> int:
        data = self._get_all_data()
        return data.get("temps", {}).get("cpu_temp", 45)

    def get_gpu_temp(self) -> int:
        data = self._get_all_data()
        return data.get("temps", {}).get("gpu_temp", 50)

    def get_fan_rpm(self, fan_id: int) -> int:
        data = self._get_all_data()
        return data.get("fans", {}).get(f"fan{fan_id}_rpm", 2500 if fan_id == 1 else 2300)

    def get_fan_boost(self, fan_id: int) -> int:
        data = self._get_all_data()
        return data.get("fans", {}).get(f"fan{fan_id}_boost", 0)

    def get_power_mode(self) -> PowerMode:
        data = self._get_all_data()
        mode_name = data.get("power", {}).get("current_mode", "Balanceado")
        for mode in PowerMode:
            if mode.value[0] == mode_name:
                return mode
        return PowerMode.BALANCED

    def get_g_mode_status(self) -> bool:
        data = self._get_all_data()
        return data.get("power", {}).get("g_mode", False)

    def set_power_mode(self, mode: PowerMode) -> bool:
        response = self._send_request({
            "action": "set_power_mode",
            "mode": mode.value[0]
        })
        return response.get("status") == "success"

    def set_fan_boost(self, fan_id: int, percentage: int) -> bool:
        response = self._send_request({
            "action": "set_fan_boost",
            "fan_id": fan_id,
            "percentage": percentage
        })
        return response.get("status") == "success"

    def toggle_g_mode(self) -> bool:
        response = self._send_request({"action": "toggle_g_mode"})
        return response.get("status") == "success"


class AutoStartManager:
    def __init__(self):
        self.autostart_dir = Path.home() / '.config' / 'autostart'
        self.desktop_file = self.autostart_dir / 'g15-controller.desktop'

    def is_enabled(self) -> bool:
        return self.desktop_file.exists()

    def enable(self) -> bool:
        try:
            self.autostart_dir.mkdir(parents=True, exist_ok=True)

            script_path = os.path.abspath(__file__)
            python_path = sys.executable

            desktop_content = f"""[Desktop Entry]
Name=Dell G15 Controller
Comment=Dell G15 hardware monitoring and control
Exec={python_path} "{script_path}"
Icon=preferences-system
Terminal=false
Type=Application
Categories=System;Settings;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
"""

            self.desktop_file.write_text(desktop_content)
            os.chmod(self.desktop_file, 0o755)

            print(f"Autostart enabled: {self.desktop_file}")
            return True

        except Exception as e:
            print(f"Failed to enable autostart: {e}")
            return False

    def disable(self) -> bool:
        try:
            if self.desktop_file.exists():
                self.desktop_file.unlink()
                print(f"Autostart disabled: {self.desktop_file}")
            return True
        except Exception as e:
            print(f"Failed to disable autostart: {e}")
            return False






class SensorMonitor(QThread):
    data_updated = pyqtSignal(dict)

    def __init__(self, daemon_client):
        super().__init__()
        self.daemon_client = daemon_client
        self.running = True

    def _collect_data(self):
        return {
            'cpu_temp': self.daemon_client.get_cpu_temp(),
            'gpu_temp': self.daemon_client.get_gpu_temp(),
            'fan1_rpm': self.daemon_client.get_fan_rpm(1),
            'fan2_rpm': self.daemon_client.get_fan_rpm(2),
            'fan1_boost': self.daemon_client.get_fan_boost(1),
            'fan2_boost': self.daemon_client.get_fan_boost(2),
            'power_mode': self.daemon_client.get_power_mode(),
            'g_mode': self.daemon_client.get_g_mode_status()
        }

    def update_once(self):
        try:
            data = self._collect_data()
            self.data_updated.emit(data)
        except Exception as e:
            print(f"Update once error: {e}")

    def run(self):
        update_count = 0
        while self.running:
            try:
                update_count += 1
                data = self._collect_data()
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
                return "#4CAF50", "Frio", "#E8F5E9"
            elif value < 70:
                return "#FFC107", "Normal", "#FFF8E1"
            elif value < 85:
                return "#FF9800", "Quente", "#FFF3E0"
            else:
                return "#F44336", "Muito Quente", "#FFEBEE"
        else:
            if value < 2000:
                return "#2196F3", "Baixo", "#E3F2FD"
            elif value < 4000:
                return "#4CAF50", "Normal", "#E8F5E9"
            else:
                return "#FF9800", "Alto", "#FFF3E0"


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

        self.manual_toggle = QPushButton("Manual DESLIG.")
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
        self.manual_toggle.setText("Manual LIGADO" if self.manual_enabled else "Manual DESLIG.")
        self.update_manual_button_style(self.manual_enabled)
        self.boost_slider.setEnabled(self.manual_enabled)

        if not self.manual_enabled:
            self.boost_slider.setValue(0)
            # Só emite o sinal se o manual foi desativado manualmente pelo usuário
            # Não emite quando é desativado automaticamente por mudança de modo
            if self.manual_toggle.isChecked() == False:
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
        super().__init__("MODO-G DESLIGADO")
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
        self.setText("MODO-G LIGADO" if self.is_on else "MODO-G DESLIGADO")
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

        title = QLabel("Modo de Energia")
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

        self.g_mode_action = QAction("Alternar Modo-G", self)
        self.g_mode_action.triggered.connect(self.toggle_g_mode.emit)
        menu.addAction(self.g_mode_action)

        menu.addSeparator()

        self.temp_action = QAction("CPU: --°C | GPU: --°C", self)
        self.temp_action.setEnabled(False)
        menu.addAction(self.temp_action)

        menu.addSeparator()

        show_action = QAction("Mostrar Janela", self)
        show_action.triggered.connect(self.show_window.emit)
        menu.addAction(show_action)

        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def update_status(self, g_mode: bool, cpu_temp: int, gpu_temp: int):
        self.g_mode_active = g_mode
        self.cpu_temp = cpu_temp
        self.gpu_temp = gpu_temp

        self.create_icon()

        status = "ATIVO" if g_mode else "INATIVO"
        self.setToolTip(f"Dell G15 Controller\nModo-G: {status}\nCPU: {cpu_temp}°C | GPU: {gpu_temp}°C")

        self.temp_action.setText(f"CPU: {cpu_temp}°C | GPU: {gpu_temp}°C")
        self.g_mode_action.setText(f"Desabilitar Modo-G" if g_mode else "Habilitar Modo-G")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        QApplication.setStyle('Fusion')

        self.daemon_client = G15DaemonClient()
        if not self.daemon_client.daemon_available:
            self.show_daemon_required_dialog()
            return

        self.settings = None
        self.custom_message_shown = False
        self.autostart_manager = AutoStartManager()
        self.mode_changing = False

        self.setup_ui()
        self.setup_monitoring()
        self.setup_tray()

    def show_daemon_required_dialog(self):
        app = QApplication.instance()
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Dell G15 Controller")
        msg.setText("<b>G15 Daemon obrigatório</b>")
        msg.setInformativeText("Execute primeiro:\n<b>sudo python3 g15_daemon.py</b>\n\nDepois inicie este programa novamente.")
        
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        
        msg.setStyleSheet("""
            QMessageBox {
                background: #F5F6FA;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QMessageBox QLabel {
                color: #2C3E50;
                font-size: 12px;
                padding: 15px;
            }
            QMessageBox QPushButton {
                background: #2196F3;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 11px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: #1976D2;
            }
        """)
        
        msg.exec()
        app.quit()

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

        model_label = QLabel("Modelo: Dell G15 (via daemon)")
        model_label.setStyleSheet("""
            font-size: 12px;
            color: #666666;
            padding: 4px 10px;
            background: white;
            border: 1px solid #E0E0E0;
            border-radius: 12px;
        """)

        self.g_mode_button = GModeButton()
        self.g_mode_button.toggled_signal.connect(self.toggle_g_mode)

        header_layout.addWidget(title)
        header_layout.addWidget(model_label)
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

        self.cpu_thermal = ThermalCard("Temperatura da CPU", "°C", 100)
        self.gpu_thermal = ThermalCard("Temperatura da GPU", "°C", 100)
        self.fan1_rpm = ThermalCard("Velocidade Ventoinha CPU", " RPM", 6000)
        self.fan2_rpm = ThermalCard("Velocidade Ventoinha GPU", " RPM", 6000)

        thermal_layout.addWidget(self.cpu_thermal)
        thermal_layout.addWidget(self.gpu_thermal)
        thermal_layout.addWidget(self.fan1_rpm)
        thermal_layout.addWidget(self.fan2_rpm)

        fan_section = QFrame()
        fan_section.setStyleSheet("QFrame { background: transparent; }")
        fan_layout = QHBoxLayout(fan_section)
        fan_layout.setSpacing(15)

        self.fan1_control = FanControlCard(1, "Controle Ventoinha CPU")
        self.fan2_control = FanControlCard(2, "Controle Ventoinha GPU")

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
<b>Instruções:</b><br><br>
• <b>Modo-G:</b> Ativa resfriamento máximo<br>
• <b>Modos de Energia:</b> Escolha seu perfil térmico<br>
• <b>Controle Manual:</b> Selecione modo Personalizado primeiro<br>
• <b>Bandeja do Sistema:</b> Duplo-clique para mostrar/ocultar<br><br>
<b>Hardware:</b> Controlador Dell G15""")

        info_text.setStyleSheet("""
            font-size: 12px;
            color: #666666;
            line-height: 1.5;
        """)
        info_text.setWordWrap(True)

        self.autostart_checkbox = QCheckBox("Inicializar com o sistema")
        self.autostart_checkbox.setChecked(self.autostart_manager.is_enabled())
        self.autostart_checkbox.toggled.connect(self.on_autostart_toggled)
        self.autostart_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                font-weight: 500;
                color: #333333;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #CCCCCC;
                border-radius: 3px;
                background: white;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #2196F3;
                border-radius: 3px;
                background: #2196F3;
                image: url(data:image/svg+xml,%3csvg viewBox='0 0 16 16' fill='white' xmlns='http://www.w3.org/2000/svg'%3e%3cpath d='m13.854 3.646-7.5 7.5a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6 10.293l7.146-7.147a.5.5 0 0 1 .708.708z'/%3e%3c/svg%3e);
            }
        """)

        info_layout.addWidget(info_text)
        info_layout.addWidget(self.autostart_checkbox)
        info_layout.addStretch()

        settings_layout.addWidget(self.power_selector)
        settings_layout.addWidget(info_panel, 1)

        tabs.addTab(monitor_tab, "Monitor")
        tabs.addTab(settings_tab, "Configurações")

        main_layout.addLayout(header_layout)
        main_layout.addWidget(tabs)

    def setup_monitoring(self):
        self.monitor = SensorMonitor(self.daemon_client)
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


    def update_sensor_data(self, data):
        self.cpu_thermal.update_value(data['cpu_temp'])
        self.gpu_thermal.update_value(data['gpu_temp'])
        self.fan1_rpm.update_value(data['fan1_rpm'])
        self.fan2_rpm.update_value(data['fan2_rpm'])

        self.fan1_control.update_rpm(data['fan1_rpm'])
        self.fan2_control.update_rpm(data['fan2_rpm'])
        self.fan1_control.update_boost(data['fan1_boost'])
        self.fan2_control.update_boost(data['fan2_boost'])

        # Só atualiza o seletor de modo se não estiver mudando de modo
        if not self.mode_changing:
            self.power_selector.set_mode(data['power_mode'])
        
        self.g_mode_button.set_state(data['g_mode'])

        if hasattr(self, 'tray'):
            self.tray.update_status(data['g_mode'], data['cpu_temp'], data['gpu_temp'])

    def toggle_g_mode(self, state=None):
        self.daemon_client.toggle_g_mode()
        self.daemon_client._cached_data = None
        if hasattr(self, 'monitor'):
            self.monitor.update_once()

    def on_mode_changed(self, mode: PowerMode):
        self.mode_changing = True
        success = self.daemon_client.set_power_mode(mode)
        QTimer.singleShot(2000, lambda: setattr(self, 'mode_changing', False))

        if mode == PowerMode.CUSTOM:
            if not self.custom_message_shown:
                self.custom_message_shown = True
                QMessageBox.information(self, "Modo Personalizado",
                    "Modo personalizado ativado.\nHabilite controle Manual nos cartões das ventoinhas.")
        else:
            # Desabilita controles manuais sem disparar eventos
            self.fan1_control.manual_enabled = False
            self.fan1_control.manual_toggle.setChecked(False)
            self.fan1_control.manual_toggle.setText("Manual DESLIG.")
            self.fan1_control.update_manual_button_style(False)
            self.fan1_control.boost_slider.setEnabled(False)
            self.fan1_control.boost_slider.setValue(0)
            
            self.fan2_control.manual_enabled = False
            self.fan2_control.manual_toggle.setChecked(False)
            self.fan2_control.manual_toggle.setText("Manual DESLIG.")
            self.fan2_control.update_manual_button_style(False)
            self.fan2_control.boost_slider.setEnabled(False)
            self.fan2_control.boost_slider.setValue(0)

    def on_fan_boost_changed(self, fan_id: int, boost: int):
        if self.daemon_client.get_power_mode() != PowerMode.CUSTOM:
            QMessageBox.warning(self, "Aviso de Modo",
                "Por favor, selecione o modo Personalizado primeiro.")
            return

        self.daemon_client.set_fan_boost(fan_id, boost)

    def on_autostart_toggled(self, enabled: bool):
        try:
            if enabled:
                if self.autostart_manager.enable():
                    QMessageBox.information(self, "Inicialização Automática Habilitada",
                        "O Dell G15 Controller agora iniciará automaticamente com o sistema.\n\n"
                        "Nota: Se estiver usando o modo daemon, certifique-se de que o "
                        "serviço g15-daemon esteja instalado e habilitado.")
                else:
                    self.autostart_checkbox.setChecked(False)
                    QMessageBox.warning(self, "Erro",
                        "Falha ao habilitar inicialização automática. Verifique as permissões.")
            else:
                if self.autostart_manager.disable():
                    QMessageBox.information(self, "Inicialização Automática Desabilitada",
                        "O Dell G15 Controller não iniciará mais automaticamente com o sistema.")
                else:
                    self.autostart_checkbox.setChecked(True)
                    QMessageBox.warning(self, "Erro",
                        "Falha ao desabilitar inicialização automática. Verifique as permissões.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao configurar inicialização automática: {e}")
            self.autostart_checkbox.setChecked(not enabled)

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_raise()

    def quit_application(self):
        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if hasattr(self, 'tray') and self.tray.isVisible():
            self.hide()
            if hasattr(self, 'tray'):
                self.tray.showMessage(
                    "Dell G15 Controller",
                    "Minimizado para bandeja do sistema",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            event.ignore()
        else:
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.stop()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app.setStyle('Fusion')

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    
    if not hasattr(window, 'daemon_client') or not window.daemon_client.daemon_available:
        return
    
    window.show()

    print("=" * 60)
    print(" Dell G15 Control Center - v4.0 DAEMON-ONLY")
    print("=" * 60)
    print("Mode: DAEMON CLIENT")
    print("Root: NO")
    print("Model: Dell G15 (via daemon)")
    print("=" * 60)
    print("Monitoring started - values should update every second...")
    print("=" * 60)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()