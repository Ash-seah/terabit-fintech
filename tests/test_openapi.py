from app.main import app


def test_openapi_contains_core_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/historical/{ticker}" in paths
    assert "/api/v1/quotes/{symbol}" in paths
    assert "/api/v1/companies/{symbol}/profile" in paths
