"""Browser-verified Migori facility records used by the local demo seed.

The coordinates below are the place coordinates exposed by the Google Maps
listings observed in the user's Chrome session on 2026-08-09.  They establish
that a named place listing exists at the coordinate; they are not a substitute
for an official Ministry of Health facility registry or an operational-status
verification.  Ownership and level are local seed classifications retained for
model compatibility, not claims verified by the Maps listings.
"""

from django.contrib.gis.geos import Point


MIGORI_MAP_VERIFIED_FACILITIES = {
    "CCHIS-HF-001": {
        "name": "Lwala Community Hospital",
        "facility_type": "HOSPITAL",
        "ownership": "PRIVATE",
        "level": "LEVEL_4",
        "ward_code": "KE-WARD-1261",
        "ward_name": "North Kamagambo",
        "sub_county": "Rongo",
        "latitude": -0.6781171,
        "longitude": 34.6088094,
        "source_name": "Google Maps place listing",
        "source_observed_at": "2026-08-09",
        "source_url": (
            "https://www.google.com/maps/place/Lwala+Community+Hospital/"
            "data=!4m7!3m6!1s0x182b314e1a8b9673:0x8f98a829b2ab0f16!8m2!3d-0.6781171!4d34.6088094"
            "!16s%2Fg%2F1hm6gy1qw"
        ),
    },
    "CCHIS-HF-002": {
        "name": "AGENGA DISPENSARY",
        "facility_type": "DISPENSARY",
        "ownership": "PUBLIC",
        "level": "LEVEL_2",
        "ward_code": "KE-WARD-1284",
        "ward_name": "North Kadem",
        "sub_county": "Nyatike",
        "latitude": -0.884,
        "longitude": 34.256291,
        "source_name": "Google Maps place listing",
        "source_observed_at": "2026-08-09",
        "source_url": (
            "https://www.google.com/maps/place/AGENGA+DISPENSARY/"
            "@-0.8839946,34.2537161,17z/data=!3m1!4b1!4m6!3m5!1s0x19d4a5052b4252d3:0x502d3cef41813b54"
            "!8m2!3d-0.884!4d34.256291!16s%2Fg%2F11fvqxl8rl"
        ),
    },
    "CCHIS-HF-003": {
        "name": "Macalder Mission Dispensary",
        "facility_type": "DISPENSARY",
        "ownership": "FAITH_BASED",
        "level": "LEVEL_2",
        "ward_code": "KE-WARD-1285",
        "ward_name": "Macalder/Kanyarwanda",
        "sub_county": "Nyatike",
        "latitude": -0.9546974,
        "longitude": 34.2856868,
        "source_name": "Google Maps place listing",
        "source_observed_at": "2026-08-09",
        "source_url": (
            "https://www.google.com/maps/place/Macalder+Mission+Dispensary/"
            "@-0.954692,34.2831119,17z/data=!3m1!4b1!4m6!3m5!1s0x19d4a72226b49249:0x4a39beb2cfa166ec"
            "!8m2!3d-0.9546974!4d34.2856868!16s%2Fg%2F11k62750vx"
        ),
    },
    "CCHIS-HF-004": {
        "name": "Got Kachola Dispensary",
        "facility_type": "DISPENSARY",
        "ownership": "PUBLIC",
        "level": "LEVEL_2",
        "ward_code": "KE-WARD-1287",
        "ward_name": "Got Kachola",
        "sub_county": "Nyatike",
        "latitude": -0.9601557,
        "longitude": 34.1437905,
        "source_name": "Google Maps place listing",
        "source_observed_at": "2026-08-09",
        "source_url": (
            "https://www.google.com/maps/place/Got+Kachola+Dispensary/"
            "@-0.9601503,34.1412156,17z/data=!3m1!4b1!4m6!3m5!1s0x19d49fa5779be6bd:0x1d6afbe8003d746c"
            "!8m2!3d-0.9601557!4d34.1437905!16s%2Fg%2F11jpfj5thn"
        ),
    },
    "CCHIS-HF-005": {
        "name": "Ikerege Medical Center",
        "facility_type": "CLINIC",
        "ownership": "PRIVATE",
        "level": "LEVEL_2",
        "ward_code": "KE-WARD-1290",
        "ward_name": "Bukira Centrl/Ikerege",
        "sub_county": "Kuria West",
        "latitude": -1.181123,
        "longitude": 34.5417619,
        "source_name": "Google Maps place listing",
        "source_observed_at": "2026-08-09",
        "source_url": (
            "https://www.google.com/maps/place/Ikerege+Medical+Center/"
            "@-1.1811176,34.539187,17z/data=!3m1!4b1!4m6!3m5!1s0x182cb3c4b508cd83:0x8ec1cc28999529ca"
            "!8m2!3d-1.181123!4d34.5417619!16s%2Fg%2F11k62hxfjy"
        ),
    },
}


def build_seed_facility_payload(facility_code: str) -> dict:
    """Return the model payload used by ``seed_demo_data`` for one facility."""

    record = MIGORI_MAP_VERIFIED_FACILITIES[facility_code]
    return {
        "name": record["name"],
        "facility_code": facility_code,
        "facility_type": record["facility_type"],
        "ownership": record["ownership"],
        "level": record["level"],
        # The old phone numbers were synthetic scenario values.  Do not carry
        # them into the browser-verified records unless a source is recorded.
        "contact_phone": "",
        "point": Point(record["longitude"], record["latitude"], srid=4326),
    }
