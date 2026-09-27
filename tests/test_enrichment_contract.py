from app.observer.enrichment import enrich_candidate,candidate_has_required_facts

def test_malformed_routine_fails_contract():
    observer={"user":{"home":True,"area":"Office area"},"schedule":{"next_timed_event":None}}
    candidate={"type":"routine_departure_deviation","reason":"malformed"}
    assert candidate_has_required_facts(enrich_candidate(observer,candidate)) is False
