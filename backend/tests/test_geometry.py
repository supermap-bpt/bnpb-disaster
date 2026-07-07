from app.services.geometry import douglas_peucker, simplify_ring_to_max_points


def test_douglas_peucker_collapses_collinear_points():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    result = douglas_peucker(points, epsilon=0.01)
    assert result == [(0.0, 0.0), (3.0, 0.0)]


def test_douglas_peucker_keeps_significant_deviation():
    points = [(0.0, 0.0), (1.0, 5.0), (2.0, 0.0)]
    result = douglas_peucker(points, epsilon=0.01)
    assert result == points


def test_simplify_ring_returns_unchanged_when_already_small():
    ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert simplify_ring_to_max_points(ring, max_points=150) == ring


def test_simplify_ring_reduces_large_ring_under_cap():
    # A near-circular ring with 500 points (not collinear, so DP must do real work).
    import math

    ring = [
        [math.cos(t) * 10, math.sin(t) * 10]
        for t in (i * 2 * math.pi / 500 for i in range(500))
    ]
    ring.append(ring[0])

    simplified = simplify_ring_to_max_points(ring, max_points=150)

    assert len(simplified) <= 150
    assert len(simplified) >= 4
