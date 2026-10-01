"""Test publication boundaries and actual rendered navigation, without a browser."""
import html
import importlib.util
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

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])
        if tag == 'script':
            self.scripts.append(attrs.get('src'))


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
            self.assertEqual(parsed.scripts, ['/m1-cpu-idle-research/assets/site.js'])

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
        previous = self.builder.docs.pop(path, None)
        try:
            self.assertIn('PCPM calibration plan', self.builder.home())
            self.builder.docs[path] = '# Experimental PCPM sampler'
            home = self.builder.home()
            self.assertIn('PCPM sampler', home)
            self.assertIn('native state calibration remains open', home)
            self.assertIn(self.builder.doc_url(path), home)
        finally:
            if previous is None:
                self.builder.docs.pop(path, None)
            else:
                self.builder.docs[path] = previous

    def test_home_and_agent_handoff_preserve_evidence_boundary(self):
        home = (self.output / 'index.html').read_text()
        self.assertIn('no established Linux policy fix', home)
        self.assertIn('Native target captures are still pending', home)
        self.assertIn('Cells are not live CPU activity', home)
        handoff = (self.output / 'llms.txt').read_text()
        self.assertIn(self.revision, handoff)
        self.assertIn('Do not claim novelty from search absence', handoff)
        self.assertIn('/issues/1', handoff)


if __name__ == '__main__':
    unittest.main()
