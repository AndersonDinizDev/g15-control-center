# Dell G15 Controller Commander

Centro de controle moderno e repleto de recursos para notebooks gamer Dell G15 executando Linux. Fornece monitoramento de hardware em tempo real e controle de ventoinhas com uma interface PyQt6 elegante.

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
- **Integração de Hardware**: Chamadas ACPI diretas + fallback para sensores hwmon

## Requisitos

### Requisitos do Sistema
- **Sistema Operacional**: Linux (testado no Linux Mint, Ubuntu, Debian)
- **Hardware**: Notebook gamer Dell G15 (5511, 5515, 5520, 5525, 5530, 5535)
- **Python**: 3.8 ou superior
- **Privilégios**: Acesso root necessário para controle de hardware

### Dependências
- **acpi-call-dkms**: Comunicação ACPI com BIOS
- **policykit-1**: Privilégios de root
- **libxcb-cursor0**: Interface Qt
- **PyQt6**: Framework de GUI
- **psutil**: Informações do sistema (opcional)

## Instalação

### 1. Instalar Dependências do Sistema

#### No Ubuntu/Debian/Linux Mint:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv acpi-call-dkms policykit-1 libxcb-cursor0
```

#### No Fedora:
```bash
sudo dnf install python3 python3-pip acpi_call polkit libxcb
```

#### No Arch Linux:
```bash
sudo pacman -S python python-pip polkit libxcb
yay -S acpi_call # ou instalar do AUR
```

### 2. Clonar o Repositório
```bash
git clone https://github.com/AndersonDinizDev/g15-controller-commander.git
cd g15-controller-commander
```

### 3. Configurar Ambiente Python
```bash
# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate

# Instalar dependências Python
pip install -r requirements.txt
```

### 4. Carregar Módulo ACPI
```bash
sudo modprobe acpi_call
```

## Uso

### Início Rápido
```bash
# Certifique-se de estar no diretório do projeto
cd g15-controller-commander

# Ativar ambiente virtual (se não estiver ativo)
source venv/bin/activate

# Executar a aplicação com privilégios root
sudo python3 g15_controller_commander.py
```

### Notas Importantes
- **Privilégios root são obrigatórios** para controle de hardware
- A aplicação **sairá com erro** se não executada como root
- Certifique-se de que o módulo `acpi_call` esteja carregado antes de executar

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

#### "ERROR: This application requires root privileges"
**Solução**: Sempre executar com `sudo`:
```bash
sudo python3 g15_controller_commander.py
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

### Modo Debug
Executar com saída verbosa para diagnosticar problemas:
```bash
sudo python3 g15_controller_commander.py --verbose  # Se implementado
```

## Estrutura do Projeto
```
g15-controller-commander/
├── g15_controller_commander.py  # Aplicação principal
├── requirements.txt             # Dependências Python
├── README.md                   # Este arquivo
├── .gitignore                  # Regras de ignorar Git
└── venv/                       # Ambiente virtual (criado pelo usuário)
```

## Aviso Legal

Este software controla diretamente componentes de hardware. Use por sua própria conta e risco. Os autores não são responsáveis por qualquer dano ao hardware que possa ocorrer com o uso deste software.

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.