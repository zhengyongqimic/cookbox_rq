"""add video source fields

Revision ID: 8a6d3f0d4f21
Revises: 6b6af20bdfcc
Create Date: 2026-04-08 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a6d3f0d4f21'
down_revision = '6b6af20bdfcc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('video_resources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('canonical_url', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('source_content_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('provider', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('acquisition_mode', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('region_strategy', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('source_title', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('source_author', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('collector_job_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('cookies_profile_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('failure_code', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('failure_detail', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_video_resources_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_video_resources_canonical_url'), ['canonical_url'], unique=False)
        batch_op.create_index(batch_op.f('ix_video_resources_source_content_id'), ['source_content_id'], unique=False)

    op.execute("UPDATE video_resources SET platform = 'upload' WHERE platform IS NULL")
    op.execute("UPDATE video_resources SET acquisition_mode = 'upload' WHERE acquisition_mode IS NULL")
    op.execute("UPDATE video_resources SET region_strategy = 'local' WHERE region_strategy IS NULL")


def downgrade():
    with op.batch_alter_table('video_resources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_video_resources_source_content_id'))
        batch_op.drop_index(batch_op.f('ix_video_resources_canonical_url'))
        batch_op.drop_index(batch_op.f('ix_video_resources_platform'))
        batch_op.drop_column('failure_detail')
        batch_op.drop_column('failure_code')
        batch_op.drop_column('cookies_profile_id')
        batch_op.drop_column('collector_job_id')
        batch_op.drop_column('source_author')
        batch_op.drop_column('source_title')
        batch_op.drop_column('region_strategy')
        batch_op.drop_column('acquisition_mode')
        batch_op.drop_column('provider')
        batch_op.drop_column('source_content_id')
        batch_op.drop_column('canonical_url')
        batch_op.drop_column('platform')
