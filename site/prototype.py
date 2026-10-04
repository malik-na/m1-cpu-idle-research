#!/usr/bin/env python3
"""THROWAWAY: three visual explanations on the existing / route, via ?variant=A/B/C.

Question: which structure best explains recorded M1 observations and their limits?
Run: python3 site/prototype.py
Only this development entry point injects the variants and switcher.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# Keep the one-command preview independent of the user's global Python packages.
if importlib.util.find_spec('markdown') is None:
    environment = Path(tempfile.gettempdir()) / 'm1-visual-prototype-python'
    python = environment / 'bin/python'
    if not python.exists():
        subprocess.check_call([sys.executable, '-m', 'venv', str(environment)])
    subprocess.check_call([str(python), '-m', 'pip', 'install', 'Markdown==3.7'])
    os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import build

SITE = Path(__file__).resolve().parent
VARIANTS = SITE / 'prototype-variants'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix='m1-visual-prototype-'))
    revision = build.git('rev-parse', 'HEAD').decode().strip()
    builder = build.Builder(revision, '/')
    builder.build(build.safe_output(output))
    report_path = 'experiments/aurora-apsc-observer/native-evidence/abi3-E/validator-report.json'
    report = json.loads(builder.files[report_path])
    data = {'revision': revision, 'report': report, 'witnesses': report['witnesses']}
    body = '''<div class="prototype-notice"><strong>Visual prototype</strong>
        Three ways to explain the same saved evidence. Choose a direction; this page is a throwaway preview.</div>'''
    for name in ('story', 'lab', 'map'):
        body += (VARIANTS / (name + '.html')).read_text()
        (output / 'assets' / ('prototype-' + name + '.css')).write_text((VARIANTS / (name + '.css')).read_text())
        (output / 'assets' / ('prototype-' + name + '.js')).write_text((VARIANTS / (name + '.js')).read_text())
    body += '''<aside id="prototype-switcher" aria-label="Compare visual prototypes">
      <button id="prototype-previous" aria-label="Previous variant">←</button>
      <div><span class="switcher-kicker">COMPARE DIRECTIONS</span><strong id="prototype-label"></strong></div>
      <button id="prototype-next" aria-label="Next variant">→</button>
      <button id="prototype-state-toggle" aria-expanded="false" aria-controls="prototype-state">State</button>
    </aside><pre id="prototype-state" hidden></pre>'''
    page = builder.layout('Visual prototype', body, active='overview', description='Throwaway visual examples of the recorded M1 CPU-idle findings.')
    styles = ''.join('<link rel="stylesheet" href="/assets/prototype-' + name + '.css">' for name in ('story', 'lab', 'map'))
    styles += '<link rel="stylesheet" href="/assets/prototype-shell.css">'
    scripts = '<script>window.PROTOTYPE_DATA=' + json.dumps(data).replace('</', '<\\/') + ';</script>'
    scripts += ''.join('<script src="/assets/prototype-' + name + '.js"></script>' for name in ('story', 'lab', 'map'))
    scripts += '<script src="/assets/prototype-switcher.js"></script>'
    page = page.replace('</head>', styles + '</head>').replace('</body>', scripts + '</body>')
    (output / 'index.html').write_text(page)
    for name in ('prototype-shell.css', 'prototype-switcher.js'):
        (output / 'assets' / name).write_text((SITE / name).read_text())
    print('Prototype: http://localhost:' + str(args.port) + '/?variant=A', flush=True)
    if not args.build_only:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(output)))
        server.serve_forever()


if __name__ == '__main__':
    main()
