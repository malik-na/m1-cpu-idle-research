# First native PCPM records-only qualification

The J313/T8103 `-wfi-pcpm` kernel booted with the reviewed release, GNU
Build-ID and configuration. Wi-Fi loaded a page; the screen visibly changed
at brightness 155→40→155. The separate [deployment receipt](aurora-wfi-pcpm-deployment-receipt.json)
retains stock as the default and the working WFI image. The first collector
preflight failed before acquisition; its [incident receipt](pcpm-records-preflight-incident-receipt.json)
preserves the error and the verified unused one-shot states. The corrected
collector then completed one fresh records-only acquisition on this boot.

The [raw numerical export](native-evidence/records-abi2/README.md), its
[source-hash receipt](native-evidence/records-abi2/export-receipt.json), and
the [manual review](pcpm-native-records-review.json) make the result
replayable without publishing the boot ID, arguments, full FDT, logs or private
module package. The private packet manifest is pinned by SHA-256 in both
receipts. The [public verifier](verify_records_export.py) checks the exported
files and replays the conditional software-interval calculation; its
[tests](test_verify_records_export.py) exercise rejected and accepted
intervals. It cannot authenticate the withheld private packet by itself.

| Check | Observed |
| --- | --- |
| PCPM control | `records 90 100 0`; 90/90 rows, no missed slots or errors |
| PCPM mapping | Existing internal clockless regmap at main PMGR `0x23b700000`/`0x14000` |
| PCPM register reads | **Zero**; every row has `read_attempted=0`, `raw_valid=0` |
| APSC control | `records 9500`; 6,884 event rows, no overflow or missing commits |
| Four P workers | Pinned to CPUs 4–7; active, one-active, released, wake phases validated |
| Phase-interior PCPM brackets | 14 active, 14 one-active, 24 released, 14 wake, using measured transitions plus 300 ms guards |
| Counter qualification | 1,792 pre and 1,792 post exchanges, 24 MHz metadata, no recorded errors |
| Environment | AC connected, battery 100%, brightness 155 and thermal zone 33.5 °C at both endpoints |

The APSC stream contains 65, 273, 310 and 170 complete idle-entry/exit
pairs on P CPUs 4–7. Three trailing unmatched P entries occur near capture
end, outside the witnesses below. The PCPM record brackets are locally valid
on E CPU 0, lasting 6–84 raw ticks.

Under the **predeclared but unverified** pairwise counter-error assumption
`E=240` ticks and software-boundary guard `G=24,000` ticks, 26 of 90 PCPM
brackets satisfy the strict all-four-P software-interval inequalities.
Twenty-one of the 24 brackets fully inside the measured released phase also
satisfy them. For example, sample 58 spans ticks
`[14,894,051,089, 14,894,051,127]`; complete CPU4/5/6/7 entry and exit
pairs enclose it with a minimum post-guard margin of 6,173,352 ticks. The
[review JSON](pcpm-native-records-review.json) lists the raw event IDs,
endpoints and every accepted released-phase sample. Counter pre/post results
are compatible with a constant-offset model, but cannot establish that
`E=240` held throughout the unsampled capture interval. This is conditional
**software** overlap, not a measured hardware state.

The independent review permits a sparse MMIO **screening** run on a fresh
boot under the [predeclared protocol](NATIVE-CALIBRATION-PROTOCOL.md), after
new live identity, device, environment and unused-one-shot checks. That run
must retain every raw word, error and timing bracket and be compared with
matched controls before assigning any PMGR-state meaning. This records-only
packet contains no PCPM `ACTUAL` code, physical-power observation, energy
measurement, or APSC WFI-seam command read. It does not close issue #6 or
answer issue #5.
