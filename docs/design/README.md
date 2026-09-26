# Design documents (historical)

These are the original research and design notes written before implementation. They describe the plan,
not necessarily the system as built. Where they differ, the implementation and its documentation win:

- architecture and usage: [../../README.md](../../README.md)
- dataset construction: [../../data/processed/dataset_report.md](../../data/processed/dataset_report.md)
- measured results: [../../reports/evaluation_report.md](../../reports/evaluation_report.md)

Notable differences from the plans: labels are verified by a deterministic analyzer (SQLite compilation +
AST rules) rather than taken from the mutation intent; the model receives the schema as a second input
segment; PERMISSION_DENIED is decided by an access-policy check instead of being learned; repairs are
generated as candidates and accepted only when the analyzer verifies them.
