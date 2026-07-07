def _perpendicular_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    if (x1, y1) == (x2, y2):
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    denominator = ((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5
    return numerator / denominator


def douglas_peucker(
    points: list[tuple[float, float]], epsilon: float
) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points

    max_distance, index = 0.0, 0
    for i in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[i], points[0], points[-1])
        if distance > max_distance:
            index, max_distance = i, distance

    if max_distance > epsilon:
        left = douglas_peucker(points[: index + 1], epsilon)
        right = douglas_peucker(points[index:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]


def simplify_ring_to_max_points(
    ring: list[list[float]], max_points: int = 150
) -> list[list[float]]:
    """Reduces a polygon ring to at most max_points vertices via Douglas-Peucker,
    increasing epsilon until under the cap. Needed because OData's $filter is sent
    as a URL query string - an unsimplified administrative boundary (commonly
    thousands of vertices) would blow past practical URL length limits."""
    if len(ring) <= max_points:
        return ring

    points = [(p[0], p[1]) for p in ring]
    epsilon = 0.0001
    simplified = points
    while len(simplified) > max_points and epsilon < 1.0:
        simplified = douglas_peucker(points, epsilon)
        epsilon *= 2

    return [[x, y] for x, y in simplified]
