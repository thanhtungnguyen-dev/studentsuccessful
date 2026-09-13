"""Allow explicitly optional Application Profile contact/address facts.

Revision ID: b61f0a2c9d34
Revises: aba441bbcc36
"""

from alembic import op

revision = "b61f0a2c9d34"
down_revision = "aba441bbcc36"
branch_labels = None
depends_on = None

COLUMNS = (
    "phone_number", "address_city", "address_state_province",
    "address_postal_code", "address_country_code",
)


def upgrade():
    for column in COLUMNS:
        op.alter_column("application_profiles", column, nullable=True)


def downgrade():
    # PostgreSQL refuses this transaction if nulls exist. Never fabricate facts or delete data.
    for column in COLUMNS:
        op.alter_column("application_profiles", column, nullable=False)
