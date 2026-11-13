"""Fill the discount cards of the captures from before #1750 (#2807).

Revision ID: 0079
Revises: 0078

Changes data: the upgrade sets `captures.discounts` only where it is NULL (not known) and the capture has a stored raw
payload. It runs the current parser of the source on the raw and stores its cards (an empty list for no card). A raw
that the parser cannot read, or a source with no cards, stays NULL. No other column changes.
The downgrade changes nothing: it cannot tell the filled rows from the rows that ingest filled, and the column stays.
"""

import gzip
import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0079")


def upgrade() -> None:
    from app.parsers import get_parser

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, source, raw_gz FROM captures "
                                "WHERE discounts IS NULL AND raw_gz IS NOT NULL")).all()
    update = sa.text("UPDATE captures SET discounts = CAST(:d AS json) WHERE id = :id")
    for cid, source, raw_gz in rows:
        parser = get_parser(source)
        if parser is None:
            continue
        try:
            cards = parser.parse(json.loads(gzip.decompress(raw_gz))).discounts
        except Exception as e:  # an old raw that the parser cannot read stays not known
            log.warning("capture %s: no discount cards: %s", cid, e)
            continue
        if cards is not None:
            bind.execute(update, {"d": json.dumps(cards), "id": cid})


def downgrade() -> None:
    pass
