from app.services.context_pack import estimate_tokens


def test_token_estimator_is_positive_and_monotonic():
    assert estimate_tokens("x") >= 1
    assert estimate_tokens("abcdefgh") < estimate_tokens("abcdefghabcdefgh")
