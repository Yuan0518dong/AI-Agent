"""Offline REL legacy/corrected evaluation without sending Provider requests."""

import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import evaluate_agent
from backend.app.services import evaluation_service


LEGACY_SCENARIO_PATH = ROOT_DIR / "backend" / "evaluation" / "agent_scenarios.json"
CORRECTED_SCENARIO_PATH = ROOT_DIR / "backend" / "evaluation" / "agent_scenarios_corrected.json"
DEFAULT_REPORT_DIR = ROOT_DIR / "docs" / "evaluation" / "agent-reliability-rel"
PRESERVED_LEGACY_REPORTS = [
    ROOT_DIR / "docs" / "evaluation" / "第七版Batch4Agent真实模型评测报告.json",
    ROOT_DIR / "docs" / "evaluation" / "agent-reliability-a2" / "第七版Batch4Agent真实模型评测报告.json",
    ROOT_DIR / "docs" / "evaluation" / "agent-reliability-a3" / "第七版Batch4Agent真实模型评测报告.json",
    ROOT_DIR / "docs" / "evaluation" / "agent-reliability-a3" / "A3真实Agent失败分类.json",
]
HISTORICAL_REPORTS = [
    ("A0", PRESERVED_LEGACY_REPORTS[0]),
    ("A2", PRESERVED_LEGACY_REPORTS[1]),
    ("A3", PRESERVED_LEGACY_REPORTS[2]),
]


def run_reliability_evaluation(report_dir: Path = DEFAULT_REPORT_DIR) -> dict:
    """Run offline mock suites and index immutable A0/A2/A3 evidence."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        legacy_runtime = evaluate_agent.run_evaluation(
            temp_path / "legacy",
            scenario_path=LEGACY_SCENARIO_PATH,
        )
        corrected_runtime = evaluate_agent.run_evaluation(
            temp_path / "corrected",
            scenario_path=CORRECTED_SCENARIO_PATH,
        )

    legacy_agent = evaluation_service.build_batch4_agent_report(legacy_runtime["cases"])
    corrected_agent = evaluation_service.build_batch4_agent_report(corrected_runtime["cases"])
    report = {
        "metadata": {
            "executionMode": "mock-offline",
            "providerRequests": 0,
            "realProviderEvaluated": False,
            "reportingRule": "Legacy and corrected metrics are separate and must not be plotted as one continuous series.",
        },
        "legacySuite": {
            "purpose": "Preserve the A0/A2/A3 fixture and evidence lineage; no historical file is edited or replaced.",
            "fixture": _file_metadata(LEGACY_SCENARIO_PATH),
            "preservedReports": [_file_metadata(path) for path in PRESERVED_LEGACY_REPORTS],
            "historicalRealProviderRuns": [
                _historical_report(label, path) for label, path in HISTORICAL_REPORTS
            ],
            "offlineMockRegression": legacy_agent,
        },
        "correctedSuite": {
            "purpose": "Current REL engineering acceptance with canonical action and corrected rollback contract.",
            "fixture": _file_metadata(CORRECTED_SCENARIO_PATH),
            "providerAccounting": {
                "providerRequests": 0,
                "promptTokens": 0,
                "completionTokens": 0,
                "estimatedCostUsd": 0.0,
                "deterministicDecisionCount": 0,
                "failureRunIds": [],
            },
            "offlineMockRegression": corrected_agent,
            "rollbackCase": next(
                item for item in corrected_runtime["cases"] if item["id"] == "agent_case_016"
            ),
        },
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "legacy-corrected-offline-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (report_dir / "legacy-corrected-offline-report.md").write_text(
        markdown_summary(report),
        encoding="utf-8",
    )
    return report


def markdown_summary(report: dict) -> str:
    legacy = report["legacySuite"]
    corrected = report["correctedSuite"]
    legacy_metrics = legacy["offlineMockRegression"]["metrics"]
    corrected_metrics = corrected["offlineMockRegression"]["metrics"]
    rollback = corrected["rollbackCase"]
    return "\n".join(
        [
            "# REL Legacy and Corrected Offline Evaluation",
            "",
            "## Scope",
            "",
            "This is a Mock-only offline gate. It made 0 Provider requests and does not claim updated real-model metrics.",
            "The historical A0/A2/A3 evidence remains immutable; corrected-suite results are a separate engineering-acceptance series.",
            "",
            "## Metrics",
            "",
            "| Metric | Legacy suite | Corrected suite |",
            "|---|---:|---:|",
            f"| Tool selection success | {legacy_metrics['toolSelectionSuccessRate']} | {corrected_metrics['toolSelectionSuccessRate']} |",
            f"| Confirmation completeness | {legacy_metrics['confirmationCompleteness']} | {corrected_metrics['confirmationCompleteness']} |",
            f"| Recovery success | {legacy_metrics['recoverySuccessRate']} | {corrected_metrics['recoverySuccessRate']} |",
            f"| Guard recall | {legacy_metrics['guardRecall']} | {corrected_metrics['guardRecall']} |",
            "",
            "## Corrected Rollback",
            "",
            f"- `autoConfirm`: `{rollback.get('autoConfirm')}`",
            f"- Formal flashcards: `{rollback.get('flashcardCountBefore')}` -> `{rollback.get('flashcardCountAfter')}`",
            f"- Draft statuses after failure: `{rollback.get('draftStatusesAfter')}`",
            f"- ActionLog status after failure: `{rollback.get('actionLogStatusAfter')}`",
            f"- Rollback verified: `{rollback.get('rollbackVerified')}`",
            "",
            "## Historical Runs",
            "",
            *[
                (
                    f"- `{item['label']}`: requests `{item['metrics'].get('providerRequests')}`, "
                    f"prompt/completion Token `{item['metrics'].get('promptTokens')}/{item['metrics'].get('completionTokens')}`, "
                    f"cost `${item['metrics'].get('estimatedCostUsd')}`, failures `{', '.join(item['failureRunIds']) or 'none'}`"
                )
                for item in legacy["historicalRealProviderRuns"]
            ],
            "",
            "## Preserved Evidence",
            "",
            *[
                f"- `{item['path']}` SHA-256 `{item['sha256']}`"
                for item in legacy["preservedReports"]
            ],
            "",
        ]
    )


def _file_metadata(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _historical_report(label: str, path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        "label": label,
        "report": _file_metadata(path),
        "metrics": report.get("metrics", {}),
        "failureRunIds": report.get("failureRunIds", []),
    }


if __name__ == "__main__":
    run_reliability_evaluation()
