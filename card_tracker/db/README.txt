SQLAlchemy ORM Layer

This package is the forward path for database access in new scripts.

The canonical SQLite schema remains db/schema.sql for now. Existing scripts can
keep using sqlite3 until they are naturally edited, but new scripts should prefer:

from card_tracker.db import session_scope
from card_tracker.db.models import Card

with session_scope() as session:
    cards = session.query(Card).filter(Card.name.ilike("%Houndoom%")).all()

Install the dependency before running ORM-backed scripts:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pip install -r requirements.txt

Future migration path:

1. Keep db/schema.sql as the source of truth until the current scripts settle.
2. Use these models for new scripts and for old scripts when they need edits.
3. Later, consider Alembic once schema migrations become frequent.
