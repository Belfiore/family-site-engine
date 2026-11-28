"""Heritage styles: the settings, the files a site gets, and the suggestion for which style fits a family.

A site picks a style with `style.heritage` in site.config.json (docs/themes.md). The styles themselves are in
engine/themes/ (one CSS file each, listed in engine/themes/registry.json). This module

  * reads and checks the `style` setting (a site without it is built as it always was),
  * puts the style's attribute and stylesheets into the pages,
  * copies only the style files a site needs, and
  * works out which style the family's own data points to (suggest). It only suggests. Nothing is ever switched
    by it, and it reads no network, no model and nothing outside the site's data folder.

What the suggestion reads, and why it is only ever a suggestion, is in docs/themes.md.
"""
import json, os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(os.path.dirname(HERE), 'engine', 'themes')

_registry = None


def registry():
    global _registry
    if _registry is None:
        with open(os.path.join(THEMES_DIR, 'registry.json'), encoding='utf-8') as f:
            _registry = json.load(f)
    return _registry


def themes():
    return {t['id']: t for t in registry()['themes']}


# ------------------------------------------------------------------ the setting
def style_settings(raw):
    """{'id': ..., 'options': {...}} for a site that has applied a style, or None (no style, or the Classic Archive).
    Classic Archive is the look the engine has always had, so choosing it is the same as having no style."""
    s = (raw or {}).get('style')
    if not isinstance(s, dict): return None
    tid = s.get('heritage')
    t = themes().get(tid)
    if not t or not t.get('file'): return None
    opts = s.get('options') if isinstance(s.get('options'), dict) else {}
    return {'id': tid, 'file': t['file'], 'options': {k: v for k, v in opts.items() if k in (t.get('options') or {})}}


def check(cfg):
    """(errors, warnings) for the style setting, beyond what the schema says."""
    errors, warnings = [], []
    s = (cfg.get('_raw') or cfg).get('style')
    if s is None: return errors, warnings
    if not isinstance(s, dict): return ['style: this must be an object, for example {"heritage": "german"}.'], warnings
    tid = s.get('heritage')
    t = themes()
    if tid is not None and tid not in t:
        errors.append('style.heritage: "%s" is not a style. The styles are: %s.' % (tid, ', '.join(sorted(t))))
    elif tid:
        for k, v in (s.get('options') or {}).items():
            if k not in {o for x in t.values() for o in (x.get('options') or {})}:
                errors.append('style.options.%s: this is not an option of any style. The options are: %s.' % (k, ', '.join(sorted({o for x in t.values() for o in (x.get('options') or {})}))))
            elif k not in (t[tid].get('options') or {}):
                warnings.append('style.options.%s: the %s style has no such option. It is ignored.' % (k, tid))
            elif not isinstance(v, bool):
                errors.append('style.options.%s: use true or false.' % k)
    return errors, warnings


# ------------------------------------------------------------------ the pages
def wanted(cfg):
    """True when the pages carry the theme machinery: a site that has applied a style, or one with the settings page
    (which needs every style on hand to try them)."""
    return bool(cfg.get('_style') or cfg.get('_admin'))


def head_tags(cfg, ctx):
    """Links and the small script that go at the end of the head. Nothing for a site without a style or a settings page."""
    if not wanted(cfg): return []
    out = []
    base = ctx['base'] + 'themes/'
    st = cfg.get('_style')
    if st:
        out.append('<link rel="stylesheet" href="%sbase.css">' % base)
        out.append('<link rel="stylesheet" href="%s%s">' % (base, st['file']))
    out.append('<script src="%sheritage.js"></script>' % ctx['base'])
    return out


def html_attrs(cfg):
    st = cfg.get('_style')
    if not st: return ''
    a = ' data-heritage="%s"' % st['id']
    if st['options'].get('texture') is False: a += ' data-h-texture="off"'
    return a


def mark_html(src, cfg):
    """Put the style's attributes on the <html> tag. Unchanged for a site without a style."""
    a = html_attrs(cfg)
    if not a: return src
    return re.sub(r'<html\b', '<html' + a, src, count=1, flags=re.I)


def copy_assets(engine_dir, out_base, cfg):
    """Copy the style files a site needs: every style for a site with the settings page (to try them), only the
    applied style, base.css and the fonts that style names for a site that has applied one, nothing otherwise."""
    if not wanted(cfg): return []
    src, dst = os.path.join(engine_dir, 'themes'), os.path.join(out_base, 'themes')
    if cfg.get('_admin'):
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return ['all']
    os.makedirs(os.path.join(dst, 'fonts'), exist_ok=True)
    names = ['base.css', cfg['_style']['file']]
    for n in names: shutil.copy(os.path.join(src, n), os.path.join(dst, n))
    with open(os.path.join(src, cfg['_style']['file']), encoding='utf-8') as f:
        for fn in sorted(set(re.findall(r'url\(fonts/([^)]+)\)', f.read()))):
            shutil.copy(os.path.join(src, 'fonts', fn), os.path.join(dst, 'fonts', fn))
    return names


# ------------------------------------------------------------------ the suggestion
# Countries the families came to rather than from: they do not point to a heritage style. A family whose places
# are all here gets no European suggestion, and the answer says so.
NEW_WORLD = {'US', 'CA', 'AU', 'NZ'}

# names, in lower case, to the codes the registry uses
COUNTRY_NAMES = {
    'united states': 'US', 'united states of america': 'US', 'usa': 'US', 'u.s.a.': 'US', 'u.s.': 'US', 'us': 'US', 'america': 'US',
    'canada': 'CA', 'australia': 'AU', 'new zealand': 'NZ', 'south africa': 'ZA',
    'england': 'GB-ENG', 'wales': 'GB-WLS', 'scotland': 'GB-SCT', 'northern ireland': 'GB-NIR', 'ireland': 'IE', 'republic of ireland': 'IE', 'eire': 'IE',
    'united kingdom': 'GB-ENG', 'uk': 'GB-ENG', 'great britain': 'GB-ENG', 'britain': 'GB-ENG',
    'germany': 'DE', 'deutschland': 'DE', 'prussia': 'DE', 'austria': 'AT', 'switzerland': 'CH-DE',
    'italy': 'IT', 'italia': 'IT', 'france': 'FR', 'spain': 'ES', 'espana': 'ES', 'españa': 'ES', 'portugal': 'PT', 'mexico': 'MX', 'cuba': 'CU', 'argentina': 'AR',
    'poland': 'PL', 'polska': 'PL', 'czechia': 'CZ', 'czech republic': 'CZ', 'slovakia': 'SK', 'hungary': 'HU', 'ukraine': 'UA', 'lithuania': 'LT', 'latvia': 'LV',
    'estonia': 'EE', 'romania': 'RO', 'russia': 'RU', 'belarus': 'BY', 'croatia': 'HR', 'serbia': 'RS', 'bulgaria': 'BG', 'slovenia': 'SI',
    'sweden': 'SE', 'norway': 'NO', 'denmark': 'DK', 'finland': 'FI', 'iceland': 'IS',
}
# two-letter codes some sites write in a place's "country" field
ISO2 = {'US': 'US', 'CA': 'CA', 'AU': 'AU', 'NZ': 'NZ', 'GB': 'GB-ENG', 'IE': 'IE', 'DE': 'DE', 'AT': 'AT', 'CH': 'CH-DE', 'IT': 'IT', 'FR': 'FR', 'ES': 'ES', 'PT': 'PT',
        'MX': 'MX', 'AR': 'AR', 'PL': 'PL', 'CZ': 'CZ', 'SK': 'SK', 'HU': 'HU', 'UA': 'UA', 'LT': 'LT', 'LV': 'LV', 'EE': 'EE', 'RO': 'RO', 'RU': 'RU',
        'SE': 'SE', 'NO': 'NO', 'DK': 'DK', 'FI': 'FI', 'IS': 'IS', 'ZA': 'ZA'}
US_STATES = {'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado', 'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois',
             'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota', 'mississippi', 'missouri', 'montana',
             'nebraska', 'nevada', 'new hampshire', 'new jersey', 'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
             'pennsylvania', 'rhode island', 'south carolina', 'south dakota', 'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington', 'west virginia',
             'wisconsin', 'wyoming', 'new england'}
US_CODES = {'AL', 'AK', 'AZ', 'AR', 'CO', 'CT', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV',
            'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'}
CA_REGIONS = {'ontario', 'quebec', 'nova scotia', 'new brunswick', 'manitoba', 'alberta', 'british columbia', 'saskatchewan', 'newfoundland', 'prince edward island'}
# regions, counties and ports that name a country on their own (a short list, to read places written without one)
REGIONS = {
    'IT': 'sicily sicilia campania caserta benevento napoli naples agrigento palermo calabria puglia basilicata abruzzo molise lazio roma rome toscana tuscany lombardia lombardy '
          'veneto piemonte piedmont liguria genoa genova sardinia sardegna salerno avellino foggia bari catania messina trapani',
    'DE': 'sachsen saxony bayern bavaria thuringia thüringen brandenburg berlin hamburg bremen dresden leipzig chemnitz bautzen kreis oelsnitz vogtland hannover hessen westfalen '
          'rheinland baden württemberg wuerttemberg schleswig mecklenburg pommern silesia schlesien',
    'GB-ENG': 'london cornwall devon dorset somerset kent surrey sussex essex suffolk norfolk middlesex hertfordshire bedfordshire berkshire hampshire wiltshire gloucestershire '
              'oxfordshire warwickshire birmingham staffordshire worcestershire lancashire yorkshire cheshire cumberland durham northumberland lincolnshire liverpool manchester '
              'bristol southampton portsmouth plymouth bodmin cambridgeshire',
    'GB-SCT': 'orkney shetland aberdeen glasgow edinburgh fife lanarkshire argyll perth inverness dundee highland ayrshire',
    'GB-WLS': 'cardiff swansea glamorgan pembrokeshire gwynedd anglesey monmouthshire',
    'IE': 'cork kerry mayo galway dublin clare tipperary limerick waterford wexford wicklow sligo donegal kilkenny leitrim roscommon westmeath ardmore',
    'GB-NIR': 'antrim down armagh tyrone fermanagh londonderry derry belfast',
    'FR': 'paris normandie normandy bretagne brittany alsace lorraine provence bordeaux lyon marseille picardie',
    'ES': 'madrid barcelona sevilla seville andalucia andalusia cataluña catalonia galicia valencia castilla',
    'PL': 'warszawa warsaw krakow kraków lodz łódź poznan gdansk wroclaw galicia silesia',
    'SE': 'stockholm göteborg gothenburg malmö skåne', 'NO': 'oslo bergen trondheim', 'DK': 'copenhagen københavn jutland', 'FI': 'helsinki',
}
REGION_INDEX = {}
for _code, _words in REGIONS.items():
    for _w in _words.split():
        REGION_INDEX.setdefault(_w, _code)
# rough boxes (south, north, west, east), used only for a place with no country, no name that says one and no home region
BOXES = [
    ('GB-SCT', (55.4, 60.9, -7.8, -1.7)), ('IE', (51.3, 55.45, -10.6, -5.4)), ('GB-WLS', (51.35, 53.45, -5.4, -2.7)), ('GB-ENG', (49.8, 55.8, -6.4, 1.9)),
    ('IT', (36.5, 46.7, 6.6, 18.6)), ('DE', (47.3, 55.0, 5.9, 15.1)),
]
SURNAME_PATTERNS = {
    'DE': r'(mann|stein|berg|bauer|müller|mueller|schmidt|schmitt|meyer|meier|weber|wagner|becker|fischer|hoffmann|schulz|koch|richter|eifler|weickert|just)$',
    'IT': r'(i|ello|etti|elli|ini|ino|one|ucci|atore|ardi)$',
    'PL': r'(ski|ska|cki|wicz|czyk|ewski)$',
    'SE': r'(sson|sen|gren|strom|ström|lund|holm)$',
    'IE': r"^(mc|mac|o')",
    'FR': r'(eau|eaux|ois|ier|ault)$',
}


def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '').lower().replace('.', '. ').replace('  ', ' ')).strip()


def code_of(text):
    """The country code a piece of place text points to, or None. The country is read from the last word group
    that names one; a region or county word is the fallback."""
    if not text: return None
    t = str(text)
    parts = [p.strip() for p in re.split(r'[,;(/)]', t) if p.strip()]
    for p in reversed(parts):
        k = _norm(p).rstrip('.')
        if k in COUNTRY_NAMES: return COUNTRY_NAMES[k]
        if k in US_STATES: return 'US'
        if k in CA_REGIONS: return 'CA'
        if p in US_CODES: return 'US'
    for p in reversed(parts):
        for w in re.findall(r"[\wÀ-ÿ']+", _norm(p)):
            if w in REGION_INDEX: return REGION_INDEX[w]
    return None


def box_code(lat, lng):
    try: lat, lng = float(lat), float(lng)
    except (TypeError, ValueError): return None
    for code, (s, n, w, e) in BOXES:
        if s <= lat <= n and w <= lng <= e: return code
    return None


def place_code(place, home_code):
    """A place's country: its country field, then its own words, then the home region, then its coordinates."""
    c = place.get('country')
    if c:
        k = str(c).strip()
        got = ISO2.get(k.upper()) if len(k) == 2 else COUNTRY_NAMES.get(_norm(k).rstrip('.'))
        if got: return got
        got = code_of(k)
        if got: return got
    for field in ('name', 'address', 'modernAddress', 'historicName'):
        got = code_of(place.get(field))
        if got: return got
    if place.get('inHomeRegion') and home_code: return home_code
    return box_code(place.get('lat'), place.get('lng'))


def _load(site, cfg, name):
    d = os.path.join(site, (cfg.get('data') or {}).get('dir') or 'data', name)
    if not os.path.exists(d): return []
    with open(d, encoding='utf-8') as f: j = json.load(f)
    if isinstance(j, dict): j = j.get(name.split('.')[0]) or []
    return j if isinstance(j, list) else []


def collect(site, cfg):
    """What the data says, as counts. Only people who may be shown on the site count in the people figures
    (never someone living, never someone in a hidden region), and no name leaves this function."""
    mp = cfg.get('map') or {}
    home_code = code_of((mp.get('home') or {}).get('name'))
    places = [p for p in _load(site, cfg, 'places.json') if (p.get('status') in (None, 'published'))]
    people = _load(site, cfg, 'people.json')
    hidden = set((cfg.get('tree') or {}).get('hiddenRegions') or [])
    shown = {p.get('id'): p for p in people if not (p.get('isLiving') or p.get('living')) and not p.get('placeholder') and p.get('region') not in hidden}
    by_id, place_countries = {}, {}
    for p in places:
        c = place_code(p, home_code)
        by_id[p.get('id')] = c
        if c: place_countries[p.get('id')] = c
    births = {}
    for pid, p in shown.items():
        b = p.get('birth') or {}
        c = by_id.get(b.get('placeId')) or code_of(b.get('place'))
        if c: births[pid] = c
    for pl in places:                                               # born events carry the person too
        for e in pl.get('events') or []:
            if e.get('type') != 'born': continue
            for pid in e.get('personIds') or []:
                if pid in shown and pid not in births and by_id.get(pl.get('id')): births[pid] = by_id[pl['id']]
    origins = []
    for p in shown.values():
        im = p.get('immigration')
        for item in ([im] if isinstance(im, dict) else im or []):
            c = None
            m = re.search(r'\bfrom ([^)]+)\)?', str(item.get('port') or ''))
            if m: c = code_of(m.group(1))
            if c: origins.append(c)
        for v in p.get('voyages') or []:
            c = code_of(v.get('from'))
            if c and c not in NEW_WORLD: origins.append(c)
    surnames = {}
    for p in shown.values():
        s = (p.get('surname') or '').strip()
        if s: surnames[s.lower()] = surnames.get(s.lower(), 0) + 1
    return {'places': list(place_countries.values()), 'births': list(births.values()), 'origins': origins,
            'surnames': surnames, 'people_shown': len(shown)}


def surname_codes(surnames):
    out = []
    for s in surnames:
        for code, pat in SURNAME_PATTERNS.items():
            if re.search(pat, s, re.I): out.append(code); break
    return out


def to_style(code):
    for t in registry()['themes']:
        if code in (t.get('countries') or []): return t['id']
    return None


def name_of(code):
    for k, v in COUNTRY_NAMES.items():
        if v == code and len(k) > 3: return k.title() if code not in ('GB-ENG',) else 'England'
    return code


NAMES = {'GB-ENG': 'England', 'GB-WLS': 'Wales', 'GB-SCT': 'Scotland', 'GB-NIR': 'Northern Ireland', 'IE': 'Ireland', 'DE': 'Germany', 'AT': 'Austria', 'IT': 'Italy',
         'FR': 'France', 'ES': 'Spain', 'PT': 'Portugal', 'PL': 'Poland', 'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland', 'IS': 'Iceland',
         'US': 'the United States', 'CA': 'Canada', 'CH-DE': 'Switzerland'}


def _share(codes):
    """Count by style, ignoring countries the family came to. {style: n}, total."""
    out, total = {}, 0
    for c in codes:
        if c in NEW_WORLD: continue
        sid = to_style(c)
        total += 1
        if sid: out[sid] = out.get(sid, 0) + 1
    return out, total


MIN_EVIDENCE = 5
WEIGHTS = {'places': 0.5, 'births': 0.3, 'origins': 0.15, 'surnames': 0.05}


def suggest(site, cfg):
    """Which style the family's own data points to.

    Returns {'suggested': id, 'ranked': [{'id', 'percent'}], 'mixed': bool, 'thin': bool, 'reason': str, 'evidence': {...}}.
    Places, birthplaces and where people sailed from carry the weight; surnames only break ties. A style
    that stands for a religion or a people rather than a country (Jewish and Ashkenazi) is never suggested: nothing
    in the data can say that, and the engine does not guess it.
    """
    d = collect(site, cfg)
    sets = {
        'places': _share(d['places']), 'births': _share(d['births']), 'origins': _share(d['origins']),
        'surnames': _share(surname_codes(d['surnames'])),
    }
    evidence = {k: {'styles': v[0], 'total': v[1]} for k, v in sets.items()}
    used = {k: v for k, v in sets.items() if v[1] > 0 and k != 'surnames'}
    n_points = sum(v[1] for k, v in sets.items() if k != 'surnames')
    new_world = sum(1 for c in d['places'] if c in NEW_WORLD)
    if n_points < MIN_EVIDENCE:
        reason = 'Suggested: Classic Archive. '
        if new_world and new_world >= len(d['places']) * 0.8 and not n_points:
            reason += 'All %d places with a known country are in the United States or Canada, so the data does not point to a heritage style.' % len(d['places'])
        else:
            reason += 'The data names too few places outside the Americas (%d) to say.' % n_points
        return {'suggested': 'classic', 'ranked': [], 'mixed': False, 'thin': True, 'reason': reason, 'evidence': evidence}
    wsum = sum(WEIGHTS[k] for k in used) + (WEIGHTS['surnames'] if sets['surnames'][1] else 0)
    score = {}
    for k, (cnt, tot) in list(used.items()) + ([('surnames', sets['surnames'])] if sets['surnames'][1] else []):
        for sid, n in cnt.items():
            score[sid] = score.get(sid, 0) + WEIGHTS[k] / wsum * (n / tot)
    if not score:
        return {'suggested': 'classic', 'ranked': [], 'mixed': False, 'thin': True, 'evidence': evidence,
                'reason': 'Suggested: Classic Archive. The places outside the Americas are not in a country the styles stand for.'}
    total = sum(score.values())
    ranked = sorted(({'id': k, 'percent': round(100 * v / total)} for k, v in score.items()), key=lambda r: -r['percent'])
    top = ranked[0]
    ts = themes()
    p_cnt, p_tot = sets['places']
    b_cnt, b_tot = sets['births']
    if top['percent'] >= 60:
        bits = []
        if p_tot: bits.append('%d%% of places with a known country (outside the United States and Canada) are in %s (%d of %d)' % (round(100 * p_cnt.get(top['id'], 0) / p_tot), _countries(top['id'], d['places']), p_cnt.get(top['id'], 0), p_tot))
        if b_tot: bits.append('%d of %d birthplaces named are there too' % (b_cnt.get(top['id'], 0), b_tot))
        reason = 'Suggested: %s. %s.' % (ts[top['id']]['name'], '; '.join(bits) if bits else 'Most of the data points there')
        second = [r for r in ranked[1:] if r['percent'] >= 15]
        if second: reason += ' Also in the data: %s.' % ', '.join('%s %d%%' % (ts[r['id']]['name'], r['percent']) for r in second)
        return {'suggested': top['id'], 'ranked': ranked[:3], 'mixed': False, 'thin': False, 'reason': reason, 'evidence': evidence}
    keep = [r for r in ranked if r['percent'] >= 15][:3] or ranked[:2]
    reason = 'Suggested: %s. The data points to more than one: %s.' % (ts[keep[0]['id']]['name'], ', '.join('%s %d%%' % (ts[r['id']]['name'], r['percent']) for r in keep))
    return {'suggested': keep[0]['id'], 'ranked': keep, 'mixed': True, 'thin': False, 'reason': reason, 'evidence': evidence}


def _countries(style_id, place_codes):
    codes = sorted({c for c in place_codes if to_style(c) == style_id})
    names = [NAMES.get(c, c) for c in codes]
    return ' and '.join(names) if len(names) <= 2 else ', '.join(names[:-1]) + ' and ' + names[-1]
