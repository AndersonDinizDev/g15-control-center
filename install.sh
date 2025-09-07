#!/bin/bash

set -euo pipefail

# ===================================================================
# Dell G15 Controller Commander - Instalador Automatizado
# ===================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_NAME="g15-controller-commander"
readonly INSTALL_DIR="/opt/g15-controller"
readonly BIN_LINK="/usr/local/bin/g15-controller"
readonly SERVICE_FILE="/etc/systemd/system/g15-daemon.service"
readonly DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"
readonly HWDB_FILE="/etc/udev/hwdb.d/90-dell-g15-gmode.hwdb"


# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Funções de logging
log() {
    echo -e "${CYAN}[INFO]${NC} $*"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

fatal() {
    error "$@"
    exit 1
}

# Função para executar comandos com log
execute() {
    local cmd="$*"
    log "Executando: $cmd"
    if ! eval "$cmd" >/dev/null 2>&1; then
        fatal "Falha ao executar: $cmd"
    fi
}

# Verificação de root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        fatal "Este script deve ser executado como root. Use: sudo $0"
    fi
}

# Detectar distribuição
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        case $ID in
            ubuntu|debian|linuxmint|pop)
                log "Distribuição detectada: $PRETTY_NAME"
                return 0
                ;;
            *)
                warning "Distribuição $PRETTY_NAME não testada, continuando..."
                return 0
                ;;
        esac
    else
        fatal "Não foi possível detectar a distribuição Linux"
    fi
}

# Verificar hardware Dell G15
check_hardware() {
    log "Verificando compatibilidade de hardware..."
    
    # Verificar DMI
    local vendor model
    vendor=$(dmidecode -s system-manufacturer 2>/dev/null || echo "")
    model=$(dmidecode -s system-product-name 2>/dev/null || echo "")
    
    if [[ "$vendor" != *"Dell"* ]]; then
        warning "Hardware Dell não detectado. Vendor: $vendor"
        read -p "Deseja continuar mesmo assim? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            fatal "Instalação cancelada pelo usuário"
        fi
    fi
    
    if [[ "$model" == *"G15"* ]]; then
        success "Dell G15 detectado: $model"
    else
        warning "Modelo G15 não detectado explicitamente. Model: $model"
        read -p "Deseja continuar? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            fatal "Instalação cancelada pelo usuário"
        fi
    fi
    
    # Verificar módulo acpi_call
    if ! lsmod | grep -q acpi_call; then
        log "Tentando carregar módulo acpi_call..."
        if ! modprobe acpi_call 2>/dev/null; then
            warning "Módulo acpi_call não carregado. Será instalado durante as dependências."
        fi
    fi
}

# Instalar dependências do sistema
install_system_deps() {
    log "Instalando dependências do sistema..."
    
    execute "apt update"
    
    local deps=(
        "python3"
        "python3-pip" 
        "python3-venv"
        "acpi-call-dkms"
        "policykit-1"
        "libxcb-cursor0"
        "dmidecode"
        "udev"
        "systemd"
    )
    
    for dep in "${deps[@]}"; do
        log "Instalando $dep..."
        execute "apt install -y $dep"
    done
    
    # Carregar módulo acpi_call
    log "Carregando módulo acpi_call..."
    execute "modprobe acpi_call"
    
    success "Dependências do sistema instaladas"
}

# Criar usuário do sistema se necessário
setup_system_user() {
    if ! id g15-controller &>/dev/null; then
        log "Criando usuário do sistema g15-controller..."
        execute "useradd --system --home-dir $INSTALL_DIR --shell /bin/false g15-controller"
    fi
}

# Instalar aplicação
install_application() {
    log "Instalando aplicação em $INSTALL_DIR..."
    
    # Parar serviço se estiver rodando
    if systemctl is-active --quiet g15-daemon 2>/dev/null; then
        log "Parando serviço existente..."
        execute "systemctl stop g15-daemon"
    fi
    
    # Criar diretório de instalação
    execute "mkdir -p $INSTALL_DIR"
    execute "cd $SCRIPT_DIR"
    
    # Copiar arquivos da aplicação
    log "Copiando arquivos da aplicação..."
    execute "cp -r src/ $INSTALL_DIR/"
    execute "cp requirements.txt $INSTALL_DIR/"
    execute "cp pyproject.toml $INSTALL_DIR/"
    execute "cp system/g15-controller-commander.svg $INSTALL_DIR/icon.svg"
    
    # Criar ambiente virtual
    log "Criando ambiente virtual Python..."
    execute "python3 -m venv $INSTALL_DIR/venv"
    
    # Instalar dependências Python
    log "Instalando dependências Python..."
    execute "$INSTALL_DIR/venv/bin/pip install --upgrade pip"
    execute "$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt"
    
    # Definir permissões
    execute "chown -R root:root $INSTALL_DIR"
    execute "chmod -R 755 $INSTALL_DIR"
    execute "chmod +x $INSTALL_DIR/src/g15_controller_commander.py"
    execute "chmod +x $INSTALL_DIR/src/g15_daemon.py"
    
    success "Aplicação instalada em $INSTALL_DIR"
}

# Instalar serviço systemd
install_systemd_service() {
    log "Instalando serviço systemd..."
    
    execute "cp system/g15-daemon.service $SERVICE_FILE"
    execute "systemctl daemon-reload"
    execute "systemctl enable g15-daemon.service"
    
    success "Serviço systemd instalado e habilitado"
}

# Instalar atalho desktop
install_desktop_entry() {
    log "Instalando atalho desktop..."
    
    execute "cp system/g15-controller-commander.desktop $DESKTOP_FILE"
    execute "chmod 644 $DESKTOP_FILE"
    execute "update-desktop-database /usr/share/applications/"
    
    success "Atalho desktop instalado"
}

# Instalar mapeamento de tecla G-Mode
install_gmode_key() {
    log "Instalando mapeamento da tecla G-Mode..."
    
    execute "cp system/90-dell-g15-gmode.hwdb $HWDB_FILE"
    execute "systemd-hwdb update"
    execute "udevadm trigger --subsystem-match=input --attr-match=name='AT Translated Set 2 keyboard'"
    
    success "Mapeamento da tecla G-Mode instalado"
}

# Criar link simbólico
create_symlink() {
    log "Criando link simbólico..."
    
    if [[ -L "$BIN_LINK" ]]; then
        execute "rm $BIN_LINK"
    fi
    
    execute "ln -s $INSTALL_DIR/venv/bin/python $BIN_LINK"
    execute "chmod +x $BIN_LINK"
    
    success "Link simbólico criado: $BIN_LINK"
}

# Iniciar serviços
start_services() {
    log "Iniciando serviços..."
    
    execute "systemctl start g15-daemon.service"
    
    if systemctl is-active --quiet g15-daemon; then
        success "Daemon g15-daemon iniciado com sucesso"
    else
        warning "Falha ao iniciar daemon. Verifique os logs: journalctl -u g15-daemon.service"
    fi
}

# Verificação pós-instalação
post_install_check() {
    log "Executando verificações pós-instalação..."
    
    # Verificar arquivos
    local files=("$INSTALL_DIR/src/g15_daemon.py" "$SERVICE_FILE" "$DESKTOP_FILE" "$HWDB_FILE")
    for file in "${files[@]}"; do
        if [[ ! -f "$file" ]]; then
            fatal "Arquivo não encontrado: $file"
        fi
    done
    
    # Verificar serviço
    if ! systemctl is-enabled --quiet g15-daemon; then
        fatal "Serviço g15-daemon não está habilitado"
    fi
    
    # Verificar conectividade daemon
    sleep 2
    if [[ -S "/tmp/g15-daemon.sock" ]]; then
        success "Socket do daemon detectado"
    else
        warning "Socket do daemon não encontrado. O daemon pode estar inicializando."
    fi
    
    success "Verificações pós-instalação concluídas"
}

# Mostrar informações finais
show_completion_info() {
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║            INSTALAÇÃO CONCLUÍDA!                ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${CYAN}🚀 Como usar:${NC}"
    echo -e "  • Abrir interface: ${YELLOW}g15-controller${NC} (ou pelo menu de aplicações)"
    echo -e "  • Status daemon: ${YELLOW}systemctl status g15-daemon${NC}"
    echo -e "  • Ver logs: ${YELLOW}journalctl -u g15-daemon -f${NC}"
    echo -e "  • Pressionar tecla: ${YELLOW}F9${NC} (ativa/desativa G-Mode)"
    echo
    echo -e "${CYAN}📁 Arquivos instalados:${NC}"
    echo -e "  • Aplicação: ${YELLOW}$INSTALL_DIR${NC}"
    echo -e "  • Serviço: ${YELLOW}$SERVICE_FILE${NC}"
    echo -e "  • Atalho: ${YELLOW}$DESKTOP_FILE${NC}"
    echo
    echo -e "${CYAN}🛠️  Para desinstalar:${NC}"
    echo -e "  • Execute: ${YELLOW}sudo ./uninstall.sh${NC}"
    echo
    echo -e "${PURPLE}⚠️  IMPORTANTE:${NC}"
    echo -e "  • Reinicie o sistema para ativação completa da tecla G-Mode"
    echo -e "  • O daemon inicia automaticamente no boot"
    echo
    echo -e "${GREEN}Instalação concluída com sucesso!${NC}"
    echo
}

# Função principal
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          Dell G15 Controller Commander               ║"
    echo "║                 Instalador v1.0                     ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    log "Iniciando instalação do Dell G15 Controller Commander..."
    
    check_root
    detect_distro
    check_hardware
    install_system_deps
    setup_system_user
    install_application
    install_systemd_service
    install_desktop_entry
    install_gmode_key
    create_symlink
    start_services
    post_install_check
    show_completion_info
    
    success "Instalação concluída com sucesso!"
}

# Executar apenas se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi