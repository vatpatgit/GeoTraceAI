import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-at-least-32-characters-long")
os.environ.setdefault("ENV", "test")
os.environ["LLM_PROVIDER"] = "none"  # tests never call a live LLM, whatever backend/.env configures
os.environ.setdefault("HAZARD_FEED_PROVIDER", "none")
os.environ.setdefault("JOB_RUNNER", "off")
os.environ.setdefault("AUTO_MIGRATE", "false")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://geotrace:geotrace_test@localhost:55432/geotrace_test"
)
os.environ.setdefault("STORAGE_DIR", os.path.join(os.path.dirname(__file__), "_storage"))

import pytest  # noqa: E402

from app.geo.synthetic import make_synthetic_pair  # noqa: E402


@pytest.fixture(scope="session")
def synth(tmp_path_factory):
    """4-band uint16 UTM pair with exactly known rectangular changes (session-scoped: read-only)."""
    return make_synthetic_pair(tmp_path_factory.mktemp("synth"))


@pytest.fixture(scope="session")
def synth_rgb(tmp_path_factory):
    return make_synthetic_pair(tmp_path_factory.mktemp("synth_rgb"), rgb_only=True, dtype="uint8", seed=11, name="rgb")
