#!/bin/bash
# Dell G15 Control Center uninstaller.

set -euo pipefail

readonly APP_NAME="g15-control-center"
readonly INSTALL_DIR="/var/opt/g15-controller"
readonly BIN_LINK="/usr/local/bin/g15-controller"
readonly SERVICE_FILE="/etc/systemd/system/g15-daemon.service"
readonly DESKTOP_FILE="/usr/local/share/applications/${APP_NAME}.desktop"
readonly HWDB_FILE="/etc/udev/hwdb.d/90-dell-g15-gmode.hwdb"
readonly CONFIG_DIR="/etc/g15-daemon"

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
fatal() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

execute() {
    log "Executando: $*"
    eval "$*" >/dev/null 2>&1 || true
}

require_root() {
    [[ $EUID -eq 0 ]] || fatal "Execute como root: sudo $0"
}

main() {
    require_root

    log "Parando serviço..."
    execute "systemctl stop g15-daemon"
    execute "systemctl disable g15-daemon"

    log "Removendo arquivos..."
    execute "rm -f $SERVICE_FILE $BIN_LINK $DESKTOP_FILE $HWDB_FILE /tmp/g15-daemon.sock"
    execute "rm -rf $INSTALL_DIR $CONFIG_DIR"

    log "Atualizando systemd / udev..."
    execute "systemctl daemon-reload"
    execute "systemd-hwdb update"
    execute "udevadm trigger --subsystem-match=input --attr-match=name='AT Translated Set 2 keyboard'"

    success "Desinstalação concluída."
}

main "$@"
