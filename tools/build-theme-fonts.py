"""Copy the woff2 files the heritage themes use out of the @fontsource packages (all SIL Open Font Licence) and print
the @font-face rules for each theme.

    npm i --prefix /tmp/fonts @fontsource/<each family below>
    python3 tools/build-theme-fonts.py /tmp/fonts/node_modules/@fontsource

The woff2 files go to engine/themes/fonts/. The printed CSS is pasted into the top of engine/themes/<id>.css (the files
that are already there keep it). Run it again only to add a family or a weight. Families are named hf-<slug> so they
never clash with a font a site loads itself.
"""
import os, shutil, sys

SRC = sys.argv[1]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engine', 'themes', 'fonts')

# theme: [(package, weights, styles)]
THEMES = {
    'english':     [('im-fell-english', [400], ['normal', 'italic']), ('libre-baskerville', [400, 700], ['normal']), ('libre-baskerville', [400], ['italic'])],
    'german':      [('work-sans', [400, 600], ['normal']), ('work-sans', [400], ['italic']), ('unifrakturcook', [700], ['normal'])],
    'italian':     [('marcellus', [400], ['normal']), ('eb-garamond', [400, 600], ['normal']), ('eb-garamond', [400], ['italic'])],
    'irish':       [('uncial-antiqua', [400], ['normal']), ('crimson-pro', [400, 600], ['normal']), ('crimson-pro', [400], ['italic'])],
    'scottish':    [('spectral', [600], ['normal']), ('source-serif-4', [400, 600], ['normal']), ('source-serif-4', [400], ['italic'])],
    'french':      [('playfair-display', [700], ['normal']), ('playfair-display', [400], ['italic']), ('lora', [400, 700], ['normal']), ('lora', [400], ['italic'])],
    'spanish':     [('fraunces', [600], ['normal']), ('karla', [400, 700], ['normal']), ('karla', [400], ['italic'])],
    'polish':      [('bitter', [600], ['normal']), ('alegreya-sans', [400, 700], ['normal']), ('alegreya-sans', [400], ['italic'])],
    'scandinavian': [('josefin-sans', [600], ['normal']), ('source-sans-3', [400, 600], ['normal']), ('source-sans-3', [400], ['italic'])],
    'jewish':      [('frank-ruhl-libre', [500, 700], ['normal']), ('crimson-text', [400, 600], ['normal']), ('crimson-text', [400], ['italic'])],
}
NAMES = {'im-fell-english': 'IM Fell English', 'libre-baskerville': 'Libre Baskerville', 'work-sans': 'Work Sans', 'unifrakturcook': 'UnifrakturCook',
         'marcellus': 'Marcellus', 'eb-garamond': 'EB Garamond', 'uncial-antiqua': 'Uncial Antiqua', 'crimson-pro': 'Crimson Pro', 'spectral': 'Spectral',
         'source-serif-4': 'Source Serif 4', 'playfair-display': 'Playfair Display', 'lora': 'Lora', 'fraunces': 'Fraunces', 'karla': 'Karla',
         'bitter': 'Bitter', 'alegreya-sans': 'Alegreya Sans', 'josefin-sans': 'Josefin Sans', 'source-sans-3': 'Source Sans 3',
         'frank-ruhl-libre': 'Frank Ruhl Libre', 'crimson-text': 'Crimson Text'}
RANGES = {'latin': 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD',
          'latin-ext': 'U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF'}
os.makedirs(OUT, exist_ok=True)
for theme, fams in THEMES.items():
    css = []
    for pkg, weights, styles in fams:
        for st in styles:
            for w in weights:
                for sub in ('latin', 'latin-ext'):
                    name = '%s-%s-%s-%s.woff2' % (pkg, sub, w, st)
                    src = os.path.join(SRC, pkg, 'files', name)
                    if not os.path.exists(src):
                        if sub == 'latin-ext': continue      # some families have no extended set
                        sys.exit('missing ' + src)
                    shutil.copy(src, os.path.join(OUT, name))
                    css.append("@font-face { font-family: 'hf-%s'; font-style: %s; font-weight: %d; font-display: swap; src: url(fonts/%s) format('woff2'); unicode-range: %s; }"
                               % (pkg, st, w, name, RANGES[sub]))
    print('/* ===== %s ===== */' % theme)
    print('\n'.join(css))
