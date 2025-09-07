# Dell G15 Control Center

Centro de controle moderno para notebooks Dell G15 executando Linux. Oferece monitoramento em tempo real e controle de ventoinhas através de uma arquitetura client-daemon segura.

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-green)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Linux](https://img.shields.io/badge/OS-Linux-orange)](https://kernel.org)

## Recursos

### Monitoramento
- **Temperaturas em Tempo Real**: CPU e GPU com atualizações ao vivo
- **Velocidade das Ventoinhas**: Leituras RPM precisas via ACPI/hwmon
- **Interface na Bandeja**: Acesso rápido sem ocupar área de trabalho

### Controle de Energia
- **4 Modos**: Silencioso, Balanceado, Performance e Personalizado
- **Controle Manual**: Ajuste individual de ventoinhas no modo Personalizado
- **G-Mode**: Resfriamento máximo ativado via tecla F9
- **Persistência**: Configurações salvas e restauradas automaticamente

### Arquitetura Segura
- **Separação de Privilégios**: Interface sem root, daemon com privilégios mínimos
- **Comunicação Segura**: Unix socket com autenticação por token
- **Instalação Automática**: Script inteligente com detecção de hardware

## Requisitos

### Sistema
- Dell G15 (modelos 5511, 5515, 5520, 5525, 5530, 5535)
- Linux (Ubuntu, Debian, Mint, Pop!_OS)
- Python 3.8+

### Dependências
Instaladas automaticamente pelo script:
- acpi-call-dkms (comunicação ACPI)
- PyQt6 (interface gráfica)
- policykit-1 (elevação de privilégios)

## Instalação

### Método Automático (Recomendado)

```bash
git clone https://github.com/AndersonDinizDev/g15-control-center.git
cd g15-control-center
sudo ./install.sh
```

O instalador:
- Detecta hardware Dell G15
- Instala dependências necessárias
- Configura daemon systemd
- Mapeia tecla G-Mode (F9)
- Adiciona ao menu de aplicações

### Verificação

```bash
# Status do daemon
systemctl status g15-daemon

# Abrir aplicação
g15-controller
```

## Como Usar

### Interface Principal
1. **Aba Monitor**: Temperaturas e RPM em tempo real
2. **Aba Configurações**: Modos de energia e controles manuais
3. **Bandeja do Sistema**: Acesso rápido via ícone na bandeja

### Modos de Energia
- **Silencioso**: Baixo ruído, temperatura conservadora
- **Balanceado**: Equilíbrio entre performance e ruído
- **Performance**: Máxima performance, ventoinhas mais rápidas
- **Personalizado**: Controle manual habilitado

### G-Mode
- **Ativação**: Tecla F9 ou botão na interface
- **Função**: Resfriamento máximo para jogos intensivos
- **Comportamento**: Sobrepõe configurações atuais

### Controle Manual
1. Selecione modo **Personalizado**
2. Ative controle **Manual** na ventoinha desejada
3. Ajuste com sliders ou botões predefinidos (25%, 50%, 75%, 100%)

## Arquitetura Técnica

### Componentes
- **g15_control_center.py**: Interface PyQt6 (usuário normal)
- **g15_daemon.py**: Daemon de controle (root)
- **Unix Socket**: Comunicação segura com autenticação

### Arquivos de Sistema
- **Serviço**: `/etc/systemd/system/g15-daemon.service`
- **Configurações**: `/etc/g15-daemon/config.json`
- **Logs**: `/var/log/g15-daemon.log`
- **Mapeamento de Tecla**: `/etc/udev/hwdb.d/90-dell-g15-gmode.hwdb`

## Solução de Problemas

### Daemon não inicia
```bash
# Verificar status
systemctl status g15-daemon

# Ver logs
journalctl -u g15-daemon -f

# Reiniciar serviço
sudo systemctl restart g15-daemon
```

### Módulo ACPI
```bash
# Verificar se está carregado
lsmod | grep acpi_call

# Carregar manualmente
sudo modprobe acpi_call
```

### Sensores não detectados
```bash
# Listar sensores disponíveis
sensors | grep -E "(dell|fan|temp)"

# Verificar hwmon
ls /sys/class/hwmon/
```

### Interface não abre
```bash
# Verificar dependências Qt
sudo apt install --reinstall libxcb-cursor0

# Executar em modo debug
python3 src/g15_control_center.py
```

## Desinstalação

```bash
cd g15-control-center
sudo ./uninstall.sh
```

Remove completamente:
- Aplicação e configurações
- Serviço systemd  
- Mapeamento de tecla G-Mode
- Atalho do menu
- Logs do sistema

## Estrutura do Projeto

```
g15-control-center/
├── src/
│   ├── g15_control_center.py    # Interface cliente
│   ├── g15_daemon.py            # Daemon de controle
│   └── __init__.py
├── system/
│   ├── g15-daemon.service       # Serviço systemd
│   ├── g15-control-center.desktop  # Atalho desktop
│   ├── g15-control-center.svg   # Ícone
│   └── 90-dell-g15-gmode.hwdb   # Mapeamento G-Mode
├── install.sh                   # Instalador automático
├── uninstall.sh                 # Desinstalador
├── pyproject.toml              # Metadados do projeto
├── requirements.txt            # Dependências Python
└── README.md
```

## Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Add nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## Segurança

- Daemon roda com privilégios mínimos necessários
- Comunicação via Unix socket com permissões restritas
- Validação de todas as operações ACPI
- Rate limiting para prevenir abuso

## Licença

Este projeto está licenciado sob a Licença MIT. Veja [LICENSE](LICENSE) para detalhes.

## Aviso

Este software controla componentes de hardware diretamente. Use por sua própria conta e risco. Os desenvolvedores não se responsabilizam por danos ao hardware.

---

**Links Úteis:**
- [Issues](https://github.com/AndersonDinizDev/g15-control-center/issues) - Reportar problemas
- [Releases](https://github.com/AndersonDinizDev/g15-control-center/releases) - Downloads