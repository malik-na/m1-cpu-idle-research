# Experimental T8103 physical-counter qualification

This experiment implements the [cross-CPU clock protocol](../linux-apsc-observer/CLOCK-QUALIFICATION.md)
needed to interpret the APSC observer's conditional final-entrant analysis.
It is a source patch and offline analysis tool for a **later native Linux
session**. It has not been installed, booted or run on this Mac. No measured
clock error, APSC overlap, physical idle state or power benefit is established.
The [build receipt](BUILD-VALIDATION.md) records the exact patch and checked
configurations; [review and remaining work](REVIEW.md) separates source and
synthetic validation from the still-required native evidence.

The falsifiable question is whether causally ordered exchanges between all
eight CPUs constrain their relative physical-counter offsets tightly enough
for the intended event comparisons. Failed acquisition, inconsistent offsets
and intervals too wide to resolve an order are useful results. A finite test
cannot guarantee a bound during every moment of the intervening idle capture.

## Source and separation from idle

Apply [the patch](0001-t8103-counter-qualification.patch) to Asahi Linux
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a).
It adds a built-in, default-off `CONFIG_APPLE_COUNTER_QUALIFICATION` helper
under `drivers/soc/apple/`. It is separate from the [APSC observer](../linux-apsc-observer/README.md):
it does not edit the observer's files or insert a hook into the idle path.
It reads CPU counter and identification registers and uses ordinary kernel
SMP calls. It does not map or access APSC/PMGR registers or change the idle
policy, governor, frequency limits or timer access controls.

Enabling the option does not start an exchange. An explicit debugfs write
runs one bounded phase, waking CPUs and adding memory traffic. There is no
background sampler. The operator must keep both qualification phases outside
observer captures and energy windows: the two independent interfaces do not
enforce this scheduling rule for each other. The qualification traffic must
settle before the idle window according to the predeclared run protocol.

The implementation supports a **star** from one selected reference CPU to
the other seven, with 1–256 rounds per target in interleaved target order.
The default protocol uses 256 rounds per target; lower-count acquisition
checks must report their actual count and cannot substitute for that coverage.
The protocol's optional directed all-pairs variant is not implemented. Star
data can yield conditional bounds for the other pairs only under an explicit
stable-offset assumption across the different rounds. This limit must remain
in any resulting evidence report.

## Acquisition contract

Read [ABI 1](ABI.md) before writing a collector. Debugfs exposes
`apple_counter_qualification/control`, `status`, and `events.csv`. Two
preallocated phase buffers retain `pre` and `post` separately until reboot.
Each phase is consumed once, including a failed attempt; there is no reset or
retry in the same boot. The first failure ends acquisition while preserving
its record and prior successful records. Missing values are blank, never a
substitute zero. Export is deferred until the phase's worker has finished.

The reference worker stays pinned across both source timestamps and the
synchronous remote callback. The callback records two target timestamps,
actual CPU identity and frequency, and acknowledges the unique request.
Each stamp uses the selected raw physical counter with explicit barriers
and counter-dependent ordering. CPU hotplug is read-locked through preparation
and worker completion. Both phases retain per-CPU frequency, timer-access,
identification and workaround metadata; changed or incompatible state fails
the acquisition. An absent workaround is configuration evidence, not proof
that all possible hardware errata are absent.

Storage and attempted rounds are bounded. The synchronous SMP call has no
hard completion timeout, so this is not a wall-clock guarantee. No timeout
path frees a payload while another CPU may still be using it. A target that
does not return remains a native-run failure requiring the established boot
fallback; no such behavior has been tested here.

## Later native procedure

Follow the [native-run prerequisites](../linux-apsc-observer/NATIVE-RUN.md),
including a separately authorized boot, fallback, exact image/configuration,
source/patch hashes, firmware, DT, actual CPU topology, native/guest identity,
power state and workload definition. Build success is not permission to
install or boot. Keep security settings and CPU power policy outside the
scope of this diagnostic.

Select a logical reference CPU from the verified booted topology, predeclare
the rounds, acceptable acquisition latency, tolerance, endpoint uncertainty,
and settling interval. `reference_cpu` below is a placeholder; do not assume
a fixed CPU number is an efficiency or performance core. During the authorized
native session, one possible sequence is:

```sh
: "${counter_run_dir:?set a private run directory outside the repository}"
: "${reference_cpu:?choose an online logical CPU from this boot}"
printf 'pre %s 256\n' "$reference_cpu" | sudo tee /sys/kernel/debug/apple_counter_qualification/control >/dev/null
sudo cat /sys/kernel/debug/apple_counter_qualification/status >"$counter_run_dir/pre-status.txt"
sudo cat /sys/kernel/debug/apple_counter_qualification/events.csv >"$counter_run_dir/pre-events.csv"
```

Inspect and preserve the result even if the write reports failure. Proceed
only after a complete pre phase, a reviewed per-phase decoder result, the declared
settling period, and the independent observer's readiness checks. Run the
separately declared idle window; save and drain it before the post phase:

```sh
printf 'post\n' | sudo tee /sys/kernel/debug/apple_counter_qualification/control >/dev/null
sudo cat /sys/kernel/debug/apple_counter_qualification/status >"$counter_run_dir/status.txt"
sudo cat /sys/kernel/debug/apple_counter_qualification/events.csv >"$counter_run_dir/events.csv"
```

The final export retains both phases. Preserve intermediate and final files,
SHA-256 hashes, exact commands, source/object/configuration identities, boot
packet, observed errors and independently recorded phase/capture scheduling.
A missing post phase must remain missing; another boot cannot supply it.
ABI fields alone cannot authenticate a shared boot or establish that the
idle capture really occurred between phases. Root authentication belongs in
the operator's terminal; no password belongs in an artifact or script.
Before post runs, its absence correctly prevents a combined interpretation;
it does not hide the separate pre-phase analysis.

## Offline interpretation

From this repository root:

```sh
python3 experiments/linux-counter-qualification/analyze.py /path/to/private/events.csv /path/to/private/status.txt
python3 -m unittest discover -s experiments/linux-counter-qualification -p 'test_*.py'
```

The default evidence label is `unverified_input`. Use `--synthetic-fixture`
only for artificial input. Optional `--pairwise-tolerance-ticks E` and
`--endpoint-uncertainty-ticks U` make the proposed tolerance and endpoint
expansion explicit unsigned integers. Supplying zero is an explicit
assumption, not measured absence of uncertainty. The analyzer never supplies
a bound automatically to the APSC candidate analyzer or certifies hardware
clock qualification.

The raw offset interval for remote B relative to reference A is
`[b1 - a1, b0 - a0]`, using wide signed arithmetic. Its width contains
communication, dispatch and barrier uncertainty; it is not clock skew.
Any chosen endpoint expansion must retain the raw interval. Combining rounds
assumes a stable offset over those rounds. An empty intersection contradicts
that model; dropping inconvenient samples to produce a pass is not allowed.
A derived non-reference pair uses `[Lj - Ui, Uj - Li]` under the same model.

An interval fully inside the declared tolerance constrains that comparison
under the stated assumptions; a disjoint interval contradicts it; a partially
overlapping interval is inconclusive. Before/after agreement cannot exclude
an unsampled transient excursion. Both the [clock protocol](../linux-apsc-observer/CLOCK-QUALIFICATION.md)
and [evidence standard](../../wiki/Evidence-Standard.md) apply to any published
interpretation. Publish only sanitized artifacts under [PROVENANCE](../../PROVENANCE.md).
