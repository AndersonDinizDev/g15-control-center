# Dell G15 Control Center (Bazzite / Fedora Atomic)

Centro de controle nativo para notebooks Dell G15 no Linux. Construído sobre `sysfs`, `platform_profile` e o driver `alienware_wmi` do Kernel — sem DKMS, sem módulos out-of-tree.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-green)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Linux](https://img.shields.io/badge/OS-Bazzite%20%7C%20Fedora-orange)](https://bazzite.gg)

## Recursos

### Monitoramento
- **Temperaturas**: CPU e GPU lidas via `hwmon` do `alienware_wmi` (com fallback de leitura para `dell_smm` / `dell_ddv`).
- **Ventoinhas**: RPM em tempo real do `alienware_wmi`.

### Controle
- **Power Profiles** (`/sys/firmware/acpi/platform_profile`): Silencioso, Balanceado, Performance.
- **Personalizado**: herda o profile atual e permite ajuste manual de boost da ventoinha de CPU/GPU (`fan{1,2}_boost` do `alienware_wmi`).
- **G-Mode**: ativação via `/sys/devices/platform/alienware-wmi/thermal_mode` (mesmo comportamento do Alienware Command Center).
- **Tecla F9 (G-Mode)**: mapeada via `udev/hwdb` (scancode 0x68 → `KEY_PROG1`) e capturada pelo daemon.
- **Persistência**: configuração em `/etc/g15-daemon/config.json`, restaurada no boot.

### Compatibilidade Atômica
- Instalação em `/var/opt/g15-controller` (respeita `/usr` imutável).
- Serviço systemd com logs via `journald`.
- Sem dependência de DKMS — não quebra em atualizações de Kernel.

## Requisitos

### Hardware / Kernel
- Dell G15 com driver `alienware_wmi` carregado (`lsmod | grep alienware_wmi`).
  Disponível nativamente em Kernels Linux 6.x+ na maioria das distros baseadas em Fedora.
- Sem o `alienware_wmi`, o controle de ventoinhas e G-Mode **não funciona** — o programa só monitoraria sensores.

### Software
- Bazzite OS, Fedora Silverblue/Kinoite/Workstation (ou qualquer distro com systemd + `alienware_wmi`).
- Python 3.9+
- PyQt6 6.4+ (instalado automaticamente em venv pelo instalador).

## Instalação

```bash
git clone https://github.com/AndersonDinizDev/g15-control-center.git
cd g15-control-center
sudo ./install.sh
```

O instalador:
1. Verifica presença do `alienware_wmi`.
2. Instala em `/var/opt/g15-controller` com venv isolado.
3. Habilita o serviço `g15-daemon` no systemd.
4. Mapeia a tecla **G-Mode (F9)** via udev/hwdb.
5. Cria atalho no menu de aplicações.

> **Nota**: após a primeira instalação, pode ser necessário **reiniciar uma vez** para o kernel re-aplicar o keymap da tecla G-Mode no `atkbd`.

## Uso

```bash
g15-controller          # abre a interface
sudo systemctl status g15-daemon
journalctl -u g15-daemon -f
```

### Modos de Energia
- **Silencioso / Balanceado / Performance**: aplicam o profile correspondente do kernel; o daemon desfaz qualquer boost manual e devolve o controle das ventoinhas para a curva da BIOS.
- **Personalizado**: mantém o profile atual e adiciona o boost manual definido nos sliders. O `fan{1,2}_boost` é aditivo sobre a curva — o EC continua reagindo às temperaturas, só ventoinha um pouco mais.
- **G-Mode (F9)**: força performance + boost máximo via `thermal_mode=0xab`. Ao desativar, o daemon restaura o estado anterior (incluindo boosts manuais salvos).

## Solução de Problemas

### Daemon não inicia
```bash
journalctl -u g15-daemon -f
```

### Sliders sem efeito
Confirme que o `alienware_wmi` está carregado e expõe os arquivos de boost:
```bash
ls /sys/class/hwmon/hwmon*/fan*_boost 2>/dev/null
lsmod | grep alienware_wmi
```
Se nada aparecer, seu kernel não tem o driver e o controle de ventoinhas não funcionará.

### Tecla G-Mode não responde
```bash
sudo evtest /dev/input/by-path/platform-i8042-serio-0-event-kbd
```
Aperte F9 — deve aparecer `KEY_PROG1` (code 148). Se aparecer `KEY_UNKNOWN`, reinicie uma vez para o atkbd recarregar o keymap.

### Permissão no socket
O socket fica em `/tmp/g15-daemon.sock` com `0666`. Se a UI não conectar, verifique se o daemon está ativo (`systemctl is-active g15-daemon`).

## Desinstalação

```bash
sudo ./uninstall.sh
```

## Aviso

Este software interage diretamente com sysfs/ACPI. Use por sua conta e risco.

---
**Desenvolvido para a comunidade Dell G15 no Linux.**
