"""Trilha de auditoria append-only em JSONL com encadeamento de hashes (tamper-evident)."""

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLogger:
    """Registra decisões do agente, chamadas de ferramentas e verificações de guardrails.

    Cada registro inclui o hash do anterior; alterar ou remover uma linha quebra a cadeia
    e é detectado por `verify`.
    """

    def __init__(self, path: Path, run_id: str | None = None) -> None:
        self.path = path
        self.run_id = run_id or uuid.uuid4().hex
        self._lock = threading.Lock()
        self._last_hash = self._read_last_hash()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS_HASH
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1])["hash"] if lines else GENESIS_HASH

    def log(self, event: str, **details: Any) -> None:
        with self._lock:
            record = {
                "run_id": self.run_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                "details": details,
                "prev_hash": self._last_hash,
            }
            record["hash"] = _digest(record)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._last_hash = record["hash"]


def verify(path: Path) -> bool:
    """Confere a integridade da cadeia de hashes do arquivo de auditoria."""
    previous = GENESIS_HASH
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        claimed = record.pop("hash")
        if record["prev_hash"] != previous or _digest(record) != claimed:
            return False
        previous = claimed
    return True
