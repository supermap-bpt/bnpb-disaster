from app.services.cache import cache_attributes, get_cached_attributes


def test_cache_attributes_roundtrip():
    attrs = [{"Name": "orbitNumber", "Value": "57694"}, {"Name": "orbitDirection", "Value": "DESCENDING"}]
    cache_attributes("product-attrs-1", attrs)
    assert get_cached_attributes("product-attrs-1") == attrs
    assert get_cached_attributes("unknown-id") is None


def test_attributes_endpoint_returns_cached_attributes(client):
    cache_attributes(
        "router-attrs-1",
        [
            {"Name": "operationalMode", "Value": "IW"},
            {"Name": "orbitDirection", "Value": "DESCENDING"},
        ],
    )

    response = client.get("/api/products/router-attrs-1/attributes")

    assert response.status_code == 200
    assert response.json() == {
        "attributes": [
            {"name": "operationalMode", "value": "IW"},
            {"name": "orbitDirection", "value": "DESCENDING"},
        ]
    }


def test_attributes_endpoint_returns_404_for_unknown_product(client):
    response = client.get("/api/products/totally-unknown-id/attributes")
    assert response.status_code == 404


def test_attributes_endpoint_coerces_non_string_values(client):
    # CDSE Attribute Values can come back as numbers (e.g. orbitNumber) - the
    # endpoint must not crash building a `str`-typed ProductAttribute.
    cache_attributes("router-attrs-2", [{"Name": "orbitNumber", "Value": 57694}])

    response = client.get("/api/products/router-attrs-2/attributes")

    assert response.status_code == 200
    assert response.json() == {"attributes": [{"name": "orbitNumber", "value": "57694"}]}
