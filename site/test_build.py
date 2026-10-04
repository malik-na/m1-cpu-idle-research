"""Test publication boundaries and actual rendered navigation, without a browser."""
import html
import csv
import gzip
import importlib.util
import io
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

MODULE = Path(__file__).with_name('build.py')
SPEC = importlib.util.spec_from_file_location('research_site_build', MODULE)
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.scripts = []
        self.inline_scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])
        if tag == 'script':
            if attrs.get('src'):
                self.scripts.append(attrs['src'])
            else:
                self.inline_scripts.append(attrs.get('type'))


class BoundaryTests(unittest.TestCase):
    def test_output_cannot_be_repository_or_ancestor(self):
        for path in (build.ROOT, build.ROOT / 'generated', build.ROOT.parent, '/'):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                build.safe_output(path)

    def test_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(build.safe_output(root), root.resolve())
            (root / 'keep.txt').write_text('Keep me.')
            with self.assertRaises(ValueError):
                build.safe_output(root)
            self.assertEqual((root / 'keep.txt').read_text(), 'Keep me.')

    def test_output_symlink_into_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / 'link'
            link.symlink_to(build.ROOT, target_is_directory=True)
            with self.assertRaises(ValueError):
                build.safe_output(link)

    def test_base_path_is_project_safe(self):
        self.assertEqual(build.normalize_base('/'), '')
        self.assertEqual(build.normalize_base('/m1-cpu-idle-research/'), '/m1-cpu-idle-research')
        for bad in ('https://example.test', '/../secret', '/a b', '/x?y', '/x#z', '//x'):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                build.normalize_base(bad)

    def test_publication_allowlist_excludes_private_and_site_files(self):
        for bad in ('.git/config', 'site/build.py', 'private/capture.json', 'sources/synced.md', 'notes/.private/id', 'notes/__pycache__/thing.pyc'):
            self.assertFalse(build.public_file(bad), bad)
        for good in ('AGENTS.md', 'MANIFEST.sha256', 'site/README.md', 'notes/raw/trace.json', 'experiments/example/ABI.md'):
            self.assertTrue(build.public_file(good), good)

    def test_github_style_heading_fragments_retain_double_hyphens(self):
        self.assertEqual(build.github_slug('E3 — Find an independent native physical-state signal', '-'), 'e3--find-an-independent-native-physical-state-signal')

    def test_revision_must_be_full_commit(self):
        for revision in ('main', 'HEAD', 'afdaaba', 'x' * 40):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                build.Builder(revision, '/')


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / 'site'
        cls.revision = build.git('rev-parse', 'HEAD').decode().strip()
        cls.builder = build.Builder(cls.revision, '/m1-cpu-idle-research')
        cls.builder.build(cls.output)
        cls.pages = {}
        for file in cls.output.rglob('*.html'):
            parser = PageParser()
            parser.feed(file.read_text())
            cls.pages[file.relative_to(cls.output).as_posix()] = parser

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_local_links_and_fragments_resolve(self):
        errors = []
        prefix = '/m1-cpu-idle-research/'
        for page, parsed in self.pages.items():
            for target in parsed.links:
                url = urlsplit(target)
                if url.scheme or url.netloc:
                    continue
                if not url.path:
                    destination = page
                elif url.path.startswith(prefix):
                    destination = unquote(url.path[len(prefix):]) or 'index.html'
                else:
                    errors.append((page, target, 'not under project base'))
                    continue
                if not (self.output / destination).is_file():
                    errors.append((page, target, 'missing file'))
                elif url.fragment and destination in self.pages and unquote(url.fragment) not in self.pages[destination].ids:
                    errors.append((page, target, 'missing fragment'))
        self.assertEqual(errors, [], '\n'.join(map(str, errors)))

    def test_every_document_has_readable_html_and_exact_original(self):
        self.assertGreater(len(self.builder.docs), 30)
        for path, text in self.builder.docs.items():
            self.assertEqual((self.output / 'evidence' / path).read_bytes(), self.builder.files[path])
            page = self.output / 'read' / Path(path).with_suffix('.html')
            body = page.read_text()
            self.assertIn('<article class="doc">', body)
            self.assertIn(self.builder.source_url(path), body)
            self.assertIn('<h1', body)

    def test_content_is_exact_git_revision_not_working_tree(self):
        for path, data in self.builder.files.items():
            expected = build.git('show', self.revision + ':' + path)
            self.assertEqual(data, expected, path)
        self.assertNotIn('site/build.py', self.builder.files)
        self.assertNotIn('.git/config', self.builder.files)

    def test_source_links_are_immutable_and_no_external_runtime_assets(self):
        for page, parsed in self.pages.items():
            for target in parsed.links:
                if target.startswith(build.REPO + '/blob/') or target.startswith(build.REPO + '/tree/'):
                    self.assertRegex(target, re.escape(build.REPO) + r'/(?:blob|tree)/[0-9a-f]{40}(?:/|$)')
            expected = ['/m1-cpu-idle-research/assets/site.js']
            if page == 'index.html' and self.builder.evidence_map_data() is not None:
                expected.append('/m1-cpu-idle-research/assets/evidence-map.js')
                self.assertEqual(parsed.inline_scripts, ['application/json'])
            else:
                self.assertEqual(parsed.inline_scripts, [])
            self.assertEqual(parsed.scripts, expected)

    def test_library_data_is_escaped_and_full_text_searchable(self):
        self.builder.docs['wiki/Test.md'] = '# Example <script>\n\nA unique deeper body token: arbitrarystatevalue <img src=x onerror=bad>. '
        self.builder.titles['wiki/Test.md'] = 'Example <script>'
        try:
            page = self.builder.library()
            self.assertIn('arbitrarystatevalue', page)
            self.assertIn('Example &lt;script&gt;', page)
            self.assertNotIn('<img src=x onerror=bad>', page)
            self.assertNotIn('<script>\n', page)
        finally:
            del self.builder.docs['wiki/Test.md']
            del self.builder.titles['wiki/Test.md']

    def test_link_rewrite_preserves_fragments_and_downloads(self):
        self.assertEqual(self.builder.resolve_link('wiki/Home.md', 'Evidence-Standard.md#claim-rules'), '/m1-cpu-idle-research/read/wiki/Evidence-Standard.html#claim-rules')
        self.assertEqual(self.builder.resolve_link('wiki/Home.md', '../notes/raw/mac-fbt-inventory-26A428.json'), '/m1-cpu-idle-research/evidence/notes/raw/mac-fbt-inventory-26A428.json')
        self.assertEqual(self.builder.resolve_link('wiki/Home.md', '#navigation'), '#navigation')
        with self.assertRaises(ValueError):
            self.builder.resolve_link('wiki/Home.md', '../../private.txt')
        with self.assertRaises(ValueError):
            self.builder.resolve_link('wiki/Home.md', 'missing.md')

    def test_pcpm_bench_tracks_selected_published_snapshot(self):
        path = 'experiments/linux-pcpm-sampler/README.md'
        report_path = 'experiments/aurora-apsc-observer/native-evidence/abi3-E/validator-report.json'
        report = self.builder.files.pop(report_path, None)
        previous = self.builder.docs.pop(path, None)
        try:
            self.assertIn('PCPM calibration plan', self.builder.home())
            self.builder.docs[path] = '# Experimental PCPM sampler'
            home = self.builder.home()
            self.assertIn('PCPM sampler', home)
            self.assertIn('native state calibration remains open', home)
            self.assertIn(self.builder.doc_url(path), home)
        finally:
            if report is not None:
                self.builder.files[report_path] = report
            if previous is None:
                self.builder.docs.pop(path, None)
            else:
                self.builder.docs[path] = previous

    def test_home_and_agent_handoff_preserve_evidence_boundary(self):
        home = (self.output / 'index.html').read_text()
        self.assertIn('no established Linux policy fix', home)
        if 'experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.md' in self.builder.docs:
            self.assertNotIn('Native target captures are still pending', home)
            self.assertIn('pre-DSB', home)
            self.assertIn('No further #5 reboots unless a genuinely independent timing signal', home)
            if self.builder.evidence_map_data() is not None:
                self.assertIn('Schematic · not a measured timeline', home)
                self.assertIn('do not measure energy savings', home)
                self.assertIn('does not rule out deeper states or establish rail power', home)
                self.assertNotIn('prototype-switcher', home)
            else:
                self.assertIn('physical sleep and energy remain unobserved', home)
        else:
            self.assertIn('Native target captures are still pending', home)
        if self.builder.evidence_map_data() is None:
            self.assertIn('Cells are not live CPU activity', home)
        handoff = (self.output / 'llms.txt').read_text()
        self.assertIn(self.revision, handoff)
        self.assertIn('Do not claim novelty from search absence', handoff)
        self.assertIn('/issues/1', handoff)

    def test_visual_counts_and_word_match_retained_raw_rows(self):
        home = (self.output / 'index.html').read_text()
        payload = re.search(r'<script type="application/json" id="evidence-map-data">(.*?)</script>', home, re.S)
        if payload is None:
            self.skipTest('selected snapshot predates the visual evidence packets')
        data = json.loads(payload.group(1))
        raw_path = 'experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/pcpm-samples.csv.gz'
        raw = list(csv.DictReader(io.StringIO(gzip.decompress(self.builder.files[raw_path]).decode())))
        self.assertEqual(data['pcpm']['reads'], len(raw))
        self.assertEqual({row['raw'] for row in raw}, {data['pcpm']['word']})
        for claim in data['claims'].values():
            self.assertIn(claim['source'], self.builder.home())
            self.assertIn(claim['source'].removeprefix('/m1-cpu-idle-research/'), self.pages)
        self.assertFalse(data['ps3']['booted'])
        self.assertEqual(data['ps3']['attempts'], data['ps3']['cap'] * 5)

    def test_nonconstant_packet_cannot_render_constant_state_claim(self):
        path = 'experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/mmio-phase-screen.json'
        previous = self.builder.files.get(path)
        if previous is None:
            self.skipTest('selected snapshot predates PCPM capture')
        screen = json.loads(previous)
        screen['excluded'][0]['raw_word'] ^= 1
        try:
            self.builder.files[path] = json.dumps(screen).encode()
            with self.assertRaisesRegex(ValueError, 'constant-word negative'):
                self.builder.home()
        finally:
            self.builder.files[path] = previous

    def test_snapshot_without_ps3_checkpoint_cannot_claim_installation(self):
        receipt = 'experiments/linux-pcpm-sampler/ps3-prototype/cap2-deployment-receipt.json'
        result = 'experiments/linux-pcpm-sampler/ps3-prototype/CAP2-DEPLOYMENT-RESULT.md'
        saved_receipt = self.builder.files.pop(receipt, None)
        saved_result = self.builder.docs.pop(result, None)
        try:
            home = self.builder.home()
            self.assertNotIn('Installed image', home)
            self.assertNotIn('Its installed PS3 image', home)
            self.assertNotIn('id="EvidenceMap"', home)
        finally:
            if saved_receipt is not None:
                self.builder.files[receipt] = saved_receipt
            if saved_result is not None:
                self.builder.docs[result] = saved_result


if __name__ == '__main__':
    unittest.main()
