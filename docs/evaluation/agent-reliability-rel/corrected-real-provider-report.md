# REL Corrected Suite Real Provider Evaluation

This is the authorized real-provider evaluation of the fixed corrected suite. It does not replace or alter A0/A2/A3 evidence.

| Metric | Value |
|---|---:|
| Execution status | completed |
| Runs | 60 |
| Failed runs | 0 |
| Tool selection success | 1.0 |
| Guard recall | 1.0 |
| Confirmation completeness | 1.0 |
| Recovery success | 1.0 |
| p50 / p95 latency ms | 2094.0 / 4454.0 |
| Provider requests | 57 / 126 |
| prompt / completion tokens | 94286 / 5553 |
| Estimated cost USD | 0.014755 / 0.27 |
| Runtime deterministic decisions | 54 |
| Runs with runtime deterministic decisions | 36 |
| Fallback decisions | 17 |

## Corrected rollback fixture

`agent_case_016` runs three fixed `autoConfirm=true` transaction checks locally, without a Provider request. Each verifies that the first formal flashcard write is rolled back, both drafts remain `confirmed`, and the ActionLog remains `accepted` after the second draft lacks `front`.

## Failure runs

- none

The report stores aggregate metrics, tool sequences, safe Guard categories, and per-run accounting only. It stores no prompts, model responses, credentials, or Provider configuration.
