# Throwaway visual evidence prototype

Question: which visual structure makes the saved native Linux findings and their limits easier to understand?

Three variants share the existing homepage route, header, navigation, source documents and real public evidence:

- **A — Guided story:** an editorial explanation of SET, BUSY sample, DSB, WFI and callback exit, plus one exact software-ticket example.
- **B — Trace inspector:** select any of the 18 recorded ABI 3 witnesses; inspect its raw command, software callback intervals, ticket bracket and post-hoc classification.
- **C — Evidence map:** follow the claim dependencies, decode the constant PCPM word and inspect the prospective PS3 access gates.

Run from this checkout with one command:

```sh
python3 site/prototype.py
```

Open `http://localhost:8767/?variant=A`, `?variant=B` or `?variant=C`. The floating arrows and left/right keyboard keys switch directions. The State button shows the selected variant, pinned source revision, saved evidence counts and current interaction. State stays in memory; the variant is encoded in the shareable URL. If the pinned Markdown dependency is absent, the runner installs it into a temporary virtual environment without changing global Python packages.

The runner builds the real notebook from the selected immutable Git commit, then overlays the throwaway variants only in its development preview. Ordinary `site/build.py` and the Pages workflow never import the prototype, variant code or switcher. The prototype is preserved on branch `prototype/visual-evidence-20261004`, outside the research merge branch and main.

The trace inspector takes its witnesses directly from the published [E validator report](../experiments/aurora-apsc-observer/native-evidence/abi3-E/validator-report.json). Horizontal ticket positions are ordinal, with no elapsed-time scale. The story's source-order diagram is schematic. The evidence map preserves the [PCPM negative result](../experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/README.md) and the [installed, unbooted PS3 checkpoint](../experiments/linux-pcpm-sampler/ps3-prototype/CAP2-DEPLOYMENT-RESULT.md). None depicts live telemetry, measured physical sleep or an energy benefit; interacting with the page never touches hardware.

Decision: the operator selected **C — Evidence map**, saying “I like C”. No further preference rationale was supplied. Rewrite its chosen elements for the real site and retain this full comparison on the throwaway branch. This preview has no new automated tests; it receives a manual browser and evidence-boundary review.
