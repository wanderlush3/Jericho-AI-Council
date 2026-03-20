"""
Jericho — Tests for Location System (F-026)

Tests for core/locations.py: LocationFeature, Location, LocationManager,
lifecycle, feature management, updates, parent/child hierarchy, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.locations import (
    Location,
    LocationError,
    LocationFeature,
    LocationLifecycleError,
    LocationManager,
    LocationNotFoundError,
    LocationValidationError,
)


# ─── Helpers ──────────────────────────────────────────────────


def _make_feature(**overrides) -> LocationFeature:
    """Create a default LocationFeature for testing."""
    defaults = {
        "name": "Great Hall",
        "description": "A massive stone hall",
        "feature_type": "building",
    }
    defaults.update(overrides)
    return LocationFeature.create(**defaults)


def _make_manager(tmp_path: Path) -> LocationManager:
    """Create a LocationManager with a temp directory."""
    return LocationManager(locations_dir=tmp_path / "locations")


def _create_sample(mgr: LocationManager, **overrides) -> Location:
    """Create a minimal location via the manager."""
    defaults = {
        "name": "Ironhaven",
        "description": "A fortified port city",
        "author": "Council",
    }
    defaults.update(overrides)
    name = defaults.pop("name")
    desc = defaults.pop("description")
    return mgr.create(name, desc, **defaults)


# ═══════════════════════════════════════════════════════════════
# LocationFeature
# ═══════════════════════════════════════════════════════════════


class TestLocationFeature:
    def test_fields(self):
        f = LocationFeature(name="Tower", description="A watchtower", feature_type="building")
        assert f.name == "Tower"
        assert f.description == "A watchtower"
        assert f.feature_type == "building"

    def test_frozen(self):
        f = _make_feature()
        with pytest.raises(AttributeError):
            f.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        f = _make_feature()
        d = f.to_dict()
        f2 = LocationFeature.from_dict(d)
        assert f == f2

    def test_create_factory(self):
        f = LocationFeature.create("Market Square", "A bustling market", "landmark")
        assert f.name == "Market Square"
        assert f.feature_type == "landmark"

    def test_invalid_feature_type(self):
        with pytest.raises(LocationValidationError, match="Feature type"):
            LocationFeature.create("X", "Y", feature_type="imaginary")

    def test_default_feature_type(self):
        f = LocationFeature(name="X", description="Y")
        assert f.feature_type == "custom"

    def test_all_valid_types(self):
        for ft in ("landmark", "district", "building", "natural", "infrastructure", "custom"):
            f = LocationFeature.create("Test", "Desc", feature_type=ft)
            assert f.feature_type == ft


# ═══════════════════════════════════════════════════════════════
# Location
# ═══════════════════════════════════════════════════════════════


class TestLocation:
    def test_fields(self):
        f = _make_feature()
        loc = Location(
            id="LOC-0001",
            name="Ironhaven",
            description="A fortified port city",
            author="Council",
            features=[f],
        )
        assert loc.id == "LOC-0001"
        assert loc.name == "Ironhaven"
        assert loc.status == "draft"
        assert loc.version == 1
        assert len(loc.features) == 1

    def test_frozen(self):
        loc = Location(id="LOC-0001", name="A", description="D", author="C")
        with pytest.raises(AttributeError):
            loc.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        f = _make_feature()
        loc = Location.create(
            id="LOC-0001",
            name="Ironhaven",
            description="A fortified port city",
            author="Council",
            lore="Founded by iron-willed sailors",
            features=[f],
            tags=["port", "fortress"],
            parent_location_id="",
            coordinates="42.3N, 71.1W",
            metadata={"origin": "session-1"},
        )
        d = loc.to_dict()
        loc2 = Location.from_dict(d)
        assert loc == loc2

    def test_create_factory(self):
        loc = Location.create(
            id="LOC-0001",
            name="Ironhaven",
            description="A fortified port city",
            author="Council",
        )
        assert loc.status == "draft"
        assert loc.version == 1
        assert loc.created_at != ""
        assert loc.updated_at != ""

    def test_defaults(self):
        loc = Location(id="LOC-0001", name="A", description="D", author="C")
        assert loc.lore == ""
        assert loc.features == []
        assert loc.tags == []
        assert loc.parent_location_id == ""
        assert loc.coordinates == ""
        assert loc.version == 1
        assert loc.metadata == {}

    def test_from_dict_missing_optionals(self):
        data = {"id": "LOC-0001", "name": "A", "description": "D", "author": "C"}
        loc = Location.from_dict(data)
        assert loc.status == "draft"
        assert loc.version == 1
        assert loc.features == []

    def test_create_with_metadata(self):
        loc = Location.create(
            id="LOC-0001",
            name="A",
            description="D",
            author="C",
            metadata={"key": "value"},
        )
        assert loc.metadata == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# LocationManager Init
# ═══════════════════════════════════════════════════════════════


class TestLocationManagerInit:
    def test_creates_directory(self, tmp_path):
        mgr = LocationManager(locations_dir=tmp_path / "new_locs")
        assert mgr.directory.exists()

    def test_existing_directory(self, tmp_path):
        d = tmp_path / "locs"
        d.mkdir()
        mgr = LocationManager(locations_dir=d)
        assert mgr.directory == d

    def test_repr(self, tmp_path):
        mgr = _make_manager(tmp_path)
        r = repr(mgr)
        assert "LocationManager" in r
        assert "locations=0" in r


# ═══════════════════════════════════════════════════════════════
# Location Creation
# ═══════════════════════════════════════════════════════════════


class TestLocationCreation:
    def test_basic(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        assert loc.id == "LOC-0001"
        assert loc.name == "Ironhaven"
        assert loc.status == "draft"

    def test_sequential_ids(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc1 = _create_sample(mgr, name="Alpha")
        loc2 = _create_sample(mgr, name="Beta")
        assert loc1.id == "LOC-0001"
        assert loc2.id == "LOC-0002"

    def test_persistence(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        loaded = mgr.get(loc.id)
        assert loaded.name == loc.name
        assert loaded.author == loc.author

    def test_with_all_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        feat = _make_feature()
        loc = mgr.create(
            "Ironhaven",
            "A fortified port city",
            author="Council",
            lore="Founded by iron-willed sailors",
            features=[feat],
            tags=["port", "fortress"],
            coordinates="42.3N, 71.1W",
            metadata={"origin": "test"},
        )
        assert loc.lore == "Founded by iron-willed sailors"
        assert len(loc.features) == 1
        assert loc.tags == ["port", "fortress"]
        assert loc.coordinates == "42.3N, 71.1W"
        assert loc.metadata == {"origin": "test"}

    def test_empty_name_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationValidationError, match="Name"):
            mgr.create("", "Desc", author="Council")

    def test_empty_description_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationValidationError, match="Description"):
            mgr.create("Ironhaven", "", author="Council")

    def test_empty_author_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationValidationError, match="Author"):
            mgr.create("Ironhaven", "Desc", author="")

    def test_whitespace_stripping(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = mgr.create("  Ironhaven  ", "  Port city  ", author="  Council  ")
        assert loc.name == "Ironhaven"
        assert loc.description == "Port city"
        assert loc.author == "Council"

    def test_with_parent(self, tmp_path):
        mgr = _make_manager(tmp_path)
        parent = _create_sample(mgr, name="Continent")
        child = mgr.create(
            "Ironhaven", "Port city", author="Council",
            parent_location_id=parent.id,
        )
        assert child.parent_location_id == parent.id

    def test_invalid_parent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationValidationError, match="Parent location not found"):
            mgr.create(
                "Ironhaven", "Port city", author="Council",
                parent_location_id="LOC-9999",
            )


# ═══════════════════════════════════════════════════════════════
# Location Retrieval
# ═══════════════════════════════════════════════════════════════


class TestLocationRetrieval:
    def test_get_by_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        loaded = mgr.get(loc.id)
        assert loaded.id == loc.id

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationNotFoundError, match="LOC-9999"):
            mgr.get("LOC-9999")

    def test_list_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        locs = mgr.list_locations()
        assert len(locs) == 2

    def test_filter_by_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc1 = _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        mgr.update_status(loc1.id, "active")
        drafts = mgr.list_locations(status="draft")
        assert len(drafts) == 1
        assert drafts[0].name == "Beta"

    def test_filter_by_author(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Council")
        _create_sample(mgr, name="Beta", author="Sage")
        council_locs = mgr.list_locations(author="council")  # case-insensitive
        assert len(council_locs) == 1
        assert council_locs[0].name == "Alpha"

    def test_filter_by_tag(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", tags=["port", "fortress"])
        _create_sample(mgr, name="Beta", tags=["village"])
        ports = mgr.list_locations(tag="port")
        assert len(ports) == 1
        assert ports[0].name == "Alpha"

    def test_filter_by_parent(self, tmp_path):
        mgr = _make_manager(tmp_path)
        parent = _create_sample(mgr, name="Continent")
        child = mgr.create(
            "Ironhaven", "Port city", author="Council",
            parent_location_id=parent.id,
        )
        _create_sample(mgr, name="Standalone")
        children = mgr.list_locations(parent_location_id=parent.id)
        assert len(children) == 1
        assert children[0].id == child.id

    def test_combined_filters(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Council", tags=["port"])
        _create_sample(mgr, name="Beta", author="Council", tags=["village"])
        _create_sample(mgr, name="Gamma", author="Sage", tags=["port"])
        results = mgr.list_locations(author="council", tag="port")
        assert len(results) == 1
        assert results[0].name == "Alpha"

    def test_empty_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_locations() == []


# ═══════════════════════════════════════════════════════════════
# Status Lifecycle
# ═══════════════════════════════════════════════════════════════


class TestStatusLifecycle:
    def test_draft_to_active(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update_status(loc.id, "active")
        assert updated.status == "active"

    def test_active_to_archived(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        mgr.update_status(loc.id, "active")
        updated = mgr.update_status(loc.id, "archived")
        assert updated.status == "archived"

    def test_skip_phase_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        with pytest.raises(LocationLifecycleError):
            mgr.update_status(loc.id, "archived")  # draft → archived not allowed

    def test_archived_terminal(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        mgr.update_status(loc.id, "active")
        mgr.update_status(loc.id, "archived")
        with pytest.raises(LocationLifecycleError):
            mgr.update_status(loc.id, "active")

    def test_unknown_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        with pytest.raises(LocationValidationError, match="Unknown status"):
            mgr.update_status(loc.id, "imaginary")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationNotFoundError):
            mgr.update_status("LOC-9999", "active")

    def test_status_update_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update_status(loc.id, "active")
        assert updated.updated_at >= loc.updated_at


# ═══════════════════════════════════════════════════════════════
# Feature Management
# ═══════════════════════════════════════════════════════════════


class TestFeatureManagement:
    def test_add_feature(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        feat = _make_feature()
        updated = mgr.add_feature(loc.id, feat)
        assert len(updated.features) == 1

    def test_duplicate_feature_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr, features=[_make_feature()])
        dup = _make_feature(name="great hall")  # case-insensitive
        with pytest.raises(LocationValidationError, match="already exists"):
            mgr.add_feature(loc.id, dup)

    def test_remove_feature(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f1 = _make_feature(name="Hall")
        f2 = _make_feature(name="Tower")
        loc = _create_sample(mgr, features=[f1, f2])
        updated = mgr.remove_feature(loc.id, "Hall")
        assert len(updated.features) == 1
        assert updated.features[0].name == "Tower"

    def test_remove_nonexistent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        with pytest.raises(LocationValidationError, match="not found"):
            mgr.remove_feature(loc.id, "Nonexistent")

    def test_add_feature_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        feat = _make_feature()
        mgr.add_feature(loc.id, feat)
        reloaded = mgr.get(loc.id)
        assert len(reloaded.features) == 1

    def test_remove_feature_case_insensitive(self, tmp_path):
        mgr = _make_manager(tmp_path)
        f1 = _make_feature(name="Hall")
        f2 = _make_feature(name="Tower")
        loc = _create_sample(mgr, features=[f1, f2])
        updated = mgr.remove_feature(loc.id, "  HALL  ")
        assert len(updated.features) == 1

    def test_multiple_features(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        for i in range(10):
            feat = LocationFeature.create(f"Feature-{i}", f"Desc-{i}", "landmark")
            loc = mgr.add_feature(loc.id, feat)
        assert len(loc.features) == 10


# ═══════════════════════════════════════════════════════════════
# Location Update
# ═══════════════════════════════════════════════════════════════


class TestLocationUpdate:
    def test_update_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(loc.id, name="Ironhaven v2")
        assert updated.name == "Ironhaven v2"

    def test_update_description(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(loc.id, description="A thriving trade hub")
        assert updated.description == "A thriving trade hub"

    def test_update_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(loc.id, lore="Founded centuries ago")
        assert updated.lore == "Founded centuries ago"

    def test_immutable_field_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        with pytest.raises(LocationValidationError, match="immutable"):
            mgr.update(loc.id, id="LOC-9999")

    def test_author_immutable(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        with pytest.raises(LocationValidationError, match="immutable"):
            mgr.update(loc.id, author="Sage")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(LocationNotFoundError):
            mgr.update("LOC-9999", name="Ghost")

    def test_multiple_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(
            loc.id, name="New Name", description="New Desc", tags=["new-tag"],
        )
        assert updated.name == "New Name"
        assert updated.description == "New Desc"
        assert updated.tags == ["new-tag"]

    def test_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(loc.id, name="Changed")
        assert updated.updated_at >= loc.updated_at

    def test_update_coordinates(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = _create_sample(mgr)
        updated = mgr.update(loc.id, coordinates="42.3N, 71.1W")
        assert updated.coordinates == "42.3N, 71.1W"


# ═══════════════════════════════════════════════════════════════
# Children
# ═══════════════════════════════════════════════════════════════


class TestChildren:
    def test_get_children(self, tmp_path):
        mgr = _make_manager(tmp_path)
        parent = _create_sample(mgr, name="Continent")
        mgr.create("City A", "Desc", author="C", parent_location_id=parent.id)
        mgr.create("City B", "Desc", author="C", parent_location_id=parent.id)
        _create_sample(mgr, name="Standalone")
        children = mgr.get_children(parent.id)
        assert len(children) == 2

    def test_no_children(self, tmp_path):
        mgr = _make_manager(tmp_path)
        parent = _create_sample(mgr, name="Leaf")
        children = mgr.get_children(parent.id)
        assert children == []


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode(self, tmp_path):
        mgr = _make_manager(tmp_path)
        loc = mgr.create(
            "Ätlántis 日本語",
            "描述 — description with émojis 🏰",
            author="Fõrge",
        )
        loaded = mgr.get(loc.id)
        assert loaded.name == "Ätlántis 日本語"

    def test_long_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        long_text = "A" * 100_000
        loc = mgr.create("Ironhaven", "Port", author="Council", lore=long_text)
        loaded = mgr.get(loc.id)
        assert len(loaded.lore) == 100_000

    def test_many_features(self, tmp_path):
        mgr = _make_manager(tmp_path)
        features = [LocationFeature.create(f"F-{i}", f"D-{i}", "landmark") for i in range(50)]
        loc = mgr.create("Ironhaven", "Port", author="Council", features=features)
        loaded = mgr.get(loc.id)
        assert len(loaded.features) == 50

    def test_corrupt_json_skipped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr)
        # Write a corrupt file
        corrupt = mgr.directory / "LOC-0099.json"
        corrupt.write_text("{bad json", encoding="utf-8")
        locs = mgr.list_locations()
        assert len(locs) == 1  # corrupt file skipped

    def test_persistence_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        feat = _make_feature()
        loc = mgr.create(
            "Ironhaven",
            "Port city",
            author="Council",
            lore="Founded by seafarers",
            features=[feat],
            tags=["port", "fortress"],
            coordinates="42.3N, 71.1W",
            metadata={"origin": "test"},
        )
        mgr.update_status(loc.id, "active")
        mgr.add_feature(loc.id, LocationFeature.create("Dock", "A large dock", "infrastructure"))

        # Reload from a fresh manager
        mgr2 = LocationManager(locations_dir=mgr.directory)
        loaded = mgr2.get(loc.id)
        assert loaded.name == "Ironhaven"
        assert loaded.status == "active"
        assert len(loaded.features) == 2
        assert loaded.lore == "Founded by seafarers"
        assert loaded.tags == ["port", "fortress"]


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(LocationNotFoundError, LocationError)
        assert issubclass(LocationValidationError, LocationError)
        assert issubclass(LocationLifecycleError, LocationError)
        assert issubclass(LocationError, Exception)

    def test_not_found_fields(self):
        e = LocationNotFoundError("LOC-0001")
        assert e.location_id == "LOC-0001"
        assert "LOC-0001" in str(e)

    def test_validation_fields(self):
        e = LocationValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)

    def test_lifecycle_fields(self):
        e = LocationLifecycleError("LOC-0001", "draft", "archived")
        assert e.location_id == "LOC-0001"
        assert e.current_status == "draft"
        assert e.requested_status == "archived"
