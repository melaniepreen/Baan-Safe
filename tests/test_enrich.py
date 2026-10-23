from enrich.context import location_context, sample_districts


KEYS = {
    "in_flood_extent_1d",
    "in_flood_extent_7d",
    "in_flood_extent_30d",
    "repeat_flood_area",
    "rainfall_last_24h_mm",
    "rainfall_forecast_24h_mm",
    "nearest_hospitals",
    "candidate_shelters",
    "data_freshness",
}


def test_three_sample_districts():
    names = sample_districts(3)
    assert len(names) >= 3
    for name in names:
        ctx = location_context(name, None, None)
        assert KEYS <= ctx.keys()
        assert isinstance(ctx["nearest_hospitals"], list)
        assert isinstance(ctx["candidate_shelters"], list)
        assert ctx["matched_district"] == name


def test_coordinate_query():
    ctx = location_context(None, 18.39, 99.84)
    assert KEYS <= ctx.keys()
    assert ctx["point"]["lat"] == 18.39
