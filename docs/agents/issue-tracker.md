# Issue tracker: GitHub

Research decisions for this repository live in [GitHub Issues](https://github.com/malik-na/m1-cpu-idle-research/issues). The current [Wayfinder map, “Decide whether base-M1 Linux CPU idle needs an APSC/DVFS wait”](https://github.com/malik-na/m1-cpu-idle-research/issues/1), is the index for the APSC/DVFS effort. Its child issues hold individual questions and their eventual resolution comments.

## Wayfinding operations

- **Map:** One issue labelled `wayfinder:map`. Its body holds the destination, notes, brief links to resolved decisions, fog, and scope boundary. It does not repeat ticket answers.
- **Ticket:** A native GitHub sub-issue with one `wayfinder:research`, `wayfinder:task`, `wayfinder:grilling`, or `wayfinder:prototype` label. The issue body states the question; its resolution goes in a comment before closing.
- **Blocking:** Use GitHub's native issue dependencies. The `blocked_by` API accepts the blocker's numeric database `id`, not the visible issue number. If native dependencies are unavailable, write a `Blocked by:` line in the child body.
- **Frontier:** Read the map's open sub-issues in order. Skip a ticket that has an open blocker or an assignee. Claim the first eligible ticket by assigning it to yourself before investigation.
- **Resolve:** Post the answer with linked evidence as a resolution comment, close the ticket, then add a one-line gist linking its title under the map's “Decisions so far.” Add newly precise tickets and blocking edges as earlier answers clear the fog.

Use `gh api repos/malik-na/m1-cpu-idle-research/issues/1/sub_issues` to list the map's children. Follow the repository's [evidence standard](../../wiki/Evidence-Standard.md) and [agent instructions](../../AGENTS.md); a closed research ticket documents what is known and its limits, not a hardware claim beyond its evidence.
