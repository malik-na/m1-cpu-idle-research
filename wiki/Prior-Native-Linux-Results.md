# Prior Native Linux Results

These results came from an **earlier native Linux session** on the M1, with a ThinkPad T480 used for external collection. They were recovered during the present macOS investigation and have **not been rerun on the current disk/boot configuration**. The compact, sanitized [120-second native-capture summary](../notes/t480-references/evidence__alarm-cpu-idle-03-summary.json) is retained; the earlier private lab reports and their incomplete relative evidence trees are intentionally excluded from this public repository.

## What the historical capture says

The 120-second `cpuidle` accounting reported `CPU PD` software time for all eight CPUs: roughly **85.5–91.0%** for E cores and **99.1–99.6%** for P cores. The summary also records per-core entry counts and a separate shorter trace with idle callbacks, scheduler events, interrupts and timers. This establishes that the **software driver state was selected and returned** in that prior environment. The `state1/time` numbers are callback accounting; they do not independently measure the physical core or cluster rail.

The whole-machine battery discharge over that window averaged about **3.85 W**. It is a context measurement, not a CPU-only power estimate or an improvement relative to macOS. The trace includes wakeup candidates such as arch timer activity; their counts do not prove that each event was the cause of a particular idle exit.

An earlier menu/teo ABBA comparison produced nearly identical whole-machine averages, approximately **3.8630 W** for menu and **3.8648 W** for teo, under an uncontrolled background workload. This did not show a measurable governor benefit. It does not rule out a benefit under a different controlled workload, and it is not evidence about the proposed APSC/DVFS ordering mechanism.

## How to reuse the result

Treat it as a **baseline to refresh**, not a current-machine assertion. On the next native Linux boot, record the actual kernel, device tree, m1n1, cpuidle driver, governor, per-state disable bits and counts, cpufreq policy, and fast-switch status. Then run a question-specific capture. The previous all-eight `CPU PD` result makes repeating a generic “does deep WFI ever run?” test low value; the open issue is whether that software state corresponds to the physical residency or last-core ordering being sought.
