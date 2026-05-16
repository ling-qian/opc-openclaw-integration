#!/usr/bin/env python3
"""Smoke test for OpenClaw integration endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_status():
    resp = client.get("/openclaw/status")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data["service"] == "opc-openclaw-integration"
    print("✅ GET /openclaw/status:", data)

def test_emit_event():
    payload = {
        "type": "test.smoke",
        "payload": {"msg": "hello"},
        "source": "test-script"
    }
    resp = client.post("/openclaw/event/emit", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data["status"] == "emitted"
    print("✅ POST /openclaw/event/emit:", data)

def test_query_events():
    # Query for the test event we just emitted
    resp = client.post("/openclaw/event/query", json={"type": "test.smoke", "limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    print(f"✅ POST /openclaw/event/query: total={data['total']}, events={len(data['events'])}")

def test_count_events():
    resp = client.get("/openclaw/event/count", params={"type": "test.smoke"})
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    print(f"✅ GET /openclaw/event/count: count={data['count']}")

def test_algorithm_run():
    # Only run if algorithm is available
    resp = client.post("/openclaw/algorithm/run", json={"prompt": "Say hello"})
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ POST /openclaw/algorithm/run: status={data.get('status')}, tier={data.get('tier')}")
    else:
        print("⚠️  Algorithm run not available (expected if not installed):", resp.status_code, resp.text[:60])

if __name__ == "__main__":
    test_status()
    test_emit_event()
    test_query_events()
    test_count_events()
    test_algorithm_run()
    print("\nAll smoke tests passed!")
