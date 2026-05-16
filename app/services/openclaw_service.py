"""
OpenClaw Service Integration for OPC Platform
Encapsulates EventBus, Algorithm, Pulse, and Memory Tiers access.
"""
import os
import json
import secrets
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Configure logger
logger = logging.getLogger(__name__)

# Custom exceptions
class OpenClawError(Exception):
    """Base exception for OpenClaw service errors."""
    pass

class EventHistoryError(OpenClawError):
    """Event history storage/retrieval error."""
    pass

# OpenClaw workspace root
OPENCLAW_WORKSPACE = os.getenv('OPENCLAW_WORKSPACE', str(Path.home() / '.openclaw' / 'workspace'))
# Pulse HTTP endpoint (if running)
PULSE_ENDPOINT = os.getenv('OPENCLAW_PULSE_URL', 'http://127.0.0.1:31337')
# Event payload size limit (default 1MB)
MAX_PAYLOAD_SIZE = int(os.getenv('OPENCLAW_MAX_PAYLOAD_SIZE', 1024 * 1024))

class OpenClawService:
    """Main entry point for OPC Platform to interact with OpenClaw capabilities."""

    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = Path(workspace or OPENCLAW_WORKSPACE)
        self.event_history_dir = self.workspace / 'memory' / 'event-history'
        self.algorithm_work_dir = self.workspace / '.openclaw' / 'work'
        self.event_history_dir.mkdir(parents=True, exist_ok=True)
        self.algorithm_work_dir.mkdir(parents=True, exist_ok=True)

    # ------------------ Event System ------------------
    def emit_event(self, event_type: str, payload: Dict[str, Any], source: str = 'opc-platform') -> Dict[str, Any]:
        """Emit an event. Prefer Pulse HTTP API; fallback to local JSONL append."""
        # Validate payload size
        payload_bytes = json.dumps(payload).encode('utf-8')
        if len(payload_bytes) > MAX_PAYLOAD_SIZE:
            raise OpenClawError(f"Payload too large (max {MAX_PAYLOAD_SIZE} bytes)")

        event = {
            "id": f"evt_{self._now_timestamp()}_{secrets.token_hex(4)}",
            "type": event_type,
            "payload": payload,
            "source": source,
            "timestamp": self._now_iso()
        }

        # Try Pulse first
        try:
            import requests
            resp = requests.post(
                f"{PULSE_ENDPOINT}/api/tools/event_emit",
                json=event,
                timeout=2
            )
            if resp.status_code == 200:
                logger.info("Event emitted via Pulse: %s", event_type)
                return {"event_id": event["id"], "status": "emitted"}
        except Exception as e:
            logger.debug("Pulse unavailable, fallback to local: %s", e)

        # Fallback: append to local history
        try:
            self._append_event_to_history(event)
            logger.info("Event emitted locally: %s -> %s", event_type, event["id"])
            return {"event_id": event["id"], "status": "emitted"}
        except Exception as e:
            logger.error("Failed to emit event: %s", e)
            raise EventHistoryError(f"Cannot emit event: {e}")

    def query_events(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Query past events with filters."""
        try:
            events = self._read_events(filters)
            total = len(events)
            order = filters.get('order', 'desc')
            events.sort(key=lambda e: e['timestamp'], reverse=(order == 'desc'))
            limit = filters.get('limit', 100)
            offset = filters.get('offset', 0)
            paged = events[offset:offset+limit]
            logger.debug("Queried events: total=%d, returned=%d", total, len(paged))
            return {
                "events": paged,
                "total": total,
                "limit": limit,
                "offset": offset,
                "order": order
            }
        except Exception as e:
            logger.error("Query events failed: %s", e)
            raise EventHistoryError(str(e))

    def count_events(self, filters: Dict[str, Any]) -> int:
        """Count events matching filters (optimized, no full load)."""
        try:
            count = 0
            after = filters.get('after')
            before = filters.get('before')
            type_filter = filters.get('type')
            source_filter = filters.get('source')
            for file_path in self._iter_event_files(after, before):
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            if type_filter and ev.get('type') != type_filter:
                                continue
                            if source_filter and ev.get('source') != source_filter:
                                continue
                            count += 1
                        except json.JSONDecodeError:
                            continue
            return count
        except Exception as e:
            logger.error("Count events failed: %s", e)
            raise EventHistoryError(str(e))

    def group_events_by(self, field: str, filters: Dict[str, Any]) -> Dict[str, int]:
        """Group counts by a field (efficient)."""
        try:
            counts: Dict[str, int] = {}
            after = filters.get('after')
            before = filters.get('before')
            type_filter = filters.get('type')
            source_filter = filters.get('source')
            for file_path in self._iter_event_files(after, before):
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            if type_filter and ev.get('type') != type_filter:
                                continue
                            if source_filter and ev.get('source') != source_filter:
                                continue
                            key = ev.get(field, 'unknown')
                            counts[key] = counts.get(key, 0) + 1
                        except (json.JSONDecodeError, KeyError):
                            continue
            return counts
        except Exception as e:
            logger.error("Group events failed: %s", e)
            raise EventHistoryError(str(e))

    # ------------------ Algorithm Orchestration ------------------
    def run_algorithm(self, prompt: str, tier: Optional[str] = None, work_dir: Optional[str] = None) -> Dict[str, Any]:
        """Run the Algorithm orchestrator and return structured result."""
        work_path = Path(work_dir) if work_dir else self.algorithm_work_dir / f'run-{self._now_timestamp()}'
        work_path.mkdir(parents=True, exist_ok=True)

        bootstrap = self.workspace / '.agents' / 'skills' / 'algorithm' / 'index.js'
        if not bootstrap.exists():
            logger.error("Algorithm skill not found at %s", bootstrap)
            raise FileNotFoundError(f"Algorithm skill not found at {bootstrap}")

        result_file = work_path / 'result.json'
        runner_code = f"""
const {{ Orchestrator }} = require('{bootstrap.as_posix()}');
const orch = new Orchestrator({{
  workDir: '{work_path.as_posix()}',
  log: (lvl, msg) => console.log('['+lvl+']', msg)
}});
orch.run({json.dumps(prompt)}).then(state => {{
  const result = {{status: 'completed', tier: state.tier, artifacts: Object.keys(state.artifacts||{{}})}};
  require('fs').writeFileSync('{result_file.as_posix()}', JSON.stringify(result));
  process.exit(0);
}}).catch(err => {{
  const result = {{status: 'error', message: err.message}};
  require('fs').writeFileSync('{result_file.as_posix()}', JSON.stringify(result));
  process.exit(1);
}});
"""
        runner_script = work_path / 'run_opc.js'
        runner_script.write_text(runner_code)

        try:
            logger.info("Starting Algorithm run, work_dir=%s", work_path)
            # Use start_new_session to isolate subprocess
            result = subprocess.run(
                ['node', str(runner_script)],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=180,
                start_new_session=True
            )
            # Logs for debugging
            if result.stdout:
                logger.debug("Algorithm stdout: %s", result.stdout[:500])
            if result.stderr:
                logger.warning("Algorithm stderr: %s", result.stderr[:500])

            if result.returncode != 0:
                logger.error("Algorithm process failed with code %d", result.returncode)
                # Try to read result file anyway
                if result_file.exists():
                    try:
                        data = json.loads(result_file.read_text())
                        data.setdefault('status', 'error')
                        data.setdefault('message', f"Non-zero exit: {result.returncode}")
                        return data
                    except Exception:
                        pass
                return {"status": "error", "message": f"Algorithm failed (exit {result.returncode})", "stdout": result.stdout, "stderr": result.stderr}

            if not result_file.exists():
                logger.error("Result file not found: %s", result_file)
                return {"status": "error", "message": "No result file produced", "stdout": result.stdout, "stderr": result.stderr}

            data = json.loads(result_file.read_text())
            logger.info("Algorithm completed: tier=%s, artifacts=%s", data.get('tier'), data.get('artifacts'))
            return data
        finally:
            # Keep runner_script for post-mortem (optional: could remove on success)
            pass

    # ------------------ Helper Methods ------------------
    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat() + 'Z'

    def _now_timestamp(self) -> str:
        return datetime.utcnow().strftime('%Y%m%d%H%M%S')

    def _append_event_to_history(self, event: Dict[str, Any]):
        """Append event to daily JSONL file."""
        date_str = self._now_iso()[:10]
        file_path = self.event_history_dir / f'{date_str}.jsonl'
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + '\n')

    def _iter_event_files(self, after: Optional[str], before: Optional[str]):
        """Yield event file paths sorted by name (date order)."""
        if not self.event_history_dir.exists():
            return
        files = sorted(self.event_history_dir.glob('*.jsonl'))
        for fp in files:
            # Apply date-range filter on filename to avoid opening unnecessary files
            fname = fp.name
            try:
                file_date = fname[:10]  # YYYY-MM-DD
                if after and file_date < after[:10]:
                    continue
                if before and file_date > before[:10]:
                    continue
                yield fp
            except Exception:
                continue

    def _read_events(self, filters: Dict[str, Any]) -> list:
        """Read and filter events from JSONL files."""
        events = []
        type_filter = filters.get('type')
        source_filter = filters.get('source')
        after = filters.get('after')
        before = filters.get('before')
        for file_path in self._iter_event_files(after, before):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            if type_filter and ev.get('type') != type_filter:
                                continue
                            if source_filter and ev.get('source') != source_filter:
                                continue
                            if after and ev['timestamp'] < after:
                                continue
                            if before and ev['timestamp'] >= before:
                                continue
                            events.append(ev)
                        except json.JSONDecodeError as e:
                            logger.debug("Skipping malformed line in %s: %s", file_path, e)
                            continue
            except Exception as e:
                logger.warning("Error reading event file %s: %s", file_path, e)
        return events

# Singleton instance
openclaw_service = OpenClawService()
