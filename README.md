# CATAI Linux

Linux port of [wil-pe/CATAI](https://github.com/wil-pe/CATAI) — pixel art desktop cats, powered by Ollama LLM.

## Quickstart

```bash
# 1. Install dependencies
bash install.sh

# 2. (Optional) Install Ollama for AI chat
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
ollama pull qwen2.5:3b

# 3. (Optional) Download high-quality sprites
python3 catai.py --download

# 4. Run!
python3 catai.py
```

Without Ollama, cats roam the desktop but stay silent. Without `--download`, procedurally generated sprites are used.

| Action | Control |
|--------|---------|
| Chat with a cat | Left click |
| Move a cat | Right click + drag |
| Settings | Ctrl+S |
| Quit | Ctrl+Q |

## Manual Installation (Fedora 43)

```bash
# System dependencies
sudo dnf install python3 python3-pip SDL2 SDL2_image SDL2_mixer SDL2_ttf

# Python dependencies
pip install pygame pillow requests --user

# Run
python3 catai.py
```

## Usage

| Action | Control |
|--------|---------|
| Open chat | Left click on a cat |
| Move cat | Right click + drag |
| Settings | Ctrl+S or [Settings] button at bottom right |
| Quit | Ctrl+Q |

## Options

```bash
# Spawn specific cats
python3 catai.py --cats orange black grey

# Choose Ollama model
python3 catai.py --model qwen2.5:3b

# Change sprite scale (1-6)
python3 catai.py --scale 4

# Fullscreen
python3 catai.py --fullscreen

# Download sprites from GitHub
python3 catai.py --download

# Opaque background (disable transparency)
python3 catai.py --opaque
```

## Cats and Personalities

| Color | Name FR | Name EN | Name ES | Personality |
|-------|---------|---------|---------|-------------|
| orange | Citrouille | Pumpkin | Calabaza | Playful & mischievous |
| black | Ombre | Shadow | Sombra | Mysterious & philosophical |
| white | Neige | Snow | Nieve | Elegant & poetic |
| grey | Einstein | Einstein | Einstein | Wise & scholarly |
| brown | Indiana | Indiana | Indiana | Adventurous storyteller |
| cream | Caramel | Caramel | Caramelo | Cuddly & comforting |

## Multilingual

The interface supports 3 languages: French, English, Spanish.
Switch language in Settings (Ctrl+S) by clicking [FR], [EN], or [ES].

Cat names, Ollama personalities, and meows adapt to the selected language.

## Ollama (required for AI chat)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start the server
ollama serve &

# Download a lightweight model (recommended)
ollama pull qwen2.5:3b
# or
ollama pull llama3.2:3b
```

Without Ollama, cats roam the desktop but stay silent.

## Custom Sprites

Place your PNGs in `./sprites/<color>/<state>/<direction>/frame_NNN.png`.

Supported states: `angry`, `drinking`, `eating`, `running-8-frames`, `waking-getting-up`
Directions: `east`, `north`, `north-east`, `north-west`, `south`, `south-east`, `south-west`, `west`
Rotations (idle/sleeping): `./sprites/<color>/rotations/<direction>.png`

Format: PNG 68x68 px with transparency (RGBA), named `frame_000.png` to `frame_NNN.png`.

The original CATAI macOS sprites (MIT) are compatible. Use `--download` to fetch them automatically.

Non-orange cats use an HSB tinting system to colorize orange sprites — no separate sprites needed for each color.

## Configuration Files

- `~/.catai_settings.json` — preferences (model, scale, active cats, language)
- `~/.catai_memory.json` — conversation history (per unique cat)

## Differences from CATAI macOS

| Feature | macOS | Linux |
|---------|-------|-------|
| Real PNG sprites | 368 sprites | via --download or ori/ |
| HSB tinting for colors | | |
| Ollama integration | | |
| Personalities | | |
| Conversation memory | 20 msgs | 20 msgs (~/.catai_memory.json) |
| Dock overlay | AppKit | borderless window (transparent on X11) |
| Native Wayland | N/A | via SDL2 (XWayland) |
| Random meow bubbles | | |
| Multilingual FR/EN/ES | | |
| Animation states | 6 states | 7 states (idle, walking, sleeping, eating, drinking, angry, waking) |
| 8 directions | | |
| Ollama model selection | dropdown | click to cycle |
| Cat name editing | | |
| Sprite download | manual | --download |

## Credits

This project is a Linux port of [CATAI](https://github.com/wil-pe/CATAI) by **wil-pe**.

Code and assets reused from the original project (MIT):
- **Pixel art sprites** — 368 orange cat sprites (`cute_orange_cat/`) drawn by wil-pe, used via `--download` or copied from `ori/CATAI/`
- **HSB tinting logic** — The `tintSprite()` colorization algorithm from wil-pe/CATAI's `cat.swift` was rewritten in Python to produce black, white, grey, brown, and cream variants from orange sprites
- **Cat personalities and names** — Citrouille, Ombre, Neige, Einstein, Indiana, Caramel and their Ollama prompts are adapted from the original project
- **Animation structure** — States (idle, walking, sleeping, eating, drinking, angry, waking) and 8 directions follow CATAI macOS's animation system

## License

This project is distributed under the **GNU General Public License v3** (GPLv3).

Derivative elements from the original [wil-pe/CATAI](https://github.com/wil-pe/CATAI) project remain under their original **MIT** license. The `LICENSE` file contains the full text of both licenses.