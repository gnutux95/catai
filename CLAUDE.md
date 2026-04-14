# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CATAI Linux is a Pygame-based desktop pet app — pixel art cats that roam your desktop and chat via Ollama LLM. It's a Linux port of the macOS original (wil-pe/CATAI), written as a single Python file (`catai.py`, ~2100 lines). Version 3.0.0 adds X11 transparency, panel detection, macOS-style interaction model, warm parchment UI, and sound effects.

## Running

```bash
python3 catai.py                          # default (1 orange cat, auto-detect mode)
python3 catai.py --cats orange black grey  # spawn specific cats
python3 catai.py --model qwen2.5:3b       # choose Ollama model
python3 catai.py --scale 4                 # sprite scale (1-6)
python3 catai.py --fullscreen             # fullscreen mode
python3 catai.py --download               # download sprites from GitHub
python3 catai.py --opaque                 # force opaque background
python3 catai.py --mode desktop           # force transparent overlay mode
python3 catai.py --mode window            # force opaque window mode
python3 catai.py --sound                  # enable sound effects
python3 catai.py --no-sound               # disable sound effects
```

Dependencies: `pygame`, `pillow`, `requests`, `python-xlib` (optional, for X11 features) (+ SDL2 libraries). Install script for Fedora/Debian: `bash install.sh`.

No tests, no build step, no linter configured.

## Architecture (Single File)

Everything lives in `catai.py`. The major sections, top to bottom:

- **Constants** — `CAT_COLORS` dict of `CatColorDef` objects defines the 6 cat colors/names/personalities/HSB tinting params. `ANIM_FOLDERS` maps state names to sprite folder names. `ONE_SHOT_STATES` for animations that play to completion.
- **Localization** — `L10N_STRINGS` and `L10N_MEOWS` per-language translations (FR/EN/ES). `l10n()` helper and `random_meow()`.
- **Sound System** — `SoundManager` class generates procedural sounds (meow, purr, click) using numpy or simple tone generation. Gracefully disabled if mixer fails.
- **HSB Tinting** — `rgb_to_hsb()`, `hsb_to_rgb()`, `tint_surface_hsb()` perform per-pixel HSB color transformation for non-orange cats (matches original Swift logic exactly).
- **Sprite generation** — `make_cat_surface()` creates fallback pixel-art cats when PNG sprites aren't available.
- **Sprite loading** — `load_sprite()` loads from `sprites/<color>/<state>/<direction>/frame_NNN.png` with caching. Rotation sprites for idle/sleeping from `sprites/<color>/rotations/<direction>.png`. Non-orange cats are HSB-tinted from orange sprites.
- **Pixel font** — `PIXEL_FONT_DATA` is a hand-encoded 5x7 bitmap font. `render_pixel_text()` and `wrap_pixel_text()` handle all text rendering (no TTF dependency).
- **ChatBubble** — Click-to-open chat overlay per cat (warm parchment style with triangular tail, like macOS). Streams responses from Ollama. Memory keyed by per-cat UUID.
- **SettingsPanel** — Centered panel with warm parchment theme: language flags with highlight, color bubbles (add/select cats, × to remove), cat preview sprite, personality display, name editing, continuous scale slider, model selector (click to cycle). Like macOS ColorBubblesView + PixelSlider.
- **Cat entity** — `Cat` dataclass with state machine (7 states: `idle`, `walking`, `sleeping`, `eating`, `drinking`, `angry`, `waking`). One-shot animations play to completion. Direction is a cardinal string (`"east"`, `"west"`, etc.). Click vs drag detection with 5px threshold.
- **Context menu** — Right-click on cat shows pixel-art menu (Settings, Quit), like macOS.
- **Download** — `--download` flag fetches sprites from the CATAI GitHub repo.
- **Transparency** — Dual-mode: Desktop mode (X11 with compositor: transparent overlay, panel detection via `_NET_WORKAREA`), Window mode (Wayland/fallback: opaque background with scanlines). Auto-detected at startup.
- **Main loop** — Pygame event loop at 60 FPS. Left-click opens chat, left-drag moves cat (5px threshold to distinguish), right-click shows context menu. Ctrl+S opens settings, Ctrl+Q quits.

## Dual-Mode Rendering

- **Desktop mode** (default on X11): Full-screen borderless transparent overlay. Cats walk on the panel/taskbar (like macOS dock). Background is transparent (see desktop). X11 window properties set via python-xlib.
- **Window mode** (default on Wayland, or with `--opaque`/`--mode window`): Dark background with scanlines. HUD bar at bottom.

## Interaction Model (matches macOS)

- **Left-click** on cat: toggle chat bubble (if moved < 5px, it's a click)
- **Left-drag** on cat: move cat (if moved >= 5px, it's a drag)
- **Right-click** on cat: context menu (Settings, Quit)
- **Ctrl+S**: toggle settings panel
- **Ctrl+Q**: quit

## Sprite Directory

```
sprites/<cat_color>/<state>/<direction>/frame_NNN.png   # animations
sprites/<cat_color>/rotations/<direction>.png            # idle/sleeping
```

States: `angry`, `drinking`, `eating`, `running-8-frames`, `waking-getting-up`
Directions: `east`, `north`, `north-east`, `north-west`, `south`, `south-east`, `south-west`, `west`

On first launch, `_ensure_rotations()` copies sprites from `ori/CATAI/cute_orange_cat/` if they don't exist in `sprites/`.

## Ollama Integration

- Connects to `http://localhost:11434` (default Ollama endpoint)
- Streaming chat via `POST /api/chat` with `stream: true`
- Each cat gets its own `system` prompt from `CatColorDef.prompt()` (language-aware)
- Conversation memory capped at 20 messages per cat (`MAX_MEMORY`), keyed by per-cat UUID
- Ollama availability checked every 5 seconds on main thread
- Available models refreshed every 30 seconds for the settings panel dropdown

## Key Design Details

- The entire UI uses warm parchment colors (`0xF2, 0xE6, 0xCC` fill, `0x4C, 0x33, 0x1A` borders) matching the macOS PixelBorder style.
- HSB tinting: orange sprites are the only source art. Other colors are derived via per-pixel hue shift, saturation multiply, and brightness offset (matching the original Swift `tintSprite()`).
- One-shot animations (`eating`, `drinking`, `angry`, `waking`) play to completion then auto-transition to `idle`.
- `waking` state plays when a sleeping cat wakes up (matches original).
- Memory is keyed by `cat.id` (UUID), not color — multiple cats of the same color have separate conversations.
- Chat input capped at 200 characters. Display shows last 40 chars.
- Sound effects are procedurally generated (no external WAV files needed). Uses numpy if available, falls back to simple tone generation.
- Panel/taskbar height detected via `_NET_WORKAREA` on X11 (python-xlib). On Wayland, defaults to 0.
- Cats walk on the panel/taskbar like the macOS version (feet on the dock).
- X11 transparency uses `_NET_WM_WINDOW_TYPE_DESKTOP` and `_NET_WM_STATE_BELOW` window properties.
- Window tracking on X11 uses `_NET_ACTIVE_WINDOW` (for potential title-bar walking, not yet implemented in behavior).