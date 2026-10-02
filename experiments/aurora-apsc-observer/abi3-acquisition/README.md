# ABI 3 collector logic review copy

This source is a sanitized copy of the private native acquisition collector for
the prospective A/D/E/conditional-C ticket block. It exposes the exact
capture/validation logic for review, including the explicit worker export
token, loss checks, source and boot gates, fresh-boot chain, environmental
checks, a first-boot user Wi-Fi/visible-brightness receipt and current-boot
Wi-Fi receipts for later phases,
an E-hash-bound C review gate, the all-packet boot ledger, and incident packet
preservation with explicit control-write uncertainty. A carries the only
155→40→155 visual test; D/E/C carry its receipt hash and require a current-boot
backlight interface/readback at 155, without repeating the visual cycle. This
public collector copy was never run for live acquisition; the private
executable collector bound by `REDACTION-RECEIPT.json` captured the native A
packet. The public copy is imported only for offline publication and replay.
Its two placeholder lines for the repository path and local account make it
unsuitable for native acquisition.

`REDACTION-RECEIPT.json` binds the private and public collector hashes and
records the only changed line numbers. The synthetic tests pass against both
copies: `python3 -m unittest -v test_capture_abi3.py` (18 tests). The private
workload binary and private boot/source identity are excluded.

`publish_abi3_a.py` is a runnable public review copy of the offline A
publisher. `PUBLISHER-REDACTION-RECEIPT.json` binds it to the private exporter
and names its limited changes. To replay the published A numerical packet
without private inputs, run from this directory:

```sh
python3 publish_abi3_a.py --verify-public-stage ../native-evidence/abi3-A
```

For a separately authorized staging run on a sealed private A packet, use
`python3 publish_abi3_a.py --packet /absolute/private/abi3-A-TIMESTAMP --out
/absolute/new/stage`. The output directory must not exist. The public exporter
validates the collector redaction receipt before either command. The reviewed
[A data packet](../native-evidence/abi3-A/README.md) contains the projection,
its input hash mapping, and the interpretation boundary. That packet's
`README.md` is separate repository documentation outside the staged data
manifest; `--verify-public-stage` checks the data files and manifest, not the
README text. Publication of raw boot, account, device, or network data is
outside this copy.
