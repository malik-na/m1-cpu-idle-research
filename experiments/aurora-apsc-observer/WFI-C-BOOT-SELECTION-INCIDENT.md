# C control boot-selection incident, 2 October 2026

The first reboot requested for the ABI 2 C control returned to the **stock
Omarchy kernel**, so it was not used for a C capture. The operator then
restarted, selected `Aurora-APSC-research-wfi-seam` in the Limine menu and
unlocked the disk. The following boot reported the WFI research release and
entry. This incident changes the boot procedure for the remaining controls;
it supplies **no CPU-idle or command-register observation**.

The guarded private `prepare-wfi-next-boot.py` helper was invoked for the
first reboot. Its source as inspected after the incident (SHA-256
`86548f3ec7848f55c1608f947eee1ff51342df00b0390f0680b8a6bb59e942af`)
sets `LoaderEntryOneShot` to the WFI entry, reads that EFI variable back,
and calls `systemctl reboot` only after a matching readback. The helper's
standard output and an independent pre-reboot EFI-variable dump were **not
retained** for this attempt. The invocation and subsequent reboot do not,
by themselves, prove the variable's value at the handoff to Limine.

The local boot journal records a stock-kernel boot at **23:45:24 IST**
(`7.1.12-2-11.17-sep-ARCH`), followed by a distinct WFI-kernel boot at
**23:50:27 IST** (`7.1.12-ARCH-apsc-20261002-wfi`). The operator reported
that the first boot proceeded automatically without choosing a menu entry,
then reported manually choosing the WFI entry on the next restart. Live
inspection after the stock boot found no pending one-shot request. The WFI
EFI image and reviewed Limine configuration hashes still matched the
[deployment](wfi-deployment-receipt.json) and
[retirement](wfi-efi-retirement-receipt.json) receipts. The subsequent
same-boot qualification reported the WFI entry, expected GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, and configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
The full boot IDs, logs and EFI-variable observations remain private.

The evidence does not determine whether Limine ignored a valid one-shot
request, the request disappeared before Limine read it, or another boot-path
event intervened. A missing one-shot request after boot is consistent with
normal consumption as well as those alternatives. In particular, the stock
boot is **not evidence that the WFI kernel attempted to start and failed**.
No C packet was acquired on the stock boot. C remains governed by the
unchanged fresh-boot and same-image gates in the
[predeclared plan](WFI-PLAN.md); acquisition may proceed only after the
manually selected WFI boot passes its own device, topology and observer
qualification.
