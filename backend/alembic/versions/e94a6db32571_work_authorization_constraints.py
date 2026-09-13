"""Constrain explicit authorization facts without rewriting legacy values.

Revision ID: e94a6db32571
Revises: d83f5ca21460
"""
from alembic import op

revision = "e94a6db32571"
down_revision = "d83f5ca21460"
branch_labels = None
depends_on = None


def upgrade():
    # Existing invalid facts block transactional DDL. No automatic legal mapping.
    op.create_check_constraint("ck_work_authorization_country_code", "work_authorizations", "country_code ~ '^[A-Z]{2}$'")
    op.create_check_constraint("ck_work_authorization_status", "work_authorizations", "authorization_status IN ('CITIZEN', 'PERMANENT_RESIDENT', 'STUDENT_WORK_AUTHORIZATION', 'TEMPORARY_WORK_AUTHORIZATION', 'OTHER', 'STUDENT_VISA_CPT_OPT', 'WORK_VISA')")


def downgrade():
    op.drop_constraint("ck_work_authorization_status", "work_authorizations", type_="check")
    op.drop_constraint("ck_work_authorization_country_code", "work_authorizations", type_="check")
