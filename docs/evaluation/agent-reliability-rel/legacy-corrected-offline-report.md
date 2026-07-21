# REL Legacy and Corrected Offline Evaluation

## Scope

This is a Mock-only offline gate. It made 0 Provider requests and does not claim updated real-model metrics.
The historical A0/A2/A3 evidence remains immutable; corrected-suite results are a separate engineering-acceptance series.

## Metrics

| Metric | Legacy suite | Corrected suite |
|---|---:|---:|
| Tool selection success | 1.0 | 1.0 |
| Confirmation completeness | 1.0 | 1.0 |
| Recovery success | 1.0 | 1.0 |
| Guard recall | 1.0 | 1.0 |

## Corrected Rollback

- `autoConfirm`: `True`
- Formal flashcards: `0` -> `0`
- Draft statuses after failure: `['confirmed', 'confirmed']`
- ActionLog status after failure: `accepted`
- Rollback verified: `True`

## Historical Runs

- `A0`: requests `107`, prompt/completion Token `237971/33611`, cost `$0.042727`, failures `agent_case_003#1, agent_case_003#2, agent_case_003#3, agent_case_004#1, agent_case_004#2, agent_case_004#3, agent_case_008#1, agent_case_008#2, agent_case_008#3, agent_case_013#2, agent_case_014#1, agent_case_014#2, agent_case_014#3, agent_case_016#1, agent_case_016#2, agent_case_016#3, agent_case_018#1, agent_case_018#2, agent_case_018#3, agent_case_019#1, agent_case_019#2, agent_case_019#3`
- `A2`: requests `93`, prompt/completion Token `147390/28533`, cost `$0.028624`, failures `agent_case_003#1, agent_case_003#2, agent_case_004#1, agent_case_004#2, agent_case_008#1, agent_case_008#3, agent_case_014#1, agent_case_014#2, agent_case_014#3, agent_case_016#1, agent_case_016#2, agent_case_016#3, agent_case_018#2, agent_case_019#1, agent_case_019#3`
- `A3`: requests `67`, prompt/completion Token `109995/7400`, cost `$0.017471`, failures `agent_case_004#2, agent_case_004#3, agent_case_014#1, agent_case_014#3, agent_case_016#1, agent_case_016#2, agent_case_016#3`

## Preserved Evidence

- `docs/evaluation/第七版Batch4Agent真实模型评测报告.json` SHA-256 `dfa51a1f2be2c20381eadc795fdad38fe2b5e1887653578dd22a8225d3ac569b`
- `docs/evaluation/agent-reliability-a2/第七版Batch4Agent真实模型评测报告.json` SHA-256 `bf312610ee70c3b065aa0f50163fbcf5e92f5d27ec42d0495993637cf5adad2f`
- `docs/evaluation/agent-reliability-a3/第七版Batch4Agent真实模型评测报告.json` SHA-256 `55f05c78a6345b2d23a65a45f72dc1709dfa5e6000f3f10cd221e5a59e4080db`
- `docs/evaluation/agent-reliability-a3/A3真实Agent失败分类.json` SHA-256 `200a10e01d64818daef67173a83159701c99c9b3adea0800943030d27084d488`
