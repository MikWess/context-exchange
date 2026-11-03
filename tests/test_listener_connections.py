from unittest.mock import patch

from src.app.client import listener

CONFIG = {"server_url": "http://127.0.0.1:8000", "agent_id": "me"}


def test_cache_handles_multiple_agents_per_person():
    connections = [{"id": "connection", "connected_user": {"agents": [
        {"id": "one", "name": "First"}, {"id": "two", "name": "Second"}
    ]}}, {"id": "empty", "connected_user": {"agents": []}}]
    with patch.object(listener, "api_request", side_effect=[connections,
        {"permissions": [{"category": "info", "level": "auto"}]}, {"permissions": []}
    ]) as request:
        listener.refresh_connections(CONFIG)
    assert set(listener._connection_cache) == {"one", "two"}
    assert request.call_count == 3  # One permission lookup per connection, not per agent.
    assert listener.should_auto_respond({"from_agent_id": "two", "category": "info"}, CONFIG)
    assert not listener.should_auto_respond({"from_agent_id": "two", "category": "personal"}, CONFIG)


def test_failed_permissions_replace_previously_automatic_cache():
    listener._connection_cache = {"one": {"permissions": {"info": "auto"}}}
    connections = [{"id": "connection", "connected_user": {"agents": [{"id": "one", "name": "First"}]}}]
    with patch.object(listener, "api_request", side_effect=[connections, OSError("offline")]):
        listener.refresh_connections(CONFIG)
    assert listener._connection_cache["one"]["permissions"] == {}
    assert not listener.should_auto_respond({"from_agent_id": "one", "category": "info"}, CONFIG)
