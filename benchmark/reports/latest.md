# AOIE Benchmark Report

Generated: 2026-10-31T19:03:46.808309+00:00

Agent(s): **scripted-http**.
All figures are measured from actual runs against the controlled
demo app. No numbers are hand-authored.

## Headline metrics

| Metric | Value |
| --- | --- |
| Total runs | 41 |
| Apparent success rate (agent-claimed) | 70.73% |
| Verified success rate (AOIE) | 24.39% |
| **False completion rate** | 65.52% |
| Outcome integrity | 24.39% |
| False-completion detection rate | 100.00% |
| Recovery success rate | 11.43% |
| Mean recovery attempts / run | 0.854 |
| Mean verification latency (ms) | 11.61 |
| AOIE accuracy vs ground truth | 90.24% |

## AOIE outcomes

- FAILED: 27
- UNKNOWN: 4
- VERIFIED: 10

## Failure classifications

- UI_FALSE_COMPLETION: 15
- AUTH_FAILURE: 6
- TIMEOUT: 6
- STATE_CONFLICT: 4

## Per-run detail

| Task | Scenario | Ground truth | Agent claim | AOIE outcome | Failure class | Caught | Recovered |
| --- | --- | --- | --- | --- | --- | --- | --- |
| profile_name | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| profile_name | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| profile_name | wrong_value | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| profile_name | wrong_target | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| profile_name | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| profile_name | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
| profile_name | stale_read | succeeded | SUCCESS | UNKNOWN | STATE_CONFLICT | — |  |
| profile_name | transient_backend_write | succeeded | SUCCESS | VERIFIED |  | — | ✓ |
| project_desc | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| project_desc | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| project_desc | wrong_value | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| project_desc | wrong_target | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| project_desc | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| project_desc | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
| project_desc | stale_read | succeeded | SUCCESS | UNKNOWN | STATE_CONFLICT | — |  |
| project_desc | transient_backend_write | succeeded | SUCCESS | VERIFIED |  | — | ✓ |
| settings_email | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| settings_email | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| settings_email | wrong_value | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| settings_email | wrong_target | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| settings_email | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| settings_email | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
| settings_email | stale_read | succeeded | SUCCESS | UNKNOWN | STATE_CONFLICT | — |  |
| settings_email | transient_backend_write | succeeded | SUCCESS | VERIFIED |  | — | ✓ |
| order_status | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| order_status | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| order_status | wrong_value | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| order_status | wrong_target | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| order_status | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| order_status | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
| order_status | stale_read | succeeded | SUCCESS | UNKNOWN | STATE_CONFLICT | — |  |
| order_status | transient_backend_write | succeeded | SUCCESS | VERIFIED |  | — | ✓ |
| create_item | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| create_item | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| create_item | wrong_target | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| create_item | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| create_item | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
| delete_item | none | succeeded | SUCCESS | VERIFIED |  | — |  |
| delete_item | fail_backend_write | failed | SUCCESS | FAILED | UI_FALSE_COMPLETION | ✓ |  |
| delete_item | auth_failure | failed | fail | FAILED | AUTH_FAILURE | ✓ |  |
| delete_item | timeout | failed | fail | FAILED | TIMEOUT | ✓ |  |
