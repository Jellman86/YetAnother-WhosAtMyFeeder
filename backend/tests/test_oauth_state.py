"""OAuth state is provider-bound, bounded, single-use and monotonic."""

from app.services import oauth_state


def test_expiry_boundary_and_a_fresh_process_fail_closed(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(oauth_state.time, "monotonic", lambda: now[0])
    states = oauth_state.OAuthStateStore(ttl_seconds=10)
    state = states.issue("gmail")
    assert not oauth_state.OAuthStateStore().consume("gmail", state)
    now[0] = 110
    assert not states.consume("gmail", state)
    assert not states.consume("gmail", state)


def test_wrong_provider_preserves_legitimate_callback_and_replay_fails():
    states = oauth_state.OAuthStateStore()
    state = states.issue("outlook")
    assert not states.consume("gmail", state)
    assert states.consume("outlook", state)
    assert not states.consume("outlook", state)
    assert not states.consume("gmail", None)


def test_owner_pending_flows_are_bounded_and_expired_entries_are_pruned(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(oauth_state.time, "monotonic", lambda: now[0])
    states = oauth_state.OAuthStateStore(ttl_seconds=10, maximum=2)
    first = states.issue("gmail")
    now[0] += 1
    second = states.issue("gmail")
    third = states.issue("inaturalist")
    assert not states.consume("gmail", first)
    assert len(states._expires) == 2
    now[0] += 10
    fresh = states.issue("outlook")
    assert len(states._expires) == 1
    assert not states.consume("gmail", second)
    assert not states.consume("inaturalist", third)
    assert states.consume("outlook", fresh)
