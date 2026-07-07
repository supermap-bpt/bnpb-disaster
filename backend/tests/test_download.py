import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import text

from app.auth import DownloadTokenManager
from app.config import Settings
from app.services.cache import cache_product_name, cache_product_size
from app.services.download import open_download_stream


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM activity_logs"))


@respx.mock
def test_download_endpoint_streams_file_with_cached_name(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    cache_product_name("dl-product-1", "S1A_IW_GRDH_1SDV_20260126.SAFE")
    respx.get("https://catalogue.test/Products(dl-product-1)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(dl-product-1)/$value"}
        )
    )
    respx.get("https://download.test/Products(dl-product-1)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    response = client.get("/api/download/dl-product-1")

    assert response.status_code == 200
    assert response.content == b"fake-zip-bytes"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="S1A_IW_GRDH_1SDV_20260126.SAFE.zip"'
    )


@respx.mock
def test_download_endpoint_falls_back_to_product_id_when_name_not_cached(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(never-searched-id)/$value").mock(
        return_value=httpx.Response(
            301,
            headers={"Location": "https://download.test/Products(never-searched-id)/$value"},
        )
    )
    respx.get("https://download.test/Products(never-searched-id)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    response = client.get("/api/download/never-searched-id")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="never-searched-id.zip"'


@respx.mock
def test_download_endpoint_returns_502_on_upstream_error(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(missing-id)/$value").mock(
        return_value=httpx.Response(404)
    )

    response = client.get("/api/download/missing-id")

    assert response.status_code == 502


@respx.mock
def test_download_endpoint_creates_a_completed_activity_log(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    cache_product_name("dl-log-product-1", "S1A_IW_GRDH_1SDV_20260126.SAFE")
    respx.get("https://catalogue.test/Products(dl-log-product-1)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(dl-log-product-1)/$value"}
        )
    )
    respx.get("https://download.test/Products(dl-log-product-1)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes" * 100)
    )

    response = client.get("/api/download/dl-log-product-1")
    assert response.status_code == 200

    logs_response = client.get("/api/logs")
    logs = logs_response.json()["items"]
    download_logs = [log for log in logs if log["action"] == "Download Product"]
    assert len(download_logs) == 1
    assert download_logs[0]["status"] == "completed"
    assert download_logs[0]["progress"] == 100


@respx.mock
def test_download_endpoint_includes_cached_size_in_log_description(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    cache_product_name("dl-size-product-1", "S1A_IW_GRDH_1SDV_20260126.SAFE")
    cache_product_size("dl-size-product-1", "1632MB")
    respx.get("https://catalogue.test/Products(dl-size-product-1)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(dl-size-product-1)/$value"}
        )
    )
    respx.get("https://download.test/Products(dl-size-product-1)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    response = client.get("/api/download/dl-size-product-1")
    assert response.status_code == 200

    logs_response = client.get("/api/logs")
    logs = logs_response.json()["items"]
    download_logs = [log for log in logs if log["action"] == "Download Product"]
    assert len(download_logs) == 1
    assert download_logs[0]["description"] == "Downloading S1A_IW_GRDH_1SDV_20260126.SAFE.zip (1632MB)"


@respx.mock
def test_download_endpoint_omits_size_suffix_when_not_cached(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(dl-no-size-product)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(dl-no-size-product)/$value"}
        )
    )
    respx.get("https://download.test/Products(dl-no-size-product)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    response = client.get("/api/download/dl-no-size-product")
    assert response.status_code == 200

    logs_response = client.get("/api/logs")
    logs = logs_response.json()["items"]
    download_logs = [log for log in logs if log["action"] == "Download Product"]
    assert len(download_logs) == 1
    assert download_logs[0]["description"] == "Downloading dl-no-size-product.zip"


@respx.mock
def test_download_endpoint_completes_log_even_without_content_length(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(dl-log-no-length)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(dl-log-no-length)/$value"}
        )
    )
    respx.get("https://download.test/Products(dl-log-no-length)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes", headers={})
    )

    response = client.get("/api/download/dl-log-no-length")
    assert response.status_code == 200

    logs_response = client.get("/api/logs")
    logs = logs_response.json()["items"]
    download_logs = [log for log in logs if log["action"] == "Download Product"]
    assert len(download_logs) == 1
    # Still reaches completed even if Content-Length was never available to compute
    # intermediate percentages from.
    assert download_logs[0]["status"] == "completed"


@respx.mock
async def test_open_download_stream_closes_client_when_send_raises(monkeypatch):
    settings = Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_catalogue_url="https://catalogue.test/Products",
    )
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(conn-fail)/$value").mock(
        side_effect=httpx.ConnectError("boom")
    )

    captured_clients = []
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured_clients.append(self)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    with pytest.raises(httpx.ConnectError):
        await open_download_stream("conn-fail", settings, DownloadTokenManager(settings))

    # The last AsyncClient constructed is the one open_download_stream() creates for
    # the actual product download (the token manager's own client, constructed and
    # closed earlier via `async with`, is captured first). It must be closed even
    # though client.send() raised before a response was ever returned.
    assert len(captured_clients) == 2
    assert captured_clients[-1].is_closed is True


from app.routers.download import _should_report_progress


def test_should_report_progress_true_when_5_percent_higher():
    assert _should_report_progress(current_pct=5, last_reported_pct=0) is True


def test_should_report_progress_false_when_less_than_5_percent_higher():
    assert _should_report_progress(current_pct=3, last_reported_pct=0) is False


def test_should_report_progress_true_at_100_regardless_of_gap():
    assert _should_report_progress(current_pct=100, last_reported_pct=97) is True
