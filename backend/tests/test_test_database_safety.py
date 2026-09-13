import pytest

from backend.tests.database_target import validate_test_target


@pytest.mark.parametrize(
    "overrides",
    [
        {"ALLOW_DISPOSABLE_TEST_DATABASE": "0"},
        {"TEST_DATABASE_URL": ""},
        {"TEST_DATABASE_URL": "postgresql+psycopg2://localhost/studentsuccessful"},
        {"TEST_DATABASE_URL": "sqlite:///studentsuccessful_test_x.db"},
        {"APP_ENV": "production"},
    ],
)
def test_refuses_unsafe_test_database(overrides):
    environ = {
        "TEST_DATABASE_URL": "postgresql+psycopg2://localhost/studentsuccessful_test_ci",
        "ALLOW_DISPOSABLE_TEST_DATABASE": "1",
    }
    environ.update(overrides)
    with pytest.raises(ValueError):
        validate_test_target(environ)


def test_accepts_explicit_disposable_postgresql():
    url = "postgresql+psycopg2://localhost/studentsuccessful_test_ci"
    assert (
        validate_test_target({"TEST_DATABASE_URL": url, "ALLOW_DISPOSABLE_TEST_DATABASE": "1"})
        == url
    )


def test_application_database_url_is_never_a_test_fallback():
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        validate_test_target(
            {
                "DATABASE_URL": "postgresql+psycopg2://staging.example/studentsuccessful",
                "ALLOW_DISPOSABLE_TEST_DATABASE": "1",
            }
        )
