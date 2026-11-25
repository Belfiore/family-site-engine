"""Read a JavaScript data file (const NAME = { ... };) without running it.

Older family sites kept their data as a JavaScript object literal: unquoted keys, single or double quotes,
comments and trailing commas. This reads that literal as data, so a converter never has to execute a site's
script to get at its contents. Only literals are understood (objects, arrays, strings, numbers, true, false,
null, undefined); anything else, such as a function call, is an error.
"""
import re

TOKEN = re.compile(r'''
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\$]|\$(?!\{))*`)
  | (?P<num>-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_$][A-Za-z0-9_$]*)
  | (?P<punct>[{}\[\]:,;=().!?<>+\-*/%&|^~@#])
''', re.S | re.X)

ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0'}


def unquote(s):
    body, out, i = s[1:-1], [], 0
    while i < len(body):
        c = body[i]
        if c == '\\' and i + 1 < len(body):
            n = body[i + 1]
            if n == 'u' and re.match(r'[0-9a-fA-F]{4}', body[i + 2:i + 6]):
                out.append(chr(int(body[i + 2:i + 6], 16))); i += 6; continue
            if n == '\n':
                i += 2; continue
            out.append(ESCAPES.get(n, n)); i += 2; continue
        out.append(c); i += 1
    return ''.join(out)


def tokens(src, pos=0):
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            line = src.count('\n', 0, pos) + 1
            raise ValueError('line %d: cannot read %r' % (line, src[pos:pos + 30]))
        pos = m.end()
        kind = m.lastgroup
        if kind in ('ws', 'comment'): continue
        yield kind, m.group(kind), src.count('\n', 0, m.start()) + 1


class Reader:
    """Reads one value from a stream of tokens, taking only as many tokens as the value needs."""
    def __init__(self, toks):
        self.toks = toks
        self.buf = []

    def peek(self):
        if not self.buf:
            self.buf.append(next(self.toks, (None, None, None)))
        return self.buf[0]

    def take(self, value=None):
        t = self.peek()
        self.buf.pop(0)
        if t[0] is None: raise ValueError('the file ends too early')
        if value is not None and t[1] != value: raise ValueError('line %s: expected %r, found %r' % (t[2], value, t[1]))
        return t

    def value(self):
        kind, text, line = self.take()
        if text == '{':
            obj = {}
            while self.peek()[1] != '}':
                k, key, kl = self.take()
                if k == 'str': key = unquote(key)
                elif k not in ('name', 'num'): raise ValueError('line %s: a key cannot be %r' % (kl, key))
                self.take(':')
                obj[key] = self.value()
                if self.peek()[1] == ',': self.take(',')
                elif self.peek()[1] != '}': raise ValueError('line %s: expected , or }' % self.peek()[2])
            self.take('}')
            return obj
        if text == '[':
            arr = []
            while self.peek()[1] != ']':
                arr.append(self.value())
                if self.peek()[1] == ',': self.take(',')
                elif self.peek()[1] != ']': raise ValueError('line %s: expected , or ]' % self.peek()[2])
            self.take(']')
            return arr
        if kind == 'str': return unquote(text)
        if kind == 'num': return float(text) if re.search(r'[.eE]', text) else int(text)
        if text == '-' and self.peek()[0] == 'num':
            v = self.value(); return -v
        if kind == 'name' and text in ('true', 'false', 'null', 'undefined'):
            return {'true': True, 'false': False, 'null': None, 'undefined': None}[text]
        raise ValueError('line %s: %r is not data (only objects, arrays, strings, numbers, true, false and null are read)' % (line, text))


def read_assignment(src, name=None):
    """The value assigned in `const NAME = ...` (or var or let): the first such assignment if no name is given."""
    toks = tokens(src)
    window = []
    for t in toks:
        window = (window + [t])[-3:]
        if len(window) == 3 and window[0][0] == 'name' and window[0][1] in ('const', 'var', 'let') and window[1][0] == 'name' and window[2][1] == '=':
            if name is None or window[1][1] == name:
                return window[1][1], Reader(toks).value()
    raise ValueError('no assignment to %s found' % (name or 'a constant'))
