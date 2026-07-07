from app.models import ProductAttribute
from app.services.attribute_grouping import group_attributes


def test_groups_known_attributes_into_their_sections():
    attributes = [
        ProductAttribute(name="orbitNumber", value="57694"),
        ProductAttribute(name="instrumentShortName", value="SAR"),
        ProductAttribute(name="platformShortName", value="SENTINEL-1"),
        ProductAttribute(name="somethingUnmapped", value="foo"),
    ]

    grouped = group_attributes(attributes)

    assert grouped.product == [{"label": "Absolute orbit number", "value": "57694"}]
    assert grouped.instrument == [{"label": "Instrument short name", "value": "SAR"}]
    assert grouped.platform == [{"label": "Platform short name", "value": "SENTINEL-1"}]
    assert grouped.other == [{"label": "somethingUnmapped", "value": "foo"}]


def test_missing_attributes_are_simply_absent_not_errors():
    grouped = group_attributes([])
    assert grouped.product == []
    assert grouped.instrument == []
    assert grouped.platform == []
    assert grouped.other == []
