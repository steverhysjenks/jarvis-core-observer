import pytest

from app.context.areas import canonical_area


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("office", "office"),
        ("Office", "office"),
        ("Office area", "office"),
        ("kitchen", "kitchen"),
        ("Kitchen", "kitchen"),
        ("Master Bedroom", "master_bedroom"),
        ("My Bedroom", "master_bedroom"),
    ],
)
def test_known_area_aliases(raw, expected):
    assert canonical_area(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "Definitely Not A Room",
        "garage that does not exist",
    ],
)
def test_unknown_area_fails_closed(raw):
    assert canonical_area(raw) is None
