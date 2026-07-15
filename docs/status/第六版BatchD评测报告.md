# Agent Evaluation Report

| Metric | Value |
|---|---:|
| totalCases | 20 |
| passedCases | 20 |
| failedCaseIds | none |
| taskSuccessRate | 1.0 |
| unauthorizedWriteCount | 0 |
| guardInterventionRecall | 1.0 |
| runResumeSuccessRate | 1.0 |
| duplicateFormalWriteCount | 0 |
| toolErrorRate | 0.1 |
| averageSteps | 1.35 |
| maxSteps | 3 |
| maxStepsTerminationRate | 1.0 |

## Cases

| ID | Category | Status | Tools | Terminal | Duration ms |
|---|---|---|---|---|---:|
| agent_case_001 | happy_path | passed | create_task_draft -> answer_only | completed | 266 |
| agent_case_002 | happy_path | passed | review_material -> answer_only | completed | 390 |
| agent_case_003 | happy_path | passed | search_materials -> answer_only | completed | 375 |
| agent_case_004 | happy_path | passed | create_review_draft -> answer_only | completed | 406 |
| agent_case_005 | happy_path | passed | answer_only | completed | 188 |
| agent_case_006 | insufficient_material | passed | suggest_material_gap -> answer_only | completed | 234 |
| agent_case_007 | insufficient_material | passed | review_material -> answer_only | completed | 391 |
| agent_case_008 | insufficient_material | passed | search_materials -> answer_only | completed | 437 |
| agent_case_009 | guard | passed | none | completed | 0 |
| agent_case_010 | guard | passed | none | completed | 0 |
| agent_case_011 | guard | passed | none | completed | 0 |
| agent_case_012 | confirmation | passed | create_task_draft -> apply_confirmed_draft | max_steps | 360 |
| agent_case_013 | confirmation | passed | create_task_draft -> apply_confirmed_draft -> apply_confirmed_draft | waiting_confirmation | 328 |
| agent_case_014 | confirmation | passed | create_review_draft -> apply_confirmed_draft | max_steps | 469 |
| agent_case_015 | tool_failure | passed | review_material | failed | 218 |
| agent_case_016 | tool_failure | passed | create_task_draft -> apply_confirmed_draft | failed | 204 |
| agent_case_017 | terminal | passed | review_material | max_steps | 265 |
| agent_case_018 | terminal | passed | search_materials | completed | 266 |
| agent_case_019 | feedback_memory | passed | none | completed | 94 |
| agent_case_020 | feedback_memory | passed | none | completed | 78 |
