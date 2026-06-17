from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.narrativeos.persistence.db import SessionRow
from src.narrativeos.repository import SQLAlchemyRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Force a reader session into a paid chapter for smoke verification.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--chapter-index", type=int, default=3)
    args = parser.parse_args()

    repository = SQLAlchemyRepository(database_url=args.database_url)
    with repository.SessionLocal() as db:
        row = db.get(SessionRow, args.session_id)
        if row is None:
            raise SystemExit(f"Unknown session: {args.session_id}")
        state = dict(row.narrative_state_json or {})
        state["chapter_index"] = args.chapter_index
        row.chapter_index = args.chapter_index
        row.narrative_state_json = state
        db.commit()


if __name__ == "__main__":
    main()
