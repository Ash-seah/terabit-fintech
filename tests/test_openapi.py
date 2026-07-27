from app.main import app


def test_openapi_contains_core_routes() -> None:
    assert app.docs_url == "/api/docs"
    assert app.openapi_url == "/api/openapi.json"
    paths = app.openapi()["paths"]
    assert "/api/v1/historical/{ticker}" in paths
    assert "/api/v1/quotes/{symbol}" in paths
    assert "/api/v1/companies/{symbol}/profile" in paths


def test_docs_are_mounted_under_api_prefix() -> None:
    assert app.docs_url == "/api/docs"
    assert app.redoc_url == "/api/redoc"
    assert app.openapi_url == "/api/openapi.json"
