# Research website

This static GitHub Pages site renders the canonical research notebook into readable HTML. Its evidence matrix is a short editorial entry point; the wiki, notes, experiment contracts, and original evidence remain the source of truth. GitHub issues carry current coordination status. The site labels its research date and exact commit, rather than presenting a live hardware dashboard.

The design takes inspiration from [omarchy-m-testing](https://omarchy-m-testing.org/): a dark monospace interface, compact navigation, and an evidence matrix with explicit labels. Its layout, palette, chip illustration, and CSS are original. It uses system fonts, no copied branding, no trackers, and no external runtime assets.

## Build and preview

Python 3.9 or later and the pinned `Markdown==3.7` dependency are sufficient:

```sh
python3 -m venv /tmp/m1-site-venv
/tmp/m1-site-venv/bin/pip install -r site/requirements.txt
/tmp/m1-site-venv/bin/python site/build.py \
  --output /tmp/m1-research-site-preview \
  --base-path /
python3 -m http.server 8080 --directory /tmp/m1-research-site-preview
```

Open `http://localhost:8080/`. The output directory must be new or empty and outside the repository. The builder never removes an existing output tree. Use a different output directory for each build, or clean your own preview output deliberately.

For GitHub Pages, use `--base-path /m1-cpu-idle-research` and `--revision` followed by the full deployment commit SHA. Revision defaults to `HEAD`. The workflow uploads the resulting directory as its Pages artifact.

## Publication contract

Research content comes from `git show` at the selected immutable commit, **not from working files**. Only ordinary Git blobs in the explicit publication allowlist are included: the root README, AGENTS, PROVENANCE and manifest, this `site/README.md` build guide, plus `wiki/`, `notes/`, `experiments/`, `docs/`, and `tools/`. Symlinks, dotfiles, caches, `sources/`, untracked files, and the website generator itself are excluded. Thus, an uncommitted experiment or private local capture cannot silently enter the deployed research snapshot. Content changes must be reviewed and committed before they appear.

The allowlist is not a privacy scanner. Files inside it still require the repository's normal publication review and provenance rules. The generator reads styling and templates from `site/` in the checked-out worktree, allowing local UI preview before committing. In deployment, that worktree is the selected Actions commit.

The builder:

- Converts every published Markdown document into a page under `read/`, with a table of contents, source revision, immutable source link, and original Markdown link.
- Rewrites repository-relative links into the matching rendered page or original evidence file. Missing publication targets fail the build.
- Copies original publication bytes under `evidence/`, including raw captures, patch sources, and the original manifest. That manifest covers the repository packet, not generated HTML or only the copied subset.
- Produces a client-side full-text document library. Search and category filters run locally; the complete library and all document links remain available without JavaScript.
- Creates `llms.txt` as an entry point to the immutable agent handoff and the live decision map. It does not grant permission for experiments or change the repository's evidence rules.
- Writes `snapshot.json` with commit and counts. Its `runtime_qualification: false` describes this site's inability to qualify hardware; it is not a machine telemetry value.

The curated homepage lives in `build.py`. The operator selected the evidence-map direction from a [separate three-variant prototype](https://github.com/malik-na/m1-cpu-idle-research/tree/d8b4582d7c6a657b4133ee42950c27cac1bed029/site); [design issue #11](https://github.com/malik-na/m1-cpu-idle-research/issues/11) records the decision. The implementation uses `templates/evidence-map.html` and the local `assets/evidence-map.css` / `assets/evidence-map.js`. Prototype variants and their switcher are retained only on the throwaway branch.

For snapshots containing the ABI 3 E validator report, PCPM phase screen and unbooted PS3 deployment receipt, the homepage derives displayed counts, the raw 32-bit word, post-hoc count and access caps from those immutable publication bytes. The word decoder and selectable claim nodes are read-only; they make no network request or hardware access. A nonconstant PCPM packet cannot render the constant-word negative illustration. Historical snapshots without the complete evidence set keep the earlier summary. The diagram is a schematic across separate captures, not a measured timeline or live power display. Its source links, unmeasured physical/energy limits and #5 independent-timing gate remain explicit, and the initial result and next gates remain readable without JavaScript.

When the research conclusion changes, update the summary alongside its canonical evidence and tests. Do not derive a positive hardware result from an issue being closed or a build passing.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/m1-site-venv/bin/python \
  -m unittest discover -s site -p 'test_*.py'
```

The tests build a complete project-prefixed site from the selected Git snapshot, then check every local HTML link and fragment, original bytes, immutable source URLs, output safety, publication exclusions, escaping, and the evidence boundary. They also cover the GitHub-style double-hyphen heading fragments used by existing research links.

Browser QA remains necessary for desktop and mobile reading, the evidence table's horizontal scrolling, keyboard focus, full-text search, category filters, and the copy-handoff interaction. Synthetic build tests do not establish visual quality or physical hardware behavior.
