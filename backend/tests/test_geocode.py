import httpx
import pytest
import respx

from app.config import Settings
from app.services.geocode import geocode_suggestions


@pytest.fixture
def settings() -> Settings:
    return Settings(nominatim_url="https://nominatim.test/search")


@respx.mock
async def test_geocode_suggestions_returns_bbox_normalized_to_min_max_lon_lat(settings):
    respx.get("https://nominatim.test/search").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "4.325",
                    "lon": "97.985",
                    "display_name": "Aceh Tamiang, Aceh, Indonesia",
                    # Nominatim order: [south, north, west, east]
                    "boundingbox": ["3.8887805", "4.5354847", "97.7283391", "98.2874680"],
                },
            ],
        )
    )

    results = await geocode_suggestions("Aceh Tamiang", settings)

    assert len(results) == 1
    assert results[0].displayName == "Aceh Tamiang, Aceh, Indonesia"
    # normalized to [minLon, minLat, maxLon, maxLat]
    assert results[0].bbox == [97.7283391, 3.8887805, 98.2874680, 4.5354847]
    assert results[0].polygon is None


@respx.mock
async def test_geocode_suggestions_simplifies_large_polygon(settings):
    import math

    ring = [
        [math.cos(t) * 0.5 + 97.9, math.sin(t) * 0.5 + 4.3]
        for t in (i * 2 * math.pi / 500 for i in range(500))
    ]
    ring.append(ring[0])

    respx.get("https://nominatim.test/search").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "4.3",
                    "lon": "97.9",
                    "display_name": "Aceh Tamiang, Aceh, Indonesia",
                    "boundingbox": ["3.8", "4.8", "97.4", "98.4"],
                    "geojson": {"type": "Polygon", "coordinates": [ring]},
                },
            ],
        )
    )

    results = await geocode_suggestions("Aceh Tamiang", settings)

    assert results[0].polygon is not None
    assert len(results[0].polygon) <= 150
    assert len(results[0].polygon) < len(ring)


@respx.mock
async def test_geocode_suggestions_returns_empty_list_when_no_match(settings):
    respx.get("https://nominatim.test/search").mock(return_value=httpx.Response(200, json=[]))

    results = await geocode_suggestions("nonexistent place xyz", settings)

    assert results == []


@respx.mock
def test_geocode_endpoint_returns_200_with_results_list(client):
    respx.get("https://nominatim.test/search").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "4.325",
                    "lon": "97.985",
                    "display_name": "Aceh Tamiang, Indonesia",
                    "boundingbox": ["3.8887805", "4.5354847", "97.7283391", "98.2874680"],
                }
            ],
        )
    )
    response = client.get("/api/geocode", params={"q": "Aceh Tamiang"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["lat"] == 4.325
    assert body["results"][0]["bbox"] == [97.7283391, 3.8887805, 98.2874680, 4.5354847]


def test_geocode_endpoint_requires_query_param(client):
    response = client.get("/api/geocode")
    assert response.status_code == 422
