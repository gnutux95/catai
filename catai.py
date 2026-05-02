#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 CATAI Linux contributors
# SPDX-FileCopyrightText: 2025 wil-pe (MIT-licensed original CATAI sprites and HSB tinting logic)
"""
CATAI Linux — Port of wil-pe/CATAI for Linux
Pixel art desktop cats with Ollama LLM chat
Requires: pygame, pillow, requests
Install:  pip install pygame pillow requests
Sprites:  Place PNG frames in ./sprites/<cat_color>/<state>/<direction>/
          or run with --download to fetch from GitHub
"""

import pygame
import sys
import os
import json
import math
import time
import random
import threading
import requests
import argparse
import subprocess
import zipfile
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from PIL import Image
import io
import base64
import ctypes

# ──────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────

VERSION       = "3.0.0-linux"
SPRITE_DIR    = Path(__file__).parent / "sprites"
MEMORY_FILE   = Path.home() / ".catai_memory.json"
SETTINGS_FILE = Path.home() / ".catai_settings.json"
OLLAMA_URL    = "http://localhost:11434"
SCALE         = 3          # pixel art scale factor (3x = 204×204 px cat)
CAT_BASE_SIZE = 68         # original sprite px
FPS           = 10         # animation FPS (matches original 10 FPS)
WALK_SPEED    = 1.5        # pixels/frame
MAX_MEMORY    = 20         # messages per cat
BUBBLE_DURATION = 4.0      # seconds for random meow bubbles
CHAT_BUBBLE_W = 340
CHAT_INPUT_H  = 36
MAX_INPUT_LEN = 200        # max chars in chat input
DRAG_THRESHOLD = 5         # pixels to distinguish click from drag
SOUND_DIR     = Path(__file__).parent / "sounds"

# Directions matching the original sprite sheet
DIRECTIONS = ["south", "south-east", "east", "north-east",
              "north", "north-west", "west", "south-west"]

# Map walking direction (dx, dy) to nearest cardinal direction
DIR_MAP_8 = {
    (0, 1):   "south",
    (1, 1):   "south-east",
    (1, 0):   "east",
    (1, -1):  "north-east",
    (0, -1):  "north",
    (-1, -1): "north-west",
    (-1, 0):  "west",
    (-1, 1):  "south-west",
}

# Animation states: maps internal state name to sprite folder name
ANIM_FOLDERS = {
    "walking": "running-8-frames",
    "eating": "eating",
    "drinking": "drinking",
    "angry": "angry",
    "waking": "waking-getting-up",
}

# One-shot animations (play to completion, then return to idle)
ONE_SHOT_STATES = {"eating", "drinking", "angry", "waking"}

# ──────────────────────────────────────────────────────────
# LOCALIZATION
# ──────────────────────────────────────────────────────────

L10N_STRINGS = {
    "title":     {"fr": ":: REGlAGES ::", "en": ":: SETTINGS ::", "es": ":: AJUSTES ::"},
    "cats":      {"fr": "MES CHATS", "en": "MY CATS", "es": "MIS GATOS"},
    "name":      {"fr": "Nom:", "en": "Name:", "es": "Nombre:"},
    "size":      {"fr": "TAILLE", "en": "SIZE", "es": "TAMANO"},
    "model":     {"fr": "MODELE OLLAMA", "en": "OLLAMA MODEL", "es": "MODELO OLLAMA"},
    "quit":      {"fr": "Quitter", "en": "Quit", "es": "Salir"},
    "settings":  {"fr": "Reglages...", "en": "Settings...", "es": "Ajustes..."},
    "talk":      {"fr": "Parle au chat...", "en": "Talk to the cat...", "es": "Habla al gato..."},
    "hi":        {"fr": "Miaou! ~(=^..^=)~", "en": "Meow! ~(=^..^=)~", "es": "Miau! ~(=^..^=)~"},
    "loading":   {"fr": "Chargement...", "en": "Loading...", "es": "Cargando..."},
    "no_ollama": {"fr": "(Ollama indisponible)", "en": "(Ollama unavailable)", "es": "(Ollama no disponible)"},
    "err":       {"fr": "Mrrp... pas de connexion", "en": "Mrrp... no connection", "es": "Mrrp... sin conexion"},
    "lang_label":{"fr": "LANGUE", "en": "LANGUAGE", "es": "IDIOMA"},
    "say":       {"fr": "Dis quelque chose...", "en": "Say something...", "es": "Di algo..."},
    "ollama_ok": {"fr": "Ollama: OK", "en": "Ollama: OK", "es": "Ollama: OK"},
    "ollama_off":{"fr": "Ollama: OFF", "en": "Ollama: OFF", "es": "Ollama: OFF"},
    "click_cat": {"fr": "Cliquer pour parler", "en": "Click cat to chat", "es": "Click para hablar"},
    "drag":      {"fr": "Glisser pour deplacer", "en": "Drag to move", "es": "Arrastra para mover"},
    "close":     {"fr": "Fermer", "en": "Close", "es": "Cerrar"},
}

L10N_MEOWS = {
    "fr": ["Miaou~", "Mrrp!", "Prrrr...", "Miaou miaou!", "Nyaa~", "*ronron*", "Mew!", "Prrrt?"],
    "en": ["Meow~", "Mrrp!", "Purrrr...", "Meow meow!", "Nyaa~", "*purr*", "Mew!", "Prrrt?"],
    "es": ["Miau~!", "Mrrp!", "Purrrr...", "Miau miau!", "Nyaa~", "*ronroneo*", "Mew!", "Prrrt?"],
}


def l10n(key: str, lang: str = "en") -> str:
    return L10N_STRINGS.get(key, {}).get(lang, L10N_STRINGS.get(key, {}).get("en", key))


def random_meow(lang: str = "en") -> str:
    meows = L10N_MEOWS.get(lang, L10N_MEOWS["en"])
    return random.choice(meows)


# ──────────────────────────────────────────────────────────
# SOUND SYSTEM
# ──────────────────────────────────────────────────────────

class SoundManager:
    """Manages procedural sound effects for CATAI."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.mixer_ok = False
        self.sounds = {}
        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.mixer_ok = True
            self._generate_sounds()
        except Exception:
            self.mixer_ok = False

    def _generate_sounds(self):
        """Generate procedural sound effects (meow, purr, click)."""
        import struct
        import array

        try:
            self.sounds["meow"] = self._make_meow_sound()
            self.sounds["purr"] = self._make_purr_sound()
            self.sounds["click"] = self._make_click_sound()
        except Exception:
            pass

    def _make_meow_sound(self) -> Optional[pygame.mixer.Sound]:
        """Generate a simple meow sound."""
        try:
            import numpy as np
            sample_rate = 22050
            duration = 0.3
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

            # Meow: rising then falling frequency
            freq = 600 + 400 * np.sin(np.pi * t / duration) - 200 * t / duration
            phase = np.cumsum(2 * np.pi * freq / sample_rate)
            wave = 0.3 * np.sin(phase)

            # Apply envelope (attack-decay)
            envelope = np.ones_like(t)
            attack = int(0.02 * sample_rate)
            decay = int(0.1 * sample_rate)
            envelope[:attack] = np.linspace(0, 1, attack)
            envelope[-decay:] = np.linspace(1, 0, decay)
            wave *= envelope

            # Convert to 16-bit signed integer
            wave_int = (wave * 32767).astype(np.int16)
            sound = pygame.mixer.Sound(buffer=wave_int.tobytes())
            sound.set_volume(0.4)
            return sound
        except ImportError:
            return self._make_simple_tone(500, 0.25, 0.3)

    def _make_purr_sound(self) -> Optional[pygame.mixer.Sound]:
        """Generate a purring sound (low rumble)."""
        try:
            import numpy as np
            sample_rate = 22050
            duration = 0.5
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

            # Purr: low frequency with modulation
            freq = 25 + 5 * np.sin(2 * np.pi * 3 * t)  # ~25Hz with 3Hz modulation
            phase = np.cumsum(2 * np.pi * freq / sample_rate)
            wave = 0.15 * np.sin(phase)

            # Add some harmonics
            wave += 0.1 * np.sin(2 * phase)
            wave += 0.05 * np.sin(3 * phase)

            # Envelope
            envelope = np.ones_like(t)
            attack = int(0.05 * sample_rate)
            decay = int(0.1 * sample_rate)
            envelope[:attack] = np.linspace(0, 1, attack)
            envelope[-decay:] = np.linspace(1, 0, decay)
            wave *= envelope

            wave_int = (wave * 32767).astype(np.int16)
            sound = pygame.mixer.Sound(buffer=wave_int.tobytes())
            sound.set_volume(0.3)
            return sound
        except ImportError:
            return self._make_simple_tone(100, 0.5, 0.2)

    def _make_click_sound(self) -> Optional[pygame.mixer.Sound]:
        """Generate a soft UI click sound."""
        try:
            import numpy as np
            sample_rate = 22050
            duration = 0.05
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

            freq = 1000
            wave = 0.2 * np.sin(2 * np.pi * freq * t)

            # Quick decay
            envelope = np.exp(-t * 60)
            wave *= envelope

            wave_int = (wave * 32767).astype(np.int16)
            sound = pygame.mixer.Sound(buffer=wave_int.tobytes())
            sound.set_volume(0.3)
            return sound
        except ImportError:
            return self._make_simple_tone(800, 0.05, 0.2)

    def _make_simple_tone(self, freq: int, duration: float, volume: float) -> Optional[pygame.mixer.Sound]:
        """Fallback: generate a simple tone without numpy."""
        try:
            sample_rate = 22050
            n_samples = int(sample_rate * duration)
            buf = bytearray(n_samples * 2)
            for i in range(n_samples):
                t = i / sample_rate
                val = int(volume * 32767 * math.sin(2 * math.pi * freq * t)
                          * max(0, 1 - t / duration))
                buf[i*2] = val & 0xFF
                buf[i*2+1] = (val >> 8) & 0xFF
            sound = pygame.mixer.Sound(buffer=bytes(buf))
            sound.set_volume(0.3)
            return sound
        except Exception:
            return None

    def play(self, name: str):
        """Play a named sound effect."""
        if not self.enabled or not self.mixer_ok:
            return
        snd = self.sounds.get(name)
        if snd:
            try:
                snd.play()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────
# CAT COLORS, PERSONALITIES & HSB TINTING
# ──────────────────────────────────────────────────────────

@dataclass
class CatColorDef:
    id: str
    color: tuple           # (R, G, B) display color for UI
    hue_shift: float       # HSB hue shift for tinting (-1..1)
    sat_mul: float         # HSB saturation multiplier
    bri_off: float         # HSB brightness offset
    names: dict            # {"fr": "...", "en": "...", "es": "..."}
    traits: dict           # per-language trait string
    skills: dict           # per-language skill string

    def prompt(self, name: str, lang: str) -> str:
        t = self.traits.get(lang, self.traits.get("en", ""))
        s = self.skills.get(lang, self.skills.get("en", ""))
        if lang == "en":
            return f"You are a little {t} cat named {name}. {s} Respond briefly with cat sounds (meow, purr, mrrp). Max 2-3 sentences."
        elif lang == "es":
            return f"Eres un gatito {t} llamado {name}. {s} Responde brevemente con sonidos de gato (miau, purr, mrrp). Maximo 2-3 frases."
        else:
            return f"Tu es un petit chat {t} nomme {name}. {s} Reponds brievement avec des sons de chat (miaou, purr, mrrp). Max 2-3 phrases."

    def get_name(self, lang: str) -> str:
        return self.names.get(lang, self.names.get("en", self.id))


CAT_COLORS: Dict[str, CatColorDef] = {
    c.id: c for c in [
        CatColorDef(id="orange", color=(255, 140, 0),
            hue_shift=0, sat_mul=1, bri_off=0,
            names={"fr": "Citrouille", "en": "Pumpkin", "es": "Calabaza"},
            traits={"fr": "joueur et espiegle", "en": "playful and mischievous", "es": "jugueton y travieso"},
            skills={"fr": "Tu adores les blagues et jeux de mots.", "en": "You love jokes and puns.", "es": "Adoras los chistes y juegos de palabras."}),
        CatColorDef(id="black", color=(40, 40, 60),
            hue_shift=0, sat_mul=0.1, bri_off=-0.45,
            names={"fr": "Ombre", "en": "Shadow", "es": "Sombra"},
            traits={"fr": "mysterieux et philosophe", "en": "mysterious and philosophical", "es": "misterioso y filosofo"},
            skills={"fr": "Tu poses des questions profondes et aimes reflechir.", "en": "You ask deep questions and love to reflect.", "es": "Haces preguntas profundas y te encanta reflexionar."}),
        CatColorDef(id="white", color=(230, 240, 255),
            hue_shift=0, sat_mul=0.05, bri_off=0.4,
            names={"fr": "Neige", "en": "Snow", "es": "Nieve"},
            traits={"fr": "elegant et poetique", "en": "elegant and poetic", "es": "elegante y poetico"},
            skills={"fr": "Tu t'exprimes avec grace et tu adores la poesie.", "en": "You speak gracefully and love poetry.", "es": "Te expresas con gracia y adoras la poesia."}),
        CatColorDef(id="grey", color=(150, 150, 170),
            hue_shift=0, sat_mul=0, bri_off=-0.05,
            names={"fr": "Einstein", "en": "Einstein", "es": "Einstein"},
            traits={"fr": "sage et savant", "en": "wise and scholarly", "es": "sabio y erudito"},
            skills={"fr": "Tu expliques des faits scientifiques fascinants.", "en": "You explain fascinating scientific facts.", "es": "Explicas datos cientificos fascinantes."}),
        CatColorDef(id="brown", color=(139, 90, 43),
            hue_shift=-0.03, sat_mul=0.7, bri_off=-0.2,
            names={"fr": "Indiana", "en": "Indiana", "es": "Indiana"},
            traits={"fr": "aventurier et conteur", "en": "adventurous storyteller", "es": "aventurero y cuentacuentos"},
            skills={"fr": "Tu racontes des aventures extraordinaires.", "en": "You tell extraordinary adventures.", "es": "Cuentas aventuras extraordinarias."}),
        CatColorDef(id="cream", color=(255, 220, 160),
            hue_shift=0.02, sat_mul=0.3, bri_off=0.15,
            names={"fr": "Caramel", "en": "Caramel", "es": "Caramelo"},
            traits={"fr": "calin et reconfortant", "en": "cuddly and comforting", "es": "cariñoso y reconfortante"},
            skills={"fr": "Tu remontes le moral avec tendresse.", "en": "You comfort with tenderness.", "es": "Animas con ternura."}),
    ]
}


# ──────────────────────────────────────────────────────────
# HSB TINTING (matches original Swift per-pixel logic)
# ──────────────────────────────────────────────────────────

def rgb_to_hsb(r: float, g: float, b: float) -> tuple:
    """RGB [0..1] -> HSB (hue [0..1], saturation [0..1], brightness [0..1])."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    delta = mx - mn
    h = 0.0
    if delta > 0.001:
        if mx == r:
            h = ((g - b) / delta) % 6 / 6
        elif mx == g:
            h = ((b - r) / delta + 2) / 6
        else:
            h = ((r - g) / delta + 4) / 6
        if h < 0:
            h += 1.0
    s = delta / mx if mx > 0.001 else 0.0
    return (h, s, mx)


def hsb_to_rgb(h: float, s: float, b: float) -> tuple:
    """HSB -> RGB [0..1]."""
    c = b * s
    x = c * (1 - abs((h * 6) % 2 - 1))
    m = b - c
    sector = int(h * 6) % 6
    if sector == 0:   r1, g1, b1 = c, x, 0
    elif sector == 1: r1, g1, b1 = x, c, 0
    elif sector == 2: r1, g1, b1 = 0, c, x
    elif sector == 3: r1, g1, b1 = 0, x, c
    elif sector == 4: r1, g1, b1 = x, 0, c
    else:             r1, g1, b1 = c, 0, x
    return (r1 + m, g1 + m, b1 + m)


def tint_surface_hsb(surf: pygame.Surface, color_def: CatColorDef) -> pygame.Surface:
    """Apply HSB tinting to a sprite surface (matches original Swift logic exactly)."""
    if color_def.id == "orange":
        return surf

    w, h = surf.get_size()
    # Convert to PIL for pixel access, then back
    data = pygame.image.tostring(surf, "RGBA")
    img = Image.frombytes("RGBA", (w, h), data)
    pixels = img.load()

    hs = color_def.hue_shift
    sm = color_def.sat_mul
    bo = color_def.bri_off

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 3:
                continue

            af = a / 255.0
            # Unpremultiply
            rf = r / (255.0 * af) if af > 0 else 0
            gf = g / (255.0 * af) if af > 0 else 0
            bf = b / (255.0 * af) if af > 0 else 0

            hue, sat, bri = rgb_to_hsb(rf, gf, bf)

            nh = (hue + hs + 1) % 1.0
            ns = max(0, min(1, sat * sm))
            nb = max(0, min(1, bri + bo))

            nr, ng, nbb = hsb_to_rgb(nh, ns, nb)

            # Premultiply and write back
            pixels[x, y] = (
                int(max(0, min(255, nr * af * 255))),
                int(max(0, min(255, ng * af * 255))),
                int(max(0, min(255, nbb * af * 255))),
                a,
            )

    data = img.tobytes()
    return pygame.image.fromstring(data, (w, h), "RGBA")


# ──────────────────────────────────────────────────────────
# SPRITE GENERATION (fallback pixel art if no PNGs)
# ──────────────────────────────────────────────────────────

def make_cat_surface(color: tuple, state: str, frame: int, size: int) -> pygame.Surface:
    """Generate a simple pixel-art cat sprite procedurally."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = color
    dark = tuple(max(0, v - 60) for v in c[:3])
    u = size // 8  # unit

    # Body
    body_rect = pygame.Rect(u, 3*u, 6*u, 4*u)
    pygame.draw.ellipse(s, c, body_rect)

    # Head
    head_rect = pygame.Rect(2*u, u, 4*u, 3*u)
    pygame.draw.ellipse(s, c, head_rect)

    # Ears
    ear_pts_l = [(2*u, 2*u), (u, 0), (3*u, u)]
    ear_pts_r = [(6*u, 2*u), (7*u, 0), (5*u, u)]
    pygame.draw.polygon(s, c, ear_pts_l)
    pygame.draw.polygon(s, c, ear_pts_r)

    # Eyes
    eye_y = int(1.8 * u)
    blink = (state == "sleeping") or (frame % 8 == 0 and state == "idle")
    if blink:
        pygame.draw.line(s, dark, (3*u, eye_y), (3*u+u//2, eye_y), max(1, u//3))
        pygame.draw.line(s, dark, (5*u, eye_y), (5*u+u//2, eye_y), max(1, u//3))
    else:
        pygame.draw.circle(s, dark, (3*u + u//4, eye_y), u//3)
        pygame.draw.circle(s, dark, (5*u + u//4, eye_y), u//3)
        pygame.draw.circle(s, (10,10,10), (3*u + u//4, eye_y), u//5)
        pygame.draw.circle(s, (10,10,10), (5*u + u//4, eye_y), u//5)

    # Tail
    tail_offset = int(math.sin(frame * 0.5) * u) if state in ("idle", "sleeping") else 0
    tail_pts = [
        (7*u, 6*u),
        (8*u - tail_offset, 5*u),
        (7*u + u//2, 7*u),
    ]
    pygame.draw.lines(s, dark, False, tail_pts, max(1, u//2))

    # Walk animation
    if state == "walking":
        leg_phase = frame % 4
        leg_y = 7*u if leg_phase < 2 else 6*u + u//2
        pygame.draw.line(s, dark, (3*u, 7*u), (2*u + (1 if leg_phase < 2 else -1)*u//2, leg_y), max(1, u//2))
        pygame.draw.line(s, dark, (5*u, 7*u), (6*u + (-1 if leg_phase < 2 else 1)*u//2, leg_y), max(1, u//2))
    else:
        pygame.draw.line(s, dark, (3*u, 7*u), (2*u, 7*u+u//2), max(1, u//2))
        pygame.draw.line(s, dark, (5*u, 7*u), (6*u, 7*u+u//2), max(1, u//2))

    # Angry
    if state == "angry":
        pygame.draw.line(s, (200,50,50), (3*u, 3*u), (5*u, 3*u), max(1, u//3))

    # Eating
    if state == "eating":
        pygame.draw.circle(s, (255, 200, 80), (4*u, 8*u - (frame % 3)*u//2), u//2)

    # Drinking
    if state == "drinking":
        pygame.draw.circle(s, (100, 180, 255), (4*u, 8*u - (frame % 3)*u//2), u//2)

    return s


# ──────────────────────────────────────────────────────────
# SPRITE LOADER — tries real PNGs, falls back to procedural
# ──────────────────────────────────────────────────────────

# Cache: (cat_color, state, direction, size) -> list of loaded surfaces
_sprite_cache: Dict[Tuple[str, str, str, int], List[pygame.Surface]] = {}
# Cache: (cat_color, "rotation", direction, size) -> surface
_rotation_cache: Dict[Tuple[str, str, str, int], pygame.Surface] = {}
# Cache: (cat_color, state, direction) -> frame count
_frame_count_cache: Dict[Tuple[str, str, str], int] = {}


def _clear_sprite_caches():
    """Clear all sprite caches (call after scale change)."""
    _sprite_cache.clear()
    _rotation_cache.clear()


def _count_frames(cat_color: str, state: str, direction: str) -> int:
    """Count how many frames exist for a given state/direction.

    Falls back to orange directory if cat's own directory is missing.
    """
    key = (cat_color, state, direction)
    if key in _frame_count_cache:
        return _frame_count_cache[key]
    folder = ANIM_FOLDERS.get(state, state)
    path = SPRITE_DIR / cat_color / folder / direction
    # Fall back to orange if this color's directory doesn't exist
    if not path.is_dir() and cat_color != "orange":
        path = SPRITE_DIR / "orange" / folder / direction
    count = 0
    if path.is_dir():
        count = len([f for f in path.iterdir()
                     if f.is_file() and f.suffix.lower() == ".png"
                     and f.name.startswith("frame_")])
    _frame_count_cache[key] = count
    return count


def _load_animation_frames(cat_color: str, state: str, direction: str, size: int) -> list:
    """Load all frames for an animation state+direction, return list of surfaces.

    Tries the cat's own color directory first, then falls back to orange + HSB tint.
    """
    key = (cat_color, state, direction, size)
    if key in _sprite_cache:
        return _sprite_cache[key]

    color_def = CAT_COLORS.get(cat_color)
    folder = ANIM_FOLDERS.get(state, state)
    base_dir = SPRITE_DIR / cat_color / folder / direction

    # If cat's own directory doesn't exist, fall back to orange + tint
    use_tint = False
    if not base_dir.is_dir() and cat_color != "orange":
        base_dir = SPRITE_DIR / "orange" / folder / direction
        use_tint = True

    frames = []
    if base_dir.is_dir():
        png_files = sorted(base_dir.glob("frame_*.png"))
        for png_path in png_files:
            try:
                img = Image.open(png_path).convert("RGBA")
                img = img.resize((size, size), Image.NEAREST)
                data = img.tobytes()
                surf = pygame.image.fromstring(data, (size, size), "RGBA")
                # Apply HSB tinting for non-orange cats
                if (use_tint or (color_def and cat_color != "orange")):
                    surf = tint_surface_hsb(surf, color_def)
                frames.append(surf)
            except Exception:
                pass

    _sprite_cache[key] = frames
    return frames


def _load_rotation(cat_color: str, direction: str, size: int) -> Optional[pygame.Surface]:
    """Load a rotation (idle/sleeping) sprite."""
    key = (cat_color, "rotation", direction, size)
    if key in _rotation_cache:
        return _rotation_cache[key]

    color_def = CAT_COLORS.get(cat_color)

    # Try direct color folder first
    path = SPRITE_DIR / cat_color / "rotations" / f"{direction}.png"
    if not path.exists():
        # Try orange folder + tint
        path = SPRITE_DIR / "orange" / "rotations" / f"{direction}.png"

    if path.exists():
        try:
            img = Image.open(path).convert("RGBA")
            img = img.resize((size, size), Image.NEAREST)
            data = img.tobytes()
            surf = pygame.image.fromstring(data, (size, size), "RGBA")
            if color_def and cat_color != "orange":
                surf = tint_surface_hsb(surf, color_def)
            _rotation_cache[key] = surf
            return surf
        except Exception:
            pass

    _rotation_cache[key] = None
    return None


def load_sprite(cat_color: str, state: str, direction: str,
                frame: int, size: int) -> pygame.Surface:
    """Load the best available sprite for the given state/direction/frame.

    Priority:
    1. Real PNG animation frames
    2. Real PNG rotation image (for idle/sleeping)
    3. Procedural fallback
    """
    color_def = CAT_COLORS.get(cat_color, list(CAT_COLORS.values())[0])
    color = color_def.color

    # For animation states, try loading animation frames
    if state in ANIM_FOLDERS:
        frames = _load_animation_frames(cat_color, state, direction, size)
        if frames:
            idx = frame % len(frames)
            return frames[idx]

    # For idle/sleeping, try rotation image
    if state in ("idle", "sleeping"):
        rot = _load_rotation(cat_color, direction, size)
        if rot:
            return rot

    # Procedural fallback
    return make_cat_surface(color, state, frame, size)


# ──────────────────────────────────────────────────────────
# MEMORY
# ──────────────────────────────────────────────────────────

def load_memory() -> dict:
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except Exception:
            pass
    return {}


def save_memory(memory: dict):
    try:
        MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=2))
    except Exception:
        pass


def load_settings() -> dict:
    defaults = {
        "model": "llama3.2:3b",
        "scale": SCALE,
        "cats": ["orange"],
        "names": {},
        "lang": "en",
    }
    if SETTINGS_FILE.exists():
        try:
            s = json.loads(SETTINGS_FILE.read_text())
            defaults.update(s)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# OLLAMA
# ──────────────────────────────────────────────────────────

def ollama_available() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def ollama_models() -> list:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ollama_chat(
    model: str,
    system_prompt: str,
    messages: list,
    on_token,
    on_done,
    on_error,
):
    """Stream chat response from Ollama in a thread."""
    def run():
        try:
            payload = {
                "model": model,
                "system": system_prompt,
                "messages": messages,
                "stream": True,
            }
            with requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                stream=True,
                timeout=60,
            ) as resp:
                full = ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        full += token
                        on_token(token)
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
                on_done(full)
        except Exception as e:
            on_error(str(e))

    threading.Thread(target=run, daemon=True).start()


# ──────────────────────────────────────────────────────────
# PIXEL FONT RENDERER (tiny 5x7 bitmap font)
# ──────────────────────────────────────────────────────────

PIXEL_FONT_DATA = {
    'A': "01110 10001 10001 11111 10001 10001 10001",
    'B': "11110 10001 10001 11110 10001 10001 11110",
    'C': "01110 10001 10000 10000 10000 10001 01110",
    'D': "11110 10001 10001 10001 10001 10001 11110",
    'E': "11111 10000 10000 11110 10000 10000 11111",
    'F': "11111 10000 10000 11110 10000 10000 10000",
    'G': "01110 10001 10000 10111 10001 10001 01110",
    'H': "10001 10001 10001 11111 10001 10001 10001",
    'I': "01110 00100 00100 00100 00100 00100 01110",
    'J': "00111 00010 00010 00010 00010 10010 01100",
    'K': "10001 10010 10100 11000 10100 10010 10001",
    'L': "10000 10000 10000 10000 10000 10000 11111",
    'M': "10001 11011 10101 10001 10001 10001 10001",
    'N': "10001 11001 10101 10011 10001 10001 10001",
    'O': "01110 10001 10001 10001 10001 10001 01110",
    'P': "11110 10001 10001 11110 10000 10000 10000",
    'Q': "01110 10001 10001 10001 10101 10010 01101",
    'R': "11110 10001 10001 11110 10100 10010 10001",
    'S': "01111 10000 10000 01110 00001 00001 11110",
    'T': "11111 00100 00100 00100 00100 00100 00100",
    'U': "10001 10001 10001 10001 10001 10001 01110",
    'V': "10001 10001 10001 10001 10001 01010 00100",
    'W': "10001 10001 10001 10001 10101 11011 10001",
    'X': "10001 10001 01010 00100 01010 10001 10001",
    'Y': "10001 10001 01010 00100 00100 00100 00100",
    'Z': "11111 00001 00010 00100 01000 10000 11111",
    'a': "00000 00000 01110 00001 01111 10001 01111",
    'b': "10000 10000 11110 10001 10001 10001 11110",
    'c': "00000 00000 01110 10000 10000 10001 01110",
    'd': "00001 00001 01111 10001 10001 10001 01111",
    'e': "00000 00000 01110 10001 11111 10000 01110",
    'f': "00110 01001 01000 11100 01000 01000 01000",
    'g': "00000 01111 10001 10001 01111 00001 01110",
    'h': "10000 10000 11110 10001 10001 10001 10001",
    'i': "00100 00000 01100 00100 00100 00100 01110",
    'j': "00010 00000 00110 00010 00010 10010 01100",
    'k': "10000 10000 10010 10100 11000 10100 10010",
    'l': "01100 00100 00100 00100 00100 00100 01110",
    'm': "00000 00000 11010 10101 10101 10001 10001",
    'n': "00000 00000 11110 10001 10001 10001 10001",
    'o': "00000 00000 01110 10001 10001 10001 01110",
    'p': "00000 00000 11110 10001 10001 11110 10000",
    'q': "00000 00000 01111 10001 10001 01111 00001",
    'r': "00000 00000 01110 10001 10000 10000 10000",
    's': "00000 00000 01111 10000 01110 00001 11110",
    't': "00100 00100 01110 00100 00100 00101 00010",
    'u': "00000 00000 10001 10001 10001 10011 01101",
    'v': "00000 00000 10001 10001 10001 01010 00100",
    'w': "00000 00000 10001 10001 10101 10101 01010",
    'x': "00000 00000 10001 01010 00100 01010 10001",
    'y': "00000 00000 10001 10001 01111 00001 01110",
    'z': "00000 00000 11111 00010 00100 01000 11111",
    '0': "01110 10001 10011 10101 11001 10001 01110",
    '1': "00100 01100 00100 00100 00100 00100 01110",
    '2': "01110 10001 00001 00010 00100 01000 11111",
    '3': "11111 00001 00010 00110 00001 10001 01110",
    '4': "00010 00110 01010 10010 11111 00010 00010",
    '5': "11111 10000 11110 00001 00001 10001 01110",
    '6': "00110 01000 10000 11110 10001 10001 01110",
    '7': "11111 00001 00010 00100 01000 01000 01000",
    '8': "01110 10001 10001 01110 10001 10001 01110",
    '9': "01110 10001 10001 01111 00001 00010 01100",
    ' ': "00000 00000 00000 00000 00000 00000 00000",
    '.': "00000 00000 00000 00000 00000 01100 01100",
    ',': "00000 00000 00000 00000 00000 01100 00100",
    '!': "00100 00100 00100 00100 00100 00000 00100",
    '?': "01110 10001 00001 00010 00100 00000 00100",
    ':': "00000 01100 01100 00000 01100 01100 00000",
    '-': "00000 00000 00000 11111 00000 00000 00000",
    "'": "00100 00100 01000 00000 00000 00000 00000",
    '~': "00000 01001 10110 00000 00000 00000 00000",
    '*': "00000 00100 10101 01110 10101 00100 00000",
    '(': "00010 00100 01000 01000 01000 00100 00010",
    ')': "01000 00100 00010 00010 00010 00100 01000",
    '/': "00001 00001 00010 00100 01000 10000 10000",
    '+': "00000 00100 00100 11111 00100 00100 00000",
    '=': "00000 00000 11111 00000 11111 00000 00000",
    '_': "00000 00000 00000 00000 00000 00000 11111",
    '<': "00010 00100 01000 10000 01000 00100 00010",
    '>': "01000 00100 00010 00001 00010 00100 01000",
    '[': "01110 01000 01000 01000 01000 01000 01110",
    ']': "01110 00010 00010 00010 00010 00010 01110",
    '@': "01110 10001 10111 10101 10111 10000 01110",
    '#': "01010 01010 11111 01010 11111 01010 01010",
    '$': "01110 10100 01110 00101 00101 01110 00100",
    '%': "11001 11001 00010 00100 01000 10011 10011",
    '&': "01100 10010 01100 10101 10010 01101 00000",
    '"': "01010 01010 00000 00000 00000 00000 00000",
    '^': "00100 01010 10001 00000 00000 00000 00000",
    '|': "00100 00100 00100 00100 00100 00100 00100",
    '\\': "10000 10000 01000 00100 00010 00001 00001",
    ';': "00000 01100 01100 00000 01100 00100 00010",
    # Accented characters (French/Spanish)
    '\u00e0': "00000 00000 01110 00001 01111 10001 01111",  # à
    '\u00e1': "00000 00000 01110 00001 01111 10001 01111",  # á (same glyph)
    '\u00e2': "00000 00000 01110 00001 01111 10001 01111",  # â (same glyph)
    '\u00e4': "00000 00000 01110 00001 01111 10001 01111",  # ä (same glyph)
    '\u00e8': "00000 00000 01110 10001 11111 10000 01110",  # è
    '\u00e9': "00000 00000 01110 10001 11111 10000 01110",  # é
    '\u00ea': "00000 00000 01110 10001 11111 10000 01110",  # ê
    '\u00eb': "00000 00000 01110 10001 11111 10000 01110",  # ë
    '\u00f9': "00000 00000 10001 10001 10001 10011 01101",  # ù
    '\u00fa': "00000 00000 10001 10001 10001 10011 01101",  # ú
    '\u00fb': "00000 00000 10001 10001 10001 10011 01101",  # û
    '\u00fc': "00000 00000 10001 10001 10001 10011 01101",  # ü
    '\u00f4': "00000 00000 01110 10001 10001 10001 01110",  # ô
    '\u00f6': "00000 00000 01110 10001 10001 10001 01110",  # ö
    '\u00ee': "00100 00000 01100 00100 00100 00100 01110",  # î
    '\u00ef': "00100 00000 01100 00100 00100 00100 01110",  # ï
    '\u00e7': "00000 00000 01110 10000 10000 10001 01110",  # ç
    '\u00f1': "00000 00000 11110 10001 10001 10001 10001",  # ñ
    '\u00c0': "00100 01000 01110 10001 11111 10001 10001",  # À
    '\u00c9': "00100 01000 11111 10000 11110 10000 11111",  # É
    '\u00ca': "01110 00100 11111 10000 11110 10000 11111",  # Ê
    '\u00cc': "00100 01000 10000 10000 10000 10000 11111",  # Ì (unused but complete)
    '\u00d9': "00100 01000 10001 10001 10001 10001 01110",  # Ù
    '\u00d4': "01110 00100 01110 10001 10001 10001 01110",  # Ô
    '\u00c7': "01110 10001 10000 10000 10001 01110 00100",  # Ç
    '\u00d1': "01110 10001 11011 10101 10001 10001 10001",  # Ñ
}


def render_pixel_text(surface: pygame.Surface, text: str, x: int, y: int,
                       color=(255,255,255), scale=1, shadow=True):
    """Render text using 5x7 bitmap pixel font. Supports ASCII + French/Spanish accents."""
    cx = x
    for ch in text:
        # Direct lookup first (handles accented chars we added)
        glyph = PIXEL_FONT_DATA.get(ch)
        if glyph is None and ch.isalpha():
            # Try uppercase for unknown alphabetic chars
            glyph = PIXEL_FONT_DATA.get(ch.upper(), PIXEL_FONT_DATA.get(' '))
        elif glyph is None:
            glyph = PIXEL_FONT_DATA.get(' ')
        rows = glyph.split()
        for row_i, row in enumerate(rows):
            for col_i, bit in enumerate(row):
                if bit == '1':
                    px = cx + col_i * scale
                    py = y + row_i * scale
                    if shadow:
                        pygame.draw.rect(surface, (0,0,0,180),
                                         (px+scale, py+scale, scale, scale))
                    pygame.draw.rect(surface, color, (px, py, scale, scale))
        cx += 6 * scale  # 5 wide + 1 gap
    return cx


def pixel_text_width(text: str, scale=1) -> int:
    return len(text) * 6 * scale


def wrap_pixel_text(text: str, max_width: int, scale=1) -> list:
    words = text.split(' ')
    lines, line = [], ''
    for word in words:
        test = (line + ' ' + word).strip()
        if pixel_text_width(test, scale) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines if lines else ['']


# ──────────────────────────────────────────────────────────
# CHAT BUBBLE WIDGET
# ──────────────────────────────────────────────────────────

class ChatBubble:
    PADDING    = 10
    LINE_H     = 10  # px per line at scale=1
    FONT_SCALE = 1

    def __init__(self, cat, screen_w: int, screen_h: int):
        self.cat       = cat
        self.screen_w  = screen_w
        self.screen_h  = screen_h
        self.visible   = False
        self.input_text = ""
        self.messages  = []   # list of (role, text)
        self.streaming  = ""
        self.is_loading = False
        self.cursor_blink = 0.0
        self.scroll_offset = 0
        self.width  = min(CHAT_BUBBLE_W, screen_w - 20)
        self.height = min(420, screen_h - 80)

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.input_text = ""

    def get_rect(self) -> pygame.Rect:
        cx = self.cat.x + self.cat.size // 2
        cy = self.cat.y
        bx = max(5, min(cx - self.width // 2, self.screen_w - self.width - 5))
        by = max(5, cy - self.height - 10)
        return pygame.Rect(bx, by, self.width, self.height)

    def handle_key(self, event, model: str, memory: dict, settings: dict):
        if not self.visible:
            return
        lang = settings.get("lang", "en")
        if event.key == pygame.K_ESCAPE:
            self.visible = False
        elif event.key == pygame.K_RETURN and self.input_text.strip():
            self._send(model, memory, settings)
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.input_text) < MAX_INPUT_LEN:
            self.input_text += event.unicode

    def _send(self, model: str, memory: dict, settings: dict):
        user_msg = self.input_text.strip()
        self.input_text = ""
        self.messages.append(("user", user_msg))
        self.is_loading = True
        self.streaming  = ""

        cat_key = self.cat.color_key
        color_def = CAT_COLORS[cat_key]
        lang = settings.get("lang", "en")
        cat_name = settings.get("names", {}).get(cat_key, color_def.get_name(lang))
        system   = color_def.prompt(cat_name, lang)

        # Build conversation history
        mem_key  = self.cat.id  # per-cat UUID
        history  = memory.get(mem_key, [])
        ollama_msgs = [{"role": r, "content": c} for r, c in history[-MAX_MEMORY:]]
        ollama_msgs.append({"role": "user", "content": user_msg})

        def on_token(tok):
            self.streaming += tok

        def on_done(full):
            self.is_loading = False
            self.messages.append(("assistant", full or self.streaming))
            self.streaming = ""
            # Persist to memory
            history.append(("user", user_msg))
            history.append(("assistant", full or "..."))
            memory[mem_key] = history[-MAX_MEMORY:]
            save_memory(memory)

        def on_error(err):
            self.is_loading = False
            lang = settings.get("lang", "en")
            self.messages.append(("assistant", f"[Ollama error: {err}]"))
            self.streaming = ""

        if not ollama_available():
            self.is_loading = False
            lang = settings.get("lang", "en")
            self.messages.append(("assistant", l10n("no_ollama", lang)))
            return

        ollama_chat(model, system, ollama_msgs, on_token, on_done, on_error)

    def draw(self, surface: pygame.Surface, memory: dict, settings: dict):
        if not self.visible:
            return

        lang = settings.get("lang", "en")
        rect = self.get_rect()
        P    = self.PADDING
        FS   = self.FONT_SCALE
        cat_col = CAT_COLORS[self.cat.color_key].color

        # ── Tail (triangular, pointing down to cat, like macOS PixelTail) ──
        tail_h = 8
        tail_w = 12
        cx = self.cat.x + self.cat.size // 2
        tail_x = cx - tail_w // 2
        tail_y = rect.bottom
        tail_surf = pygame.Surface((tail_w, tail_h + 2), pygame.SRCALPHA)
        # Border
        for row in range(tail_h + 1):
            w = tail_w - row * 2
            if w > 0:
                x_off = (tail_w - w) // 2
                pygame.draw.rect(tail_surf, (0x4C, 0x33, 0x1A, 255),
                                 (x_off, row, w, 1))
        # Fill
        for row in range(tail_h):
            w = tail_w - row * 2 - 2
            if w > 0:
                x_off = (tail_w - w) // 2
                pygame.draw.rect(tail_surf, (0xF2, 0xE6, 0xCC, 250),
                                 (x_off, row + 1, w, 1))
        surface.blit(tail_surf, (tail_x, tail_y))

        # ── Background panel (warm parchment, like macOS PixelBorder) ──
        panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        panel.fill((0xF2, 0xE6, 0xCC, 245))
        # Double border (like macOS PixelBorder)
        px = 1
        pygame.draw.rect(panel, (0x4C, 0x33, 0x1A), (0, 0, rect.w, rect.h), px)
        pygame.draw.rect(panel, (0x4C, 0x33, 0x1A), (px*2, px*2, rect.w-px*4, rect.h-px*4), px)
        surface.blit(panel, rect.topleft)

        # ── Title bar (cat color) ──
        title_h = 18
        title_surf = pygame.Surface((rect.w, title_h), pygame.SRCALPHA)
        title_surf.fill(cat_col + (220,))
        pygame.draw.rect(title_surf, (0x4C, 0x33, 0x1A, 255), (0, title_h - 1, rect.w, 1))
        surface.blit(title_surf, rect.topleft)

        cat_name = settings.get("names", {}).get(
            self.cat.color_key,
            CAT_COLORS[self.cat.color_key].get_name(lang)
        )
        render_pixel_text(surface, cat_name,
                          rect.x + P, rect.y + 5, (255,255,255), FS)

        # Close button (× style)
        close_x = rect.right - 18
        render_pixel_text(surface, "x", close_x, rect.y + 5, (0x80, 0x30, 0x30), FS)
        self._close_rect = pygame.Rect(close_x, rect.y + 3, 14, 12)

        # ── Messages area ──
        msg_y    = rect.y + title_h + P
        msg_h    = rect.h - title_h - P*3 - CHAT_INPUT_H
        msg_area = pygame.Rect(rect.x + P, msg_y, rect.w - P*2, msg_h)

        clip = surface.get_clip()
        surface.set_clip(msg_area)

        all_msgs = list(self.messages)
        if self.streaming:
            all_msgs.append(("assistant", self.streaming + "|"))
        elif self.is_loading and not self.streaming:
            dots = "." * (int(time.time() * 2) % 4)
            all_msgs.append(("assistant", dots or "."))

        draw_y = msg_y + 2
        for role, text in all_msgs:
            is_user = (role == "user")
            prefix  = "> " if is_user else ""
            full    = prefix + text
            # Warm tones matching parchment theme
            col     = (0x3C, 0x5A, 0x8C) if is_user else (0x2C, 0x5C, 0x2C)
            lines   = wrap_pixel_text(full, msg_area.w - P, FS)
            for line in lines:
                if draw_y >= msg_y and draw_y < msg_y + msg_h:
                    render_pixel_text(surface, line, msg_area.x + 2, draw_y, col, FS)
                draw_y += (7 * FS) + 3
            draw_y += 4

        surface.set_clip(clip)

        # ── Input box ──
        input_y = rect.bottom - CHAT_INPUT_H - P//2
        input_rect = pygame.Rect(rect.x + P, input_y, rect.w - P*2, CHAT_INPUT_H - 4)
        pygame.draw.rect(surface, (0xFF, 0xFA, 0xED), input_rect)
        pygame.draw.rect(surface, (0x4C, 0x33, 0x1A), input_rect, 1)

        self.cursor_blink = time.time() % 2
        cursor = "|" if self.cursor_blink < 1 else " "
        display = self.input_text[-40:] + cursor
        render_pixel_text(surface, display,
                          input_rect.x + 4, input_rect.y + (CHAT_INPUT_H - 4)//2 - 3,
                          (0x4C, 0x33, 0x1A), FS)

        # Hint
        if not self.input_text and not self.messages:
            render_pixel_text(surface, l10n("talk", lang),
                              input_rect.x + 4, input_rect.y + (CHAT_INPUT_H - 4)//2 - 3,
                              (0x9C, 0x8C, 0x7A), FS)

    def handle_click(self, pos) -> bool:
        """Returns True if click consumed."""
        if not self.visible:
            return False
        rect = self.get_rect()
        if hasattr(self, '_close_rect') and self._close_rect.collidepoint(pos):
            self.visible = False
            return True
        if rect.collidepoint(pos):
            return True
        return False


# ──────────────────────────────────────────────────────────
# CAT ENTITY
# ──────────────────────────────────────────────────────────

@dataclass
class Cat:
    color_key: str
    x: float
    y: float
    size: int
    id: str = ""
    direction: str = "south"   # cardinal direction for sprite selection
    state: str     = "idle"
    frame: int     = 0
    frame_timer: float = 0.0
    state_timer: float = 0.0
    bubble_text: str = ""
    bubble_timer: float = 0.0
    dragging: bool = False
    drag_offset: tuple = (0, 0)
    chat: Optional[object] = None   # ChatBubble
    walk_dir: int = 1    # 1=right, -1=left for horizontal movement
    # Click vs drag detection (match macOS)
    mouse_down_pos: Optional[tuple] = None
    mouse_down_time: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:8]
        self.state_timer = random.uniform(2.0, 6.0)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def update(self, dt: float, screen_w: int, screen_h: int, lang: str = "en"):
        if self.dragging:
            return

        # One-shot animation completion
        if self.state in ONE_SHOT_STATES:
            anim_frames = self._get_frame_count()
            if anim_frames > 0 and self.frame >= anim_frames - 1:
                self.state = "idle"
                self.state_timer = random.uniform(1.5, 4.0)
                self.frame = 0
            elif anim_frames == 0:
                # No sprite frames for this state — skip immediately
                self.state = "idle"
                self.state_timer = random.uniform(1.5, 4.0)
                self.frame = 0

        # State machine
        self.state_timer -= dt
        if self.state_timer <= 0:
            if self.state in ONE_SHOT_STATES:
                # Safety timeout: force transition to idle
                self.state = "idle"
                self.frame = 0
            self._pick_next_state(lang)

        # Movement
        if self.state == "walking":
            self.x += self.walk_dir * WALK_SPEED
            # Update direction based on movement
            if self.walk_dir > 0:
                self.direction = "east"
            else:
                self.direction = "west"

            if self.x <= 0:
                self.x = 0
                self.walk_dir = 1
            elif self.x >= screen_w - self.size:
                self.x = screen_w - self.size
                self.walk_dir = -1

        # Frame animation
        self.frame_timer += dt
        if self.frame_timer >= 1.0 / FPS:
            self.frame_timer = 0
            max_frames = self._get_frame_count()
            if max_frames > 0:
                self.frame = (self.frame + 1) % max_frames
            else:
                self.frame = (self.frame + 1) % 12

        # Meow bubble
        self.bubble_timer -= dt
        if self.bubble_timer <= 0 and not self.chat.visible:
            if random.random() < 0.003:
                self.bubble_text = random_meow(lang)
                self.bubble_timer = BUBBLE_DURATION

    def _get_frame_count(self) -> int:
        """Get the number of frames for the current state/direction."""
        if self.state in ANIM_FOLDERS:
            return _count_frames(self.color_key, self.state, self.direction)
        return 12  # fallback

    def _pick_next_state(self, lang: str = "en"):
        roll = random.random()
        if roll < 0.35:
            self.state = "walking"
            self.state_timer = random.uniform(2.0, 5.0)
            if random.random() < 0.5:
                self.walk_dir *= -1
        elif roll < 0.55:
            self.state = "idle"
            self.state_timer = random.uniform(1.5, 4.0)
        elif roll < 0.68:
            self.state = "sleeping"
            self.state_timer = random.uniform(3.0, 8.0)
            self.direction = "south"
        elif roll < 0.78:
            self.state = "eating"
            self.state_timer = 10.0  # safety timeout
            self.frame = 0
        elif roll < 0.86:
            self.state = "drinking"
            self.state_timer = 10.0
            self.frame = 0
        elif roll < 0.93:
            self.state = "angry"
            self.state_timer = 10.0
            self.frame = 0
        else:
            # Wake from sleeping
            if self.state == "sleeping":
                self.state = "waking"
            else:
                self.state = "angry"
            self.state_timer = 10.0
            self.frame = 0

    def draw(self, surface: pygame.Surface):
        color_def = CAT_COLORS[self.color_key]
        color   = color_def.color

        # Load sprite with direction
        sprite = load_sprite(self.color_key, self.state, self.direction,
                             self.frame, self.size)

        surface.blit(sprite, (int(self.x), int(self.y)))

        # Speech bubble (random meow) — only when chat is closed
        if self.bubble_text and self.bubble_timer > 0 and not self.chat.visible:
            bx = int(self.x) + self.size // 2
            by = int(self.y)
            self._draw_speech_bubble(surface, self.bubble_text, bx, by, color)

    def _draw_speech_bubble(self, surface, text, cx, by, cat_color):
        """Draw a macOS-style meow bubble above the cat (centered, with tail)."""
        FS    = 1
        pad   = 6
        tw    = pixel_text_width(text, FS)
        bw, bh = tw + pad*2, 7*FS + pad*2
        tail_h = 4  # pixel tail height

        # Center horizontally on cx
        bx = cx - bw // 2
        bubble_bottom = by - 4  # small gap above cat

        # Keep on screen
        if bx + bw > surface.get_width():
            bx = surface.get_width() - bw - 2
        if bx < 2:
            bx = 2
        if bubble_bottom - bh - tail_h < 0:
            bubble_bottom = int(self.y) + self.size

        # Tail (small triangle pointing down)
        tail_w = 6
        tail_x = cx - tail_w // 2
        tail_y = bubble_bottom - tail_h
        tail_surf = pygame.Surface((tail_w, tail_h), pygame.SRCALPHA)
        for row in range(tail_h):
            w = tail_w - row * 2
            if w > 0:
                x_off = (tail_w - w) // 2
                pygame.draw.rect(tail_surf, (0x4C, 0x33, 0x1A, 255),
                                 (x_off, row, w, 1))
        # Fill tail
        for row in range(tail_h - 1):
            w = tail_w - row * 2 - 2
            if w > 0:
                x_off = (tail_w - w) // 2
                pygame.draw.rect(tail_surf, (0xF2, 0xE6, 0xCC, 255),
                                 (x_off, row + 1, w, 1))
        surface.blit(tail_surf, (tail_x, tail_y))

        # Bubble body (warm parchment with brown border, like macOS PixelBorder)
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        # Fill
        bg.fill((0xF2, 0xE6, 0xCC, 240))
        # Outer border
        px = 1
        pygame.draw.rect(bg, (0x4C, 0x33, 0x1A, 255), (0, 0, bw, bh), px)
        # Inner border
        pygame.draw.rect(bg, (0x4C, 0x33, 0x1A, 255), (px*2, px*2, bw-px*4, bh-px*4), px)

        surface.blit(bg, (bx, bubble_bottom - bh))
        render_pixel_text(surface, text, bx + pad, bubble_bottom - bh + pad,
                          (0x4C, 0x33, 0x1A), FS, shadow=False)


# ──────────────────────────────────────────────────────────
# SETTINGS PANEL
# ──────────────────────────────────────────────────────────

class SettingsPanel:
    W, H = 320, 520

    def __init__(self, screen_w, screen_h):
        self.visible  = False
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.rect     = pygame.Rect(
            (screen_w - self.W) // 2,
            (screen_h - self.H) // 2,
            self.W, self.H
        )
        self._model_input = ""
        self._editing_model = False
        self._editing_name = None   # color_key being edited, or None
        self._name_input = ""
        self._available_models = []
        self._model_index = 0
        self._selected_color = None  # which cat color is selected for detail view
        self._slider_dragging = False  # scale slider dragging state

    def toggle(self):
        self.visible = not self.visible

    def refresh_models(self):
        """Fetch available Ollama models."""
        self._available_models = ollama_models()

    def _sync_model_index(self, settings):
        """Ensure _model_index points to the current model in the list."""
        if self._available_models:
            current = settings.get("model", "")
            try:
                self._model_index = self._available_models.index(current)
            except ValueError:
                self._model_index = 0

    def handle_key(self, event, settings):
        if not self.visible:
            return
        if event.key == pygame.K_ESCAPE:
            self.visible = False
            self._editing_model = False
            self._editing_name = None
            return
        if self._editing_model:
            if event.key == pygame.K_RETURN:
                settings["model"] = self._model_input
                save_settings(settings)
                self._editing_model = False
            elif event.key == pygame.K_BACKSPACE:
                self._model_input = self._model_input[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._model_input += event.unicode
        elif self._editing_name is not None:
            if event.key == pygame.K_RETURN:
                settings.setdefault("names", {})[self._editing_name] = self._name_input
                save_settings(settings)
                self._editing_name = None
            elif event.key == pygame.K_BACKSPACE:
                self._name_input = self._name_input[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self._name_input) < 20:
                self._name_input += event.unicode

    def handle_click(self, pos, settings, cats: list, screen_w, screen_h) -> bool:
        if not self.visible:
            return False
        if not self.rect.collidepoint(pos):
            self.visible = False
            self._editing_model = False
            self._editing_name = None
            return False

        rx = pos[0] - self.rect.x
        ry = pos[1] - self.rect.y
        lang = settings.get("lang", "en")

        # Language flag row
        flag_y = 34
        flag_x_start = 80
        for i, (flag_lang, label) in enumerate([("fr", "FR"), ("en", "EN"), ("es", "ES")]):
            fr = pygame.Rect(self.rect.x + flag_x_start + i * 40, self.rect.y + flag_y, 34, 16)
            if fr.collidepoint(pos):
                settings["lang"] = flag_lang
                save_settings(settings)
                return True

        # Color bubbles (add/remove/select cats — like macOS ColorBubblesView)
        bubble_y = 88
        bx_start = self.rect.x + 15
        gap = 32
        total_w = len(CAT_COLORS) * gap - (gap - 28)
        bx_start = self.rect.x + (self.W - total_w) // 2
        for i, key in enumerate(CAT_COLORS):
            cx = bx_start + i * gap + 14
            cy = self.rect.y + bubble_y + 14
            dist = math.sqrt((pos[0] - cx)**2 + (pos[1] - cy)**2)
            if dist <= 14:
                existing = [c for c in cats if c.color_key == key]
                if existing:
                    # Select this cat for detail view
                    self._selected_color = key
                else:
                    # Add a cat of this color
                    new_cat = _make_cat(key, screen_w, screen_h,
                                        settings.get("scale", SCALE))
                    cats.append(new_cat)
                    settings["cats"] = [c.color_key for c in cats]
                    self._selected_color = key
                    save_settings(settings)
                self._editing_model = False
                self._editing_name = None
                return True

        # × button on active cats (remove cat — like macOS)
        for i, key in enumerate(CAT_COLORS):
            cx = bx_start + i * gap + 14
            cy = self.rect.y + bubble_y + 14
            active = any(c.color_key == key for c in cats)
            if active and len(cats) > 1:
                # × button position (top-right of bubble)
                x_r = pygame.Rect(cx + 8, cy - 14, 12, 12)
                if x_r.collidepoint(pos):
                    existing = [c for c in cats if c.color_key == key]
                    if existing:
                        cats.remove(existing[0])
                        settings["cats"] = [c.color_key for c in cats]
                        if self._selected_color == key:
                            self._selected_color = cats[0].color_key if cats else None
                        save_settings(settings)
                    return True

        # Cat name editing — click on name field
        if self._selected_color:
            name_y = self.rect.y + 148
            name_rect = pygame.Rect(self.rect.x + 70, name_y, self.W - 90, 16)
            if name_rect.collidepoint(pos):
                self._editing_name = self._selected_color
                self._editing_model = False
                self._name_input = settings.get("names", {}).get(
                    self._selected_color,
                    CAT_COLORS[self._selected_color].get_name(lang)
                )
                return True

        # Model input click
        model_box_y = self.rect.y + 270
        model_rect = pygame.Rect(self.rect.x + 10, model_box_y, self.W - 20, 20)
        if model_rect.collidepoint(pos):
            if self._available_models:
                self._sync_model_index(settings)
                self._model_index = (self._model_index + 1) % len(self._available_models)
                settings["model"] = self._available_models[self._model_index]
                save_settings(settings)
            else:
                self._editing_model = True
                self._model_input   = settings.get("model", "")
            self._editing_name  = None
            return True

        # Scale slider (continuous, like macOS PixelSlider)
        slider_y = self.rect.y + 330
        slider_rect = pygame.Rect(self.rect.x + 15, slider_y, self.W - 30, 20)
        if slider_rect.collidepoint(pos):
            self._slider_dragging = True
            self._update_slider(pos, settings, cats, slider_rect)
            return True

        return True

    def handle_drag(self, pos, settings, cats):
        """Handle slider dragging."""
        if self._slider_dragging:
            slider_y = self.rect.y + 330
            slider_rect = pygame.Rect(self.rect.x + 15, slider_y, self.W - 30, 20)
            self._update_slider(pos, settings, cats, slider_rect)

    def _update_slider(self, pos, settings, cats, slider_rect):
        """Update scale from slider position."""
        ratio = max(0, min(1, (pos[0] - slider_rect.x) / slider_rect.w))
        new_scale = max(1, min(6, round(1 + ratio * 5)))
        if new_scale != settings.get("scale", SCALE):
            settings["scale"] = new_scale
            save_settings(settings)
            _clear_sprite_caches()
            for cat in cats:
                cat.size = CAT_BASE_SIZE * settings["scale"]

    def handle_mouse_up(self):
        """End slider dragging."""
        self._slider_dragging = False

    def draw(self, surface, settings, cats, ollama_ok):
        if not self.visible:
            return

        lang = settings.get("lang", "en")
        P  = 10
        FS = 1

        # Background panel (warm parchment, like macOS)
        panel = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        panel.fill((0xF2, 0xE6, 0xCC, 245))
        # Double border
        pygame.draw.rect(panel, (0x4C, 0x33, 0x1A), (0, 0, self.W, self.H), 2)
        pygame.draw.rect(panel, (0x4C, 0x33, 0x1A), (4, 4, self.W-8, self.H-8), 1)
        surface.blit(panel, self.rect.topleft)

        # ── Title ──
        render_pixel_text(surface, l10n("title", lang),
                          self.rect.x + P, self.rect.y + 8, (0x4C, 0x33, 0x1A), FS)

        # ── Language flags (like macOS FlagRowView) ──
        render_pixel_text(surface, l10n("lang_label", lang),
                          self.rect.x + P, self.rect.y + 28, (0x6C, 0x4C, 0x2A), FS)
        flag_x = self.rect.x + 80
        for i, (fl, label) in enumerate([("fr", "FR"), ("en", "EN"), ("es", "ES")]):
            if lang == fl:
                # Highlight box (like macOS)
                bx = flag_x + i * 40
                pygame.draw.rect(surface, (0xFF, 0xCC, 0x4C),
                                 (bx - 2, self.rect.y + 27, 34, 14))
                pygame.draw.rect(surface, (0x4C, 0x33, 0x1A),
                                 (bx - 2, self.rect.y + 27, 34, 14), 1)
            col = (0x4C, 0x33, 0x1A) if lang == fl else (0x9C, 0x8C, 0x7A)
            render_pixel_text(surface, f"[{label}]", flag_x + i*40, self.rect.y + 28,
                              col, FS)

        # ── "MY CATS" label ──
        render_pixel_text(surface, l10n("cats", lang),
                          self.rect.x + P, self.rect.y + 52, (0x4C, 0x33, 0x1A), FS)

        # ── Color bubbles (like macOS ColorBubblesView) ──
        bubble_y = 74
        gap = 32
        total_w = len(CAT_COLORS) * gap - (gap - 28)
        bx_start = self.rect.x + (self.W - total_w) // 2

        for i, (key, color_def) in enumerate(CAT_COLORS.items()):
            cx = bx_start + i * gap + 14
            cy = self.rect.y + bubble_y + 14
            col = color_def.color
            active = any(c.color_key == key for c in cats)
            selected = (key == self._selected_color)

            # Draw bubble
            pygame.draw.circle(surface, col, (cx, cy), 12)

            # Border
            border_col = (0xFF, 0xCC, 0x4C) if (selected and active) else (0x4C, 0x33, 0x1A)
            border_w = 2 if (selected and active) else 1
            pygame.draw.circle(surface, border_col, (cx, cy), 12, border_w)

            # Dim inactive
            if not active:
                dim = pygame.Surface((24, 24), pygame.SRCALPHA)
                dim.fill((0xF2, 0xE6, 0xCC, 120))
                surface.blit(dim, (cx - 12, cy - 12))

            # × button on active cats
            if active and len(cats) > 1:
                x_cx = cx + 8
                x_cy = cy - 8
                pygame.draw.circle(surface, (0xCC, 0x33, 0x33), (x_cx, x_cy), 6)
                render_pixel_text(surface, "x", x_cx - 2, x_cy - 3, (255,255,255), FS)

        # ── Selected cat details (like macOS) ──
        if self._selected_color and self._selected_color in CAT_COLORS:
            sel = self._selected_color
            color_def = CAT_COLORS[sel]
            cat_cfg = None
            for c in cats:
                if c.color_key == sel:
                    cat_cfg = c
                    break

            # Cat preview sprite
            preview_size = 48
            try:
                preview_surf = load_sprite(sel, "idle", "south", 0, preview_size)
                px = self.rect.x + (self.W - preview_size) // 2
                py = self.rect.y + 94
                surface.blit(preview_surf, (px, py))
            except Exception:
                pass

            # Name
            render_pixel_text(surface, l10n("name", lang),
                              self.rect.x + P, self.rect.y + 148, (0x4C, 0x33, 0x1A), FS)
            name = settings.get("names", {}).get(sel, color_def.get_name(lang))
            if self._editing_name == sel:
                display_name = self._name_input + "_"
                name_rect = pygame.Rect(self.rect.x + 70, self.rect.y + 148, self.W - 90, 16)
                pygame.draw.rect(surface, (0xFF, 0xFA, 0xED), name_rect)
                pygame.draw.rect(surface, (0x4C, 0x33, 0x1A), name_rect, 1)
                render_pixel_text(surface, display_name,
                                  name_rect.x + 3, name_rect.y + 3, (0x4C, 0x33, 0x1A), FS)
            else:
                render_pixel_text(surface, name,
                                  self.rect.x + 70, self.rect.y + 148, (0x4C, 0x33, 0x1A), FS)

            # Personality (trait + skill, like macOS)
            trait = color_def.traits.get(lang, "")
            render_pixel_text(surface, f"* {trait}",
                              self.rect.x + P, self.rect.y + 168, (0x80, 0x4C, 0x1A), FS)
            skill = color_def.skills.get(lang, "")
            render_pixel_text(surface, skill[:40],
                              self.rect.x + P, self.rect.y + 180, (0x9C, 0x6C, 0x3A), FS)

        # ── Size section (continuous slider, like macOS PixelSlider) ──
        render_pixel_text(surface, l10n("size", lang),
                          self.rect.x + P, self.rect.y + 310, (0x4C, 0x33, 0x1A), FS)
        scale = settings.get("scale", SCALE)
        render_pixel_text(surface, f"x{scale}",
                          self.rect.x + self.W - 40, self.rect.y + 310, (0x4C, 0x33, 0x1A), FS)

        # Slider track
        slider_y = self.rect.y + 328
        slider_x = self.rect.x + 15
        slider_w = self.W - 30
        track_h = 6
        track_y = slider_y + 8
        pygame.draw.rect(surface, (0x4C, 0x33, 0x1A),
                         (slider_x, track_y, slider_w, track_h))
        # Filled portion
        ratio = (scale - 1) / 5
        fill_w = int(slider_w * ratio)
        pygame.draw.rect(surface, (0xFF, 0x99, 0x33),
                         (slider_x, track_y, fill_w, track_h))
        # Knob
        knob_x = slider_x + fill_w
        knob_size = 10
        pygame.draw.rect(surface, (0x4C, 0x33, 0x1A),
                         (knob_x - knob_size//2, track_y - 2, knob_size, track_h + 4))
        pygame.draw.rect(surface, (0xFF, 0xCC, 0x4C),
                         (knob_x - knob_size//2 + 2, track_y, knob_size - 4, track_h))

        # ── Model section ──
        render_pixel_text(surface, l10n("model", lang),
                          self.rect.x + P, self.rect.y + 256, (0x4C, 0x33, 0x1A), FS)
        if self._editing_model:
            model_val = self._model_input
            model_border = (0xFF, 0x99, 0x33)
        else:
            model_val = settings.get("model", "")
            model_border = (0x4C, 0x33, 0x1A)
            if self._available_models:
                model_val = settings.get("model", self._available_models[0])
        model_box = pygame.Rect(self.rect.x + P, self.rect.y + 270, self.W - 20, 20)
        pygame.draw.rect(surface, (0xFF, 0xFA, 0xED), model_box)
        pygame.draw.rect(surface, model_border, model_box, 1)
        render_pixel_text(surface, model_val[:30],
                          model_box.x + 3, model_box.y + 6, (0x4C, 0x33, 0x1A), FS)
        if self._available_models and not self._editing_model:
            render_pixel_text(surface, f"({len(self._available_models)})",
                              model_box.right - 30, model_box.y + 6, (0x9C, 0x8C, 0x7A), FS)

        # ── Help text ──
        render_pixel_text(surface, l10n("click_cat", lang),
                          self.rect.x + P, self.rect.y + self.H - 38,
                          (0x9C, 0x8C, 0x7A), FS)
        render_pixel_text(surface, l10n("drag", lang),
                          self.rect.x + P, self.rect.y + self.H - 24,
                          (0x9C, 0x8C, 0x7A), FS)


# ──────────────────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────────────────

def _make_cat(color_key: str, screen_w: int, screen_h: int, scale: int) -> Cat:
    size = CAT_BASE_SIZE * scale
    x    = random.randint(size, max(size+1, screen_w - size*2))
    y    = screen_h - size  # walk on the floor (panel/taskbar)
    cat  = Cat(color_key=color_key, x=x, y=y, size=size)
    cat.chat = ChatBubble(cat, screen_w, screen_h)
    return cat


# ──────────────────────────────────────────────────────────
# HUD BAR
# ──────────────────────────────────────────────────────────

def draw_hud(surface, cats, settings, ollama_ok, show_settings, transparent):
    """Bottom HUD bar."""
    lang = settings.get("lang", "en")
    sw = surface.get_width()
    sh = surface.get_height()
    bar_h = 28
    bar   = pygame.Surface((sw, bar_h), pygame.SRCALPHA)
    if transparent:
        bar.fill((15, 13, 25, 180))
    else:
        bar.fill((15, 13, 25, 210))
    pygame.draw.line(bar, (60,60,90), (0,0), (sw,0), 1)
    surface.blit(bar, (0, sh - bar_h))

    render_pixel_text(surface, "CATAI", 8, sh - bar_h + 9,
                      (180, 120, 255), 1)

    # Ollama dot
    col = (80,255,80) if ollama_ok else (255,80,80)
    pygame.draw.circle(surface, col, (80, sh - bar_h//2), 4)

    # Settings gear
    render_pixel_text(surface, f"[{l10n('settings', lang)}]", sw - 100, sh - bar_h + 9,
                      (160,140,220), 1)


# ──────────────────────────────────────────────────────────
# SPRITE DOWNLOAD
# ──────────────────────────────────────────────────────────

GITHUB_REPO = "wil-pe/CATAI"
SPRITE_SUBDIR = "cute_orange_cat"


def download_sprites():
    """Download sprite assets from the original CATAI GitHub repo."""
    import tempfile
    import shutil

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SPRITE_SUBDIR}"
    print(f"Fetching sprite list from {api_url}...")

    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"Error fetching sprite list: {e}")
        print("Falling back to zip download...")
        _download_zip()
        return

    # Download each file
    target_dir = SPRITE_DIR / "orange"
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        if item["type"] == "dir":
            name = item["name"]
            print(f"  Downloading {name}/...")
            _download_dir_recursive(item["url"], target_dir / name)

    # Copy rotations
    rot_src = target_dir / "rotations"
    if not rot_src.exists():
        # Try downloading rotations separately
        rot_api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SPRITE_SUBDIR}/rotations"
        try:
            resp = requests.get(rot_api, timeout=10)
            resp.raise_for_status()
            rot_items = resp.json()
            rot_src.mkdir(parents=True, exist_ok=True)
            for item in rot_items:
                if item["type"] == "file":
                    _download_file(item["download_url"], rot_src / item["name"])
        except Exception as e:
            print(f"  Warning: Could not download rotations: {e}")

    print(f"Done! Sprites saved to {SPRITE_DIR}")


def _download_dir_recursive(api_url: str, target: Path):
    """Recursively download a directory from GitHub API."""
    target.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"    Error listing directory: {e}")
        return

    for item in items:
        if item["type"] == "file":
            _download_file(item["download_url"], target / item["name"])
        elif item["type"] == "dir":
            _download_dir_recursive(item["url"], target / item["name"])


def _download_file(url: str, target: Path):
    """Download a single file."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        target.write_bytes(resp.content)
    except Exception as e:
        print(f"    Error downloading {url}: {e}")


def _download_zip():
    """Fallback: download the entire repo as a zip and extract sprites."""
    zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"
    print(f"Downloading repo from {zip_url}...")

    import tempfile
    tmp = tempfile.mkdtemp()
    zip_path = Path(tmp) / "catai.zip"

    try:
        resp = requests.get(zip_url, timeout=30, stream=True)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)

        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                # Find the sprite subdirectory
                if SPRITE_SUBDIR + "/" in name and not name.endswith("/"):
                    # Extract relative to the sprite subdir
                    rel = name.split(SPRITE_SUBDIR + "/", 1)[-1]
                    if rel:
                        target = SPRITE_DIR / "orange" / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())

        print(f"Done! Sprites saved to {SPRITE_DIR}")
    except Exception as e:
        print(f"Error downloading zip: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ──────────────────────────────────────────────────────────
# TRANSPARENT WINDOW SETUP (ctypes X11 — no python-xlib needed)
# ──────────────────────────────────────────────────────────

def detect_display_server() -> str:
    """Detect whether we're running on X11, Wayland, or XWayland."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "x11":
        return "x11"
    if session_type == "wayland":
        return "wayland"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "wayland"  # safe default: opaque window

# ctypes X11 bindings — eliminates the python-xlib dependency
_libX11 = None
_X11_open = False  # True once we've confirmed X11 is reachable

def _get_libx11():
    """Lazy-load libX11.so."""
    global _libX11
    if _libX11 is not None:
        return _libX11
    try:
        _libX11 = ctypes.CDLL("libX11.so.6")
    except OSError:
        try:
            _libX11 = ctypes.CDLL("libX11.so")
        except OSError:
            _libX11 = None
    return _libX11

def _x11_available() -> bool:
    """Check if we can connect to an X11 display (works for X11 and XWayland)."""
    global _X11_open
    if _X11_open:
        return True
    if not os.environ.get("DISPLAY"):
        return False
    try:
        result = subprocess.run(
            ["xdpyinfo"], capture_output=True, timeout=2
        )
        if result.returncode == 0:
            _X11_open = True
            return True
    except Exception:
        pass
    return False


# ── ctypes X11 helpers ──

class _X11Conn:
    """Minimal X11 connection via ctypes for window property manipulation."""

    def __init__(self):
        lib = _get_libx11()
        if lib is None:
            raise RuntimeError("libX11 not available")
        # XOpenDisplay(NULL)
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_void_p]
        self.dpy = lib.XOpenDisplay(None)
        if not self.dpy:
            raise RuntimeError("Cannot open X11 display")
        self.lib = lib
        # Cache atom lookups
        self._atoms = {}
        # Get default root window
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.root = lib.XDefaultRootWindow(self.dpy)
        # Screen dimensions
        lib.XDisplayWidth.restype = ctypes.c_int
        lib.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XDisplayHeight.restype = ctypes.c_int
        lib.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XDefaultScreen.restype = ctypes.c_int
        lib.XDefaultScreen.argtypes = [ctypes.c_void_p]
        scr = lib.XDefaultScreen(self.dpy)
        self.screen_w = lib.XDisplayWidth(self.dpy, scr)
        self.screen_h = lib.XDisplayHeight(self.dpy, scr)

    def intern_atom(self, name: str) -> int:
        if name not in self._atoms:
            self.lib.XInternAtom.restype = ctypes.c_ulong
            self.lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            self._atoms[name] = self.lib.XInternAtom(self.dpy, name.encode(), 0)
        return self._atoms[name]

    def change_property(self, window, prop, prop_type, format, data):
        """XChangeProperty for 32-bit atom/CARDINAL arrays."""
        self.lib.XChangeProperty.restype = ctypes.c_int
        self.lib.XChangeProperty.argtypes = [
            ctypes.c_void_p,  # display
            ctypes.c_ulong,   # window
            ctypes.c_ulong,   # property
            ctypes.c_ulong,   # type
            ctypes.c_int,     # format (32)
            ctypes.c_int,     # mode (Replace=0)
            ctypes.c_void_p,  # data
            ctypes.c_int,     # nelements
        ]
        arr = (ctypes.c_ulong * len(data))(*data)
        self.lib.XChangeProperty(
            self.dpy, window, prop, prop_type, 32, 0,
            arr, len(data)
        )

    def get_property(self, window, prop, prop_type=None):
        """XGetWindowProperty — returns list of c_ulong values or None."""
        # We need XGetWindowProperty which is more complex with ctypes.
        # Use subprocess + xdotool/xprop as a simpler fallback, or the full ctypes path.
        # For panel height, we use a subprocess approach which is more robust.
        return None  # Handled by get_panel_height_x11 below

    def flush(self):
        self.lib.XFlush(self.dpy)

    def close(self):
        # XCloseDisplay via ctypes segfaults on Python 3.14+.
        # Don't close — the kernel reclaims the fd on exit anyway.
        pass


def get_panel_height_x11() -> int:
    """Get panel/taskbar height on X11 using _NET_WORKAREA.

    Uses xdotool/xprop subprocess or ctypes. Returns the height of
    the bottom panel (0 if none detected).
    """
    try:
        # Try xdotool first — most reliable and no deps
        result = subprocess.run(
            ["xdotool", "getdisplaygeometry"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                # xdotool gives full screen size, not workarea.
                # Try xprop for workarea.
                pass
    except Exception:
        pass

    # Try xprop for _NET_WORKAREA
    try:
        result = subprocess.run(
            ["xprop", "-root", "_NET_WORKAREA"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            # Parse: _NET_WORKAREA(CARDINAL) = 0, 27, 1920, 1053
            import re
            m = re.search(r'=\s*(.+)', result.stdout)
            if m:
                vals = [int(v.strip()) for v in m.group(1).split(',')]
                if len(vals) >= 4:
                    wa_y = vals[1]
                    wa_h = vals[3]
                    # Get screen height from xdotool or xrandr
                    screen_h = 0
                    try:
                        r2 = subprocess.run(
                            ["xdotool", "getdisplaygeometry"],
                            capture_output=True, text=True, timeout=2
                        )
                        if r2.returncode == 0:
                            # Format: WxH (some versions) or "W H"
                            # Actually: "screen_width screen_height"
                            sp = r2.stdout.strip().split()
                            if len(sp) >= 2:
                                screen_h = int(sp[1])
                    except Exception:
                        pass
                    if screen_h == 0:
                        # Fallback: use Xrandr
                        try:
                            r3 = subprocess.run(
                                ["xrandr", "--current"],
                                capture_output=True, text=True, timeout=2
                            )
                            if r3.returncode == 0:
                                for line in r3.stdout.splitlines():
                                    if '*' in line:
                                        # e.g. "1920x1080+0+0"
                                        m2 = re.search(r'(\d+)x(\d+)', line)
                                        if m2:
                                            screen_h = int(m2.group(2))
                                            break
                        except Exception:
                            pass
                    if screen_h > 0:
                        panel_h = screen_h - (wa_y + wa_h)
                        return max(0, panel_h)
    except Exception:
        pass

    # Fallback: try python-xlib if installed
    try:
        from Xlib import X, display as xdisplay
        dpy = xdisplay.Display()
        root = dpy.screen().root
        net_current_desktop = dpy.intern_atom('_NET_CURRENT_DESKTOP')
        prop = root.get_full_property(net_current_desktop, X.AnyPropertyType)
        current_desktop = prop.value[0] if prop else 0
        net_workarea = dpy.intern_atom('_NET_WORKAREA')
        workarea_prop = root.get_full_property(net_workarea, X.AnyPropertyType)
        if workarea_prop:
            workarea = workarea_prop.value
            idx = current_desktop * 4
            if idx + 3 < len(workarea):
                wa_y = workarea[idx + 1]
                wa_h = workarea[idx + 3]
                screen_h = dpy.screen().height_in_pixels
                dpy.close()
                return max(0, screen_h - (wa_y + wa_h))
        dpy.close()
    except Exception:
        pass

    return 0


def get_active_window_geometry_x11() -> Optional[Tuple[int, int, int, int]]:
    """Get active window geometry on X11. Returns (x, y, w, h) or None."""
    try:
        import subprocess
        # Get active window ID
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode != 0:
            return None
        win_id = int(result.stdout.strip())

        # Get window geometry
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", str(win_id)],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode != 0:
            return None
        geom = {}
        for line in result.stdout.strip().splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                geom[k.strip()] = int(v.strip())
        if 'X' in geom and 'Y' in geom and 'WIDTH' in geom and 'HEIGHT' in geom:
            if geom['WIDTH'] >= 100 and geom['HEIGHT'] >= 100:
                return (geom['X'], geom['Y'], geom['WIDTH'], geom['HEIGHT'])
    except Exception:
        pass

    # Fallback: try python-xlib
    try:
        from Xlib import X, display as xdisplay
        dpy = xdisplay.Display()
        root = dpy.screen().root
        net_active_window = dpy.intern_atom('_NET_ACTIVE_WINDOW')
        active_prop = root.get_full_property(net_active_window, X.AnyPropertyType)
        if not active_prop:
            dpy.close()
            return None
        win_id = active_prop.value[0]
        if win_id == 0:
            dpy.close()
            return None
        win = dpy.create_resource_object('window', win_id)
        geom = win.get_geometry()
        translated = geom.root.translate_coords(win.id, 0, 0)
        x, y = translated.x, translated.y
        w, h = geom.width, geom.height
        if w < 100 or h < 100:
            dpy.close()
            return None
        dpy.close()
        return (x, y, w, h)
    except Exception:
        return None


def _find_pygame_window_x11() -> Optional[int]:
    """Find our Pygame window ID via xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "CATAI Linux"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return first match
            for line in result.stdout.strip().splitlines():
                wid = line.strip()
                if wid.isdigit():
                    return int(wid)
    except Exception:
        pass
    return None


def setup_x11_transparent_window(window_id: int = None) -> tuple:
    """Configure X11 window properties for transparent desktop overlay.

    Uses a floating overlay approach: window stays above other windows
    with skip-taskbar, skip-pager, and sticky. Transparent areas are
    click-through via X Shape input mask.

    Returns (success, window_id).
    """
    lib = _get_libx11()
    if lib is None:
        print("[CATAI] libX11 not available, skipping X11 window setup")
        return False, None

    try:
        conn = _X11Conn()
    except Exception as e:
        print(f"[CATAI] Cannot open X11 display: {e}")
        return False, None

    try:
        # Find our Pygame window
        if window_id is None:
            window_id = _find_pygame_window_x11()
        if window_id is None:
            conn.close()
            return False, None

        win = window_id

        # ── Window type: UTILITY (stays above, not in taskbar, not disruptive) ──
        # DOCK type breaks mouse focus on some compositors. UTILITY + ABOVE
        # gives the same "always on top" behavior with proper input handling.
        conn.change_property(
            win,
            conn.intern_atom("_NET_WM_WINDOW_TYPE"),
            conn.intern_atom("ATOM"), 32,
            [conn.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")]
        )

        # ── Window state: above, skip taskbar, skip pager ──
        # ABOVE ensures we're visible above regular windows
        conn.change_property(
            win,
            conn.intern_atom("_NET_WM_STATE"),
            conn.intern_atom("ATOM"), 32,
            [
                conn.intern_atom("_NET_WM_STATE_ABOVE"),
                conn.intern_atom("_NET_WM_STATE_SKIP_TASKBAR"),
                conn.intern_atom("_NET_WM_STATE_SKIP_PAGER"),
            ]
        )

        # ── Sticky: show on all desktops ──
        conn.change_property(
            win,
            conn.intern_atom("_NET_WM_DESKTOP"),
            conn.intern_atom("CARDINAL"), 32,
            [0xFFFFFFFF]
        )

        conn.flush()
        conn.close()
        print(f"[CATAI] X11 window {window_id} configured as overlay (UTILITY + ABOVE)")
        return True, window_id
    except Exception as e:
        print(f"[CATAI] X11 window setup failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return False, None


def apply_window_shape(surface, win_id, dpy_cache=None):
    """Apply X Shape mask from surface alpha channel for true transparency.

    Uses python-xlib for the Shape extension (ctypes XShape is complex).
    Creates a 1-bit mask from the alpha channel and applies both Bounding
    and Input shapes so transparent areas are click-through.

    Returns (True, dpy) on success (dpy can be reused next call),
    (False, None) on failure.
    """
    try:
        from Xlib import X, display as xdisplay
        from Xlib.ext import shape
        import numpy as np
    except ImportError:
        # No python-xlib or numpy — skip shape updates
        return False, None

    dpy = dpy_cache
    try:
        w, h = surface.get_size()

        # Extract alpha channel via surfarray (fast with numpy)
        alpha = pygame.surfarray.pixels_alpha(surface)  # shape: (w, h), values 0-255
        # surfarray is indexed as (x, y), X11 expects row-major (y, x)
        mask = (alpha.T > 10).astype(np.uint8)  # shape: (h, w), threshold at 10
        del alpha  # Release surface lock immediately

        # Pack into 1-bit bitmap: 8 pixels per byte, MSB first
        # Pad width to multiple of 8
        padded_w = (w + 7) // 8 * 8
        if padded_w > w:
            mask = np.pad(mask, ((0, 0), (0, padded_w - w)))

        # Pad each scanline to 32-bit (4-byte) boundary for X11
        scanline_bytes = padded_w // 8
        padded_scanline = (scanline_bytes + 3) // 4 * 4
        if padded_scanline > scanline_bytes:
            mask = np.pad(mask, ((0, 0), (0, (padded_scanline - scanline_bytes) * 8)))

        # Reshape into groups of 8 bits and pack
        mask_reshaped = mask.reshape(h, padded_scanline, 8)
        bit_weights = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint8)
        bitmap = np.sum(mask_reshaped * bit_weights, axis=2, dtype=np.uint8)
        bitmap_bytes = bitmap.tobytes()

        # Create or reuse X11 connection
        if dpy is None:
            dpy = xdisplay.Display()
        root = dpy.screen().root
        pixmap = root.create_pixmap(padded_scanline * 8, h, 1)
        gc = pixmap.create_gc(foreground=1, background=0)

        # Upload the 1-bit bitmap data
        pixmap.put_image(
            gc, 0, 0, padded_scanline * 8, h,
            0,   # format: XYPixmap (bitmap)
            0,   # left_pad
            1,   # depth
            bitmap_bytes
        )

        # Apply BOTH Bounding and Input shape masks
        # Bounding = visual shape (what's visible)
        # Input = click-through shape (where mouse events pass through)
        win = dpy.create_resource_object('window', win_id)
        win.shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, pixmap)
        win.shape_mask(shape.SO.Set, shape.SK.Input, 0, 0, pixmap)

        pixmap.free(gc)
        dpy.flush()
        return True, dpy
    except Exception:
        # Non-fatal: shape update failure just means some frames show black background
        try:
            if dpy:
                dpy.close()
        except Exception:
            pass
        return False, None


def setup_transparent_window() -> tuple:
    """Set up transparent desktop overlay window.

    Returns (use_transparent, panel_height, display_server, use_xshape).
    - use_transparent: whether to use transparent background
    - panel_height: height of bottom panel/taskbar in pixels
    - display_server: "x11" or "wayland"
    - use_xshape: whether to use X Shape extension for transparency
    """
    display_server = detect_display_server()
    use_xshape = False

    # Set SDL environment for compositor cooperation
    os.environ["SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR"] = "0"

    panel_height = 0
    use_transparent = False

    if display_server == "x11":
        panel_height = get_panel_height_x11()
        # On X11: transparent overlay + X Shape for click-through
        use_transparent = True
        use_xshape = True

    elif display_server == "wayland":
        # Wayland compositors (GNOME Mutter, KDE KWin) don't support
        # X Shape on XWayland windows. Forcing XWayland gives a black
        # fullscreen overlay with no transparency and no click-through.
        # KISS: use native Wayland in window mode. Cats are visible and
        # interactive. Click-through isn't possible on Wayland anyway.
        use_transparent = False
        print("[CATAI] Wayland detected: using window mode (no overlay transparency on Wayland)")

    return use_transparent, panel_height, display_server, use_xshape


# ──────────────────────────────────────────────────────────
# CONTEXT MENU (right-click on cat, like macOS)
# ──────────────────────────────────────────────────────────

def _draw_context_menu(surface, menu: dict, lang: str):
    """Draw a simple pixel-art context menu."""
    x, y = menu["pos"]
    items = menu["items"]
    FS = 1
    item_h = 16
    pad = 8
    max_w = max(pixel_text_width(label, FS) for _, label in items) + pad * 2
    menu_h = len(items) * item_h + 4

    # Keep on screen
    sw = surface.get_width()
    sh = surface.get_height()
    if x + max_w > sw:
        x = sw - max_w - 4
    if y + menu_h > sh:
        y = sh - menu_h - 4

    # Background (warm parchment, like macOS)
    bg = pygame.Surface((max_w, menu_h), pygame.SRCALPHA)
    bg.fill((0xF2, 0xE6, 0xCC, 245))
    pygame.draw.rect(bg, (0x4C, 0x33, 0x1A), (0, 0, max_w, menu_h), 1)
    surface.blit(bg, (x, y))

    # Items
    for i, (action, label) in enumerate(items):
        iy = y + 2 + i * item_h
        render_pixel_text(surface, label, x + pad, iy + 3, (0x4C, 0x33, 0x1A), FS)


def _handle_context_menu_click(pos, menu: dict, settings: dict,
                                cats: list, sw: int, sh: int,
                                settings_panel) -> bool:
    """Handle a click on the context menu. Returns True if consumed."""
    x, y = menu["pos"]
    items = menu["items"]
    FS = 1
    item_h = 16
    pad = 8
    max_w = max(pixel_text_width(label, FS) for _, label in items) + pad * 2
    menu_h = len(items) * item_h + 4

    # Keep on screen (same as draw)
    sw_val = sw
    sh_val = sh
    if x + max_w > sw_val:
        x = sw_val - max_w - 4
    if y + menu_h > sh_val:
        y = sh_val - menu_h - 4

    # Check if click is within menu
    menu_rect = pygame.Rect(x, y, max_w, menu_h)
    if not menu_rect.collidepoint(pos):
        return False

    # Determine which item was clicked
    rel_y = pos[1] - y - 2
    if rel_y < 0:
        return True
    item_idx = rel_y // item_h
    if item_idx < 0 or item_idx >= len(items):
        return True

    action = items[item_idx][0]
    if action == "settings":
        settings_panel.toggle()
    elif action == "quit":
        save_settings(settings)
        save_memory(load_memory())  # ensure memory is saved
        pygame.quit()
        sys.exit()

    return True


# ──────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CATAI Linux — desktop cats + Ollama")
    parser.add_argument("--cats", nargs="+",
                        choices=list(CAT_COLORS.keys()),
                        default=None,
                        help="Cat colors to spawn (e.g. orange black)")
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--scale", type=int, default=None, help="Sprite scale (1-6)")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--download", action="store_true",
                        help="Download sprite assets from GitHub")
    parser.add_argument("--opaque", action="store_true",
                        help="Use opaque background (disable transparency)")
    parser.add_argument("--mode", choices=["desktop", "window"], default=None,
                        help="Force rendering mode (desktop=transparent, window=opaque)")
    parser.add_argument("--sound", action="store_true", default=None,
                        help="Enable sound effects")
    parser.add_argument("--no-sound", action="store_true",
                        help="Disable sound effects")
    args = parser.parse_args()

    # Download sprites if requested
    if args.download:
        download_sprites()
        if not args.cats:
            return

    # Setup transparent window (detects X11/Wayland, panel height)
    use_transparent, panel_height, display_server, use_xshape = setup_transparent_window()

    # Override mode if specified
    if args.mode == "desktop":
        use_transparent = True
    elif args.mode == "window" or args.opaque:
        use_transparent = False
        use_xshape = False

    print(f"[CATAI] Display: {display_server}, Transparent: {use_transparent}, XShape: {use_xshape}, Panel: {panel_height}px")

    pygame.init()
    info   = pygame.display.Info()
    sw, sh = info.current_w, info.current_h

    # Create window — always fullscreen borderless for desktop mode
    flags  = pygame.NOFRAME
    if args.fullscreen or use_transparent:
        screen = pygame.display.set_mode((sw, sh), flags)
    else:
        sw = min(sw, 1280)
        sh = min(sh, 800)
        screen = pygame.display.set_mode((sw, sh), flags)

    scanline_overlay = None
    x11_win_id = None  # X11 window ID for X Shape transparency
    offscreen = None    # Off-screen SRCALPHA surface for X Shape rendering
    xshape_dpy = None   # Cached X11 Display connection for shape updates

    pygame.display.set_caption("CATAI Linux")

    try:
        pygame.display.set_icon(
            make_cat_surface((255,140,0), "idle", 0, 32)
        )
    except Exception:
        pass

    # Set up X11 window properties for desktop overlay
    if use_transparent and display_server == "x11":
        try:
            ok, x11_win_id = setup_x11_transparent_window()
            if not ok:
                x11_win_id = None
        except Exception:
            pass

    # Initialize sound system
    sound_enabled = args.sound if args.sound is not None else not args.no_sound
    sound_manager = SoundManager(enabled=sound_enabled)

    # Settings + memory
    settings = load_settings()
    memory   = load_memory()

    if args.model:   settings["model"] = args.model
    if args.scale:   settings["scale"] = args.scale
    if args.cats:    settings["cats"]  = args.cats

    scale = settings.get("scale", SCALE)
    lang  = settings.get("lang", "en")

    # Calculate usable screen area (accounting for panel)
    usable_h = sh - panel_height
    cat_floor_y = usable_h  # cats walk at panel level (like macOS dock)

    # Spawn cats — position them on the "floor" (panel/taskbar)
    cat_keys = settings.get("cats", ["orange"])
    cats: list[Cat] = []
    for key in cat_keys:
        if key in CAT_COLORS:
            cats.append(_make_cat(key, sw, usable_h, scale))

    if not cats:
        cats.append(_make_cat("orange", sw, usable_h, scale))

    # Position cats on the floor (like macOS: feet on dock)
    for cat in cats:
        cat.y = cat_floor_y - cat.size

    settings_panel = SettingsPanel(sw, sh)
    settings_panel.refresh_models()
    clock          = pygame.time.Clock()
    ollama_ok      = False
    ollama_check_t = 0.0
    model_refresh_t = 0.0

    # Right-click context menu state
    context_menu = None  # dict with "pos", "items" or None

    # Active window tracking (X11 only)
    window_track_t = 0.0
    active_win_geom = None  # (x, y, w, h) or None

    # Copy rotation sprites from original if they exist in ori/ but not in sprites/
    _ensure_rotations()

    # ── Main loop ──
    while True:
        dt = clock.tick(60) / 1000.0
        lang = settings.get("lang", "en")

        # Periodic Ollama check (main thread, simple and safe)
        ollama_check_t -= dt
        if ollama_check_t <= 0:
            ollama_check_t = 5.0
            ollama_ok = ollama_available()

        # Refresh model list periodically
        model_refresh_t -= dt
        if model_refresh_t <= 0:
            model_refresh_t = 30.0
            settings_panel.refresh_models()

        # Window tracking (X11 only, every 2 seconds)
        if display_server == "x11":
            window_track_t -= dt
            if window_track_t <= 0:
                window_track_t = 2.0
                active_win_geom = get_active_window_geometry_x11()

        # ── Events ──
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_settings(settings)
                save_memory(memory)
                if xshape_dpy:
                    try: xshape_dpy.close()
                    except: pass
                pygame.quit()
                sys.exit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and \
                   (event.mod & pygame.KMOD_CTRL):
                    save_settings(settings)
                    save_memory(memory)
                    if xshape_dpy:
                        try: xshape_dpy.close()
                        except: pass
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_s and \
                   (event.mod & pygame.KMOD_CTRL):
                    settings_panel.toggle()

                settings_panel.handle_key(event, settings)
                # Only send keys to the visible chat
                for cat in cats:
                    if cat.chat.visible:
                        cat.chat.handle_key(event, settings["model"], memory, settings)
                        break

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos

                # Check context menu first
                if context_menu is not None:
                    menu_consumed = _handle_context_menu_click(
                        pos, context_menu, settings, cats, sw, sh, settings_panel)
                    context_menu = None
                    if menu_consumed:
                        continue

                # Settings panel click
                if settings_panel.handle_click(pos, settings, cats, sw, sh):
                    sound_manager.play("click")
                # Chat bubbles
                elif any(cat.chat.handle_click(pos) for cat in cats):
                    pass
                # HUD settings button (window mode only)
                elif not use_transparent and pos[1] >= sh - 28 and pos[0] >= sw - 100:
                    settings_panel.toggle()
                    sound_manager.play("click")
                else:
                    # Cat interaction
                    for cat in reversed(cats):
                        if cat.rect.collidepoint(pos):
                            if event.button == 1:
                                # Left-click/drag: record start position
                                # Will distinguish click vs drag on mouseup
                                cat.mouse_down_pos = pos
                                cat.mouse_down_time = time.time()
                                cat.drag_offset = (
                                    pos[0] - cat.x,
                                    pos[1] - cat.y
                                )
                            elif event.button == 3:
                                # Right-click: context menu (like macOS)
                                context_menu = {
                                    "pos": pos,
                                    "cat": cat,
                                    "items": [
                                        ("settings", l10n("settings", lang)),
                                        ("quit", l10n("quit", lang)),
                                    ],
                                }
                                sound_manager.play("click")
                            break

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    pos = event.pos
                    # End slider drag
                    settings_panel.handle_mouse_up()

                    for cat in cats:
                        if cat.mouse_down_pos is not None:
                            # Calculate distance from mouse down
                            dx = pos[0] - cat.mouse_down_pos[0]
                            dy = pos[1] - cat.mouse_down_pos[1]
                            dist = math.sqrt(dx*dx + dy*dy)

                            if dist < DRAG_THRESHOLD:
                                # It's a click → toggle chat (like macOS)
                                if cat.chat.visible:
                                    cat.chat.visible = False
                                else:
                                    # Close other chat bubbles
                                    for c in cats:
                                        if c is not cat:
                                            c.chat.visible = False
                                    cat.chat.toggle()
                                    sound_manager.play("click")
                            # Either way, end drag
                            cat.dragging = False
                            cat.mouse_down_pos = None

            elif event.type == pygame.MOUSEMOTION:
                # Settings slider dragging
                if settings_panel._slider_dragging:
                    settings_panel.handle_drag(event.pos, settings, cats)

                for cat in cats:
                    if cat.mouse_down_pos is not None and event.buttons[0]:
                        # Left-button drag → move cat
                        dx = event.pos[0] - cat.mouse_down_pos[0]
                        dy = event.pos[1] - cat.mouse_down_pos[1]
                        dist = math.sqrt(dx*dx + dy*dy)
                        if dist >= DRAG_THRESHOLD:
                            cat.dragging = True
                            cat.x = event.pos[0] - cat.drag_offset[0]
                            cat.y = event.pos[1] - cat.drag_offset[1]
                            cat.x = max(0, min(sw - cat.size, cat.x))
                            cat.y = max(0, min(usable_h - cat.size, cat.y))

        # ── Update ──
        for cat in cats:
            prev_bubble_text = cat.bubble_text
            prev_state = cat.state

            cat.update(dt, sw, usable_h, lang)

            # Keep cats on the floor (like macOS dock walking)
            if not cat.dragging and cat.y > cat_floor_y - cat.size:
                cat.y = cat_floor_y - cat.size

            # Sound effects
            if cat.bubble_text and not prev_bubble_text:
                sound_manager.play("meow")
            if cat.state == "sleeping" and prev_state != "sleeping":
                sound_manager.play("purr")

        # ── Draw ──
        if use_xshape and x11_win_id is not None:
            # Render to off-screen SRCALPHA surface for X Shape transparency
            if offscreen is None or offscreen.get_size() != (sw, sh):
                offscreen = pygame.Surface((sw, sh), pygame.SRCALPHA)
            offscreen.fill((0, 0, 0, 0))
            target = offscreen
        elif use_transparent:
            screen.fill((0, 0, 0, 0))
            target = screen
        else:
            screen.fill((12, 10, 20))
            # Subtle scanline effect
            if sh < 1200:
                if scanline_overlay is None or scanline_overlay.get_size() != (sw, sh):
                    scanline_overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    for y in range(0, sh, 4):
                        pygame.draw.line(scanline_overlay, (0, 0, 0, 30), (0, y), (sw, y))
                screen.blit(scanline_overlay, (0, 0))
            target = screen

        for cat in cats:
            cat.draw(target)

        for cat in cats:
            cat.chat.draw(target, memory, settings)

        settings_panel.draw(target, settings, cats, ollama_ok)

        # HUD (only in window mode)
        if not use_transparent:
            draw_hud(target, cats, settings, ollama_ok, settings_panel.visible, False)

        # Context menu
        if context_menu is not None:
            _draw_context_menu(target, context_menu, lang)

        # Apply X Shape mask and blit to display
        if use_xshape and x11_win_id is not None:
            _, xshape_dpy = apply_window_shape(target, x11_win_id, xshape_dpy)
            screen.fill((0, 0, 0))
            screen.blit(target, (0, 0))

        pygame.display.flip()


def _ensure_rotations():
    """Copy rotation sprites from ori/ if they don't exist in sprites/."""
    ori_rot = Path(__file__).parent / "ori" / "CATAI" / SPRITE_SUBDIR / "rotations"
    target_rot = SPRITE_DIR / "orange" / "rotations"

    if ori_rot.is_dir() and not target_rot.exists():
        import shutil
        shutil.copytree(ori_rot, target_rot)
        print(f"Copied rotation sprites to {target_rot}")

    # Also copy animation folders if they don't exist in sprites/
    ori_anim = Path(__file__).parent / "ori" / "CATAI" / SPRITE_SUBDIR / "animations"
    if ori_anim.is_dir():
        target_anim = SPRITE_DIR / "orange"
        for anim_dir in ori_anim.iterdir():
            if anim_dir.is_dir() and not (target_anim / anim_dir.name).exists():
                import shutil
                shutil.copytree(anim_dir, target_anim / anim_dir.name)
                print(f"Copied animation sprites to {target_anim / anim_dir.name}")


if __name__ == "__main__":
    main()