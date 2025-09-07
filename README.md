# Dell G15 Control Center

Centro de controle moderno e repleto de recursos para notebooks gamer Dell G15 executando Linux. Funciona com arquitetura client-daemon para máxima segurança, fornecendo monitoramento de hardware em tempo real e controle de ventoinhas.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Linux](https://img.shields.io/badge/OS-Linux-orange)

## Recursos

- **Monitoramento de Temperatura em Tempo Real**: Temperaturas de CPU e GPU com atualizações ao vivo
- **Monitoramento de Velocidade dos Ventoinhas**: Leituras RPM em tempo real para ventoinhas de CPU e GPU
- **Controle de Modo de Energia**: Alterne entre modos Silencioso, Balanceado, Performance e Customizado
- **Controle Manual de Ventoinhas**: Configurações personalizadas de boost de ventoinha no modo Customizado
- **Alternância G-Mode**: Ativar/desativar modo gaming para resfriamento máximo
- **Integração com Bandeja do Sistema**: Minimizar para bandeja com controles de acesso rápido
- **Interface Moderna**: Interface limpa e responsiva com feedback visual em tempo real
- **Arquitetura Segura**: Cliente sem root + Daemon com privilégios para controle de hardware

## Requisitos

### Requisitos do Sistema
- **Sistema Operacional**: Linux (testado no Linux Mint, Ubuntu, Debian)
- **Hardware**: Notebook gamer Dell G15 (5511, 5515, 5520, 5525, 5530, 5535)
- **Python**: 3.8 ou superior
- **Privilégios**: Daemon requer root, interface roda como usuário normal

### Dependências
- **acpi-call-dkms**: Comunicação ACPI com BIOS
- **policykit-1**: Privilégios de root
- **libxcb-cursor0**: Interface Qt
- **PyQt6**: Framework de GUI
- **psutil**: Informações do sistema (opcional)

## Instalação

### Instalação Automática (Recomendada)
```bash
# Clone o repositório
git clone https://github.com/AndersonDinizDev/g15-controller-commander.git
cd g15-controller-commander

# Execute o instalador automático
sudo ./install.sh
```

**O instalador automático faz:**
- Detecta hardware Dell G15 compatível
- Instala todas as dependências automaticamente
- Configura serviço systemd (auto-start no boot)
- Integra com menu de aplicações
- Mapeia tecla G-Mode (F9)
- Configura permissões de segurança

## Uso

### Início Rápido

**Após a instalação automática:**

**Interface Gráfica:**
- Menu de aplicações → "Dell G15 Control Center"
- Ou execute: `g15-controller`

**Tecla G-Mode:**
- Pressione `F9` para alternar G-Mode instantaneamente

**Monitoramento:**
- Status do daemon: `systemctl status g15-daemon`
- Ver logs: `journalctl -u g15-daemon -f`

### Nova Arquitetura
- **Daemon**: Roda como root, controla hardware via ACPI/hwmon
- **Interface**: Roda como usuário, comunica com daemon via Unix socket
- **Segurança**: Separação de privilégios, interface sem root

### Visão Geral da Interface

#### Aba Monitor
- **Cartões de Temperatura**: Temperaturas de CPU e GPU ao vivo com status codificado por cores
- **Cartões de Velocidade dos Ventoinhas**: Monitoramento RPM em tempo real para ambas as ventoinhas
- **Controles Manuais de Ventoinhas**: Controles de boost individual (apenas modo Customizado)

#### Aba Configurações
- **Seletor de Modo de Energia**: Escolha entre 4 perfis de energia
- **Botão G-Mode**: Alternar modo de resfriamento máximo
- **Informações do Sistema**: Status de detecção de hardware

#### Bandeja do Sistema
- **Acesso Rápido**: Clique direito para exibição de temperatura e alternância G-Mode
- **Minimizar para Bandeja**: Fechar janela para minimizar (aplicação continua executando)
- **Exibição de Temperatura**: Temperaturas de CPU/GPU ao vivo no menu de contexto

## Configuração

### Modos de Energia
- **Silencioso**: Baixo ruído, resfriamento conservador
- **Balanceado**: Equilíbrio ideal entre performance e ruído
- **Performance**: Máxima performance, velocidades de ventoinha mais altas
- **Customizado**: Controle manual de ventoinha habilitado

### Controle de Ventoinhas
1. Selecionar modo de energia **Customizado**
2. Habilitar controle **Manual** no cartão da ventoinha desejada
3. Usar sliders ou botões predefinidos (0%, 25%, 50%, 75%, 100%)
4. Mudanças aplicadas imediatamente

### G-Mode
- **Propósito**: Resfriamento máximo para jogos/cargas intensivas
- **Efeito**: Substitui o modo de energia atual, define ventoinhas no máximo
- **Alternar**: Via botão da interface principal ou menu da bandeja do sistema

## Solução de Problemas

### Problemas Comuns

#### "G15 Daemon obrigatório"
**Solução**: Primeiro iniciar o daemon:
```bash
sudo python3 g15_daemon.py
```
Depois executar a interface em outro terminal:
```bash
python3 g15_controller_commander.py
```

#### "ERROR: ACPI path not found"
**Solução**: Instalar e carregar o módulo acpi_call:
```bash
sudo apt install acpi-call-dkms  # Ubuntu/Debian
sudo modprobe acpi_call
```

#### "No Dell hwmon sensors found"
**Solução**: Este é um aviso, não um erro. A aplicação usará apenas modo ACPI.

#### Aplicação não mostra temperaturas reais
**Solução**: Verificar se os sensores hwmon são detectados:
```bash
sensors | grep -E "(dell|fan|temp)"
```

#### Problemas de interface Qt
**Solução**: Instalar dependências Qt:
```bash
sudo apt install libxcb-cursor0 # Ubuntu/Debian
```

### Logs do Daemon
O daemon mantém logs em `/var/log/g15-daemon.log` para debug:
```bash
sudo tail -f /var/log/g15-daemon.log
```

## Desinstalação

Para remover completamente o Dell G15 Control Center:

```bash
cd g15-controller-commander
sudo ./uninstall.sh
```

**O desinstalador remove:**
- Todos os arquivos da aplicação (`/opt/g15-controller/`)
- Serviço systemd (`g15-daemon.service`)
- Atalho do menu de aplicações
- Mapeamento da tecla G-Mode
- Configurações e logs
- Opcionalmente remove dependências não utilizadas

## Estrutura do Projeto
```
g15-controller-commander/
├── src/                        # Código fonte
│   ├── g15_controller_commander.py  # Interface cliente (PyQt6)
│   ├── g15_daemon.py               # Daemon de controle (root)
│   └── __init__.py
├── system/                     # Arquivos de sistema
│   ├── g15-daemon.service      # Serviço systemd
│   ├── g15-controller-commander.desktop  # Atalho desktop
│   ├── g15-controller-commander.svg      # Ícone
│   └── 90-dell-g15-gmode.hwdb  # Mapeamento tecla G-Mode
├── install.sh                  # Instalador automático
├── uninstall.sh               # Desinstalador
├── pyproject.toml             # Metadados modernos
├── requirements.txt           # Dependências Python
└── README.md                  # Este arquivo
```

## Aviso Legal

Este software controla diretamente componentes de hardware. Use por sua própria conta e risco. Os autores não são responsáveis por qualquer dano ao hardware que possa ocorrer com o uso deste software.

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.