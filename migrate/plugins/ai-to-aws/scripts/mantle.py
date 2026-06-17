"""Mantle-ID normalization and catalog matching helpers.

Pure module: no network, no AWS calls. The live Mantle catalog is passed in
by the caller — these functions only normalize ids and decide availability.
"""
import re

_GEO_PREFIX = re.compile(r"^(us|eu|apac|global)\.")
# trailing -YYYYMMDD, or -vN, or :N (alone or combined like -v1:0)
_DATE_SUFFIX = re.compile(r"-\d{8}")
_VERSION_SUFFIX = re.compile(r"-v\d+")
_COLON_SUFFIX = re.compile(r":\d+$")


def to_mantle_candidate(runtime_id: str) -> str:
    """Normalize a bedrock-runtime model id to its Mantle-ID candidate form.

    Strips the geo-inference prefix (us./eu./apac./global.) and trailing
    version/date markers (-YYYYMMDD, -vN, :N). Returns the bare vendor.model
    string to be exact-matched against the live Mantle catalog.
    """
    s = _GEO_PREFIX.sub("", runtime_id)
    s = _COLON_SUFFIX.sub("", s)
    s = _DATE_SUFFIX.sub("", s)
    s = _VERSION_SUFFIX.sub("", s)
    return s


def match_in_catalog(runtime_id: str, catalog_ids: list) -> str | None:
    """Return the exact Mantle id if the normalized candidate is in the catalog,
    else None. Exact match only — never fuzzy/prefix (a near-match would
    silently target a different model)."""
    candidate = to_mantle_candidate(runtime_id)
    return candidate if candidate in catalog_ids else None


def evaluate_targets(runtime_ids: list, catalog_ids: list) -> dict:
    """Map each runtime target to its Mantle id (or None) and decide whether
    the express lane is offerable (ALL targets must be available; an empty
    catalog — e.g. lookup failed — yields all_available False)."""
    per_target = {rid: match_in_catalog(rid, catalog_ids) for rid in runtime_ids}
    all_available = bool(runtime_ids) and all(v is not None for v in per_target.values())
    return {"all_available": all_available, "per_target": per_target}
