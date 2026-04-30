#!/bin/bash
# Dell G15 Control Center installer (Bazzite / Fedora Atomic).

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_NAME="g15-control-center"
readonly INSTALL_DIR="/var/opt/g15-controller"
readonly BIN_LINK="/usr/local/bin/g15-controller"
readonly SERVICE_FILE="/etc/systemd/system/g15-daemon.service"
readonly DESKTOP_FILE="/usr/local/share/applications/${APP_NAME}.desktop"
readonly HWDB_FILE="/etc/udev/hwdb.d/90-dell-g15-gmode.hwdb"

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

log() { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fatal() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

execute() {
    local cmd="$*"
    log "Executando: $cmd"
    eval "$cmd" >/dev/null 2>&1 || fatal "Falha: $cmd"
}

require_root() {
    [[ $EUID -eq 0 ]] || fatal "Execute como root: sudo $0"
}

require_alienware_wmi() {
    if [[ ! -d /sys/devices/platform/alienware-wmi ]] && \
       ! grep -q alienware_wmi /proc/modules 2>/dev/null; then
        warning "Driver alienware_wmi não encontrado — controle de ventoinhas não funcionará."
        warning "Carregue o módulo (modprobe alienware_wmi) ou atualize seu kernel."
    fi
}

check_hardware() {
    local model
    model=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "")
    if [[ "$model" == *"G15"* ]]; then
        success "Dell G15 detectado: $model"
    else
        warning "Modelo G15 não detectado (encontrado: $model)."
        read -p "Continuar mesmo assim? [y/N] " -n 1 -r; echo
        [[ $REPLY =~ ^[Yy]$ ]] || fatal "Instalação cancelada."
    fi
}

install_application() {
    log "Instalando em $INSTALL_DIR..."
    if systemctl is-active --quiet g15-daemon 2>/dev/null; then
        execute "systemctl stop g15-daemon"
    fi
    execute "mkdir -p $INSTALL_DIR /usr/local/bin /usr/local/share/applications"
    execute "cp -r $SCRIPT_DIR/src/ $INSTALL_DIR/"
    execute "cp $SCRIPT_DIR/requirements.txt $INSTALL_DIR/"
    execute "cp $SCRIPT_DIR/system/g15-control-center.svg $INSTALL_DIR/icon.svg"

    log "Criando venv..."
    execute "python3 -m venv $INSTALL_DIR/venv"
    execute "$INSTALL_DIR/venv/bin/pip install --upgrade pip"
    execute "$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt"

    execute "chown -R root:root $INSTALL_DIR"
    execute "chmod -R 755 $INSTALL_DIR"
    execute "chmod +x $INSTALL_DIR/src/g15_daemon.py $INSTALL_DIR/src/g15_control_center.py"
}

install_systemd_service() {
    execute "cp $SCRIPT_DIR/system/g15-daemon.service $SERVICE_FILE"
    execute "systemctl daemon-reload"
    execute "systemctl enable g15-daemon.service"
}

install_desktop_entry() {
    sed "s|/opt/g15-controller|/var/opt/g15-controller|g" \
        "$SCRIPT_DIR/system/g15-control-center.desktop" > "$DESKTOP_FILE"
    execute "chmod 644 $DESKTOP_FILE"
}

install_gmode_key() {
    execute "cp $SCRIPT_DIR/system/90-dell-g15-gmode.hwdb $HWDB_FILE"
    execute "systemd-hwdb update"
    execute "udevadm trigger --subsystem-match=input --attr-match=name='AT Translated Set 2 keyboard'"
}

create_launcher() {
    cat > "$BIN_LINK" <<EOF
#!/bin/bash
$INSTALL_DIR/venv/bin/python $INSTALL_DIR/src/g15_control_center.py "\$@"
EOF
    execute "chmod +x $BIN_LINK"
}

start_services() {
    execute "systemctl start g15-daemon.service"
    if systemctl is-active --quiet g15-daemon; then
        success "Daemon iniciado."
    else
        warning "Daemon não subiu. Verifique: journalctl -u g15-daemon"
    fi
}

main() {
    require_root
    require_alienware_wmi
    check_hardware
    install_application
    install_systemd_service
    install_desktop_entry
    install_gmode_key
    create_launcher
    start_services
    success "Instalação concluída. Use o comando '${YELLOW}g15-controller${NC}' ou abra pelo menu."
}

main "$@"
