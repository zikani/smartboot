# Installation Guide

This guide provides detailed installation instructions for SmartBoot on different operating systems.

## System Requirements

### Minimum Requirements
- **Python**: 3.7 or higher
- **RAM**: 512 MB minimum
- **Disk Space**: 100 MB for application
- **USB Drive**: At least 4 GB for bootable media creation

### Supported Operating Systems
- Windows 7/8/10/11 (x64)
- Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- macOS 10.14 (Mojave) or later

## Installation

### Windows

#### Option 1: Using pip (Recommended)

1. Install Python 3.7 or higher from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Open Command Prompt or PowerShell
4. Install SmartBoot:
   ```bash
   pip install smartboot
   ```
5. Run SmartBoot:
   ```bash
   smartboot
   ```

#### Option 2: From Source

1. Install Python 3.7 or higher
2. Install Git from [git-scm.com](https://git-scm.com/download/win)
3. Clone the repository:
   ```bash
   git clone https://github.com/zikani/smartboot.git
   cd smartboot
   ```
4. Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
5. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
6. Run the application:
   ```bash
   python main.py
   ```

### Linux

#### Debian/Ubuntu

```bash
# Install dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv git

# Clone repository
git clone https://github.com/zikani/smartboot.git
cd smartboot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

#### Fedora/RHEL

```bash
# Install dependencies
sudo dnf install python3 python3-pip git

# Clone repository
git clone https://github.com/zikani/smartboot.git
cd smartboot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

#### Arch Linux

```bash
# Install dependencies
sudo pacman -S python python-pip git

# Clone repository
git clone https://github.com/zikani/smartboot.git
cd smartboot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

### macOS

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3
brew install python3 git

# Clone repository
git clone https://github.com/zikani/smartboot.git
cd smartboot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

## Dependencies

SmartBoot requires the following Python packages:

- **PyQt5** (>=5.15.0) - GUI framework
- **Python standard library modules** - os, subprocess, platform, tempfile, shutil, logging, typing

See `requirements.txt` for the complete list.

## Troubleshooting

### Windows

#### "python is not recognized"
- Ensure Python is installed and added to PATH
- Restart Command Prompt after installation

#### "Access Denied" Errors
- Run Command Prompt/PowerShell as Administrator
- Some operations require elevated privileges

#### USB Device Not Detected
- Ensure USB drive is properly connected
- Try a different USB port
- Run as Administrator

### Linux

#### Permission Denied
- Run with sudo: `sudo python main.py`
- Or add user to appropriate groups (disk, plugdev)

#### USB Device Not Detected
- Ensure udev rules are properly configured
- Check if USB is mounted: `lsblk`
- Try running with sudo

### macOS

#### "Command Not Found"
- Ensure Homebrew is properly installed
- Restart terminal after installation

#### USB Device Not Detected
- Grant Full Disk Access in System Preferences
- Run with sudo: `sudo python main.py`

## Uninstallation

### Windows (pip)
```bash
pip uninstall smartboot
```

### From Source
Simply delete the cloned directory:
```bash
# Windows
rmdir /s smartboot

# Linux/macOS
rm -rf smartboot
```

## Upgrading

### From pip
```bash
pip install --upgrade smartboot
```

### From Source
```bash
cd smartboot
git pull
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt --upgrade
```

## Portable Version (Windows)

A portable version (no installation required) can be created by:

1. Download the source code
2. Install dependencies to a local directory
3. Use a Python portable distribution
4. Run directly from the directory

See the [Building](building.md) guide for more details.
