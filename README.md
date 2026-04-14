# CATAI Linux

Port Linux de [wil-pe/CATAI](https://github.com/wil-pe/CATAI) — chats pixel art sur le bureau, connectes a Ollama.

## Installation rapide (Fedora 43)

```bash
# Dependances systeme
sudo dnf install python3 python3-pip SDL2 SDL2_image SDL2_mixer SDL2_ttf

# Dependances Python
pip install pygame pillow requests --user

# Lancer
python3 catai.py
```

## Utilisation

| Action | Commande |
|--------|----------|
| Ouvrir chat | Clic gauche sur un chat |
| Deplacer chat | Clic droit + glisser |
| Parametres | Ctrl+S ou bouton [Settings] en bas a droite |
| Quitter | Ctrl+Q |

## Options

```bash
# Spawn des chats specifiques
python3 catai.py --cats orange black grey

# Choisir le modele Ollama
python3 catai.py --model qwen2.5:3b

# Changer la taille des sprites (1-6)
python3 catai.py --scale 4

# Plein ecran
python3 catai.py --fullscreen

# Telecharger les sprites depuis GitHub
python3 catai.py --download

# Fond opaque (desactiver la transparence)
python3 catai.py --opaque
```

## Chats et personnalites

| Couleur | Nom FR | Nom EN | Nom ES | Personnalite |
|---------|--------|--------|--------|--------------|
| orange | Citrouille | Pumpkin | Calabaza | Joueur & farceur |
| black | Ombre | Shadow | Sombra | Mysterieux & philosophe |
| white | Neige | Snow | Nieve | Elegant & poetique |
| grey | Einstein | Einstein | Einstein | Sage & savant |
| brown | Indiana | Indiana | Indiana | Aventurier conteur |
| cream | Caramel | Caramel | Caramelo | Calin & reconfortant |

## Multilingue

L'interface supporte 3 langues : Francais, Anglais, Espagnol.
Changez la langue dans les parametres (Ctrl+S) en cliquant sur [FR], [EN] ou [ES].

Les noms des chats, les personnalites Ollama et les miaulements s'adaptent a la langue.

## Ollama (requis pour le chat IA)

```bash
# Installer Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Demarrer le serveur
ollama serve &

# Telecharger un modele leger (recommande)
ollama pull qwen2.5:3b
# ou
ollama pull llama3.2:3b
```

Sans Ollama, les chats se baladent mais restent muets.

## Sprites personnalises

Placez vos PNGs dans `./sprites/<color>/<state>/<direction>/frame_NNN.png`.

Etats supportes : `angry`, `drinking`, `eating`, `running-8-frames`, `waking-getting-up`
Directions : `east`, `north`, `north-east`, `north-west`, `south`, `south-east`, `south-west`, `west`
Rotations (idle/sleeping) : `./sprites/<color>/rotations/<direction>.png`

Format : PNG 68x68 px avec transparence (RGBA), nommes `frame_000.png` a `frame_NNN.png`.

Les sprites originaux de CATAI macOS (MIT) sont compatibles. Utilisez `--download` pour les telecharger automatiquement.

Les chats non-orange utilisent un systeme de teinte HSB pour coloriser les sprites orange — pas besoin de sprites separes pour chaque couleur.

## Fichiers de configuration

- `~/.catai_settings.json` — preferences (modele, scale, chats actifs, langue)
- `~/.catai_memory.json` — historique de conversations (par chat unique)

## Differences avec CATAI macOS

| Fonctionnalite | macOS | Linux |
|----------------|-------|-------|
| Sprites PNG reels | 368 sprites | via --download ou ori/ |
| Teinte HSB pour couleurs |  |  |
| Integrite Ollama |  |  |
| Personnalites |  |  |
| Memoire conversations | 20 msgs | 20 msgs (~/.catai_memory.json) |
| Overlay dock | AppKit | fenetre sans bord (transparent si X11) |
| Wayland natif | N/A | via SDL2 (XWayland) |
| Bulles aleatoires |  |  |
| Multilingue FR/EN/ES |  |  |
| Etats d'animation | 6 etats | 7 etats (idle, walking, sleeping, eating, drinking, angry, waking) |
| 8 directions |  |  |
| Selection modele Ollama | dropdown | clic pour cycle |
| Edition nom du chat |  |  |
| Telechargement sprites | manuel | --download |

## Licence

MIT — sprites originaux  wil-pe (MIT)