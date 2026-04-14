#!/usr/bin/env bash
# CATAI Linux — Installation script for Fedora 43+
set -e

echo "CATAI Linux installer"
echo "====================="

# Detect distro
if command -v dnf &>/dev/null; then
    echo "Fedora/RHEL detected"
    sudo dnf install -y python3 python3-pip \
        SDL2 SDL2_image SDL2_mixer SDL2_ttf \
        python3-pygame 2>/dev/null || true
elif command -v apt &>/dev/null; then
    echo "Debian/Ubuntu detected"
    sudo apt install -y python3 python3-pip \
        libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
        python3-xlib
fi

# Python deps
echo "Installing Python dependencies..."
pip install --user pygame pillow requests python-xlib

# Check Ollama
if ! command -v ollama &>/dev/null; then
    echo ""
    echo "Ollama not found. To enable AI chat:"
    echo "   curl -fsSL https://ollama.ai/install.sh | sh"
    echo "   ollama serve &"
    echo "   ollama pull qwen2.5:3b"
else
    echo "Ollama found: $(ollama --version 2>/dev/null || echo 'installed')"
fi

echo ""
echo "Done! Launch with:"
echo "   python3 catai.py"
echo ""
echo "Options:"
echo "   python3 catai.py --cats orange black grey"
echo "   python3 catai.py --model qwen2.5:3b --scale 4"
echo "   python3 catai.py --sound          # Enable sound effects"
echo "   python3 catai.py --mode desktop   # Force transparent overlay"
echo "   python3 catai.py --mode window    # Force opaque window"