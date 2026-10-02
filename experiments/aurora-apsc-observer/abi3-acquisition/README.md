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
backlight interface/readback at 155, without repeating the visual cycle. It has never been run against the
live observer. The two placeholder lines for the repository path and local
account intentionally make this publication copy unsuitable for native use.

`REDACTION-RECEIPT.json` binds the private and public source hashes and records
the only changed line numbers. The synthetic tests pass against both copies:
`python3 -m unittest -v test_capture_abi3.py` (18 tests). The private workload
binary and private boot/source identity are excluded. Public numerical
findings require a separately redacted, replay-checked evidence packet.
