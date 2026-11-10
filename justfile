# Rockbox + themes for iPod Classic (ipod6g). Run `just` for the recipe list.

set shell := ['bash', '-euo', 'pipefail', '-c']

# Mounted iPod. Auto-detected, override with IPOD=/Volumes/NAME just ...
ipod := env('IPOD', `for d in /Volumes/*; do if [ -d "$d/iPod_Control" ] || [ -d "$d/.rockbox" ]; then echo "$d"; break; fi; done`)

# Rockbox release to install: a version number (4.0) or 'daily'
version := env('ROCKBOX', '4.0')

dl := 'https://download.rockbox.org'
rb_url := if version == 'daily' { dl + '/daily/ipod6g/rockbox-ipod6g.zip' } else { dl + '/release/' + version + '/rockbox-ipod6g-' + version + '.zip' }
fonts_url := if version == 'daily' { dl + '/daily/fonts/rockbox-fonts.zip' } else { dl + '/release/' + version + '/rockbox-fonts-' + version + '.zip' }
bl_url := dl + '/bootloader/ipod/bootloader-ipod6g.ipod'
mks5lboot := '.cache/mks5lboot'

default:
    @just --list

# List themes in this repo
themes:
    @ls themes

# Regenerate spotify + glass (and preview/) from src/build.py
build:
    [ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip -q install 'pillow>=12'; }
    .venv/bin/python src/build.py

# Show the connected iPod: filesystem, Rockbox version, installed themes
status: _need-ipod
    @echo 'iPod: {{ ipod }}'
    @diskutil info '{{ ipod }}' | grep -E 'Volume Name|File System Personality'
    @grep -E '^(Target|Version)' '{{ ipod }}/.rockbox/rockbox-info.txt' 2>/dev/null || echo 'Rockbox: not installed'
    @ls '{{ ipod }}/.rockbox/themes' 2>/dev/null || true

# Build, back up, copy themes + settings to the iPod and eject (default: all themes)
flash *names: build backup (install names) settings && eject

# Copy settings/*.cfg into .rockbox, load them on the iPod via Manage Settings > Browse .cfg Files
settings: _need-ipod
    cp -X settings/*.cfg '{{ ipod }}/.rockbox/'

# Copy themes onto the iPod, merging into .rockbox (default: all themes)
install *names: _need-ipod
    #!/usr/bin/env bash
    set -euo pipefail
    set -- {{ names }}
    [ $# -gt 0 ] || set -- $(ls themes)
    for t in "$@"; do
        [ -d "themes/$t/.rockbox" ] || { echo "unknown theme: $t (see: just themes)"; exit 1; }
        cp -RX "themes/$t/.rockbox/" '{{ ipod }}/.rockbox/'
        echo "installed $t"
    done
    dot_clean -m '{{ ipod }}/.rockbox'
    [ -f '{{ ipod }}/.rockbox/fonts/15-Adobe-Helvetica.fnt' ] || echo 'WARNING: standard fonts missing, spotify/glass need them. Run: just fonts'

# Remove a theme's files from the iPod
uninstall name: _need-ipod
    [ -d 'themes/{{ name }}/.rockbox' ] || { echo 'unknown theme: {{ name }}'; exit 1; }
    cd 'themes/{{ name }}' && find .rockbox -type f -print0 | (cd '{{ ipod }}' && xargs -0 rm -f)
    find '{{ ipod }}/.rockbox/wps' -type d -empty -delete
    @echo 'removed {{ name }}'

# Copy the iPod's .rockbox (settings, themes, database) to backups/<timestamp>
backup: _need-ipod
    mkdir -p backups
    dest="backups/$(date +%Y%m%d-%H%M%S)" && cp -RX '{{ ipod }}/.rockbox' "$dest" && echo "backed up to $dest"

# Copy a backup back onto the iPod, e.g. just restore backups/20261109-201500
restore dir: _need-ipod
    cp -RX '{{ dir }}/' '{{ ipod }}/.rockbox/'
    dot_clean -m '{{ ipod }}/.rockbox'

# Eject the iPod
eject: _need-ipod
    diskutil eject '{{ ipod }}'

# First-time setup: Rockbox + fonts onto the disk, then the bootloader via DFU
setup: rockbox bootloader

# Download Rockbox + the standard fonts and unpack onto the iPod (ROCKBOX=daily for nightly)
rockbox: _need-fat32 fonts
    just _fetch '{{ rb_url }}'
    unzip -oq ".cache/$(basename '{{ rb_url }}')" -d '{{ ipod }}'
    @grep -E '^(Target|Version)' '{{ ipod }}/.rockbox/rockbox-info.txt'

# Download the standard Rockbox fonts pack and unpack onto the iPod
fonts: _need-ipod
    just _fetch '{{ fonts_url }}'
    unzip -oq ".cache/$(basename '{{ fonts_url }}')" -d '{{ ipod }}'

# Install the Rockbox dual-boot bootloader (iPod goes into DFU mode)
bootloader: _mks5lboot
    just _fetch '{{ bl_url }}'
    just _wait-dfu
    {{ mks5lboot }} --bl-inst .cache/bootloader-ipod6g.ipod

# Remove the Rockbox bootloader, iPod boots straight into Apple firmware again
uninstall-bootloader: _mks5lboot
    just _wait-dfu
    {{ mks5lboot }} --bl-uninst ipod6g

[private]
_need-ipod:
    @[ -n '{{ ipod }}' ] && [ -d '{{ ipod }}' ] || { echo 'No iPod mounted. Plug it in (Rockbox and Apple disk mode both mount it) or set IPOD=/Volumes/NAME'; exit 1; }

# Rockbox can't boot from HFS+ (Finder/Mac-restored iPods), only FAT32 (iTunes on Windows)
[private]
_need-fat32: _need-ipod
    @diskutil info '{{ ipod }}' | grep -q 'FAT32' || { echo 'iPod is not FAT32 (Mac-formatted?). Rockbox will not boot from it. Restore it with iTunes on Windows first, see README.'; exit 1; }

[private]
_fetch url:
    mkdir -p .cache
    [ -f ".cache/$(basename '{{ url }}')" ] || curl -fL --progress-bar -o ".cache/$(basename '{{ url }}')" '{{ url }}'

# ponytail: matches the 'DFU device state' line mks5lboot prints, adjust if a future version words it differently
[private]
_wait-dfu:
    @echo 'Quit Music/iTunes. On the iPod: hold SELECT+MENU ~12s until the screen stays black (DFU mode). Waiting...'
    until {{ mks5lboot }} --dfuscan 2>&1 | grep -q 'state'; do sleep 1; done
    @echo 'DFU device found'

# mks5lboot has no macOS binary release, build it from Rockbox source (macOS uses IOKit, no libusb needed)
[private]
_mks5lboot:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -x '{{ mks5lboot }}' ] && exit 0
    src=.cache/rockbox-src
    [ -d "$src" ] || git clone --depth 1 --filter=blob:none --sparse https://github.com/Rockbox/rockbox.git "$src"
    git -C "$src" sparse-checkout set --no-cone /utils/mks5lboot/ /utils/libtools.make /tools/
    make -C "$src/utils/mks5lboot"
    cp "$src/utils/mks5lboot/mks5lboot" '{{ mks5lboot }}'
