# Real Regression Comparison (2026-03-10)

- Baseline: `temp\real_regression_20260310_164120.json`
- Current: `temp\real_regression_latest2.json`
- Baseline overall: **pass**
- Current overall: **pass**

## Stability

- `Future exception was never retrieved` (mid run): 1
- `Future exception was never retrieved` (current run): 0

## Social/Commerce

- social_total_results: 16 -> 15 (delta -1)
- social_high_signal_results: 16 -> 15 (delta -1)
- commerce_total_results: 20 -> 19 (delta -1)
- commerce_high_signal_results: 20 -> 19 (delta -1)
- commerce_domain_coverage: 8 -> 10 (delta +2)

## Academic/Relation

- academic_paper_count: 4 -> 4 (delta +0)
- academic_code_count: 6 -> 6 (delta +0)
- academic_citation_count: 10 -> 10 (delta +0)
- mindsearch_citation_count: 7 -> 35 (delta +28)
- mindsearch_node_count: 7 -> 7 (delta +0)
- mindsearch_edge_count: 6 -> 6 (delta +0)
- mindsearch_references_text_length: 1569 -> 6271 (delta +4702)

## Notes

- Both runs are `pass`; metric fluctuations are expected for live web targets.
- Current run removed the Playwright loop-level unhandled future noise in full regression logs.
