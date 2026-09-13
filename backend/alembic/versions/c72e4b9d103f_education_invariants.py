"""Education GPA precision, factual invariants and explicit primary selection.

Revision ID: c72e4b9d103f
Revises: b61f0a2c9d34
"""

import sqlalchemy as sa
from alembic import op

revision = "c72e4b9d103f"
down_revision = "b61f0a2c9d34"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_education_gpa_pair": "(gpa_value IS NULL) = (gpa_scale IS NULL)",
    "ck_education_gpa_nonnegative": "gpa_value >= 0 AND gpa_value <> 'NaN'::numeric",
    "ck_education_gpa_scale_positive": "gpa_scale > 0 AND gpa_scale <> 'NaN'::numeric",
    "ck_education_gpa_within_scale": "gpa_value <= gpa_scale",
    "ck_education_gpa_disclosure": "NOT gpa_include_on_apps OR (gpa_value IS NOT NULL AND gpa_scale IS NOT NULL)",
    "ck_education_date_order": "(EXTRACT(YEAR FROM start_date), EXTRACT(MONTH FROM start_date)) <= (expected_grad_year, expected_grad_month)",
}


def upgrade():
    # DDL locks the table. Constraints/index validate existing rows and refuse bad
    # data transactionally; never silently choose a primary or repair user facts.
    op.alter_column("education_records", "gpa_value", existing_type=sa.Numeric(4, 2), type_=sa.Numeric(5, 2))
    op.alter_column("education_records", "is_primary", existing_type=sa.Boolean(), server_default=sa.text("FALSE"))
    for name, expression in CHECKS.items():
        op.create_check_constraint(name, "education_records", expression)
    op.create_index("uq_education_primary_user", "education_records", ["user_id"], unique=True, postgresql_where=sa.text("is_primary = TRUE"))


def downgrade():
    # Lock BEFORE checking so a concurrent writer cannot add an incompatible GPA.
    # SQL also works with Alembic --sql; no data-dependent Python/offline divergence.
    op.execute("LOCK TABLE education_records IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM education_records WHERE gpa_value > 99.99) THEN
            RAISE EXCEPTION 'Education downgrade blocked: gpa_value exceeds NUMERIC(4,2); preserve user data';
        END IF;
    END $$""")
    op.drop_index("uq_education_primary_user", table_name="education_records")
    for name in reversed(CHECKS):
        op.drop_constraint(name, "education_records", type_="check")
    op.alter_column("education_records", "is_primary", existing_type=sa.Boolean(), server_default=sa.text("TRUE"))
    op.alter_column("education_records", "gpa_value", existing_type=sa.Numeric(5, 2), type_=sa.Numeric(4, 2))
