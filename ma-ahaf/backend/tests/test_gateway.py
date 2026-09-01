from __future__ import annotations


def test_mock_gateway_roles(gateway):
    r = gateway.complete("generator", [{"role": "user", "content": "hello world"}])
    assert r.text
    assert gateway.meter.calls == 1
    assert gateway.meter.total_tokens > 0


def test_gateway_json_parse(gateway):
    data = gateway.complete_json(
        "decomposer",
        [{"role": "system", "content": "decompose into atomic claims"},
         {"role": "user", "content": "The sky is blue. Water boils at 100C."}],
    )
    assert "claims" in data
    assert len(data["claims"]) >= 1


def test_uncertainty_from_logprob(gateway):
    r = gateway.complete("generator", [{"role": "user", "content": "x"}], want_logprobs=True)
    assert 0.0 <= r.uncertainty <= 1.0
