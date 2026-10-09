"""GeoTrace schema: projects, AOIs, imagery, acquisitions, analyses, change features, alert rules/incidents, layers.

Legacy handling:
  * ``alert_configs`` rows are copied into ``alert_rules`` (region scope and confidence threshold preserved; the old
    free-text ``change_type`` has no equivalent category vocabulary, so it is kept in the rule name instead).
  * ``change_events`` and ``alert_history`` held only seeded demonstration data and are dropped. ``downgrade`` recreates
    them (empty).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)
NOW = sa.func.now()


def _gist(table: str, column: str, name: str | None = None) -> None:
    op.create_index(name or f"ix_{table}_{column}", table, [column], postgresql_using="gist")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="private"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.CheckConstraint("visibility in ('private','shared')", name="ck_projects_visibility"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "areas_of_interest",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("geometry", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("crs", sa.String(20), nullable=False, server_default="EPSG:4326"),
        sa.Column("source", sa.String(20), nullable=False, server_default="drawn"),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="SET NULL")),
        sa.Column("metadata_json", JSONB()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    op.create_index("ix_areas_of_interest_project_id", "areas_of_interest", ["project_id"])
    _gist("areas_of_interest", "geometry")

    op.create_table(
        "imagery_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("band_count", sa.Integer(), nullable=False),
        sa.Column("dtype", sa.String(16), nullable=False),
        sa.Column("crs_epsg", sa.Integer()),
        sa.Column("crs_wkt", sa.String()),
        sa.Column("pixel_size_m", sa.Float(), nullable=False),
        sa.Column("nodata", sa.Float()),
        sa.Column("footprint", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("band_descriptions", JSONB()),
        sa.Column("band_map", JSONB()),
        sa.Column("band_map_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acquisition_start", TS),
        sa.Column("acquisition_end", TS),
        sa.Column("cloud_cover_pct", sa.Float()),
        sa.Column("source_provider", sa.String(32)),
        sa.Column("source_product_id", sa.String(255)),
        sa.Column("raster_info", JSONB()),
        sa.Column("provenance", JSONB()),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.CheckConstraint("kind in ('upload','sentinel','synthetic')", name="ck_imagery_assets_kind"),
    )
    op.create_index("ix_imagery_assets_project_id", "imagery_assets", ["project_id"])
    op.create_index("ix_imagery_assets_sha256", "imagery_assets", ["sha256"])
    _gist("imagery_assets", "footprint")

    op.create_table(
        "satellite_acquisitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("collection", sa.String(64), nullable=False),
        sa.Column("product_id", sa.String(255), nullable=False),
        sa.Column("acquired_at", TS, nullable=False),
        sa.Column("cloud_cover_pct", sa.Float()),
        sa.Column("footprint", Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column("properties", JSONB()),
        sa.Column("request_params", JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="discovered"),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("imagery_assets.id", ondelete="SET NULL")),
        sa.Column("error", sa.String()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.UniqueConstraint("provider", "product_id", "created_by", "aoi_id", name="uq_acquisition_provider_product_user_aoi"),
    )
    op.create_index("ix_satellite_acquisitions_project_id", "satellite_acquisitions", ["project_id"])
    _gist("satellite_acquisitions", "footprint")

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("input_type", sa.String(12), nullable=False),
        sa.Column("before_asset_id", sa.Uuid(), sa.ForeignKey("imagery_assets.id", ondelete="SET NULL")),
        sa.Column("after_asset_id", sa.Uuid(), sa.ForeignKey("imagery_assets.id", ondelete="SET NULL")),
        sa.Column("before_date", TS),
        sa.Column("after_date", TS),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("stage_message", sa.String(300)),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", JSONB()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_by", sa.String(80)),
        sa.Column("heartbeat_at", TS),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("acquisition_params", JSONB()),
        sa.Column("method", sa.String(24)),
        sa.Column("method_reason", sa.Text()),
        sa.Column("model_id", sa.String(64)),
        sa.Column("summary", JSONB()),
        sa.Column("warnings", JSONB()),
        sa.Column("validation", JSONB()),
        sa.Column("processing", JSONB()),
        sa.Column("artifacts", JSONB()),
        sa.Column("bounds_wgs84", JSONB()),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.CheckConstraint(
            "status in ('queued','validating','acquiring_imagery','preprocessing','detecting_changes','polygonizing',"
            "'evaluating_alerts','exporting','completed','failed','cancelled')", name="ck_analysis_jobs_status"),
        sa.CheckConstraint("input_type in ('upload','sentinel','demo')", name="ck_analysis_jobs_input_type"),
    )
    op.create_index("ix_analysis_jobs_project_id", "analysis_jobs", ["project_id"])
    op.create_index("ix_analysis_jobs_status_created", "analysis_jobs", ["status", "created_at"])

    op.create_table(
        "analysis_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", TS, nullable=False, server_default=NOW),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(300)),
    )
    op.create_index("ix_analysis_events_analysis_id", "analysis_events", ["analysis_id"])

    op.create_table(
        "change_features",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("geometry", Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("centroid", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("point_on_surface", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("category_basis", sa.String(24), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("perimeter_m", sa.Float(), nullable=False),
        sa.Column("pixel_count", sa.Integer(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=False),
        sa.Column("magnitude_max", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("delta_ndvi", sa.Float()),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("severity_reasons", JSONB(), nullable=False),
        sa.Column("distance_to_boundary_m", sa.Float()),
        sa.Column("nearest_region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="SET NULL")),
        sa.Column("review_status", sa.String(12), nullable=False, server_default="unreviewed"),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", TS),
        sa.Column("review_note", sa.Text()),
        sa.Column("properties", JSONB()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.UniqueConstraint("analysis_id", "seq", name="uq_change_features_analysis_seq"),
        sa.CheckConstraint("severity in ('low','medium','high','critical')", name="ck_change_features_severity"),
        sa.CheckConstraint("review_status in ('unreviewed','confirmed','rejected')", name="ck_change_features_review"),
        sa.CheckConstraint("area_m2 > 0", name="ck_change_features_area_positive"),
    )
    _gist("change_features", "geometry")
    _gist("change_features", "centroid")
    op.create_index("ix_change_features_analysis_severity", "change_features", ["analysis_id", "severity"])
    op.create_index("ix_change_features_analysis_category", "change_features", ["analysis_id", "category"])
    op.create_index("ix_change_features_analysis_area", "change_features", ["analysis_id", "area_m2"])

    op.create_table(
        "analysis_exports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(12), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="all"),
        sa.Column("filters", JSONB()),
        sa.Column("status", sa.String(12), nullable=False, server_default="completed"),
        sa.Column("feature_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("storage_path", sa.String(500)),
        sa.Column("error", sa.String()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    op.create_index("ix_analysis_exports_analysis_id", "analysis_exports", ["analysis_id"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="CASCADE")),
        sa.Column("aoi_id", sa.Uuid(), sa.ForeignKey("areas_of_interest.id", ondelete="CASCADE")),
        sa.Column("region_relation", sa.String(16), nullable=False, server_default="intersects"),
        sa.Column("distance_m", sa.Float()),
        sa.Column("categories", JSONB()),
        sa.Column("min_area_m2", sa.Float(), nullable=False, server_default="0"),
        sa.Column("min_severity", sa.String(10), nullable=False, server_default="low"),
        sa.Column("min_magnitude", sa.Float()),
        sa.Column("min_confidence", sa.Float()),
        sa.Column("dedup_mode", sa.String(12), nullable=False, server_default="spatial"),
        sa.Column("dedup_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("dedup_overlap", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("last_evaluated_at", TS),
        sa.CheckConstraint("min_severity in ('low','medium','high','critical')", name="ck_alert_rules_min_severity"),
        sa.CheckConstraint("region_relation in ('intersects','within_distance')", name="ck_alert_rules_relation"),
        sa.CheckConstraint("dedup_mode in ('none','spatial')", name="ck_alert_rules_dedup"),
    )
    op.create_index("ix_alert_rules_owner_id", "alert_rules", ["owner_id"])

    op.create_table(
        "alert_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.Uuid(), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_id", sa.Uuid(), sa.ForeignKey("change_features.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(14), nullable=False, server_default="open"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("detected_at", TS, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("acknowledged_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("acknowledged_at", TS),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", TS),
        sa.Column("resolution_note", sa.Text()),
        sa.UniqueConstraint("rule_id", "feature_id", name="uq_alert_incident_rule_feature"),
        sa.CheckConstraint("status in ('open','acknowledged','resolved')", name="ck_alert_incidents_status"),
    )
    op.create_index("ix_alert_incidents_status_severity", "alert_incidents", ["status", "severity"])
    op.create_index("ix_alert_incidents_created", "alert_incidents", ["created_at"])
    op.create_index("ix_alert_incidents_analysis", "alert_incidents", ["analysis_id"])

    op.create_table(
        "layer_catalog",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("group", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("data_type", sa.String(24), nullable=False),
        sa.Column("render_type", sa.String(24), nullable=False),
        sa.Column("crs", sa.String(20), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("legend", JSONB()),
        sa.Column("temporal", JSONB()),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("limitations", JSONB()),
        sa.Column("default_visible", sa.Boolean(), nullable=False),
        sa.Column("default_opacity", sa.Float(), nullable=False),
        sa.Column("availability", sa.String(24), nullable=False),
        sa.Column("availability_detail", sa.Text()),
        sa.Column("last_checked_at", TS),
        sa.Column("last_updated_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )

    # ---- legacy data: alert_configs -> alert_rules ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO alert_rules (id, owner_id, name, enabled, region_id, categories, min_area_m2, min_severity,
                                 min_confidence, dedup_mode, dedup_window_days, dedup_overlap, created_at, updated_at)
        SELECT id, user_id,
               'Migrated TerraTrack rule' || COALESCE(' (' || change_type || ')', ''),
               is_active, region_id, NULL, 0, 'low', threshold, 'spatial', 30, 0.5, created_at, created_at
          FROM alert_configs
        """
    )
    op.drop_table("alert_history")
    op.drop_table("change_events")
    op.drop_table("alert_configs")


def downgrade() -> None:
    op.create_table(
        "alert_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="CASCADE")),
        sa.Column("change_type", sa.String(30)),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    op.execute(
        "INSERT INTO alert_configs (id, user_id, region_id, change_type, threshold, is_active, created_at) "
        "SELECT id, owner_id, region_id, NULL, COALESCE(min_confidence, 0.7), enabled, created_at FROM alert_rules"
    )
    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("area_affected_km2", sa.Float(), nullable=False),
        sa.Column("detected_at", TS, nullable=False),
        sa.Column("geometry", Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column("source", sa.String(50), nullable=False, server_default="sentinel-2"),
        sa.Column("ndvi_before", sa.Float()),
        sa.Column("ndvi_after", sa.Float()),
        sa.Column("metadata_json", JSONB()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    op.create_index("idx_change_events_geometry", "change_events", ["geometry"], postgresql_using="gist")
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_config_id", sa.Uuid(), sa.ForeignKey("alert_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_event_id", sa.Uuid(), sa.ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    for t in ("layer_catalog", "alert_incidents", "alert_rules", "analysis_exports", "change_features", "analysis_events",
              "analysis_jobs", "satellite_acquisitions", "imagery_assets", "areas_of_interest", "projects"):
        op.drop_table(t)
