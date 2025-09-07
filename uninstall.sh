#!/bin/bash

set -euo pipefail

# ===================================================================
# Dell G15 Controller Commander - Desinstalador Completo
# ===================================================================

readonly APP_NAME="g15-controller-commander"
readonly INSTALL_DIR="/opt/g15-controller"
readonly BIN_LINK="/usr/local/bin/g15-controller"
readonly SERVICE_FILE="/etc/systemd/system/g15-daemon.service"
readonly DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"
readonly HWDB_FILE="/etc/udev/hwdb.d/90-dell-g15-gmode.hwdb"
readonly CONFIG_DIR="/etc/g15-daemon"


# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
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

# Função para executar comandos com log (permite falha)
execute() {
    local cmd="$*"
    log "Executando: $cmd"
    if ! eval "$cmd" >/dev/null 2>&1; then
        warning "Comando falhou (continuando): $cmd"
        return 1
    fi
    return 0
}

# Função para executar comandos que devem ter sucesso
execute_required() {
    local cmd="$*"
    log "Executando: $cmd"
    if ! eval "$cmd" >/dev/null 2>&1; then
        fatal "Falha crítica ao executar: $cmd"
    fi
}

# Verificação de root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        fatal "Este script deve ser executado como root. Use: sudo $0"
    fi
}

# Confirmação do usuário
confirm_uninstall() {
    echo -e "${YELLOW}⚠️  Esta operação irá remover completamente o Dell G15 Controller Commander.${NC}"
    echo
    echo "Itens que serão removidos:"
    echo -e "  • Aplicação: ${RED}$INSTALL_DIR${NC}"
    echo -e "  • Serviço: ${RED}$SERVICE_FILE${NC}"
    echo -e "  • Atalho desktop: ${RED}$DESKTOP_FILE${NC}"
    echo -e "  • Configurações: ${RED}$CONFIG_DIR${NC}"
    echo -e "  • Mapeamento tecla G-Mode: ${RED}$HWDB_FILE${NC}"
    echo
    read -p "Deseja continuar com a desinstalação? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Desinstalação cancelada pelo usuário"
        exit 0
    fi
}

# Parar e desabilitar serviços
stop_services() {
    log "Parando e desabilitando serviços..."
    
    # Parar serviço se estiver rodando
    if systemctl is-active --quiet g15-daemon 2>/dev/null; then
        log "Parando serviço g15-daemon..."
        execute "systemctl stop g15-daemon"
    fi
    
    # Desabilitar serviço se estiver habilitado
    if systemctl is-enabled --quiet g15-daemon 2>/dev/null; then
        log "Desabilitando serviço g15-daemon..."
        execute "systemctl disable g15-daemon"
    fi
    
    success "Serviços parados e desabilitados"
}

# Remover arquivos do serviço
remove_systemd_service() {
    log "Removendo arquivos do serviço systemd..."
    
    if [[ -f "$SERVICE_FILE" ]]; then
        execute_required "rm '$SERVICE_FILE'"
        execute "systemctl daemon-reload"
        execute "systemctl reset-failed g15-daemon 2>/dev/null || true"
        success "Serviço systemd removido"
    else
        log "Arquivo de serviço não encontrado: $SERVICE_FILE"
    fi
}

# Remover aplicação
remove_application() {
    log "Removendo aplicação..."
    
    if [[ -d "$INSTALL_DIR" ]]; then
        # Matar qualquer processo em execução
        log "Terminando processos da aplicação..."
        execute "pkill -f g15_daemon.py || true"
        execute "pkill -f g15_controller_commander.py || true"
        
        # Aguardar um momento
        sleep 2
        
        # Remover diretório
        execute_required "rm -rf '$INSTALL_DIR'"
        success "Aplicação removida de $INSTALL_DIR"
    else
        log "Diretório de instalação não encontrado: $INSTALL_DIR"
    fi
}

# Remover link simbólico
remove_symlink() {
    log "Removendo link simbólico..."
    
    if [[ -L "$BIN_LINK" ]]; then
        execute_required "rm '$BIN_LINK'"
        success "Link simbólico removido: $BIN_LINK"
    else
        log "Link simbólico não encontrado: $BIN_LINK"
    fi
}

# Remover atalho desktop
remove_desktop_entry() {
    log "Removendo atalho desktop..."
    
    if [[ -f "$DESKTOP_FILE" ]]; then
        execute_required "rm '$DESKTOP_FILE'"
        execute "update-desktop-database /usr/share/applications/"
        success "Atalho desktop removido"
    else
        log "Arquivo desktop não encontrado: $DESKTOP_FILE"
    fi
}

# Remover configurações
remove_configs() {
    log "Removendo configurações..."
    
    if [[ -d "$CONFIG_DIR" ]]; then
        execute_required "rm -rf '$CONFIG_DIR'"
        success "Configurações removidas de $CONFIG_DIR"
    else
        log "Diretório de configurações não encontrado: $CONFIG_DIR"
    fi
    
    # Remover socket se existir
    if [[ -S "/tmp/g15-daemon.sock" ]]; then
        execute "rm /tmp/g15-daemon.sock"
        log "Socket removido"
    fi
}

# Remover mapeamento tecla G-Mode
remove_gmode_key() {
    log "Removendo mapeamento da tecla G-Mode..."
    
    if [[ -f "$HWDB_FILE" ]]; then
        execute_required "rm '$HWDB_FILE'"
        execute "systemd-hwdb update"
        execute "udevadm trigger --subsystem-match=input --attr-match=name='AT Translated Set 2 keyboard'"
        success "Mapeamento da tecla G-Mode removido"
    else
        log "Arquivo hwdb não encontrado: $HWDB_FILE"
    fi
}

# Remover usuário do sistema
remove_system_user() {
    log "Removendo usuário do sistema..."
    
    if id g15-controller &>/dev/null; then
        execute "userdel g15-controller"
        success "Usuário g15-controller removido"
    else
        log "Usuário g15-controller não encontrado"
    fi
}

# Limpeza de logs
cleanup_logs() {
    log "Limpando logs..."
    
    # Remover logs do journal
    execute "journalctl --vacuum-time=1s --identifier=g15-daemon || true"
    
    # Remover arquivo de log específico se existir
    if [[ -f "/var/log/g15-daemon.log" ]]; then
        execute "rm /var/log/g15-daemon.log"
        log "Log removido: /var/log/g15-daemon.log"
    fi
    
    success "Logs limpos"
}

# Oferecer remoção de dependências
offer_remove_deps() {
    echo
    echo -e "${CYAN}🧹 Limpeza de dependências${NC}"
    echo "As seguintes dependências foram instaladas para o G15 Controller:"
    echo -e "  • ${YELLOW}acpi-call-dkms${NC} (módulo ACPI)"
    echo -e "  • ${YELLOW}policykit-1${NC} (autenticação)"
    echo -e "  • ${YELLOW}libxcb-cursor0${NC} (interface Qt)"
    echo
    echo -e "${YELLOW}⚠️  Estas dependências podem ser usadas por outros programas.${NC}"
    read -p "Deseja removê-las também? [y/N] " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Removendo dependências opcionais..."
        
        # Lista de dependências que podem ser removidas
        local optional_deps=(
            "acpi-call-dkms"
        )
        
        for dep in "${optional_deps[@]}"; do
            if dpkg -l "$dep" &>/dev/null; then
                log "Removendo $dep..."
                execute "apt remove --purge -y '$dep'"
            fi
        done
        
        execute "apt autoremove -y"
        success "Dependências opcionais removidas"
    else
        log "Dependências mantidas no sistema"
    fi
}

# Verificação pós-desinstalação
post_uninstall_check() {
    log "Executando verificações pós-desinstalação..."
    
    local remaining_files=()
    local files_to_check=("$INSTALL_DIR" "$SERVICE_FILE" "$DESKTOP_FILE" "$HWDB_FILE" "$CONFIG_DIR" "$BIN_LINK")
    
    for file in "${files_to_check[@]}"; do
        if [[ -e "$file" ]]; then
            remaining_files+=("$file")
        fi
    done
    
    if [[ ${#remaining_files[@]} -gt 0 ]]; then
        warning "Alguns arquivos ainda existem:"
        printf '  • %s\n' "${remaining_files[@]}"
        echo
        read -p "Deseja forçar a remoção destes arquivos? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            for file in "${remaining_files[@]}"; do
                execute "rm -rf '$file'"
            done
            success "Arquivos restantes removidos forçadamente"
        fi
    else
        success "Nenhum arquivo residual encontrado"
    fi
    
    # Verificar se algum processo ainda está rodando
    if pgrep -f "g15_daemon\|g15_controller" >/dev/null; then
        warning "Processos relacionados ainda estão em execução"
        execute "pkill -f 'g15_daemon\|g15_controller' || true"
    fi
    
    success "Verificações pós-desinstalação concluídas"
}

# Mostrar informações finais
show_completion_info() {
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║            DESINSTALAÇÃO CONCLUÍDA!             ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${CYAN}✅ Itens removidos:${NC}"
    echo -e "  • Aplicação e arquivos"
    echo -e "  • Serviço systemd"
    echo -e "  • Atalho desktop"
    echo -e "  • Configurações"
    echo -e "  • Mapeamento tecla G-Mode"
    echo
    echo -e "${CYAN}🔄 Reinicialização recomendada:${NC}"
    echo -e "  • Para remover completamente o mapeamento da tecla G-Mode"
    echo -e "  • Para limpar qualquer cache do sistema"
    echo
    echo -e "${GREEN}Desinstalação concluída com sucesso!${NC}"
    echo
    echo -e "${CYAN}Obrigado por usar o Dell G15 Controller Commander!${NC}"
    echo
}

# Função principal
main() {
    echo -e "${RED}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          Dell G15 Controller Commander               ║"
    echo "║                Desinstalador v1.0                   ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    log "Iniciando desinstalação do Dell G15 Controller Commander..."
    
    check_root
    confirm_uninstall
    stop_services
    remove_systemd_service
    remove_application
    remove_symlink
    remove_desktop_entry
    remove_configs
    remove_gmode_key
    remove_system_user
    cleanup_logs
    post_uninstall_check
    offer_remove_deps
    show_completion_info
    
    success "Desinstalação concluída com sucesso!"
}

# Executar apenas se chamado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi