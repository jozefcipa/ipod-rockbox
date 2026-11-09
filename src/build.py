#!/usr/bin/env python3
'''Build the Spotify + Glass Rockbox themes for iPod Classic (320x240) and render PNG mockups.

Run: python3 src/build.py   (needs Pillow)
Every coordinate lives here once: the .wps/.sbs files and the mockups come from the same
layout calls, and mockups use the real Rockbox BDF fonts, so previews match the device.
'''
import bisect
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, BdfFontFile

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
THEMES = ROOT / 'themes'
PREVIEW = ROOT / 'preview'
CACHE = SRC / '.fontcache'
W, H = 320, 240
SS = 4  # supersampling for shapes and icons

# Rockbox list icon ids (apps/gui/icon.h enum themable_icons) -> our icon shape. Unlisted ids get no icon.
ICONS = {0: 'note', 1: 'folder', 2: 'playlist', 8: 'gear', 9: 'plugins', 10: 'star', 17: 'toggle',
         18: 'ring', 19: 'chevron', 20: 'gear', 23: 'gear', 24: 'system', 25: 'nowplaying', 29: 'folder'}
# Main menu rows with the icon id Rockbox gives each (apps/root_menu.c)
MENU = [('Files', 29), ('Database', 0), ('Now Playing', 25), ('Settings', 20), ('Playlists', 2),
        ('Plugins', 9), ('System', 24), ('Shortcuts', 10)]
SONG = dict(title='Midnight City', artist='M83', album="Hurry Up, We're Dreaming", next='Wait', pos=102, len=243)


def rgb(h, a=255):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def mmss(s):
    return f'{s // 60}:{s % 60:02d}'


# ---------- pixels ----------

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
LEVELS5 = [v << 3 | v >> 2 for v in range(32)]
LEVELS6 = [v << 2 | v >> 4 for v in range(64)]


def _snap(v, levels, t):
    hi = bisect.bisect_left(levels, v)
    if levels[hi] == v:
        return v  # exactly representable: never dither it
    lo = levels[hi - 1]
    return levels[hi] if (v - lo) / (levels[hi] - lo) >= t else lo


def to565(img, dither=True):
    '''Snap to the iPod's RGB565 LCD so the BMPs (and mockups) hold only colours it can show.'''
    img = img.convert('RGB')
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            t = (BAYER[y & 3][x & 3] + 0.5) / 16 if dither else 0.5
            r, g, b = px[x, y]
            px[x, y] = (_snap(r, LEVELS5, t), _snap(g, LEVELS6, t), _snap(b, LEVELS5, t))
    return img


def hex565(h):
    r, g, b = rgb(h)[:3]
    return '%02X%02X%02X' % (_snap(r, LEVELS5, 0.5), _snap(g, LEVELS6, 0.5), _snap(b, LEVELS5, 0.5))


def mask(size, box, radius):
    '''Anti-aliased rounded-rect mask.'''
    m = Image.new('L', (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([v * SS for v in box], radius=radius * SS, fill=255)
    return m.resize(size, Image.LANCZOS)


def vgradient(top, bottom, stop=H):
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    a, b = rgb(top), rgb(bottom)
    for y in range(H):
        t = min(1, y / stop)
        d.line([(0, y), (W, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return img


def icon(kind, n, color, dot=False, pad=0):
    '''Vector-ish icon drawn at SS x and downsampled. pad adds room below for the "active" dot.'''
    img = Image.new('RGBA', (n * SS, (n + pad) * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = lambda *v: [x * n * SS for x in v]
    lw = max(SS, round(n * SS * 0.1))
    if kind == 'play':
        d.polygon(u(0.22, 0.1, 0.9, 0.5, 0.22, 0.9), fill=color)
    elif kind == 'pause':
        d.rounded_rectangle(u(0.2, 0.12, 0.4, 0.88), radius=lw // 2, fill=color)
        d.rounded_rectangle(u(0.6, 0.12, 0.8, 0.88), radius=lw // 2, fill=color)
    elif kind in ('next', 'prev'):
        d.polygon(u(0.1, 0.14, 0.72, 0.5, 0.1, 0.86), fill=color)
        d.rounded_rectangle(u(0.74, 0.14, 0.88, 0.86), radius=lw // 3, fill=color)
    elif kind == 'shuffle':
        d.line(u(0.06, 0.3, 0.32, 0.3, 0.62, 0.7, 0.8, 0.7), fill=color, width=lw, joint='curve')
        d.line(u(0.06, 0.7, 0.32, 0.7, 0.62, 0.3, 0.8, 0.3), fill=color, width=lw, joint='curve')
        d.polygon(u(0.76, 0.14, 0.98, 0.3, 0.76, 0.46), fill=color)
        d.polygon(u(0.76, 0.54, 0.98, 0.7, 0.76, 0.86), fill=color)
    elif kind in ('repeat', 'repeat1'):
        d.rounded_rectangle(u(0.08, 0.26, 0.92, 0.8), radius=n * SS * 0.18, outline=color, width=lw)
        d.rectangle(u(0.46, 0.16, 0.6, 0.36), fill=(0, 0, 0, 0))
        d.polygon(u(0.46, 0.08, 0.66, 0.26, 0.46, 0.44), fill=color)
        if kind == 'repeat1':
            d.rectangle(u(0.45, 0.42, 0.57, 0.66), fill=color)
    elif kind == 'folder':
        d.rounded_rectangle(u(0.06, 0.18, 0.46, 0.4), radius=lw, fill=color)
        d.rounded_rectangle(u(0.06, 0.3, 0.94, 0.84), radius=lw, fill=color)
    elif kind == 'toggle':
        d.rounded_rectangle(u(0.04, 0.26, 0.96, 0.74), radius=n * SS * 0.24, outline=color, width=lw)
        d.ellipse(u(0.52, 0.34, 0.84, 0.66), fill=color)
    elif kind == 'ring':
        d.ellipse(u(0.2, 0.2, 0.8, 0.8), outline=color, width=lw)
    elif kind == 'chevron':
        d.line(u(0.36, 0.18, 0.68, 0.5, 0.36, 0.82), fill=color, width=round(lw * 1.4), joint='curve')
    elif kind == 'nowplaying':
        for i, (a, b) in enumerate([(0.45, 0.85), (0.15, 0.85), (0.3, 0.85), (0.55, 0.85)]):
            x = 0.1 + i * 0.22
            d.rounded_rectangle(u(x, a, x + 0.14, b), radius=lw // 2, fill=color)
    elif kind == 'gear':
        c, ro, ri = n * SS / 2, n * SS * 0.46, n * SS * 0.32
        pts = []
        for i in range(32):
            a = math.pi * 2 * i / 32
            r = ro if (i // 2) % 2 == 0 else ri
            pts.append((c + r * math.cos(a), c + r * math.sin(a)))
        d.polygon(pts, fill=color)
        d.ellipse([c - n * SS * 0.13, c - n * SS * 0.13, c + n * SS * 0.13, c + n * SS * 0.13], fill=(0, 0, 0, 0))
    elif kind == 'playlist':
        for i, w in enumerate([0.8, 0.8, 0.45]):
            y = 0.18 + i * 0.24
            d.rounded_rectangle(u(0.08, y, 0.08 + w, y + 0.12), radius=lw // 2, fill=color)
        d.ellipse(u(0.6, 0.66, 0.8, 0.86), fill=color)
        d.rectangle(u(0.72, 0.42, 0.8, 0.76), fill=color)
    elif kind == 'plugins':
        for i in range(4):
            x, y = 0.1 + (i % 2) * 0.44, 0.1 + (i // 2) * 0.44
            d.rounded_rectangle(u(x, y, x + 0.36, y + 0.36), radius=n * SS * 0.09, fill=color)
    elif kind == 'system':
        d.ellipse(u(0.06, 0.06, 0.94, 0.94), fill=color)
        d.rectangle(u(0.44, 0.42, 0.56, 0.76), fill=(0, 0, 0, 0))
        d.ellipse(u(0.43, 0.2, 0.57, 0.34), fill=(0, 0, 0, 0))
    elif kind == 'star':
        c = n * SS / 2
        pts = [(c + n * SS * (0.48 if i % 2 == 0 else 0.2) * math.sin(math.pi * i / 5),
                c + n * SS * 0.04 - n * SS * (0.48 if i % 2 == 0 else 0.2) * math.cos(math.pi * i / 5)) for i in range(10)]
        d.polygon(pts, fill=color)
    elif kind == 'note':
        d.ellipse(u(0.16, 0.6, 0.5, 0.9), fill=color)
        d.rectangle(u(0.41, 0.1, 0.5, 0.75), fill=color)
        d.polygon(u(0.5, 0.1, 0.84, 0.22, 0.84, 0.38, 0.5, 0.27), fill=color)
    if dot:
        cx, cy, r = n * SS / 2, (n + pad / 2 + 0.5) * SS, 1.5 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    img = img.resize((n, n + pad), Image.LANCZOS)
    return img.transpose(Image.FLIP_LEFT_RIGHT) if kind == 'prev' else img


def icon_strip(color, under=None, n=16):
    '''All 32 list icons stacked vertically, indexed by Rockbox icon id. under: flat colour to blend
    onto (smooth edges), or None for hard edges on magenta when the background varies.'''
    strip = Image.new('RGB', (n, n * 32), (255, 0, 255))
    for i, kind in ICONS.items():
        ic = icon(kind, n, color)
        if under:
            tile = Image.new('RGBA', (n, n), rgb(under))
            tile.alpha_composite(ic)
            tile = tile.convert('RGB')
        else:
            tile = Image.new('RGB', (n, n), (255, 0, 255))
            tile.paste(color[:3], (0, 0), ic.getchannel('A').point(lambda v: 255 if v >= 128 else 0))
        strip.paste(tile, (0, i * n))
    return to565(strip, dither=False)


def disc(n, color, inner, inner_color):
    '''Filled circle with an icon in the middle (Spotify play button).'''
    img = Image.new('RGBA', (n * SS, n * SS), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, n * SS - 1, n * SS - 1], fill=color)
    img = img.resize((n, n), Image.LANCZOS)
    k = round(n * 0.44)
    ic = icon(inner, k, inner_color)
    img.alpha_composite(ic, ((n - k) // 2 + (1 if inner == 'play' else 0), (n - k) // 2))
    return img


def knob(n, color):
    '''Hard-edged circle on magenta, Rockbox's transparent colour (no alpha in skin bitmaps).'''
    img = Image.new('RGB', (n, n), (255, 0, 255))
    ImageDraw.Draw(img).ellipse((0, 0, n - 1, n - 1), fill=color[:3])
    return img


def cover(n):
    '''Made-up album art for the mockups only.'''
    img = Image.new('RGB', (n, n))
    d = ImageDraw.Draw(img)
    a, b = rgb('FF5F6D'), rgb('3A1C71')
    for y in range(n):
        t = y / n
        d.line([(0, y), (n, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    d.ellipse((n * 0.22, n * 0.18, n * 0.78, n * 0.74), fill=rgb('FFC371'))
    for i in range(6):
        y = n * (0.5 + i * 0.07)
        d.rectangle((0, y, n, y + n * 0.025), fill=rgb('3A1C71'))
    return img


# ---------- fonts ----------

_fonts = {}


def font(name):
    if name not in _fonts:
        CACHE.mkdir(exist_ok=True)
        if not (CACHE / f'{name}.pil').exists():
            with open(SRC / 'bdf' / f'{name}.bdf', 'rb') as f:
                BdfFontFile.BdfFontFile(f).save(str(CACHE / name))
        _fonts[name] = ImageFont.load(str(CACHE / f'{name}.pil'))
    return _fonts[name]


def font_h(name):
    # convbdf keeps the declared FONT_ASCENT + FONT_DESCENT, which equals the size prefix for these
    return int(name.split('-')[0])


# ---------- skin builder: emits skin code and draws the mockup in lockstep ----------

class Skin:
    def __init__(self, theme, ext, bg, fonts, ui_font):
        self.theme, self.ext, self.bg = theme, ext, bg
        self.fonts = {1: ui_font, **fonts}
        self.head = [f'# {theme} {ext} for iPod Classic (320x240), generated by src/build.py']
        if ext == 'wps':
            self.head += ['%wd', '%X(bg.bmp)']
            self.files = {'bg.bmp': bg}
        else:
            self.files = {}
        self.head += [f'%Fl({i},{n}.fnt)' for i, n in fonts.items()]
        self.body = []
        self.mock = bg.copy()
        self.labels = iter('ABCDEFGHIJKLMNOPQRSTUVWXYZ')

    def vp(self, x, y, w, h, font_id=1, color='FFFFFF'):
        self.box, self.font_id, self.color, self.lineno = (x, y, w, h), font_id, color, 0
        self.body += ['', f'%V({x},{y},{w},{h},{font_id})', f'%Vf({color})']

    def line(self, *codes):
        self.body.append(''.join(codes))
        self.lineno += 1

    def text(self, *parts):
        '''parts: (align l|c|r, skin expr, mockup sample).'''
        x, y, w, h = self.box
        name = self.fonts[self.font_id]
        f, fh = font(name), font_h(name)
        region = self.mock.crop((x, y, x + w, y + h))
        d = ImageDraw.Draw(region)
        for al, _, sample in parts:
            tw = f.getlength(sample)
            tx = {'l': 0, 'c': (w - tw) // 2, 'r': w - tw}[al]
            d.text((tx, self.lineno * fh), sample, font=f, fill=rgb(self.color))
        self.mock.paste(region, (x, y))
        return '%s' + ''.join(f'%a{al}{expr}' for al, expr, _ in parts)

    def image(self, file, x, y, frames, display, show=0):
        '''frames: RGBA icons, composited onto the backdrop at their final spot (opaque, no fringes).
        display: skin conditional with {a}, {b}, ... standing for each sub-image.'''
        label = next(self.labels)
        ax, ay = self.box[0] + x, self.box[1] + y
        fw, fh = frames[0].size
        patch = self.bg.crop((ax, ay, ax + fw, ay + fh)).convert('RGBA')
        strip = Image.new('RGB', (fw, fh * len(frames)))
        for i, fr in enumerate(frames):
            strip.paste(Image.alpha_composite(patch, fr).convert('RGB'), (0, i * fh))
        strip = to565(strip, dither=False)
        self.files[file] = strip
        self.head.append(f'%xl({label},{file},{x},{y},{len(frames)})')
        self.mock.paste(strip.crop((0, show * fh, fw, show * fh + fh)), (ax, ay))
        subs = {c: f'%xd({label}{c})' for c in 'abcdefgh'[:len(frames)]}
        return display.format(**subs)

    def bar(self, file, w, h, fill, frac, knob_img=None):
        '''Progress bar filling the viewport. Track is baked into the backdrop; fill is drawn on top.'''
        x, y = self.box[:2]
        k = knob_img.width if knob_img else 0
        bw = w - k  # Rockbox shrinks the bar by the slider width
        patch = self.bg.crop((x + k // 2, y, x + k // 2 + bw, y + h)).convert('RGBA')
        patch.alpha_composite(fill.resize((bw, h)))
        self.files[file] = to565(patch, dither=False)
        self.mock.paste(self.files[file].crop((0, 0, round(bw * frac), h)), (x + k // 2, y))
        code = f'%pb(0,0,{w},{h},{file}'
        if knob_img:
            label = next(self.labels)
            self.files['knob.bmp'] = knob_img
            self.head.append(f'%xl({label},knob.bmp)')
            kx = x + round(bw * frac)
            self.mock.paste(knob_img, (kx, y + (h - knob_img.height) // 2), transparent_mask(knob_img))
            code += f',slider,{label}'
        return code + ')'

    def art(self, w, h, noart):
        self.head.append(f'%Cl(0,0,{w},{h},c,c)')
        x, y = self.box[:2]
        code = self.image('noart.bmp', 0, 0, [noart], '%?C<%Cd|{a}>')
        self.mock.paste(cover(w), (x, y))  # image() pasted the placeholder; mockup shows a cover
        return code

    def ui(self, x, y, w, h, row_h, pill, pill_color, fg, sel_fg, icon_fg, icon_under=None, pad=12, sel=1):
        '''Menu area (%Vi) drawn with custom list rows (%Lb). Returns the %Lb tag to put on a rendered line.
        Each row is two viewports sharing label "r": the first draws the selection pill image, the second
        the text. Rockbox wipes a text line's background before drawing it, so the selected text line uses
        the gradient style with both ends set to the pill colour, which keeps the pill intact under it.
        Icons come from two strips (normal / selected) indexed by %LI; %if skips rows with no icon (-1).'''
        fh = font_h(self.fonts[1])
        ty, iy0, tx0 = (row_h - fh) // 2, (row_h - 16) // 2, pad + 26
        label, il, sl = next(self.labels), next(self.labels), next(self.labels)
        strips = {'icons.bmp': icon_strip(rgb(icon_fg), icon_under), 'icons_sel.bmp': icon_strip(rgb(sel_fg), pill_color)}
        self.files.update({'row.bmp': pill, **strips})
        self.head += [f'%xl({label},row.bmp,0,0)', f'%xl({il},icons.bmp,{pad},{iy0},32)',
                      f'%xl({sl},icons_sel.bmp,{pad},{iy0},32)']
        self.body += ['', f'%Vi(-,{x},{y},{w},{h},1)',
                      '', f'%Vl(r,0,0,{w},{row_h},1)',
                      f'%?Lc<%xd({label}a)|>%?if(%LI,>=,0)<%?Lc<%xd({sl},%LI,1)|%xd({il},%LI,1)>|>',
                      '', f'%Vl(r,{tx0},{ty},{w - pad - tx0},{fh},1)', f'%Vf({fg})',
                      f'%Vg({pill_color},{pill_color},{sel_fg})', '%s%?Lc<%Vs(gradient)|>%LT']
        f = font(self.fonts[1])
        for i, (item, icon_id) in enumerate(MENU[:h // row_h]):
            iy = y + i * row_h
            if i == sel:
                self.mock.paste(pill, (x, iy), transparent_mask(pill))
            tile = strips['icons_sel.bmp' if i == sel else 'icons.bmp'].crop((0, icon_id * 16, 16, icon_id * 16 + 16))
            self.mock.paste(tile, (x + pad, iy + iy0), transparent_mask(tile))
            tx = x + tx0
            region = self.mock.crop((tx, iy + ty, x + w - pad, iy + ty + fh))
            ImageDraw.Draw(region).text((0, 0), item, font=f, fill=rgb(sel_fg if i == sel else fg))
            self.mock.paste(region, (tx, iy + ty))
        return f'%Lb(r,{w},{row_h})'

    def save(self):
        out = rb(self.theme) / 'wps'
        (out / self.theme).mkdir(parents=True, exist_ok=True)
        (out / f'{self.theme}.{self.ext}').write_text('\n'.join(self.head + self.body) + '\n')
        for name, img in self.files.items():
            img.convert('RGB').save(out / self.theme / name, 'BMP')
        return self.mock


def transparent_mask(img):
    return Image.frombytes('L', img.size, bytes(0 if p == (255, 0, 255) else 255 for p in img.convert('RGB').get_flattened_data()))


def rb(theme):
    '''Each theme gets its own .rockbox tree, ready to merge onto the iPod.'''
    return THEMES / theme / '.rockbox'


def write_cfg(theme, cfg):
    (rb(theme) / 'themes').mkdir(parents=True, exist_ok=True)
    base = {
        'wps': f'/.rockbox/wps/{theme}.wps',
        'sbs': f'/.rockbox/wps/{theme}.sbs',
        'backdrop': f'/.rockbox/backdrops/{theme}.bmp',
        'statusbar': 'top',
        'show icons': 'off',
        'scrollbar': 'right',
        'scrollbar width': '3',
        'iconset': '-',
        'viewers iconset': '-',
        'filetype colours': '-',
        'ui viewport': '-',
    }
    lines = [f'# {theme} theme for iPod Classic, generated by src/build.py']
    lines += [f'{k}: {v}' for k, v in {**base, **cfg}.items()]
    (rb(theme) / 'themes' / f'{theme}.cfg').write_text('\n'.join(lines) + '\n')


def save_backdrop(theme, img):
    (rb(theme) / 'backdrops').mkdir(parents=True, exist_ok=True)
    img.save(rb(theme) / 'backdrops' / f'{theme}.bmp', 'BMP')


def mp(stop, playing):
    '''%mp branches: stop, play, pause, ffwd, rewind.'''
    return f'%?mp<{stop}|{playing}|{playing}|{playing}|{playing}>'


# ---------- theme 1: Spotify ----------

def spotify():
    GREEN, WHITE, GRAY, DIM = '1DB954', 'FFFFFF', 'B3B3B3', '6A6A6A'
    cfg = {
        'font': '/.rockbox/fonts/15-Adobe-Helvetica.fnt',
        'foreground color': WHITE,
        'background color': '101010',
        'selector type': 'bar (color)',
        'line selector start color': '2A2A2A',
        'line selector end color': '2A2A2A',
        'line selector text color': GREEN,
    }
    ui_font = '15-Adobe-Helvetica'

    # Now Playing
    bg = vgradient('404040', '121212', 200)
    d = ImageDraw.Draw(bg)
    d.line([(13, 10), (18, 15), (23, 10)], fill=rgb(GRAY), width=2)  # collapse chevron
    for i in range(3):
        d.ellipse((294 + i * 5, 12, 296 + i * 5, 14), fill=rgb(GRAY))
    bg = to565(bg)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((19, 181, 300, 184), radius=2, fill=rgb('4D4D4D'))  # progress track
    s = Skin('spotify', 'wps', bg, {2: '18-Adobe-Helvetica-Bold', 3: '15-Adobe-Helvetica',
                                    4: '10-Adobe-Helvetica-Bold', 5: '12-Adobe-Helvetica',
                                    6: '10-Adobe-Helvetica'}, ui_font)
    s.vp(40, 9, 240, 10, 4, GRAY)
    s.line(s.text(('c', 'PLAYING TRACK %pp OF %pe', 'PLAYING TRACK 3 OF 12')))
    s.vp(14, 28, 140, 140)
    noart = Image.new('RGBA', (140, 140), rgb('282828'))
    noart.alpha_composite(icon('note', 56, rgb('7F7F7F')), (42, 42))
    s.line(s.art(140, 140, noart))
    s.vp(166, 36, 146, 18, 2, WHITE)
    s.line(s.text(('l', '%?it<%it|%fn>', SONG['title'])))
    s.vp(166, 58, 146, 15, 3, GRAY)
    s.line(s.text(('l', '%?ia<%ia|Unknown artist>', SONG['artist'])))
    s.vp(166, 76, 146, 12, 5, DIM)
    s.line(s.text(('l', '%id', SONG['album'])))
    s.vp(166, 128, 146, 10, 4, GREEN)
    s.line(s.text(('l', '%?It<NEXT UP|>', 'NEXT UP')))
    s.vp(166, 140, 146, 12, 5, WHITE)
    s.line(s.text(('l', '%?It<%It|>', SONG['next'])))
    s.vp(166, 153, 146, 12, 5, GRAY)
    s.line(s.text(('l', '%?It<%Ia|>', SONG['artist'])))
    s.vp(14, 178, 292, 10)
    fill = Image.new('RGBA', (1, 10), (0, 0, 0, 0))
    for yy in range(3, 7):
        fill.putpixel((0, yy), rgb(GREEN))
    s.line(s.bar('pb.bmp', 292, 10, fill, SONG['pos'] / SONG['len'], knob(10, rgb(WHITE))))
    s.vp(14, 190, 292, 10, 6, GRAY)
    s.line(s.text(('l', '%pc', mmss(SONG['pos'])), ('r', '%pt', mmss(SONG['len']))))
    s.vp(0, 202, 320, 38)
    s.line(
        s.image('shuffle.bmp', 30, 7, [icon('shuffle', 20, rgb(GRAY), pad=6),
                                       icon('shuffle', 20, rgb(GREEN), dot=True, pad=6)],
                '%?ps<{b}|{a}>', show=1),
        s.image('prev.bmp', 90, 9, [icon('prev', 20, rgb(WHITE))], '{a}'),
        s.image('play.bmp', 142, 0, [disc(36, rgb(WHITE), 'play', rgb('000000')),
                                     disc(36, rgb(WHITE), 'pause', rgb('000000'))],
                '%?mp<{a}|{b}|{a}|{b}|{b}>', show=1),
        s.image('next.bmp', 210, 9, [icon('next', 20, rgb(WHITE))], '{a}'),
        s.image('repeat.bmp', 270, 7, [icon('repeat', 20, rgb(GRAY), pad=6),
                                       icon('repeat', 20, rgb(GREEN), dot=True, pad=6),
                                       icon('repeat1', 20, rgb(GREEN), dot=True, pad=6)],
                '%?mm<{a}|{b}|{c}|{b}|{b}>', show=1),
    )
    wps_mock = s.save()

    # Menus (status bar skin + backdrop)
    bg = to565(vgradient('2A2A2A', '101010', 30))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((6, 206, 313, 236), radius=6, fill=rgb('282828'))
    d.rounded_rectangle((11, 211, 31, 231), radius=3, fill=rgb(GREEN))
    bg.paste(icon('note', 14, rgb('000000')), (14, 214), icon('note', 14, rgb('000000')))
    d.rectangle((12, 234, 307, 234), fill=rgb('4D4D4D'))
    save_backdrop('spotify', bg)
    s = Skin('spotify', 'sbs', bg, {2: '18-Adobe-Helvetica-Bold', 4: '12-Adobe-Helvetica-Bold',
                                    5: '12-Adobe-Helvetica'}, ui_font)
    pc = hex565('2A2A2A')
    pill = Image.new('RGBA', (300, 24), rgb('101010'))
    pill.paste(rgb(pc), (0, 0), mask((300, 24), (0, 0, 299, 23), 6))
    lb = s.ui(12, 32, 300, 168, 24, to565(pill, dither=False), pc, WHITE, GREEN, GRAY, '101010')
    s.vp(12, 7, 200, 18, 2, WHITE)
    s.line(lb + s.text(('l', '%?Lt<%Lt|Rockbox>', 'Rockbox')))
    s.vp(210, 10, 100, 12, 5, GRAY)
    s.line(s.text(('r', '%cH:%cM  %bl%%', '14:27  82%')))
    s.vp(38, 209, 236, 12, 4, WHITE)
    s.line(s.text(('l', mp('Nothing playing', '%?it<%it|%fn>'), SONG['title'])))
    s.vp(38, 221, 236, 12, 5, GRAY)
    s.line(s.text(('l', mp('', '%ia'), SONG['artist'])))
    s.vp(284, 211, 20, 20)
    s.line(s.image('mini.bmp', 2, 2, [icon('play', 16, rgb(WHITE)), icon('pause', 16, rgb(WHITE))],
                   '%?mp<{a}|{b}|{a}|{b}|{b}>', show=1))
    s.vp(12, 234, 296, 1)
    s.line(s.bar('pbmini.bmp', 296, 1, Image.new('RGBA', (1, 1), rgb(GREEN)), SONG['pos'] / SONG['len']))
    menu_mock = s.save()
    write_cfg('spotify', cfg)
    return wps_mock, menu_mock


# ---------- theme 2: Glass ----------

def glass_base():
    bg = vgradient('0E1233', '1B0E33')
    blobs = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    for x, y, r, c in [(40, 30, 70, 'FF8A3D'), (270, 50, 95, 'FF3D9A'), (70, 205, 110, '3D6BFF'),
                       (300, 215, 75, '22D3EE'), (170, 120, 60, '8B5CF6')]:
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgb(c, 210))
    bg = Image.alpha_composite(bg.convert('RGBA'), blobs.filter(ImageFilter.GaussianBlur(38)))
    return bg


def glass_panel(bg, box, r, tint=0.16):
    '''Frosted panel: blur what is behind, lift it with white, add a thin bright rim.'''
    x0, y0, x1, y1 = box
    shadow = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 3, x1, y1 + 3), radius=r, fill=(5, 5, 25, 90))
    bg = Image.alpha_composite(bg, shadow.filter(ImageFilter.GaussianBlur(5)))
    frosted = bg.filter(ImageFilter.GaussianBlur(10))
    frosted = Image.alpha_composite(frosted, Image.new('RGBA', bg.size, (255, 255, 255, round(255 * tint))))
    bg.paste(frosted, (0, 0), mask(bg.size, box, r))
    rim = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([v * SS for v in box], radius=r * SS, outline=(255, 255, 255, 80), width=SS)
    hl = Image.new('L', (W * SS, H * SS), 0)  # brighter rim along the top edge, like light hitting glass
    ImageDraw.Draw(hl).rectangle((0, y0 * SS, W * SS, (y0 + r) * SS), fill=255)
    rim2 = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(rim2).rounded_rectangle([v * SS for v in box], radius=r * SS, outline=(255, 255, 255, 110), width=SS)
    rim.paste(rim2, (0, 0), hl)
    return Image.alpha_composite(bg, rim.resize(bg.size, Image.LANCZOS))


def glass():
    WHITE, SOFT, DIM = 'FFFFFF', 'E4E8FF', 'B9C1E6'
    OFF = (255, 255, 255, 115)
    cfg = {
        'font': '/.rockbox/fonts/15-Adobe-Helvetica.fnt',
        'foreground color': WHITE,
        'background color': '1B1440',
        'selector type': 'bar (gradient)',
        'line selector start color': '7A9DFF',
        'line selector end color': '4D63D6',
        'line selector text color': WHITE,
    }
    ui_font = '15-Adobe-Helvetica'
    fonts = {2: '18-Adobe-Helvetica-Bold', 3: '15-Adobe-Helvetica', 4: '14-Adobe-Helvetica-Bold',
             5: '12-Adobe-Helvetica', 6: '10-Adobe-Helvetica', 7: '12-Adobe-Helvetica-Bold'}
    base = glass_base()

    # Now Playing
    bg = glass_panel(base, (8, 24, 311, 183), 16)
    bg = glass_panel(bg, (64, 192, 255, 233), 20, 0.2)
    bg = glass_panel(bg, (12, 195, 47, 230), 17, 0.12)
    bg = glass_panel(bg, (272, 195, 307, 230), 17, 0.12)
    sh = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((20, 39, 131, 150), fill=(0, 0, 20, 120))
    bg = Image.alpha_composite(bg, sh.filter(ImageFilter.GaussianBlur(4)))  # art drop shadow
    bg = to565(bg)
    lines = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    ImageDraw.Draw(lines).rectangle((19, 35, 132, 148), outline=(255, 255, 255, 90))  # 1px rim around the art
    ImageDraw.Draw(lines).rounded_rectangle((25, 155, 294, 157), radius=1, fill=(255, 255, 255, 70))  # progress track
    bg = to565(Image.alpha_composite(bg.convert('RGBA'), lines), dither=False)
    s = Skin('glass', 'wps', bg, fonts, ui_font)
    s.vp(14, 5, 80, 14, 4, WHITE)
    s.line(s.text(('l', '%cH:%cM', '14:27')))
    s.vp(226, 6, 82, 12, 5, WHITE)
    s.line(s.text(('r', '%bl%%', '82%')))
    s.vp(20, 36, 112, 112)
    noart = Image.new('RGBA', (112, 112), (255, 255, 255, 40))
    noart.alpha_composite(icon('note', 48, (255, 255, 255, 190)), (32, 32))
    s.line(s.art(112, 112, noart))
    s.vp(144, 38, 160, 18, 2, WHITE)
    s.line(s.text(('l', '%?it<%it|%fn>', SONG['title'])))
    s.vp(144, 60, 160, 15, 3, SOFT)
    s.line(s.text(('l', '%?ia<%ia|Unknown artist>', SONG['artist'])))
    s.vp(144, 79, 160, 12, 5, DIM)
    s.line(s.text(('l', '%id', SONG['album'])))
    s.vp(144, 122, 160, 12, 5, DIM)
    s.line(s.text(('l', '%pp of %pe  ·  %fc', '3 of 12  ·  FLAC')))
    s.vp(144, 135, 160, 12, 5, DIM)
    s.line(s.text(('l', '%?It<Next: %It|>', f'Next: {SONG["next"]}')))
    s.vp(20, 151, 280, 10)
    fill = Image.new('RGBA', (1, 10), (0, 0, 0, 0))
    for yy in range(4, 7):
        fill.putpixel((0, yy), (255, 255, 255, 245))
    s.line(s.bar('pb.bmp', 280, 10, fill, SONG['pos'] / SONG['len'], knob(10, rgb(WHITE))))
    s.vp(20, 164, 280, 10, 6, 'D6DCF5')
    s.line(s.text(('l', '%pc', mmss(SONG['pos'])), ('r', '-%pr', '-' + mmss(SONG['len'] - SONG['pos']))))
    s.vp(0, 190, 320, 48)
    s.line(
        s.image('shuffle.bmp', 21, 14, [icon('shuffle', 18, OFF), icon('shuffle', 18, rgb(WHITE))],
                '%?ps<{b}|{a}>', show=1),
        s.image('prev.bmp', 93, 12, [icon('prev', 22, rgb(WHITE))], '{a}'),
        s.image('play.bmp', 145, 8, [icon('play', 30, rgb(WHITE)), icon('pause', 30, rgb(WHITE))],
                '%?mp<{a}|{b}|{a}|{b}|{b}>', show=1),
        s.image('next.bmp', 205, 12, [icon('next', 22, rgb(WHITE))], '{a}'),
        s.image('repeat.bmp', 281, 14, [icon('repeat', 18, OFF), icon('repeat', 18, rgb(WHITE)),
                                        icon('repeat1', 18, rgb(WHITE))],
                '%?mm<{a}|{b}|{c}|{b}|{b}>', show=1),
    )
    wps_mock = s.save()

    # Menus
    bg = glass_panel(base, (8, 26, 311, 203), 14)
    bg = glass_panel(bg, (8, 210, 311, 235), 12, 0.2)
    bg = to565(bg)
    save_backdrop('glass', bg)
    s = Skin('glass', 'sbs', bg, {4: fonts[4], 5: fonts[5], 7: fonts[7]}, ui_font)
    pc = hex565('E8ECFF')
    pill = Image.new('RGB', (288, 24), (255, 0, 255))  # magenta corners: the frosted panel shows through
    pill.paste(rgb(pc)[:3], (0, 0), mask((288, 24), (0, 0, 287, 23), 7).point(lambda v: 255 if v >= 128 else 0))
    lb = s.ui(16, 31, 288, 168, 24, pill, pc, WHITE, '1A1F4A', WHITE)
    s.vp(16, 6, 200, 14, 4, WHITE)
    s.line(lb + s.text(('l', '%?Lt<%Lt|Rockbox>', 'Rockbox')))
    s.vp(200, 7, 108, 12, 5, WHITE)
    s.line(s.text(('r', '%cH:%cM   %bl%%', '14:27   82%')))
    s.vp(16, 212, 22, 22)
    s.line(s.image('mini.bmp', 3, 4, [icon('play', 14, rgb(WHITE)), icon('pause', 14, rgb(WHITE))],
                   '%?mp<{a}|{b}|{a}|{b}|{b}>', show=1))
    s.vp(40, 217, 214, 12, 7, WHITE)
    s.line(s.text(('l', mp('Not playing', '%?it<%it|%fn> · %ia'), f'{SONG["title"]} · {SONG["artist"]}')))
    s.vp(256, 217, 46, 12, 5, 'D6DCF5')
    s.line(s.text(('r', mp('', '%pc'), mmss(SONG['pos']))))
    menu_mock = s.save()
    write_cfg('glass', cfg)
    return wps_mock, menu_mock


# ---------- previews ----------

def sheet(rows):
    scale, gap = 2, 24
    font_l = ImageFont.load_default(size=22)
    sw, sh = W * scale, H * scale
    out = Image.new('RGB', (gap + 2 * (sw + gap), gap + len(rows) * (sh + gap + 34)), (24, 24, 28))
    d = ImageDraw.Draw(out)
    for r, (title, imgs) in enumerate(rows):
        y = gap + r * (sh + gap + 34)
        d.text((gap, y), title, font=font_l, fill=(235, 235, 240))
        for c, img in enumerate(imgs):
            out.paste(img.resize((sw, sh), Image.NEAREST), (gap + c * (sw + gap), y + 34))
    return out


def main():
    PREVIEW.mkdir(exist_ok=True)
    rows = []
    for name, fn in [('Spotify', spotify), ('Glass', glass)]:
        wps, menu = fn()
        wps.save(PREVIEW / f'{name.lower()}-wps.png')
        menu.save(PREVIEW / f'{name.lower()}-menu.png')
        rows.append((f'{name}  -  Now Playing / Menu', [wps, menu]))
    sheet(rows).save(PREVIEW / 'all.png')
    print('built', THEMES, 'and', PREVIEW)


if __name__ == '__main__':
    main()
