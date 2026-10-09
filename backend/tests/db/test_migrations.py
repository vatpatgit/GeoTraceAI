import uuid

import psycopg2
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.database import Base
from tests.db.conftest import TEST_URL, _sync_dsn

SYNC_URL = TEST_URL.replace("+asyncpg", "+psycopg2")

EXPECTED_TABLES = {
    "users", "regions", "projects", "areas_of_interest", "imagery_assets", "satellite_acquisitions", "analysis_jobs",
    "analysis_events", "analysis_exports", "change_features", "alert_rules", "alert_incidents", "layer_catalog",
}


def test_head_creates_all_tables_and_drops_legacy(migrated_database):
    eng = create_engine(SYNC_URL)
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    assert EXPECTED_TABLES <= tables
    assert not ({"change_events", "alert_history", "alert_configs"} & tables)
    assert "alembic_version" in tables


def test_models_match_migrations_no_drift(migrated_database):
    """Every model column/index/constraint must be created by a migration (and vice versa)."""
    eng = create_engine(SYNC_URL)
    try:
        with eng.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True, "include_object":
                lambda obj, name, type_, reflected, compare_to: not (type_ == "table" and name == "spatial_ref_sys")})
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        eng.dispose()
    # geoalchemy2 reports GiST indexes it did not create itself; those are created explicitly in the migration.
    meaningful = [d for d in diff if not _is_noise(d)]
    assert meaningful == [], meaningful


def _is_noise(d) -> bool:
    text_ = str(d)
    return "spatial_ref_sys" in text_ or "topology" in text_ or "tiger" in text_


def test_postgis_and_spatial_indexes_present(migrated_database):
    eng = create_engine(SYNC_URL)
    try:
        with eng.connect() as conn:
            assert conn.execute(text("SELECT postgis_version()")).scalar()
            idx = {r[0] for r in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE indexdef ILIKE '%using gist%' AND schemaname='public'"))}
    finally:
        eng.dispose()
    assert {"ix_change_features_geometry", "ix_change_features_centroid", "ix_areas_of_interest_geometry",
            "ix_imagery_assets_footprint", "idx_regions_geometry"} <= idx


def test_unique_constraint_blocks_duplicate_incidents(migrated_database):
    """The DB itself prevents duplicate (rule, feature) incidents even if application logic is retried."""
    eng = create_engine(SYNC_URL)
    uid, pid, aid, fid, rid = (str(uuid.uuid4()) for _ in range(5))
    try:
        with eng.begin() as conn:
            conn.execute(text("INSERT INTO users (id,email,password_hash,name) VALUES (:i,:e,'x','u')"), {"i": uid, "e": f"{uid}@t.io"})
            conn.execute(text("INSERT INTO projects (id,name,owner_id) VALUES (:p,'p',:u)"), {"p": pid, "u": uid})
            conn.execute(text("INSERT INTO analysis_jobs (id,project_id,created_by,name,input_type,config) VALUES (:a,:p,:u,'a','upload','{}')"),
                         {"a": aid, "p": pid, "u": uid})
            conn.execute(text("""INSERT INTO change_features (id,analysis_id,seq,geometry,centroid,point_on_surface,category,category_basis,
                                 area_m2,perimeter_m,pixel_count,magnitude,magnitude_max,severity,severity_reasons)
                                 VALUES (:f,:a,1,ST_GeomFromText('MULTIPOLYGON(((0 0,0 1,1 1,0 0)))',4326),ST_GeomFromText('POINT(0 0)',4326),
                                 ST_GeomFromText('POINT(0 0)',4326),'c','observed_difference',10,4,1,0.5,0.6,'low','[]')"""), {"f": fid, "a": aid})
            conn.execute(text("INSERT INTO alert_rules (id,owner_id,name) VALUES (:r,:u,'r')"), {"r": rid, "u": uid})
            ins = text("""INSERT INTO alert_incidents (id,rule_id,analysis_id,feature_id,severity,category,title,message,evidence,detected_at)
                          VALUES (:i,:r,:a,:f,'low','c','t','m','{}',now())""")
            conn.execute(ins, {"i": str(uuid.uuid4()), "r": rid, "a": aid, "f": fid})
        with pytest.raises(Exception) as err:
            with eng.begin() as conn:
                conn.execute(ins, {"i": str(uuid.uuid4()), "r": rid, "a": aid, "f": fid})
        assert "uq_alert_incident_rule_feature" in str(err.value)
    finally:
        with eng.begin() as conn:
            conn.execute(text("TRUNCATE alert_incidents, alert_rules, change_features, analysis_jobs, projects, users CASCADE"))
        eng.dispose()


def test_legacy_database_is_stamped_and_alert_configs_migrated():
    """Simulate a database created by the old startup code: tables exist, no alembic_version."""
    from alembic import command
    from app.migrate import _config, upgrade_to_head

    name = f"geotrace_legacy_test_{uuid.uuid4().hex[:8]}"
    dsn = _sync_dsn(TEST_URL)
    admin = psycopg2.connect(**dsn)
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{name}"')
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    try:
        legacy_dsn = {**dsn, "dbname": name}
        c = psycopg2.connect(**legacy_dsn)
        c.autocommit = True
        c.cursor().execute("CREATE EXTENSION IF NOT EXISTS postgis")
        c.close()
        # build the legacy schema with the baseline revision, then forget that Alembic ever ran
        command.upgrade(_config(url), "0001")
        uid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        c = psycopg2.connect(**legacy_dsn)
        c.autocommit = True
        cur = c.cursor()
        cur.execute("INSERT INTO users (id,email,password_hash,name,role) VALUES (%s,'legacy@t.io','x','L','admin')", (uid,))
        cur.execute("INSERT INTO alert_configs (id,user_id,change_type,threshold,is_active) VALUES (%s,%s,'deforestation',0.8,true)", (rid, uid))
        cur.execute("DROP TABLE alembic_version")
        c.close()

        note = upgrade_to_head(url)
        assert "stamped legacy" in note

        c = psycopg2.connect(**legacy_dsn)
        cur = c.cursor()
        cur.execute("SELECT name, owner_id::text, min_confidence, enabled FROM alert_rules WHERE id=%s", (rid,))
        row = cur.fetchone()
        assert row == ("Migrated TerraTrack rule (deforestation)", uid, 0.8, True)
        cur.execute("SELECT to_regclass('public.change_events'), to_regclass('public.alert_history')")
        assert cur.fetchone() == (None, None)
        # the user (and thus authentication) survives untouched
        cur.execute("SELECT email, role FROM users WHERE id=%s", (uid,))
        assert cur.fetchone() == ("legacy@t.io", "admin")
        c.close()

        command.downgrade(_config(url), "0001")  # reversible
        c = psycopg2.connect(**legacy_dsn)
        cur = c.cursor()
        cur.execute("SELECT threshold FROM alert_configs WHERE id=%s", (rid,))
        assert cur.fetchone() == (0.8,)
        c.close()
    finally:
        admin.cursor().execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()
