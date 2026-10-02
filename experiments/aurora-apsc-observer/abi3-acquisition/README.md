# ABI 3 collector logic review copy

This source is a sanitized copy of the private native acquisition collector for
the prospective A/D/E/conditional-C ticket block. It exposes the exact
capture/validation logic for review, including the explicit worker export
token, loss checks, source and boot gates, fresh-boot chain, environmental
checks, and incident packet preservation. It has never been run against the
live observer. The two placeholder lines for the repository path and local
account intentionally make this publication copy unsuitable for native use.

`REDACTION-RECEIPT.json` binds the private and public source hashes and records
the only changed line numbers. The synthetic tests pass against both copies:
`python3 -m unittest -v test_capture_abi3.py` (11 tests). The private workload
binary and private boot/source identity are excluded. Public numerical
findings require a separately redacted, replay-checked evidence packet.
