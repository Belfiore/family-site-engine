#!/usr/bin/env python3
"""Make the basicAccess settings for a site's family password (docs/basic-access.md).

    python3 tools/basic-password.py              asks for the password (not shown) and prints the block
    python3 tools/basic-password.py --scope all  every page asks, not just the home page

Paste the printed block into site.config.json. The password itself is not printed and not saved anywhere: only a random
salt and a hash of it. Use a long passphrase (four or five unrelated words). This is a stopgap for a site that is still
on GitHub Pages, not protection: the pages stay public.
"""
import argparse, base64, getpass, hashlib, json, os, sys, unicodedata

ITERATIONS = 210000


def make(password, iterations=ITERATIONS, salt=None):
    salt = salt if salt is not None else os.urandom(16)
    raw = hashlib.pbkdf2_hmac('sha256', unicodedata.normalize('NFKC', password).encode('utf-8'), salt, iterations, 32)
    return {'salt': base64.b64encode(salt).decode('ascii'), 'hash': base64.b64encode(raw).decode('ascii'), 'iterations': iterations}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make a site's basicAccess settings.")
    ap.add_argument('--scope', choices=('home', 'all'), default='home')
    ap.add_argument('--days', type=int, default=30)
    a = ap.parse_args(argv)
    pw = getpass.getpass('Family password (not shown): ')
    if len(pw) < 12:
        print('That is short. A long passphrase of several words is much harder to guess from the published hash.', file=sys.stderr)
    if pw != getpass.getpass('Again: '):
        print('The two did not match. Nothing made.', file=sys.stderr)
        return 1
    if not pw:
        print('No password given. Nothing made.', file=sys.stderr)
        return 1
    block = dict({'enabled': True, 'scope': a.scope}, **make(pw), days=a.days)
    print(json.dumps({'basicAccess': block}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
