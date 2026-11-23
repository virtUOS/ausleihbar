# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from numbers import Real

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from catalog.serializers import TranslatedFieldsMixin

from . import hours, place_groups, privacy, rights
from .models import (
    window_errors,
    Absence, Building, DeskSettings, Display, Feature, FeatureImage, Floor, FloorTemplate, Place, Reservation,
    Room, Series,
)

SHAPE_TYPES = {"room", "wall", "door", "window", "label"}
ROOM_ICONS = {"stairs", "wc_men", "wc_women", "wc_all", "wc_accessible"}


def _is_num(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


def validate_plan(plan, room_ids=None) -> dict:
    """Plan JSON: ``{"shapes": [{id, type, points, text, room_id, outline, icon,
    wall, width, flip_hinge, flip_swing}]}``.

    ``id`` is unique within the plan; ``type`` is room / wall / door / window /
    label. Rooms may carry ``outline: "wall"`` and an ``icon`` (stairs, wc_men,
    wc_women, wc_all, wc_accessible). A wall-bound door and every window have
    ``wall: {shape, edge, t}`` (a room shape of this plan, ``0 <= edge <`` its
    point count, ``0 <= t <= 1``) and ``width > 0``; doors optionally the bool
    flags ``flip_hinge`` / ``flip_swing``. Old doors keep two ``points``."""
    if not isinstance(plan, dict) or not isinstance(plan.get("shapes"), list):
        raise serializers.ValidationError('Plan must be {"shapes": [...]}.')
    seen_ids = set()
    for shape in plan["shapes"]:
        if not isinstance(shape, dict):
            raise serializers.ValidationError("Every shape must be an object.")
        if not isinstance(shape.get("id"), str) or not shape["id"]:
            raise serializers.ValidationError("Shape id must be a string.")
        if shape["id"] in seen_ids:
            raise serializers.ValidationError("Shape ids must be unique.")
        seen_ids.add(shape["id"])
        if shape.get("type") not in SHAPE_TYPES:
            raise serializers.ValidationError("Unknown shape type.")
        points = shape.get("points")
        if points is not None:
            if not isinstance(points, list) or not all(
                isinstance(p, (list, tuple)) and len(p) == 2 and all(_is_num(c) for c in p)
                for p in points
            ):
                raise serializers.ValidationError("Shape points must be [[x, y], ...].")
        text = shape.get("text")
        if text is not None and not isinstance(text, str):
            raise serializers.ValidationError("Shape text must be a string.")
        room_id = shape.get("room_id")
        if room_id is not None:
            if not isinstance(room_id, int) or isinstance(room_id, bool):
                raise serializers.ValidationError("Shape room_id must be an integer.")
            if room_ids is not None and room_id not in room_ids:
                raise serializers.ValidationError("Shape room_id is not a room of this floor.")
        if shape.get("outline") is not None and shape["outline"] != "wall":
            raise serializers.ValidationError('Room outline must be "wall".')
        if shape.get("icon") is not None and shape["icon"] not in ROOM_ICONS:
            raise serializers.ValidationError("Unknown room icon.")
        width = shape.get("width")
        is_opening = shape["type"] == "window" or "wall" in shape
        if (width is None and is_opening) or (
            width is not None and (not _is_num(width) or width <= 0)
        ):
            raise serializers.ValidationError("Opening width must be a positive number.")
        for flag in ("flip_hinge", "flip_swing"):
            if flag in shape and not isinstance(shape[flag], bool):
                raise serializers.ValidationError("Door flips must be true or false.")

    # Wall references point into the same plan, so check them once all shapes are known.
    rooms = {
        s["id"]: s for s in plan["shapes"] if s["type"] == "room"
    }
    for shape in plan["shapes"]:
        if shape["type"] == "window" or "wall" in shape:
            wall = shape.get("wall")
            if not isinstance(wall, dict):
                raise serializers.ValidationError("Opening wall must be {shape, edge, t}.")
            ref = wall.get("shape")
            room = rooms.get(ref) if isinstance(ref, str) and ref else None
            if room is None:
                raise serializers.ValidationError("Opening wall must refer to a room shape of this plan.")
            edge, t = wall.get("edge"), wall.get("t")
            count = len(room.get("points") or [])
            if not isinstance(edge, int) or isinstance(edge, bool) or not 0 <= edge < count:
                raise serializers.ValidationError("Opening wall edge is out of range.")
            if not _is_num(t) or not 0 <= t <= 1:
                raise serializers.ValidationError("Opening wall position must be between 0 and 1.")
    return plan


def validate_business_hours(value) -> dict:
    if not isinstance(value, dict) or set(value) != {str(d) for d in range(7)}:
        raise serializers.ValidationError('Business hours need the keys "0" to "6".')
    for hours in value.values():
        if hours is None:
            continue
        if (
            not isinstance(hours, (list, tuple))
            or len(hours) != 2
            or not all(isinstance(h, int) and not isinstance(h, bool) for h in hours)
            or not (6 <= hours[0] < hours[1] <= 20)
        ):
            raise serializers.ValidationError(
                "Hours must be null or [start, end] with 6 <= start < end <= 20."
            )
    return value


NAME_COLUMNS = ("name", *(f"name_{lang}" for lang in settings.MODELTRANSLATION_LANGUAGES))


class UniqueNameMixin:
    """Case-insensitive name uniqueness within a scope (all languages).

    A subclass sets ``name_taken_message`` (static, translated in the
    frontend), ``name_constraint`` (the DB constraint backing it, if any, so
    the view can map a racing ``IntegrityError`` to the same 400) and
    implements ``name_scope(attrs)`` -> queryset of rows sharing the scope.
    The check compares every name column (the raw one modeltranslation keeps
    for the active language plus each language) without lookup rewriting,
    so a row named under another language still clashes."""

    name_taken_message = ""
    name_constraint = None
    # Fields that move the object into another scope.
    name_scope_fields: tuple[str, ...] = ()

    def name_scope(self, attrs):
        raise NotImplementedError

    def _names(self, attrs) -> set[str]:
        inst = self.instance
        stored = {}
        if inst is not None and inst.pk:
            model = type(inst)
            stored = model.objects.rewrite(False).filter(pk=inst.pk).values(*NAME_COLUMNS).first() or {}
        values = set()
        for col in NAME_COLUMNS:
            value = attrs[col] if col in attrs else stored.get(col)
            if value:
                values.add(value.strip())
        return {v for v in values if v}

    def check_unique_name(self, attrs) -> None:
        touched = any(col in attrs for col in NAME_COLUMNS) or any(
            f in attrs for f in self.name_scope_fields
        )
        if not touched:
            return
        names = self._names(attrs)
        if not names:
            return
        clash = Q()
        for value in names:
            for col in NAME_COLUMNS:
                clash |= Q(**{f"{col}__iexact": value})
        qs = self.name_scope(attrs).rewrite(False).filter(clash)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": [self.name_taken_message]})


def clean_plan_symbol(value):
    """``{"x", "y", "rotation"}`` numbers (extra keys dropped) or None."""
    if value is None:
        return value
    ok = isinstance(value, dict) and all(_is_num(value.get(k)) for k in ("x", "y", "rotation"))
    if not ok:
        raise serializers.ValidationError('Symbol must be {"x", "y", "rotation"}.')
    return {k: value[k] for k in ("x", "y", "rotation")}


class FeatureImageSerializer(serializers.ModelSerializer):
    """One picture of a piece of equipment (lowest position = cover)."""

    class Meta:
        model = FeatureImage
        fields = ["id", "image", "position"]


class FeatureSerializer(UniqueNameMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """Campus-wide equipment with a picture gallery (images are managed via
    the gallery actions, read-only here)."""

    translated_fields = ("name", "description")
    name_taken_message = "Equipment with this name exists."
    name_constraint = "desk_feature_name_unique"
    images = FeatureImageSerializer(many=True, read_only=True)

    class Meta:
        model = Feature
        fields = [
            "id", "name", "name_de", "name_en",
            "description", "description_de", "description_en", "images",
        ]

    def name_scope(self, attrs):
        return Feature.objects.all()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.check_unique_name(attrs)
        return attrs


class BuildingSerializer(serializers.ModelSerializer):
    """A campus building; ``editable`` tells the client whether the viewer
    may change or delete it (app admins only)."""

    editable = serializers.SerializerMethodField()

    class Meta:
        model = Building
        fields = ["id", "code", "description", "address", "editable"]

    def validate_code(self, value):
        code = value.strip()
        if not code:
            raise serializers.ValidationError("A code is required.")
        clash = Building.objects.filter(code__iexact=code)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A building with this code already exists.")
        return code

    def get_editable(self, obj) -> bool:
        return bool(self.context.get("may_edit"))


class FloorSerializer(UniqueNameMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    translated_fields = ("name",)
    name_taken_message = "A floor with this name exists in this building."
    name_constraint = "desk_floor_name_per_building"
    name_scope_fields = ("building",)
    has_template = serializers.SerializerMethodField()
    template_url = serializers.SerializerMethodField()
    building_code = serializers.CharField(read_only=True)
    building_description = serializers.CharField(
        source="building.description", read_only=True, default=""
    )

    class Meta:
        model = Floor
        fields = [
            "id", "building", "building_code", "building_description",
            "name", "name_de", "name_en", "position", "is_active",
            "has_template", "template_url", "scale_px_per_m", "plan",
        ]
        read_only_fields = ["plan"]

    def name_scope(self, attrs):
        building = attrs["building"] if "building" in attrs else (
            self.instance.building if self.instance else None
        )
        return Floor.objects.filter(building=building)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.check_unique_name(attrs)
        return attrs

    def get_has_template(self, floor) -> bool:
        # Annotated by the viewset; never through ``floor.template`` (the blob).
        exists = getattr(floor, "template_exists", None)
        if exists is None:
            exists = floor.pk is not None and FloorTemplate.objects.filter(floor_id=floor.pk).exists()
            floor.template_exists = exists
        return bool(exists)

    def get_template_url(self, floor):
        if not self.get_has_template(floor):
            return None
        return f"/api/desks/manage/floors/{floor.pk}/template/"


class FloorPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = ["plan"]

    def validate_plan(self, plan):
        room_ids = set(self.instance.rooms.values_list("pk", flat=True))
        return validate_plan(plan, room_ids)


def validate_plan_symbols(value, floor) -> dict:
    """``{place_id: symbol | null}`` for places on ``floor`` -> ``{Place: symbol}``."""
    if not isinstance(value, dict):
        raise serializers.ValidationError('Symbols must be {"<place id>": symbol, ...}.')
    try:
        wanted = {int(key): clean_plan_symbol(sym) for key, sym in value.items()}
    except (TypeError, ValueError):
        raise serializers.ValidationError('Symbols must be {"<place id>": symbol, ...}.')
    places = Place.objects.filter(pk__in=wanted, room__floor=floor).in_bulk()
    if len(places) != len(wanted):
        raise serializers.ValidationError("A place is not on this floor.")
    return {places[pk]: sym for pk, sym in wanted.items()}


def validate_ordinary_groups(groups):
    # Only what the picker offers: ordinary groups, no system/admin groups.
    if any(not place_groups.is_ordinary(g) for g in groups):
        raise serializers.ValidationError(place_groups.SYSTEM_GROUP_MESSAGE)
    return groups


class RoomSerializer(UniqueNameMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """``pool`` is set on create only (optional: an unassigned room);
    afterwards the department changes through the assignment service."""

    translated_fields = ("name",)
    name_taken_message = "A room with this name exists on this floor."
    name_constraint = "desk_room_name_per_floor"
    name_scope_fields = ("floor",)

    class Meta:
        model = Room
        fields = [
            "id", "floor", "pool", "access_groups", "name", "name_de", "name_en", "kind",
            "is_active",
        ]
        extra_kwargs = {"pool": {"required": False}, "access_groups": {"required": False}}

    def validate_access_groups(self, groups):
        return validate_ordinary_groups(groups)

    def update(self, instance, validated_data):
        """Changed default groups are handed down to the places that follow."""
        groups = validated_data.pop("access_groups", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if groups is not None and place_groups.set_room_groups(instance, groups):
                place_groups.hand_down(instance, {g.pk for g in groups})
        return instance

    def name_scope(self, attrs):
        floor = attrs.get("floor") or self.instance.floor
        return Room.objects.filter(floor=floor)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            attrs.pop("pool", None)
        self.check_unique_name(attrs)
        return attrs


class PlaceSerializer(UniqueNameMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """Rights (which rooms/places the requester administers) are checked by
    the view; ``pool``/``pool_overridden`` are read-only (assignment)."""

    translated_fields = ("name",)
    name_taken_message = "A place with this name exists in this building."
    name_scope_fields = ("room",)
    fixed_owner_name = serializers.SerializerMethodField()

    def get_fixed_owner_name(self, place):
        owner = place.fixed_owner
        return (owner.get_full_name() or owner.get_username()) if owner else None

    class Meta:
        model = Place
        fields = [
            "id", "room", "pool", "pool_overridden", "kind", "name", "name_de", "name_en",
            "capacity", "features", "access_groups", "groups_overridden",
            # fixed_owner is the deliberate exception to the opt-out: admins
            # assign that person themselves (admin place API only).
            "is_special", "fixed_owner", "fixed_owner_name", "plan_symbol", "qr_token", "is_active",
        ]
        read_only_fields = ["qr_token", "pool", "pool_overridden"]

    def name_scope(self, attrs):
        floor = (attrs.get("room") or self.instance.room).floor
        if floor.building_id is None:
            return Place.objects.filter(room__floor=floor)
        return Place.objects.filter(room__floor__building_id=floor.building_id)

    def validate_plan_symbol(self, value):
        return clean_plan_symbol(value)

    def validate_access_groups(self, groups):
        return validate_ordinary_groups(groups)

    @transaction.atomic
    def create(self, validated_data):
        groups = validated_data.pop("access_groups", None)
        place = super().create(validated_data)
        self.apply_groups(place, groups, validated_data.get("groups_overridden"))
        return place

    @transaction.atomic
    def update(self, instance, validated_data):
        groups = validated_data.pop("access_groups", None)
        flag = validated_data.get("groups_overridden")
        # A form posts back the groups it showed: those of the room before a move.
        old_room_ids = {g.pk for g in instance.room.access_groups.all()}
        place = super().update(instance, validated_data)
        self.apply_groups(place, groups, flag, old_room_ids)
        return place

    def apply_groups(self, place, groups, flag, old_room_ids=None):
        """A following place takes its (possibly new) room's groups. Posting
        groups that differ from the room's (old or new one, on a move), or
        ``groups_overridden: true``, gives the place a set of its own;
        ``groups_overridden: false`` always follows (posted groups ignored)."""
        room_ids = {g.pk for g in place.room.access_groups.all()}
        if flag is None:
            flag = place.groups_overridden or (
                groups is not None
                and {g.pk for g in groups} not in (room_ids, old_room_ids)
            )
        if not flag:
            place_groups.sync_from_room(place)
            return
        own = {g.pk for g in groups} if groups is not None else {
            g.pk for g in place.access_groups.all()
        }
        place_groups.set_place_groups(place, own, overridden=True)

    def effective_pool_id(self, room):
        """The place's department after this write: its own when overridden,
        else the (new) room's."""
        inst = self.instance
        if inst is not None and inst.pool_overridden:
            return inst.pool_id
        return room.pool_id if room is not None else None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.check_unique_name(attrs)
        inst = self.instance
        kind = attrs.get("kind", inst.kind if inst else Place.Kind.DESK)
        capacity = attrs.get("capacity", inst.capacity if inst else None)
        if kind == Place.Kind.MEETING_ROOM and not capacity:
            raise serializers.ValidationError(
                {"capacity": "A meeting room needs a capacity."}
            )
        room = attrs.get("room") or (inst.room if inst else None)
        owner = attrs["fixed_owner"] if "fixed_owner" in attrs else (inst.fixed_owner if inst else None)
        # Re-checked only when the owner, room or kind is touched, so an
        # unrelated edit of a place with a long-standing owner still works.
        if owner is not None and room is not None and (
            "fixed_owner" in attrs or "room" in attrs or "kind" in attrs
        ):
            if kind == Place.Kind.MEETING_ROOM:
                raise serializers.ValidationError(
                    {"fixed_owner": "Meeting rooms have no fixed owner."}
                )
            pool_id = self.effective_pool_id(room)
            if not owner.is_active or owner.pk not in rights.member_user_ids(pool_id, enabled_only=False):
                raise serializers.ValidationError(
                    {"fixed_owner": "The owner must be an active member of the department."}
                )
        special = attrs["is_special"] if "is_special" in attrs else (inst.is_special if inst else False)
        if special and owner is not None:
            raise serializers.ValidationError(
                {"is_special": "A fixed desk cannot be a special place."}
            )
        return attrs


class DeskSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeskSettings
        fields = [
            "pool", "enabled", "assistant_group", "business_hours",
            "desk_grace_normal_min", "desk_grace_short_min", "desk_scarcity_free_below",
            "room_grace_normal_min", "room_grace_short_min", "room_scarcity_free_below",
            "retention_days",
            "cycle_months", "transition_weeks", "advance_months", "advance_days",
            "advance_places",
        ]
        read_only_fields = ["pool"]

    def validate_business_hours(self, value):
        return validate_business_hours(value)

    def validate_assistant_group(self, value):
        if value is not None and value.system_course_id:
            # Course groups are filled by LMS launches: never a rights group.
            raise serializers.ValidationError(
                "An LTI course group cannot be the assistants group."
            )
        if value is not None and value.system_all:
            raise serializers.ValidationError(
                "The all-users group cannot be the assistants group."
            )
        return value

    def validate(self, attrs):
        enabled = attrs.get("enabled", self.instance.enabled)
        if enabled and not self.instance.pool.access_groups.filter(
            # LTI course groups and "Alle Angemeldeten" don't count.
            system_course__isnull=True, system_all=False
        ).exists():
            raise serializers.ValidationError(
                {"enabled": "Desksharing needs at least one access group on the pool."}
            )
        merged = {
            f: attrs.get(f, getattr(self.instance, f))
            for f in ("cycle_months", "transition_weeks", "advance_months")
        }
        errors = window_errors(**merged)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def place_brief(place) -> dict:
    """Short place description used in booking errors (alternatives)."""
    return {
        "id": place.pk,
        "name": place.name,
        "room": place.room.name,
        "floor": place.room.floor.name,
    }


holder_display_name = privacy.display_name


class ViewerMixin:
    """The viewer for privacy decisions: ``context["viewer"]`` or the
    request's user. Without either everything personal is redacted."""

    @property
    def viewer(self):
        if "viewer" in self.context:
            return self.context["viewer"]
        request = self.context.get("request")
        return getattr(request, "user", None)


class FreePlaceSerializer(serializers.ModelSerializer):
    room = serializers.CharField(source="room.name")
    floor = serializers.CharField(source="room.floor.name")
    building = serializers.CharField(source="room.floor.building_code")
    floor_id = serializers.IntegerField(source="room.floor_id")

    class Meta:
        model = Place
        fields = ["id", "name", "kind", "capacity", "room", "floor", "floor_id", "building", "features"]


class ReservationSerializer(ViewerMixin, serializers.ModelSerializer):
    place = serializers.SerializerMethodField()
    holder_id = serializers.SerializerMethodField()
    booked_by_id = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()
    release_reason = serializers.SerializerMethodField()
    day = serializers.SerializerMethodField()
    start_hour = serializers.SerializerMethodField()
    end_hour = serializers.SerializerMethodField()
    start = serializers.DateTimeField(source="period.lower")
    end = serializers.DateTimeField(source="period.upper")
    neighbours = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id", "place", "day", "start_hour", "end_hour", "start", "end",
            "group", "status", "comment", "holder_id", "booked_by_id",
            "checked_in_at", "late_until", "potentially_free_at",
            "release_reason", "series_id", "neighbours",
        ]
        read_only_fields = fields

    def get_neighbours(self, obj):
        return self.context.get("neighbours", {}).get(obj.id, [])

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Only the "mine" list supplies neighbours; other endpoints omit it.
        if "neighbours" not in self.context:
            data.pop("neighbours", None)
        return data

    def get_place(self, obj):
        data = place_brief(obj.place)
        # The booking's department (``Reservation.pool``), not the place's.
        data.update(kind=obj.place.kind, building=obj.place.room.floor.building_code,
                    pool=obj.pool_id)
        return data

    def get_holder_id(self, obj):
        return privacy.user_id_for(obj, obj.holder_id, viewer=self.viewer)

    def get_booked_by_id(self, obj):
        return privacy.user_id_for(obj, obj.booked_by_id, viewer=self.viewer)

    def get_comment(self, obj):
        return privacy.comment_for(obj, viewer=self.viewer)

    def get_release_reason(self, obj):
        return privacy.release_reason_for(obj, viewer=self.viewer)

    def get_day(self, obj):
        return hours.local_day_hours(obj.period)[0].isoformat()

    def get_start_hour(self, obj):
        return hours.local_day_hours(obj.period)[1]

    def get_end_hour(self, obj):
        return hours.local_day_hours(obj.period)[2]


class ManageReservationSerializer(ReservationSerializer):
    holder_name = serializers.SerializerMethodField()
    # The viewer's own reservation (they manage it as the holder).
    mine = serializers.SerializerMethodField()

    class Meta(ReservationSerializer.Meta):
        fields = ReservationSerializer.Meta.fields + ["holder_name", "mine"]

    def get_holder_name(self, obj):
        return privacy.holder_label(obj, viewer=self.viewer)

    def get_mine(self, obj) -> bool:
        return self.viewer is not None and obj.holder_id == self.viewer.pk


class BookRequestSerializer(serializers.Serializer):
    place_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200
    )
    day = serializers.DateField()
    last_day = serializers.DateField(required=False, allow_null=True)
    start_hour = serializers.IntegerField(min_value=0, max_value=24)
    end_hour = serializers.IntegerField(min_value=0, max_value=24)
    comment = serializers.CharField(max_length=200, required=False, allow_blank=True)
    holder_id = serializers.IntegerField(required=False, allow_null=True)


class BookDaysSerializer(serializers.Serializer):
    place_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=20
    )
    days = serializers.ListField(child=serializers.DateField(), min_length=1, max_length=366)
    start_hour = serializers.IntegerField(min_value=0, max_value=24)
    end_hour = serializers.IntegerField(min_value=0, max_value=24)
    comment = serializers.CharField(max_length=200, required=False, allow_blank=True)
    holder_id = serializers.IntegerField(required=False, allow_null=True)
    on_taken = serializers.ChoiceField(choices=["fail", "request"], default="fail")
    show_name = serializers.BooleanField(default=False)

    def validate_days(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Days must be unique.")
        return value

    def validate(self, attrs):
        if len(attrs["days"]) * len(set(attrs["place_ids"])) > 1000:
            raise serializers.ValidationError({"days": "Too many days and places."})
        return attrs


class SeriesRequestSerializer(serializers.Serializer):
    place_id = serializers.IntegerField()
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), min_length=1, max_length=7
    )
    start_hour = serializers.IntegerField(min_value=hours.FIRST_HOUR, max_value=hours.LAST_HOUR - 1)
    end_hour = serializers.IntegerField(min_value=hours.FIRST_HOUR + 1, max_value=hours.LAST_HOUR)
    valid_from = serializers.DateField()
    valid_until = serializers.DateField()
    comment = serializers.CharField(max_length=200, required=False, allow_blank=True)
    holder_id = serializers.IntegerField(required=False, allow_null=True)
    on_taken = serializers.ChoiceField(choices=["conflict", "request"], default="conflict")
    show_name = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["start_hour"] >= attrs["end_hour"]:
            raise serializers.ValidationError({"end_hour": "Must be after start_hour."})
        return attrs


class SeriesSerializer(ViewerMixin, serializers.ModelSerializer):
    place = serializers.SerializerMethodField()
    holder_id = serializers.SerializerMethodField()
    booked_by_id = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()

    class Meta:
        model = Series
        fields = [
            "id", "place", "weekdays", "start_hour", "end_hour", "valid_from",
            "valid_until", "comment", "holder_id", "booked_by_id", "cancelled_at",
        ]

    def get_place(self, obj):
        data = place_brief(obj.place)
        data.update(
            kind=obj.place.kind, building=obj.place.room.floor.building_code,
            pool=obj.place.pool_id,
        )
        return data

    def get_holder_id(self, obj):
        return privacy.series_user_id(obj, obj.holder_id, viewer=self.viewer)

    def get_booked_by_id(self, obj):
        return privacy.series_user_id(obj, obj.booked_by_id, viewer=self.viewer)

    def get_comment(self, obj):
        return obj.comment if privacy.series_user_id(obj, True, viewer=self.viewer) else ""


def series_result_data(result, *, viewer) -> dict:
    """JSON for a ``SeriesResult`` (created reservations and conflicts)."""
    from . import requests as requests_svc

    context = {"viewer": viewer}
    return {
        "series": SeriesSerializer(result.series, context=context).data,
        "created": ReservationSerializer(result.created, many=True, context=context).data,
        "conflicts": [
            {
                "day": c.day.isoformat(),
                "code": c.code,
                "alternatives": [place_brief(p) for p in c.alternatives],
            }
            for c in result.conflicts
        ],
        "requests": [
            requests_svc.serialize_release(r, viewer, perspective="requester")
            for r in result.requests
        ],
    }


class AbsenceSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    # The person entered it themselves (they may delete it in the app);
    # otherwise an assistant or admin did.
    self_entered = serializers.SerializerMethodField()

    class Meta:
        model = Absence
        fields = ["id", "user", "user_name", "start_date", "end_date", "self_entered", "created_at"]
        read_only_fields = ["id", "user", "user_name", "self_entered", "created_at"]

    def get_user_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.get_username()

    def get_self_entered(self, obj) -> bool:
        return obj.created_by_id == obj.user_id

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "End must not precede start."})
        if (attrs["end_date"] - attrs["start_date"]).days + 1 > 366:
            raise serializers.ValidationError({"end_date": "At most 366 days."})
        return attrs


class ManageAbsenceSerializer(AbsenceSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())

    class Meta(AbsenceSerializer.Meta):
        read_only_fields = ["id", "user_name", "created_at"]


class DisplaySerializer(serializers.ModelSerializer):
    """A paired door display as the management page lists it."""

    room = serializers.SerializerMethodField()

    class Meta:
        model = Display
        fields = [
            "id", "name", "panel", "room", "last_seen_at", "battery_mv", "firmware", "paired_at",
        ]
        read_only_fields = fields

    def get_room(self, display) -> dict | None:
        room = display.room
        if room is None:
            return None
        return {
            "id": room.pk, "name": room.name,
            "floor": room.floor.name, "building": room.floor.building_code,
        }
