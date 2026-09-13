"""Protect explicit preference choices without repairing or seeding data."""
from alembic import op

revision = "fa5b7ec43682"
down_revision = "e94a6db32571"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint('ck_preferences_work_modes', 'career_preferences', "work_modes <@ ARRAY['ON_SITE','HYBRID','REMOTE']::text[] AND array_position(work_modes, NULL) IS NULL AND (cardinality(work_modes) = 0 OR array_ndims(work_modes) = 1)")
    op.create_check_constraint('ck_preferences_employment_types', 'career_preferences', "employment_types <@ ARRAY['INTERNSHIP','CO_OP','NEW_GRAD','PART_TIME']::text[] AND array_position(employment_types, NULL) IS NULL AND (cardinality(employment_types) = 0 OR array_ndims(employment_types) = 1)")
    op.create_check_constraint('ck_custom_preference_type', 'career_preference_custom_values', "preference_type IN ('ROLE','INDUSTRY','LOCATION','COMPANY','SKILL')")


def downgrade():
    op.drop_constraint('ck_custom_preference_type', 'career_preference_custom_values', type_="check")
    op.drop_constraint('ck_preferences_employment_types', 'career_preferences', type_="check")
    op.drop_constraint('ck_preferences_work_modes', 'career_preferences', type_="check")
