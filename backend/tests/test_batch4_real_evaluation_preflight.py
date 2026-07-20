import pytest

from backend.batch4_real_evaluation_preflight import (
    RealEvaluationAuthorizationError,
    build_preflight,
    require_explicit_authorization,
)


def test_real_evaluation_preflight_has_no_execution_path_or_credentials():
    preflight = build_preflight()

    assert preflight["executionStatus"] == "blocked_until_explicit_authorization"
    assert preflight["budget"]["noRequestSent"] is True
    assert preflight["budget"]["totalProviderRequests"]["maximum"] == 126
    assert "key" not in str(preflight).lower()


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"BATCH4_REAL_EVAL_APPROVED": "yes", "BATCH4_REAL_EVAL_MAX_REQUESTS": "125", "BATCH4_REAL_EVAL_MAX_COST_USD": "1"},
        {"BATCH4_REAL_EVAL_APPROVED": "yes", "BATCH4_REAL_EVAL_MAX_REQUESTS": "126", "BATCH4_REAL_EVAL_MAX_COST_USD": "0.26"},
    ],
)
def test_real_evaluation_requires_explicit_sufficient_authorization(environment):
    with pytest.raises(RealEvaluationAuthorizationError):
        require_explicit_authorization(environment)


def test_real_evaluation_accepts_the_reported_request_and_cost_ceiling():
    authorization = require_explicit_authorization(
        {
            "BATCH4_REAL_EVAL_APPROVED": "yes",
            "BATCH4_REAL_EVAL_MAX_REQUESTS": "126",
            "BATCH4_REAL_EVAL_MAX_COST_USD": "0.27",
        }
    )

    assert authorization.max_requests == 126
    assert authorization.max_cost_usd == 0.27
