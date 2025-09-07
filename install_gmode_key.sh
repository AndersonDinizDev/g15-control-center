#!/bin/bash

# Script para instalar o mapeamento da tecla G-Mode no Dell G15
# Execute com: sudo ./install_gmode_key.sh

set -e

echo "=== Dell G15 G-Mode Key Installer ==="
echo

# Verificar se está rodando como root
if [[ $EUID -ne 0 ]]; then
   echo "❌ Este script precisa ser executado como root (use sudo)"
   exit 1
fi

# Copiar arquivo hwdb
echo "📁 Copiando arquivo de mapeamento..."
cp 90-dell-g15-gmode.hwdb /etc/udev/hwdb.d/

# Verificar se o arquivo foi copiado
if [ ! -f /etc/udev/hwdb.d/90-dell-g15-gmode.hwdb ]; then
    echo "❌ Erro ao copiar arquivo hwdb"
    exit 1
fi

echo "✅ Arquivo hwdb copiado para /etc/udev/hwdb.d/"

# Recompilar hwdb
echo "🔄 Recompilando hardware database..."
systemd-hwdb update

# Recarregar regras udev
echo "🔄 Recarregando regras udev..."
udevadm trigger --subsystem-match=input --attr-match=name="AT Translated Set 2 keyboard"

echo
echo "✅ Instalação concluída!"
echo "📝 A tecla G-Mode (FN+F9) agora está mapeada para KEY_PROG1"
echo "🔄 Reinicie o sistema ou reconecte o teclado para ativar"
echo
echo "Para testar, use: evtest /dev/input/eventX (onde X é o número do teclado)"
echo "Para remover: sudo rm /etc/udev/hwdb.d/90-dell-g15-gmode.hwdb && sudo systemd-hwdb update"