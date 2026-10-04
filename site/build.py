#!/usr/bin/env python3
"""Render an immutable, curated research snapshot; never serve a working tree."""
import argparse
import html
import json
import posixpath
import re
import shutil
import subprocess
from string import Template
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
REPO = 'https://github.com/malik-na/m1-cpu-idle-research'
ORIGIN = 'https://malik-na.github.io'
TOP_FILES = {'README.md', 'AGENTS.md', 'PROVENANCE.md', 'MANIFEST.sha256', 'site/README.md'}
PUBLIC_DIRS = {'wiki', 'notes', 'experiments', 'docs', 'tools'}
CATEGORY_NAMES = {'wiki': 'Wiki', 'notes': 'Research notes', 'experiments': 'Experiments', 'docs': 'Agent guides', 'root': 'Project'}


def esc(value):
    return html.escape(str(value), quote=True)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def safe_output(path):
    output = Path(path).expanduser().resolve()
    if output == ROOT or ROOT in output.parents or output in ROOT.parents:
        raise ValueError('Output must be outside the repository and cannot be its ancestor.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be absent or empty; use a fresh build directory.')
    return output


def normalize_base(value):
    if value == '/':
        return ''
    if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*', value.rstrip('/')):
        raise ValueError('Base path must contain only slash-separated URL-safe segments.')
    return value.rstrip('/')


def public_file(path):
    p = PurePosixPath(path)
    return (path in TOP_FILES or p.parts[0] in PUBLIC_DIRS) and not any(part.startswith('.') or part == '__pycache__' for part in p.parts) and not path.endswith('.pyc')


def doc_title(source, fallback):
    match = re.search(r'^#\s+(.+?)\s*$', source, re.M)
    return re.sub(r'[`*_]', '', match.group(1)) if match else fallback


def plain_text(source):
    source = re.sub(r'```.*?```', '', source, flags=re.S)
    source = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', source)
    source = re.sub(r'<[^>]+>', ' ', source)
    source = re.sub(r'^[#>|\s-]+', '', source, flags=re.M)
    source = re.sub(r'[`*_]', '', source)
    return re.sub(r'\s+', ' ', source).strip()


def github_slug(value, separator):
    # GitHub removes punctuation before replacing each space; do not collapse
    # consecutive hyphens, since existing repository links depend on them.
    return re.sub(r'\s', separator, re.sub(r'[^\w\s-]', '', value.lower().strip()))


def category(path):
    head = path.split('/')[0]
    return head if head in CATEGORY_NAMES else 'root'


class LinkTree(Treeprocessor):
    def __init__(self, md, builder, source):
        super().__init__(md)
        self.builder = builder
        self.source = source

    def run(self, root):
        for element in root.iter():
            for attribute in ('href', 'src'):
                if attribute in element.attrib:
                    element.set(attribute, self.builder.resolve_link(self.source, element.get(attribute)))


class LocalLinks(Extension):
    def __init__(self, builder, source):
        self.builder, self.source = builder, source
        super().__init__()

    def extendMarkdown(self, md):
        md.treeprocessors.register(LinkTree(md, self.builder, self.source), 'research_links', 1)


class Builder:
    def __init__(self, revision, base):
        if not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Revision must be a full 40-character Git commit SHA.')
        actual = git('rev-parse', revision + '^{commit}').decode().strip()
        if actual != revision:
            raise ValueError('Revision did not resolve exactly.')
        self.revision = revision
        self.snapshot_date = git('show', '-s', '--format=%cs', revision).decode().strip()
        self.base = normalize_base(base)
        self.files = {}
        for record in git('ls-tree', '-r', '-z', revision).split(b'\0'):
            if not record:
                continue
            header, path_bytes = record.split(b'\t', 1)
            mode, kind, _ = header.split()
            path = path_bytes.decode('utf-8')
            if mode in (b'100644', b'100755') and kind == b'blob' and public_file(path):
                self.files[path] = git('show', revision + ':' + path)
        self.docs = {p: value.decode('utf-8') for p, value in self.files.items() if p.endswith('.md')}
        self.titles = {p: doc_title(value, p) for p, value in self.docs.items()}

    def url(self, path=''):
        return self.base + '/' + path.lstrip('/')

    def doc_url(self, path):
        return self.url('read/' + str(PurePosixPath(path).with_suffix('.html')))

    def source_url(self, path, raw=False):
        if raw:
            return 'https://raw.githubusercontent.com/malik-na/m1-cpu-idle-research/' + self.revision + '/' + quote(path)
        return REPO + '/blob/' + self.revision + '/' + quote(path)

    def resolve_link(self, source, url):
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            return url
        decoded = unquote(parts.path)
        if decoded.startswith('/'):
            return url
        target = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
        if target.startswith('../') or target == '..':
            raise ValueError('Documentation link escapes the repository: ' + source + ': ' + url)
        if target in self.docs:
            output = self.doc_url(target)
        elif target in self.files:
            output = self.url('evidence/' + quote(target))
        elif any(path.startswith(target.rstrip('/') + '/') for path in self.files):
            readme = target.rstrip('/') + '/README.md'
            output = self.doc_url(readme) if readme in self.docs else REPO + '/tree/' + self.revision + '/' + quote(target)
        else:
            raise ValueError('Missing published documentation target: ' + source + ': ' + url)
        return urlunsplit(('', '', output, parts.query, parts.fragment))

    def link(self, path, label, **kwargs):
        attrs = ''.join(' ' + key.rstrip('_').replace('_', '-') + '="' + esc(value) + '"' for key, value in kwargs.items())
        return '<a href="' + esc(self.doc_url(path)) + '"' + attrs + '>' + esc(label) + '</a>'

    def layout(self, title, body, active='', description='', canonical='index.html', evidence_map=False):
        nav = [('Overview', 'index.html', 'overview'), ('Findings', 'read/wiki/Findings-Index.html', 'findings'), ('Notebook', 'library.html', 'library'), ('For agents', 'read/wiki/Agent-Orientation.html', 'agents')]
        nav_html = ''.join('<a href="' + esc(self.url(path)) + '"' + (' aria-current="page"' if key == active else '') + '>' + label + '</a>' for label, path, key in nav)
        page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + esc(title) + ''' · M1 CPU Idle Research</title><meta name="description" content="''' + esc(description or 'A reproducible base-M1 CPU-idle research notebook: macOS control paths, Linux comparisons, evidence and open experiments.') + '''">
<meta name="theme-color" content="#111419"><link rel="icon" type="image/svg+xml" href="''' + esc(self.url('assets/icon.svg')) + '''">
<link rel="canonical" href="''' + esc(ORIGIN + self.url(canonical)) + '''"><link rel="stylesheet" href="''' + esc(self.url('assets/style.css')) + '''">
<script src="''' + esc(self.url('assets/site.js')) + '''" defer></script></head><body>
<a class="skip" href="#main">Skip to content</a><header class="site-header"><div class="header-inner">
<a class="brand" href="''' + esc(self.url()) + '''"><span class="brand-symbol" aria-hidden="true">[ m1 ]</span>cpu-idle / research</a><nav class="nav" aria-label="Main navigation">''' + nav_html + '''<a class="repo-link" href="''' + REPO + '''">GitHub ↗</a></nav></div></header>
<main id="main">''' + body + '''</main><footer class="footer"><div><p>M1 CPU Idle Research · an open evidence notebook</p><p>Research snapshot ''' + self.snapshot_date + ''' · <a href="''' + REPO + '/tree/' + self.revision + '''">''' + self.revision[:7] + '''</a> · static publication, not live telemetry</p></div><div><p><a href="''' + esc(self.doc_url('PROVENANCE.md')) + '''">Provenance</a> / <a href="''' + esc(self.url('evidence/MANIFEST.sha256')) + '''">File hashes</a> / <a href="''' + esc(self.url('llms.txt')) + '''">llms.txt</a></p><p>Design inspired by <a href="https://omarchy-m-testing.org/">omarchy-m-testing</a>.</p></div></footer></body></html>'''

        if evidence_map:
            page = page.replace('</head>', '<link rel="stylesheet" href="' + esc(self.url('assets/evidence-map.css')) + '"></head>')
            page = page.replace('</body>', '<script src="' + esc(self.url('assets/evidence-map.js')) + '" defer></script></body>')
        return page

    def evidence_map_data(self):
        paths = (
            'experiments/aurora-apsc-observer/native-evidence/abi3-E/validator-report.json',
            'experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/mmio-phase-screen.json',
            'experiments/linux-pcpm-sampler/ps3-prototype/cap2-deployment-receipt.json',
        )
        if not all(path in self.files for path in paths):
            return None
        abi3, screen, deployment = (json.loads(self.files[path]) for path in paths)
        reads, busy, witnesses = abi3['wfi_rows'], abi3['busy_rows'], abi3['candidate_count']
        if not 0 < busy <= reads or witnesses != len(abi3['witnesses']) or not 0 < witnesses <= busy:
            raise ValueError('Evidence map requires a consistent positive ABI 3 witness report.')
        posthoc = sum(all(peer['exit_ticket'] > row['candidate_exit_ticket'] for peer in row['peers']) for row in abi3['witnesses'])
        rows = [row for phase in screen['included'].values() for row in phase] + screen['excluded']
        words = {row['raw_word'] for row in rows}
        if (not rows or len({row['seq'] for row in rows}) != len(rows) or len(words) != 1
                or screen['first_boot_numeric_pattern']['meets_one_boot_pattern'] is not False):
            raise ValueError('Evidence map requires the retained constant-word negative PCPM screen.')
        word = words.pop()
        if type(word) is not int or not 0 <= word <= 0xffffffff:
            raise ValueError('PCPM word must be a raw 32-bit integer.')
        actual, desired = (word >> 4) & 15, word & 15
        count = len(rows)
        released = screen['valid_full_bracket_counts']['four_p_released']
        if deployment['status'] != 'distinct_modules_and_uki_installed_unbooted':
            raise ValueError('Update the evidence-map gates for the changed PS3 deployment checkpoint.')
        cap, attempts = deployment['identity']['max_rows'], deployment['identity']['max_read_attempts']
        if type(cap) is not int or cap <= 0 or attempts != cap * 5:
            raise ValueError('PS3 five-slot access cap is inconsistent.')
        abi3_url = self.doc_url('experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.md')
        pcpm_url = self.doc_url('experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/README.md')
        protocol_url = self.doc_url('experiments/linux-pcpm-sampler/PCPU-PS3-PROTOCOL.md')
        claims = {
            'native': {'title': 'Native Linux', 'status': 'Runtime evidence',
                'description': 'Published packets target base-M1 T8103/J313, with boot and source identities recorded for each capture.',
                'support': 'Native observation differs from guest tracing or source-permitted behavior. These separate packets have their own instruments and conditions.',
                'next': 'Follow the pinned packet identities, raw records and replay path before extending a claim.',
                'source': self.doc_url('wiki/Findings-Index.md')},
            'command': {'title': 'Command ordering', 'status': 'Observed before DSB',
                'description': f'ABI 3 retained {reads:,} first-attempt pre-DSB command reads. BUSY was set in {busy}; {witnesses} satisfy the strict software final-entrant ticket screen.',
                'support': 'A bounded command-state observation before DSB, linked to software observer order. No BUSY observation at the later executed WFI instruction.',
                'next': 'No further #5 reboots unless a genuinely independent timing signal becomes available. The issue stays open with this limit.', 'source': abi3_url},
            'software': {'title': 'Software state', 'status': 'Ordered observer tickets',
                'description': f'In a post-hoc screen, {posthoc} of the {witnesses} ABI 3 witnesses have every peer observer idle-exit ticket after the candidate’s post-WFI idle-exit ticket.',
                'support': 'Order between software observation points. It does not locate a peer inside its exit path or prove that a peer was physically asleep.',
                'next': 'An independently calibrated physical-state signal must be associated with the software intervals.', 'source': abi3_url},
            'physical': {'title': 'Physical state', 'status': 'Contrast unresolved',
                'description': f'Sparse PCPM sampling returned the same full word in all {count} reads, including {released} guarded all-P-released samples. The declared ACTUAL contrast failed.',
                'support': f'A negative signal screen for this register and these conditions. Constant ACTUAL = {actual} does not rule out deeper states or establish rail power.',
                'next': 'First qualify records-only acquisition on the unbooted PS3 image: zero MMIO. Review that packet before a second fresh boot may attempt bounded register reads.', 'source': pcpm_url},
            'energy': {'title': 'Energy consequence', 'status': 'Not measured',
                'description': 'The published command and PMGR packets do not measure energy savings, CPU-rail power or an idle-policy benefit.',
                'support': 'No energy inference follows from BUSY, software tickets, register names or a constant state code alone.',
                'next': 'A separately qualified energy and wake measurement, with matched workloads and observer controls, would assess consequences.', 'source': protocol_url},
        }
        return {'claims': claims, 'abi3': {'reads': reads, 'busy': busy, 'witnesses': witnesses, 'posthoc': posthoc},
                'pcpm': {'word': f'0x{word:08x}', 'reads': count, 'guardedReleased': released, 'actual': actual, 'desired': desired},
                'ps3': {'deployed': True, 'booted': False, 'cap': cap, 'attempts': attempts}}

    def evidence_map_home(self, data):
        pcpm, ps3 = data['pcpm'], data['ps3']
        physical = data['claims']['physical']
        values = {
            'command_reads': f"{data['abi3']['reads']:,}", 'busy_reads': data['abi3']['busy'],
            'witness_count': data['abi3']['witnesses'], 'abi3_result_url': data['claims']['command']['source'],
            'initial_description': physical['description'], 'initial_support': physical['support'], 'initial_next': physical['next'],
            'pcpm_result_url': physical['source'], 'ps3_protocol_url': data['claims']['energy']['source'],
            'ps3_deployment_url': self.doc_url('experiments/linux-pcpm-sampler/ps3-prototype/CAP2-DEPLOYMENT-RESULT.md'),
            'pcpm_word': pcpm['word'], 'pcpm_reads': pcpm['reads'], 'released_reads': pcpm['guardedReleased'],
            'actual': pcpm['actual'], 'desired': pcpm['desired'], 'sample_cap': ps3['cap'], 'attempt_cap': ps3['attempts'],
        }
        values = {key: esc(value) for key, value in values.items()}
        values['evidence_json'] = json.dumps(data).replace('<', r'\u003c')
        body = Template((SITE / 'templates/evidence-map.html').read_text()).substitute(values)
        return self.layout('Overview', body, active='overview', evidence_map=True)

    def home(self):
        evidence_data = self.evidence_map_data()
        if evidence_data is not None:
            return self.evidence_map_home(evidence_data)
        abi3_result = 'experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.md'
        pcpm_result = 'experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/README.md'
        ps3_deployment = 'experiments/linux-pcpm-sampler/ps3-prototype/CAP2-DEPLOYMENT-RESULT.md'
        findings = [
            ('macOS last-core wait', 'A conditional APSC / DVFS BUSY loop', 'binary', 'Binary', 'Mapped in the matching 26A428 image. Live branch frequency and effect remain open.', 'wiki/MacOS-Control-Path.md'),
            ('Linux returning deep WFI', 'Asahi · Omacom · Aurora Silicon', 'source', 'Source', 'Already implemented. Checked base-M1 idle drivers are byte-identical at pinned revisions.', 'wiki/Linux-and-Aurora-Baseline.md'),
            ('Idle callback timing', '47,068 callback pairs · one 5 s trace', 'software', 'Software trace', 'Longer apparent last-E-core callbacks near one performance marker; no direct wait or physical-state observation.', 'wiki/Live-Mac-Tracing.md'),
            ('Direct macOS wait tracing', 'Privileged FBT inventory', 'blocked', 'Restricted', 'SIP prevented usable probe enumeration in the tested configuration. No probes were enabled.', 'notes/mac-apsc-direct-observation-route.md'),
            ('Linux observation tools', 'APSC observer + counter qualification', 'preparation', 'Preparation', 'Cross-built objects and synthetic decoder tests. Native target captures are still pending.', 'experiments/linux-apsc-observer/README.md'),
            ('Physical state & energy', 'PCPM calibration → controlled comparison', 'open', 'Open', 'No calibrated native state result or measured benefit from an added Linux wait.', 'notes/native-pcpm-signal-decision.md'),
        ]
        if abi3_result in self.docs:
            findings[4] = ('Native Linux BUSY observation', 'ABI 3 · 71 BUSY / 2,185 command reads', 'software', 'Software trace', '18 software final-entrant witnesses at a pre-DSB sample. Command state at WFI and physical sleep remain unobserved.', abi3_result)
        if pcpm_result in self.docs:
            findings[5] = ('Physical state & energy', 'PCPM: 90 constant words · failed contrast', 'open', 'Open', 'No calibrated native state result or measured policy benefit. The next candidate is a per-core PS3 screen.', 'experiments/linux-pcpm-sampler/README.md')
        rows = ''.join('<tr><td>' + self.link(path, title) + '<span class="subline">' + esc(sub) + '</span></td><td><span class="badge ' + tier + '">' + label + '</span></td><td>' + esc(boundary) + '</td></tr>' for title, sub, tier, label, boundary, path in findings)
        prompt = 'Read ' + REPO + '/blob/' + self.revision + '/AGENTS.md and wiki/Agent-Orientation.md. Follow the Evidence Standard, inspect decision-map issue #1, and choose one open, unblocked ticket. Verify the target and pinned sources. Preserve raw evidence; report a falsifiable result, evidence tier, and limitations.'
        tools = [
            ('experiments/linux-apsc-observer/README.md', 'APSC observer', 'Default-off instrumentation for a later native DVFS-to-WFI capture.'),
            ('experiments/linux-counter-qualification/README.md', 'Counter qualification', 'Bounded timestamp exchanges and a decoder for conditional cross-CPU ordering.'),
            ('notes/native-pcpm-signal-decision.md', 'PCPM calibration plan', 'Test whether sparse controller-state reads distinguish software idle conditions.'),
        ]
        if abi3_result in self.docs:
            tools[0] = ('experiments/aurora-apsc-observer/README.md', 'Native APSC evidence', 'Retained raw packets, software tickets and replay tools for the bounded pre-DSB BUSY result.')
        sampler_readme = 'experiments/linux-pcpm-sampler/README.md'
        if sampler_readme in self.docs:
            tools[-1] = (sampler_readme, 'PCPM sampler', 'Sparse read-only acquisition preparation; native state calibration remains open.')
        conclusion = 'a static control-path difference; no established Linux policy fix.'
        conclusion_detail = 'The checked macOS last-core path can wait for a pending DVFS command. The pinned Linux idle path has no explicit matching wait. Whether this difference affects native hardware state, wake behavior, or energy still needs measurement.'
        conclusion_path = 'wiki/MacOS-Control-Path.md'
        observation_title = 'Does Linux overlap DVFS and idle?'
        observation_detail = 'Capture command ordering around candidate final-core deep-WFI entry, with qualified clocks and retained failures.'
        calibration_title = 'What does PCPM actually report?'
        calibration_detail = 'Compare sparse controller-state reads with matched workload and idle windows. Measure the sampler’s effect.'
        next_note = 'Native reboot experiments are planned for a later authorized session. The linked GitHub issues carry current coordination status.'
        if abi3_result in self.docs:
            conclusion = 'a native pre-DSB BUSY result; no established Linux policy fix.'
            conclusion_detail = 'Software tickets place 18 BUSY samples inside all three peers’ recorded idle-hook intervals. The command is read before dsb sy and WFI; command state at WFI, physical sleep and energy remain unobserved.'
            conclusion_path = abi3_result
            observation_title = 'Command state at WFI remains open'
            observation_detail = 'Keep the supported pre-DSB finding. No further #5 reboots unless a genuinely independent timing signal becomes available.'
        if ps3_deployment in self.docs:
            calibration_title = 'Can per-core PS3 codes change?'
            calibration_detail = 'PCPM returned 90 constant words. The new PS3 image is installed but unbooted; begin with records only, then a separately reviewed active-only access pilot.'
            next_note = 'Effort is on issue #6. Its installed PS3 image has not booted or produced a PCPU register read. The linked issues carry current coordination status.'
        tool_html = ''.join('<a class="list-item" href="' + esc(self.doc_url(path)) + '"><span class="title">' + esc(label) + '<span aria-hidden="true">↗</span></span><p>' + esc(desc) + '</p></a>' for path, label, desc in tools)
        body = '''<section class="hero"><div><div class="eyebrow"><span class="dot"></span> Field notes / Apple Silicon / T8103</div><h1>What happens<br>when M1<br><span>goes idle?</span></h1><p class="intro">Tracing the path from macOS instructions to Linux behavior. A public notebook of what we can prove, what remains uncertain, and the experiments that come next.</p><div class="actions">''' + self.link('wiki/Findings-Index.md', 'Explore the findings →', class_='button primary') + '''<a class="button" href="''' + esc(self.url('library.html')) + '''">Read the notebook</a></div></div>
<aside class="machine" aria-label="Investigated hardware"><span class="machine-label">investigation target</span><div class="small-label">Apple M1 · T8103 · J313</div><div class="cpu-diagram"><div class="cluster"><strong>Icestorm / E</strong><div class="cores"><span>0</span><span>1</span><span>2</span><span>3</span></div></div><div class="cluster p"><strong>Firestorm / P</strong><div class="cores"><span>0</span><span>1</span><span>2</span><span>3</span></div></div></div><dl><dt>Machine</dt><dd>MacBookAir10,1</dd><dt>macOS</dt><dd>27.0 / 26A428</dd><dt>Focus</dt><dd>last-core APSC wait</dd><dt>Linux decision</dt><dd>open</dd></dl><p class="machine-note">Topology diagram only. Cells are not live CPU activity or measured power states.</p></aside></section>
<div class="decision"><p><strong>Current conclusion:</strong> ''' + esc(conclusion) + '''</p><p class="detail">''' + esc(conclusion_detail) + ''' <a href="''' + esc(self.doc_url(conclusion_path)) + '''">Follow the evidence →</a></p></div>
<section class="section" aria-labelledby="matrix-title"><div class="section-head"><h2 id="matrix-title"><span class="section-number">01</span>Evidence matrix</h2><a class="meta" href="''' + esc(self.doc_url('wiki/Evidence-Standard.md')) + '''">How to read the evidence ↗</a></div><div class="table-scroll" role="region" aria-label="Evidence matrix, scroll horizontally on small screens" tabindex="0"><table class="evidence-table"><thead><tr><th scope="col">Research surface</th><th scope="col">Evidence</th><th scope="col">Result and boundary</th></tr></thead><tbody>''' + rows + '''</tbody></table></div><div class="legend"><span>Source / binary: inspected code</span><span>Software: observed events</span><span>Preparation: tools, not target results</span><span>Open: measurement still needed</span></div><p class="matrix-note">These labels describe different kinds of evidence. They are not a confidence score or a ladder to physical power proof.</p></section>
<section class="section" aria-labelledby="next-title"><div class="section-head"><h2 id="next-title"><span class="section-number">02</span>The next discriminating experiments</h2><a class="meta" href="''' + REPO + '''/issues/1">Live decision map ↗</a></div><div class="path"><article class="path-card"><span class="index">A / observe</span><h3>''' + esc(observation_title) + '''</h3><p>''' + esc(observation_detail) + '''</p><a href="''' + REPO + '''/issues/5">Native observation · issue #5 →</a></article><article class="path-card"><span class="index">B / calibrate</span><h3>''' + esc(calibration_title) + '''</h3><p>''' + esc(calibration_detail) + '''</p><a href="''' + REPO + '''/issues/6">State calibration · issue #6 →</a></article><article class="path-card"><span class="index">C / decide</span><h3>Would a Linux wait help?</h3><p>Connect runtime ordering, state meaning, and controlled energy / wake results. “No change” remains a valid outcome.</p><a href="''' + REPO + '''/issues/8">Policy evidence gate · issue #8 →</a></article></div><p class="matrix-note">''' + esc(next_note) + '''</p></section>
<section class="section split"><div><div class="section-head"><h2><span class="section-number">03</span>Experiment bench</h2></div><div class="list-panel">''' + tool_html + '''</div></div><div><div class="section-head"><h2><span class="section-number">04</span>Prior work matters</h2></div><div class="callout"><p>Asahi Linux, Omacom, and Aurora Silicon form the checked baseline. Linux already requests returning deep WFI on base M1.</p><p>Every comparison names its source revision. An absent search result cannot establish that a mechanism was previously undiscovered.</p>''' + self.link('wiki/Linux-and-Aurora-Baseline.md', 'Read the pinned source comparison →') + '''</div></div></section>
<section class="section callout" aria-labelledby="agent-title"><div class="section-head"><h2 id="agent-title"><span class="section-number">05</span>Bring an agent. Leave a reproducible result.</h2><a class="meta" href="''' + esc(self.url('llms.txt')) + '''">Machine-readable entry ↗</a></div><p>The notebook and raw records stay in Git. Start with the evidence rules, then claim one bounded question from the decision map.</p><div class="copy-row"><pre id="agent-prompt">''' + esc(prompt) + '''</pre><button class="copy-button" id="copy-handoff" type="button">Copy handoff</button></div><div id="copy-status" class="copy-status" role="status" aria-live="polite"></div>''' + self.link('wiki/Agent-Orientation.md', 'Agent orientation →') + '''</section>'''
        return self.layout('Overview', body, active='overview')

    def document(self, path):
        md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', LocalLinks(self, path)], extension_configs={'toc': {'permalink': '¶', 'permalink_title': 'Link to this section', 'slugify': github_slug}})
        content = md.convert(self.docs[path])
        content = content.replace('<table>', '<div class="table-scroll" role="region" aria-label="Research table, scroll horizontally if needed" tabindex="0"><table>').replace('</table>', '</table></div>')
        active = 'findings' if path == 'wiki/Findings-Index.md' else 'agents' if path == 'wiki/Agent-Orientation.md' else 'library'
        body = '<div class="breadcrumbs"><a href="' + esc(self.url('library.html')) + '">Notebook</a><span>/</span><span>' + esc(CATEGORY_NAMES[category(path)]) + '</span><span>/</span><span>' + esc(path) + '</span></div>'
        body += '<div class="article-layout"><aside class="sidebar"><details open><summary>On this page</summary>' + md.toc + '</details></aside><article class="doc"><div class="doc-meta"><span>Source snapshot ' + self.revision[:7] + '</span><a href="' + esc(self.source_url(path)) + '">View source ↗</a><a href="' + esc(self.url('evidence/' + quote(path))) + '">Original Markdown ↓</a></div>' + content + '</article></div>'
        return self.layout(self.titles[path], body, active=active, description=plain_text(self.docs[path])[:200], canonical='read/' + str(PurePosixPath(path).with_suffix('.html')))

    def library(self):
        entries = []
        for path in sorted(self.docs, key=lambda p: (list(CATEGORY_NAMES).index(category(p)), self.titles[p].lower())):
            text = plain_text(self.docs[path])
            if text.startswith(self.titles[path]):
                text = text[len(self.titles[path]):].strip()
            excerpt = text[:210] + ('…' if len(text) > 210 else '')
            search = (path + ' ' + self.titles[path] + ' ' + text).lower()
            entries.append('<article class="library-entry" data-category="' + category(path) + '" data-search="' + esc(search) + '"><span class="category">' + CATEGORY_NAMES[category(path)] + '</span><h2>' + self.link(path, self.titles[path]) + '</h2><p>' + esc(excerpt) + '</p><div class="source-path">' + esc(path) + '</div></article>')
        buttons = '<button type="button" data-filter="all" aria-pressed="true">All documents</button>' + ''.join('<button type="button" data-filter="' + key + '" aria-pressed="false">' + title + '</button>' for key, title in CATEGORY_NAMES.items())
        body = '<div class="eyebrow">The research library</div><h1 class="page-title">Follow the evidence.</h1><p class="page-intro">The complete published wiki, research notes, and experiment documentation. Each page links to an immutable source and preserves the original Markdown.</p><div class="search-area"><label class="search-label" for="search">Search the full text of this notebook</label><input class="search-input" id="search" type="search" placeholder="Try APSC, PCPM, BUSY, counter, or Aurora" autocomplete="off"><div class="filters" role="group" aria-label="Document category">' + buttons + '</div><p id="search-count" class="search-meta" role="status" aria-live="polite">' + str(len(entries)) + ' documents</p><noscript><p class="noscript">Search and filters use local JavaScript. All documents are listed below; you can also use your browser’s Find command.</p></noscript></div><div class="library-list">' + ''.join(entries) + '<p class="empty" id="empty-results" hidden>No matching documents. Try a broader term or choose All documents.</p></div>'
        return self.layout('Notebook', body, active='library', canonical='library.html')

    def llms(self):
        text = '# M1 CPU Idle Research\n\n> A base-M1 (T8103 / J313) CPU-idle evidence notebook, not a finished power-saving patch.\n\n'
        text += 'Research snapshot: ' + self.snapshot_date + '. Immutable repository commit: ' + self.revision + '.\n\n'
        text += 'The strongest lead is a static macOS last-active-core APSC/DVFS wait absent as an explicit wait from the pinned Linux idle path. Runtime frequency, native hardware consequence, and energy benefit remain unestablished. Source/build/synthetic evidence is not native qualification. Historical native captures are dated and incompletely reconstructable here. Do not claim novelty from search absence.\n\n'
        text += '## Start here\n\n'
        for path in ['AGENTS.md', 'wiki/Agent-Orientation.md', 'wiki/Evidence-Standard.md', 'wiki/Findings-Index.md', 'wiki/Experiment-Backlog.md', 'PROVENANCE.md']:
            text += '- [' + self.titles[path] + '](' + self.source_url(path, raw=True) + ')\n'
        text += '\n## Coordination\n\n- [Live decision map](' + REPO + '/issues/1): inspect current sub-issues and blockers; claim one open, unblocked, unassigned question before work.\n\n'
        text += '## Published notebook\n\n'
        for path in sorted(self.docs):
            text += '- [' + self.titles[path] + '](' + ORIGIN + self.doc_url(path) + '): original path `' + path + '`\n'
        return text

    def build(self, output):
        output.mkdir(parents=True, exist_ok=True)
        for path, data in self.files.items():
            dest = output / 'evidence' / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        shutil.copytree(SITE / 'assets', output / 'assets')
        for path in self.docs:
            dest = output / 'read' / PurePosixPath(path).with_suffix('.html')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(self.document(path), encoding='utf-8')
        (output / 'index.html').write_text(self.home(), encoding='utf-8')
        (output / 'library.html').write_text(self.library(), encoding='utf-8')
        (output / 'llms.txt').write_text(self.llms(), encoding='utf-8')
        (output / '.nojekyll').write_text('', encoding='utf-8')
        (output / 'snapshot.json').write_text(json.dumps({'schema': 'm1-research-site-v1', 'research_snapshot_date': self.snapshot_date, 'source_revision': self.revision, 'base_path': self.base, 'document_count': len(self.docs), 'published_evidence_files': len(self.files), 'runtime_qualification': False}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'documents': len(self.docs), 'evidence_files': len(self.files), 'source_revision': self.revision, 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New or empty directory outside the repository.')
    parser.add_argument('--base-path', default='/m1-cpu-idle-research', help='GitHub Pages project prefix; use / for local root serving.')
    parser.add_argument('--revision', help='Full source commit SHA; defaults to HEAD. Content is read from Git, not working files.')
    args = parser.parse_args()
    output = safe_output(args.output)
    revision = args.revision or git('rev-parse', 'HEAD').decode().strip()
    Builder(revision, args.base_path).build(output)


if __name__ == '__main__':
    main()
