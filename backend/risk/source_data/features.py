from __future__ import annotations

from django.conf import settings


FEATURE_SOURCE_DATA_OPS = "SOURCE_DATA_OPS_ENABLED"
FEATURE_IMPORT_CONFIRM = "SOURCE_DATA_IMPORT_CONFIRM_ENABLED"
FEATURE_DOWNSTREAM_ACTIONS = "SOURCE_DATA_DOWNSTREAM_ACTIONS_ENABLED"
FEATURE_FACILITY_READINESS_IMPORT = "FACILITY_READINESS_SNAPSHOT_IMPORT_ENABLED"
FEATURE_API_CONNECTORS = "SOURCE_DATA_API_CONNECTORS_ENABLED"
FEATURE_PHASE_AUDIT_REQUIRED = "SOURCE_DATA_PHASE_AUDIT_REQUIRED"

SOURCE_DATA_FEATURE_FLAGS = (
    FEATURE_SOURCE_DATA_OPS,
    FEATURE_IMPORT_CONFIRM,
    FEATURE_DOWNSTREAM_ACTIONS,
    FEATURE_FACILITY_READINESS_IMPORT,
    FEATURE_API_CONNECTORS,
    FEATURE_PHASE_AUDIT_REQUIRED,
)


class SourceDataFeatureDisabledError(ValueError):
    def __init__(self, flag_name: str):
        self.flag_name = flag_name
        super().__init__(f"{flag_name} is disabled.")


def source_data_feature_enabled(flag_name: str) -> bool:
    return bool(getattr(settings, flag_name, True))


def require_source_data_feature(flag_name: str) -> None:
    if not source_data_feature_enabled(flag_name):
        raise SourceDataFeatureDisabledError(flag_name)


def require_source_data_ops_enabled() -> None:
    require_source_data_feature(FEATURE_SOURCE_DATA_OPS)


def source_data_feature_flags_payload() -> dict[str, bool]:
    return {flag_name: source_data_feature_enabled(flag_name) for flag_name in SOURCE_DATA_FEATURE_FLAGS}


def facility_readiness_snapshot_import_enabled() -> bool:
    return source_data_feature_enabled(FEATURE_FACILITY_READINESS_IMPORT)


def source_data_api_connectors_enabled() -> bool:
    return source_data_feature_enabled(FEATURE_API_CONNECTORS)
