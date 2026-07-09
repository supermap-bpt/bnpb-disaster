def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_docs_available(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema_has_expected_tags(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    tag_names = {tag["name"] for tag in response.json()["tags"]}
    assert tag_names == {
        "System",
        "Geocoding",
        "Search",
        "Preview",
        "Download",
        "Attributes",
        "Satellites",
        "Landslide",
        "Logs",
    }


def test_full_flow_search_then_preview(client, monkeypatch):
    import httpx
    import respx

    with respx.mock:
        respx.post("https://identity.test/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
        )
        respx.get("https://catalogue.test/Products").mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "Id": "flow-product-1",
                            "Name": "flow-product-1.SAFE",
                            "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                            "ContentLength": 1712336896,
                            "Footprint": (
                                "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                                "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                            ),
                            "Attributes": [
                                {"Name": "productType", "Value": "GRD"},
                                {"Name": "polarisationChannels", "Value": "VV&VH"},
                            ],
                        }
                    ]
                },
            )
        )

        search_response = client.get(
            "/api/search",
            params={
                "productType": ["SENTINEL_1_GRD"],
                "dateFrom": "2026-01-01",
                "dateUntil": "2026-02-01",
                "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
            },
        )
        assert search_response.status_code == 200
        product_id = search_response.json()["results"][0]["id"]

        preview_response = client.get(f"/api/preview/{product_id}")
        assert preview_response.status_code == 200
        assert preview_response.json()["productId"] == product_id
