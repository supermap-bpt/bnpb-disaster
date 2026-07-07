from dataclasses import dataclass

from app.models import ProductAttribute

# Ported from frontend/src/components/ProductInfoModal.tsx's PRODUCT_FIELDS/
# INSTRUMENT_FIELDS/PLATFORM_FIELDS - keep these two lists in sync if either changes.
PRODUCT_FIELDS: list[tuple[str, str]] = [
    ("orbitNumber", "Absolute orbit number"),
    ("beginningDateTime", "Beginning date time"),
    ("completionTimeFromAscendingNode", "Completion time from ascending node"),
    ("cycleNumber", "Cycle number"),
    ("dataTakeID", "Data take id"),
    ("endingDateTime", "Ending date time"),
    ("instrumentConfigurationID", "Instrument configuration id"),
    ("modificationDate", "Modification date"),
    ("operationalMode", "Operational mode"),
    ("orbitDirection", "Orbit direction"),
    ("origin", "Origin"),
    ("originDate", "Origin date"),
    ("polarisationChannels", "Polarisation channels"),
    ("processingCenter", "Processing center"),
    ("processingDate", "Processing date"),
    ("processingLevel", "Processing level"),
    ("processorName", "Processor name"),
    ("processorVersion", "Processor version"),
    ("productClass", "Product class"),
    ("productComposition", "Product composition"),
    ("productType", "Product type"),
    ("publicationDate", "Publication date"),
    ("relativeOrbitNumber", "Relative orbit number"),
    ("s3Path", "S3 path"),
    ("segmentStartTime", "Segment start time"),
    ("sliceNumber", "Slice number"),
    ("sliceProductFlag", "Slice product flag"),
    ("startTimeFromAscendingNode", "Start time from ascending node"),
    ("swathIdentifier", "Swath identifier"),
    ("timeliness", "Timeliness"),
    ("totalSlices", "Total slices"),
]

INSTRUMENT_FIELDS: list[tuple[str, str]] = [
    ("instrumentShortName", "Instrument short name"),
]

PLATFORM_FIELDS: list[tuple[str, str]] = [
    ("platformShortName", "Platform short name"),
    ("platformSerialIdentifier", "Platform serial identifier"),
]

MAPPED_NAMES = {name for name, _ in PRODUCT_FIELDS + INSTRUMENT_FIELDS + PLATFORM_FIELDS}


@dataclass
class GroupedAttributes:
    product: list[dict[str, str]]
    instrument: list[dict[str, str]]
    platform: list[dict[str, str]]
    other: list[dict[str, str]]


def _rows(by_name: dict[str, str], fields: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"label": label, "value": by_name[name]} for name, label in fields if name in by_name]


def group_attributes(attributes: list[ProductAttribute]) -> GroupedAttributes:
    by_name = {attr.name: attr.value for attr in attributes}
    other = [{"label": attr.name, "value": attr.value} for attr in attributes if attr.name not in MAPPED_NAMES]
    return GroupedAttributes(
        product=_rows(by_name, PRODUCT_FIELDS),
        instrument=_rows(by_name, INSTRUMENT_FIELDS),
        platform=_rows(by_name, PLATFORM_FIELDS),
        other=other,
    )
