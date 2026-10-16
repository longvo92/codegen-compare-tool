# TODO

## P2: CURRENT consistency findings in JSON and SARIF

- [ ] Export CURRENT findings and unchecked items with stable rule IDs, severity, SWC/runnable identity, C file/line and ARXML references.
- [ ] Include policy, checked/ignored/unchecked coverage, scoped exceptions and reasons; distinguish missing input from a clean result.
- [ ] Version the JSON extension without breaking existing comparison consumers; add SARIF consistency rules alongside file-difference results.
- [ ] Support exports from `--check-current` and comparison checks, with tests proving terminal findings, artifact contents and exit codes agree.

Until implemented, comparison JSON/SARIF retain their existing schema and do not contain CURRENT findings. `--check-current` rejects these output flags instead of writing an incomplete delivery record. Capture terminal output when a delivery record is needed.
