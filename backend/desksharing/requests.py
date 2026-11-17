# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Swap and release requests between reservation holders.

- **Swap**: two reservations of one local day with overlapping periods
  exchange their places once the other holder accepts. Both holders must be
  allowed to book the other place and each place must be free for the other
  reservation's period.
- **Release request**: ask a holder to hand over the rest of a reservation.
  On acceptance the holder's reservation is released from the current full
  hour and the requester gets the same place until the original end.
  A request with ``wanted_period`` (booked days) instead hands over the
  holder's whole reservation and books the requester for the wanted hours,
  under the requester's booking limits; if that fails nothing changes, the
  request expires and the requester is told.

Privacy: payloads and notification contexts never carry the requester's name
(release requests only with ``show_name``), and a hidden desk holder's name is
never shown to the person asking.

Open requests expire (lazily on read/answer and in ``desks_tick``) when a
swapped reservation starts, a released reservation ends or a reservation is
no longer active.
"""
import logging
import uuid

from django.db import IntegrityError, OperationalError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Q
from django.utils import timezone

from . import booking, cycles, hours, notify, privacy, rights
from .booking import BookingError
from .models import ReleaseRequest, Reservation, SwapRequest
from .serializers import place_brief

logger = logging.getLogger(__name__)

OPEN = SwapRequest.Status.OPEN
ACTIVE = Reservation.Status.ACTIVE


def _now(now):
    return now or timezone.now()


def _send_after_commit(user, event: str, context: dict) -> None:
    """Notify once the surrounding transaction committed; a failing
    notification never breaks the request."""
    if user is None:
        return

    def send():
        try:
            notify.notify(user, event, context)
        except Exception:
            logger.exception("Notification %s failed for user %s", event, user.pk)

    transaction.on_commit(send)


def _brief(res, *, hide_id: bool = False) -> dict:
    """Neutral description of a reservation (no holder). ``hide_id`` drops
    the reservation id (a hidden requester's reservation, see
    ``serialize_swap``)."""
    day, start_hour, end_hour = hours.local_day_hours(res.period)
    place = res.place
    data = place_brief(place)
    data.update(kind=place.kind, building=place.room.floor.building_code)
    return {
        "id": None if hide_id else res.pk,
        "place": data,
        "day": day.isoformat(),
        "start_hour": start_hour,
        "end_hour": end_hour,
    }


def _reservation(pk):
    return Reservation.objects.select_related("place__room__floor__pool", "place__room__floor__building", "holder").get(pk=pk)


def _lock_reservations(*pks) -> dict:
    rows = (
        Reservation.objects.select_for_update(of=("self",))
        .select_related("place__room__floor__pool", "place__room__floor__building", "holder")
        .filter(pk__in=pks)
        .order_by("pk")
    )
    return {r.pk: r for r in rows}


# Expiry -------------------------------------------------------------------


def _stale_swap_q(now):
    return (
        Q(from_reservation__period__startswith__lte=now)
        | Q(to_reservation__period__startswith__lte=now)
        | ~Q(from_reservation__status=ACTIVE)
        | ~Q(to_reservation__status=ACTIVE)
    )


def _stale_release_q(now):
    # Legacy ("rest of the reservation") requests end with the reservation,
    # wanted ones when the wanted hours begin.
    return (
        Q(wanted_period__isnull=True, reservation__period__endswith__lte=now)
        | Q(wanted_period__isnull=False, wanted_period__startswith__lte=now)
        | ~Q(reservation__status=ACTIVE)
    )


def expire_requests(now=None) -> int:
    """Expire open requests whose reservations started (swap) / ended
    (release) or are no longer active. Returns the number expired."""
    now = _now(now)
    swap_ids = list(SwapRequest.objects.filter(status=OPEN).filter(_stale_swap_q(now)).values_list("pk", flat=True))
    release_ids = list(
        ReleaseRequest.objects.filter(status=OPEN).filter(_stale_release_q(now)).values_list("pk", flat=True)
    )
    expired = SwapRequest.objects.filter(pk__in=swap_ids, status=OPEN).update(
        status=SwapRequest.Status.EXPIRED
    )
    expired += ReleaseRequest.objects.filter(pk__in=release_ids, status=OPEN).update(
        status=ReleaseRequest.Status.EXPIRED
    )
    return expired


def _supersede(reservation_ids, *, keep_swap=None) -> None:
    """Expire open swap requests touching these reservations (their places
    changed or the reservation went away)."""
    qs = SwapRequest.objects.filter(status=OPEN).filter(
        Q(from_reservation_id__in=reservation_ids) | Q(to_reservation_id__in=reservation_ids)
    )
    if keep_swap is not None:
        qs = qs.exclude(pk=keep_swap)
    qs.update(status=SwapRequest.Status.EXPIRED)


def _expired_error() -> BookingError:
    return BookingError("expired", detail="This request has expired.")


# Swap ---------------------------------------------------------------------


def _check_swap(a, b, now, *, exclude=()) -> None:
    """Validate swapping the places of ``a`` (requester's) and ``b``."""
    if a.holder_id is None or b.holder_id is None or a.holder_id == b.holder_id:
        raise BookingError("not_allowed", detail="You cannot swap with yourself.")
    for res in (a, b):
        if res.status != ACTIVE or res.period.lower <= now:
            raise BookingError("not_allowed", detail="This reservation has already started.")
    if a.place.kind != b.place.kind:
        raise BookingError("kind_mismatch", detail="Only places of the same kind can be swapped.")
    day_a, _, _ = hours.local_day_hours(a.period)
    day_b, _, _ = hours.local_day_hours(b.period)
    if day_a != day_b or not (a.period.lower < b.period.upper and b.period.lower < a.period.upper):
        raise BookingError("not_allowed", detail="The reservations must overlap on one day.")
    for res, new_place, new_holder in ((a, b.place, a.holder), (b, a.place, b.holder)):
        if not new_place.is_bookable or not rights.can_book_place(new_holder, new_place):
            raise BookingError("not_allowed", detail="This place cannot be booked.")
        if booking._is_fixed_for_others(new_place, new_holder, res.period):
            raise BookingError("taken", detail="This place is assigned to someone else.")
        day, start_hour, end_hour = hours.local_day_hours(res.period)
        booking._check_hours(new_place.pool, day, start_hour, end_hour)
        if (
            Reservation.objects.filter(
                place=new_place, status=ACTIVE, period__overlap=res.period
            )
            .exclude(pk__in=[a.pk, b.pk, *exclude])
            .exists()
        ):
            raise BookingError("taken", detail="A place is not free for that time.")


def request_swap(*, user, mine: Reservation, theirs: Reservation, now=None) -> SwapRequest:
    now = _now(now)
    mine, theirs = _reservation(mine.pk), _reservation(theirs.pk)
    if mine.holder_id != user.pk:
        raise BookingError("not_allowed", detail="This is not your reservation.")
    if theirs.holder_id == user.pk:
        raise BookingError("not_allowed", detail="You cannot request your own reservation.")
    _check_swap(mine, theirs, now)
    with transaction.atomic():
        # Serialise concurrent requests for the same reservation.
        _lock_reservations(mine.pk)
        if SwapRequest.objects.filter(
            status=OPEN, from_reservation=mine, to_reservation=theirs
        ).exists():
            raise BookingError("duplicate_request", detail="You already have an open request.")
        req = SwapRequest.objects.create(from_reservation=mine, to_reservation=theirs)
        _send_after_commit(
            theirs.holder,
            notify.SWAP_REQUEST,
            {
                "request_id": req.pk,
                "offered": _brief(mine, hide_id=privacy.is_hidden(mine)),
                "own": _brief(theirs),
            },
        )
    return req


def _swap_places(a, b) -> None:
    """Exchange the places of two active reservations without ever violating
    the exclusion constraint: ``a`` steps out of it while ``b`` moves."""
    place_a, place_b = a.place_id, b.place_id
    Reservation.objects.filter(pk=a.pk).update(status=Reservation.Status.CANCELLED)
    Reservation.objects.filter(pk=b.pk).update(
        place_id=place_a, owner_use=a.place.fixed_owner_id == b.holder_id
    )
    Reservation.objects.filter(pk=a.pk).update(
        place_id=place_b, status=ACTIVE, owner_use=b.place.fixed_owner_id == a.holder_id
    )


def answer_swap(req: SwapRequest, *, user, accept: bool, now=None) -> SwapRequest:
    now = _now(now)
    expired = False
    try:
        with transaction.atomic():
            req = SwapRequest.objects.select_for_update().get(pk=req.pk)
            if req.status != OPEN:
                raise BookingError("not_open", detail="This request has been answered.")
            ids = (req.from_reservation_id, req.to_reservation_id)
            seen = dict(Reservation.objects.filter(pk__in=ids).values_list("pk", "place_id"))
            booking._lock_places(seen.values())
            rows = _lock_reservations(*ids)
            a, b = rows[ids[0]], rows[ids[1]]
            if (a.place_id, b.place_id) != (seen[ids[0]], seen[ids[1]]):
                raise BookingError("taken", detail="A reservation was moved meanwhile.")
            if b.holder_id != user.pk:
                raise BookingError("not_allowed", detail="This request is not addressed to you.")
            if (
                a.status != ACTIVE or b.status != ACTIVE
                or a.period.lower <= now or b.period.lower <= now
            ):
                req.status = SwapRequest.Status.EXPIRED
                req.save(update_fields=["status"])
                expired = True
            elif not accept:
                req.status = SwapRequest.Status.DECLINED
                req.save(update_fields=["status"])
            else:
                _check_swap(a, b, now)
                a_brief_before, b_brief_before = _brief(a), _brief(b)
                _swap_places(a, b)
                req.status = SwapRequest.Status.ACCEPTED
                req.save(update_fields=["status"])
                _supersede([a.pk, b.pk], keep_swap=req.pk)
                a = _reservation(a.pk)
                _send_after_commit(
                    a.holder,
                    notify.SWAP_ANSWER,
                    {"request_id": req.pk, "accepted": True,
                     "reservation": _brief(a), "previous": a_brief_before},
                )
            if not expired and not accept:
                _send_after_commit(
                    a.holder, notify.SWAP_ANSWER,
                    {"request_id": req.pk, "accepted": False, "reservation": _brief(a)},
                )
    except (IntegrityError, OperationalError) as exc:
        if not booking._is_conflict(exc):
            raise
        raise BookingError("taken", detail="A place was booked at the same time.") from None
    if expired:
        raise _expired_error()
    return req


# Release requests ---------------------------------------------------------


def _requester_check(requester, reservation, period) -> None:
    place = reservation.place
    if not requester.is_active or not place.is_bookable or not rights.can_book_place(requester, place):
        raise BookingError("not_allowed", detail="You may not book this place.")
    if booking._is_fixed_for_others(place, requester, period):
        raise BookingError("taken", detail="This place is assigned to someone else.")


def request_release(*, user, reservation: Reservation, show_name: bool = False, now=None) -> ReleaseRequest:
    now = _now(now)
    reservation = _reservation(reservation.pk)
    if reservation.holder_id is None or reservation.holder_id == user.pk:
        raise BookingError("not_allowed", detail="You cannot request your own reservation.")
    if reservation.status != ACTIVE or reservation.period.upper <= now:
        raise BookingError("not_allowed", detail="This reservation is over.")
    _requester_check(user, reservation, reservation.period)
    with transaction.atomic():
        _lock_reservations(reservation.pk)
        if ReleaseRequest.objects.filter(status=OPEN, reservation=reservation, requester=user).exists():
            raise BookingError("duplicate_request", detail="You already have an open request.")
        req = ReleaseRequest.objects.create(
            reservation=reservation, requester=user, show_name=bool(show_name)
        )
        context = {"request_id": req.pk, "reservation": _brief(reservation)}
        if req.show_name:
            context["requester_name"] = privacy.display_name(user)
        _send_after_commit(reservation.holder, notify.RELEASE_REQUEST, context)
    return req


def create_batch(
    *, requester, slots, start_hour: int, end_hour: int, show_name: bool, batch: uuid.UUID,
    series=None,
) -> list[ReleaseRequest]:
    """One release request per slot (``slot.blocker`` is asked for the wanted
    hours of ``slot.day``) and one mail per blocking holder. Call inside the
    caller's transaction, under the requester's lock. A blocker that changed
    meanwhile or an already open request of the requester refuses the whole
    batch. ``series``: the series whose dates these are (an accepted request
    becomes one of its occurrences)."""
    ids = [s.blocker.pk for s in slots]
    blockers = _lock_reservations(*ids)
    if ReleaseRequest.objects.filter(
        status=OPEN, reservation_id__in=ids, requester=requester
    ).exists():
        raise BookingError("duplicate_request", detail="You already have an open request.")
    created = []
    by_holder: dict[int, tuple] = {}
    for slot in slots:
        wanted = hours.local_range(slot.day, start_hour, end_hour)
        res = blockers.get(slot.blocker.pk)
        if (
            res is None or res.status != ACTIVE or res.holder_id is None
            or not (res.period.lower < wanted.upper and wanted.lower < res.period.upper)
        ):
            raise BookingError("taken", detail="A reservation changed meanwhile.")
        created.append(ReleaseRequest.objects.create(
            reservation=res, requester=requester, show_name=bool(show_name),
            wanted_period=wanted, batch=batch, series=series,
        ))
        by_holder.setdefault(res.holder_id, (res.holder, [], []))
        by_holder[res.holder_id][1].append(created[-1].pk)
        by_holder[res.holder_id][2].append(_brief(res))
    for holder, request_ids, briefs in by_holder.values():
        context = {"request_ids": request_ids, "reservations": briefs}
        if show_name:
            context["requester_name"] = privacy.display_name(requester)
        _send_after_commit(holder, notify.RELEASE_REQUEST, context)
    return created


def _cut_time(res, now):
    """Start of the handed-over part: the reservation start, or the current
    full hour once it has begun."""
    if res.period.lower > now:
        return res.period.lower
    return timezone.localtime(now, hours.TZ).replace(minute=0, second=0, microsecond=0)


def _request_brief(req, res) -> dict:
    """The reservation as the requester asked for it: wanted hours if set."""
    data = _brief(res)
    if req.wanted_period is not None:
        day, start_hour, end_hour = hours.local_day_hours(req.wanted_period)
        data.update(day=day.isoformat(), start_hour=start_hour, end_hour=end_hour)
    return data


def _ends_at(req, res):
    """When an open request expires: wanted ones when the wanted hours begin."""
    return req.wanted_period.lower if req.wanted_period is not None else res.period.upper


def _hand_over(req, res, now) -> None:
    """Release the holder's whole reservation and book the requester for the
    wanted hours. Raises ``BookingError`` (or a conflict) when the place or
    the requester's limits no longer allow it."""
    requester = req.requester
    wanted = req.wanted_period
    _requester_check(requester, res, wanted)
    day, start_hour, end_hour = hours.local_day_hours(wanted)
    booking._check_hours(res.place.pool, day, start_hour, end_hour)
    cycles.check_limits(
        actor=requester, holder=requester, places=[res.place],
        slots=[(day, res.place_id)], exclude_request_id=req.pk,
    )
    res.status = Reservation.Status.RELEASED
    res.released_at = max(now, res.period.lower)
    res.release_reason = Reservation.ReleaseReason.REQUEST
    res.save(update_fields=["status", "released_at", "release_reason"])
    # A series' date joins the series (as if booked with it), unless the
    # series ended meanwhile.
    series = req.series if req.series_id and not req.series.cancelled_at else None
    new = Reservation.objects.create(
        place=res.place, holder=requester,
        booked_by=(series.booked_by or requester) if series else requester,
        holder_hidden=privacy.snapshot_hidden(requester, res.place),
        group=uuid.uuid4(), period=wanted,
        series=series, comment=series.comment if series else "",
    )
    req.status = ReleaseRequest.Status.ACCEPTED
    req.result = new
    req.save(update_fields=["status", "result"])
    ReleaseRequest.objects.filter(reservation=res, status=OPEN).exclude(pk=req.pk).update(
        status=ReleaseRequest.Status.EXPIRED
    )
    _supersede([res.pk])
    _send_after_commit(
        requester, notify.RELEASE_ANSWER,
        {"request_id": req.pk, "accepted": True, "reservation": _brief(_reservation(new.pk))},
    )


def _handover_failed(pk) -> BookingError:
    """After a rolled-back handover: expire the request and tell the requester."""
    with transaction.atomic():
        req = ReleaseRequest.objects.select_for_update().get(pk=pk)
        if req.status == OPEN:
            req.status = ReleaseRequest.Status.EXPIRED
            req.save(update_fields=["status"])
            _send_after_commit(
                req.requester, notify.RELEASE_ANSWER,
                {"request_id": req.pk, "accepted": False, "failed": True,
                 "reservation": _request_brief(req, _reservation(req.reservation_id))},
            )
    return BookingError(
        "handover_failed", detail="The request could not be completed. Nothing was changed."
    )


def _accept_wanted(req: ReleaseRequest, *, user, now) -> ReleaseRequest:
    expired = handing_over = False
    try:
        with transaction.atomic():
            # Lock order as for bookings: holder (the requester), place,
            # reservation.
            booking._lock_holder(req.requester)
            req = ReleaseRequest.objects.select_for_update().get(pk=req.pk)
            if req.status != OPEN:
                raise BookingError("not_open", detail="This request has been answered.")
            seen_place = Reservation.objects.values_list("place_id", flat=True).get(
                pk=req.reservation_id
            )
            booking._lock_places([seen_place])
            res = _lock_reservations(req.reservation_id)[req.reservation_id]
            if res.place_id != seen_place:
                raise BookingError("taken", detail="The reservation was moved meanwhile.")
            if res.holder_id != user.pk:
                raise BookingError("not_allowed", detail="This request is not addressed to you.")
            if res.status != ACTIVE or _ends_at(req, res) <= now:
                req.status = ReleaseRequest.Status.EXPIRED
                req.save(update_fields=["status"])
                expired = True
            else:
                handing_over = True
                _hand_over(req, res, now)
    except BookingError:
        if not handing_over:
            raise
        raise _handover_failed(req.pk) from None
    except (IntegrityError, OperationalError) as exc:
        if not booking._is_conflict(exc):
            raise
        if not handing_over:
            raise BookingError("taken", detail="The place was booked at the same time.") from None
        raise _handover_failed(req.pk) from None
    if expired:
        raise _expired_error()
    return req


def answer_release(req: ReleaseRequest, *, user, accept: bool, now=None) -> ReleaseRequest:
    now = _now(now)
    if accept and req.wanted_period is not None:
        return _accept_wanted(req, user=user, now=now)
    expired = False
    try:
        with transaction.atomic():
            req = ReleaseRequest.objects.select_for_update().get(pk=req.pk)
            if req.status != OPEN:
                raise BookingError("not_open", detail="This request has been answered.")
            seen_place = Reservation.objects.values_list("place_id", flat=True).get(
                pk=req.reservation_id
            )
            booking._lock_places([seen_place])
            res = _lock_reservations(req.reservation_id)[req.reservation_id]
            if res.place_id != seen_place:
                raise BookingError("taken", detail="The reservation was moved meanwhile.")
            if res.holder_id != user.pk:
                raise BookingError("not_allowed", detail="This request is not addressed to you.")
            if res.status != ACTIVE or _ends_at(req, res) <= now:
                req.status = ReleaseRequest.Status.EXPIRED
                req.save(update_fields=["status"])
                expired = True
            elif not accept:
                req.status = ReleaseRequest.Status.DECLINED
                req.save(update_fields=["status"])
                _send_after_commit(
                    req.requester, notify.RELEASE_ANSWER,
                    {"request_id": req.pk, "accepted": False, "reservation": _request_brief(req, res)},
                )
            else:
                cut = _cut_time(res, now)
                new_period = DateTimeTZRange(cut, res.period.upper)
                requester = req.requester
                _requester_check(requester, res, new_period)
                day, start_hour, end_hour = hours.local_day_hours(new_period)
                booking._check_hours(res.place.pool, day, start_hour, end_hour)
                res.status = Reservation.Status.RELEASED
                # The release takes effect at the handover point, so released
                # hours equal the rebooked hours (statistics).
                res.released_at = max(cut, res.period.lower)
                res.release_reason = Reservation.ReleaseReason.REQUEST
                res.save(update_fields=["status", "released_at", "release_reason"])
                new = Reservation.objects.create(
                    place=res.place, holder=requester, booked_by=requester,
                    holder_hidden=privacy.snapshot_hidden(requester, res.place),
                    group=uuid.uuid4(), period=new_period,
                    # Grace counts from the handover, not the past full hour.
                    late_until=now if cut < now else None,
                )
                req.status = ReleaseRequest.Status.ACCEPTED
                req.save(update_fields=["status"])
                ReleaseRequest.objects.filter(reservation=res, status=OPEN).exclude(pk=req.pk).update(
                    status=ReleaseRequest.Status.EXPIRED
                )
                _supersede([res.pk])
                new = _reservation(new.pk)
                _send_after_commit(
                    requester, notify.RELEASE_ANSWER,
                    {"request_id": req.pk, "accepted": True, "reservation": _brief(new)},
                )
    except (IntegrityError, OperationalError) as exc:
        if not booking._is_conflict(exc):
            raise
        raise BookingError("taken", detail="The place was booked at the same time.") from None
    if expired:
        raise _expired_error()
    return req


def answer_release_batch(batch: uuid.UUID, *, user, accept: bool, now=None) -> dict:
    """Answer every open request of ``batch`` addressed to ``user``, each in
    its own transaction; one that cannot be completed does not stop the rest."""
    done, failed = [], []
    reqs = ReleaseRequest.objects.filter(
        batch=batch, status=OPEN, reservation__holder=user
    ).order_by("pk")
    for req in reqs:
        try:
            answer_release(req, user=user, accept=accept, now=now)
        except BookingError:
            failed.append(req.pk)
        else:
            done.append(req.pk)
    return {"done": done, "failed": failed}


def withdraw_release(req: ReleaseRequest, *, user) -> ReleaseRequest:
    with transaction.atomic():
        req = ReleaseRequest.objects.select_for_update().get(pk=req.pk)
        if req.requester_id != user.pk:
            raise BookingError("not_allowed", detail="This is not your request.")
        if req.status != OPEN:
            raise BookingError("not_open", detail="This request has been answered.")
        req.status = ReleaseRequest.Status.WITHDRAWN
        req.save(update_fields=["status"])
    return req


def withdraw_batch(batch: uuid.UUID, *, user) -> int:
    """Withdraw the requester's open requests of ``batch``; returns the count."""
    return ReleaseRequest.objects.filter(batch=batch, requester=user, status=OPEN).update(
        status=ReleaseRequest.Status.WITHDRAWN
    )


# Payloads -----------------------------------------------------------------


def serialize_swap(req: SwapRequest, viewer) -> dict:
    mine_side = req.from_reservation.holder_id == viewer.pk
    data = {
        "id": req.pk,
        "type": "swap",
        "status": req.status,
        "created_at": req.created_at,
    }
    if mine_side:
        data.update(
            own=_brief(req.from_reservation),
            other=_brief(req.to_reservation),
            other_holder_name=privacy.holder_label(req.to_reservation, viewer=viewer),
        )
    else:
        # Incoming: the requester stays anonymous; a hidden requester's
        # reservation id is withheld, too.
        offered = req.from_reservation
        data.update(
            own=_brief(req.to_reservation),
            other=_brief(offered, hide_id=privacy.is_hidden(offered)),
        )
    return data


def serialize_release(req: ReleaseRequest, viewer, *, perspective: str | None = None) -> dict:
    """``perspective="requester"`` renders the outgoing view although
    ``viewer`` is not the requester (an assistant booking for the requester)."""
    data = {
        "id": req.pk,
        "type": "release",
        "status": req.status,
        "created_at": req.created_at,
        "show_name": req.show_name,
        "batch": str(req.batch) if req.batch else None,
        "wanted": None,
    }
    if req.wanted_period is not None:
        day, start_hour, end_hour = hours.local_day_hours(req.wanted_period)
        data["wanted"] = {"day": day.isoformat(), "start_hour": start_hour, "end_hour": end_hour}
    if perspective == "requester" or req.requester_id == viewer.pk:
        data.update(
            other=_brief(req.reservation),
            other_holder_name=privacy.holder_label(req.reservation, viewer=viewer),
        )
    else:
        data["own"] = _brief(req.reservation)
        data["requester_name"] = privacy.display_name(req.requester) if req.show_name else None
    return data


def requests_for(user, now=None) -> dict:
    """Open incoming and outgoing requests of ``user`` (expiring stale ones first)."""
    expire_requests(now)
    swap_qs = SwapRequest.objects.filter(status=OPEN).select_related(
        "from_reservation__place__room__floor", "from_reservation__holder",
        "to_reservation__place__room__floor", "to_reservation__holder",
    )
    release_qs = ReleaseRequest.objects.filter(status=OPEN).select_related(
        "reservation__place__room__floor", "reservation__holder", "requester",
    )
    return {
        "incoming": [
            *(serialize_swap(r, user) for r in swap_qs.filter(to_reservation__holder=user)),
            *(serialize_release(r, user) for r in release_qs.filter(reservation__holder=user)),
        ],
        "outgoing": [
            *(serialize_swap(r, user) for r in swap_qs.filter(from_reservation__holder=user)),
            *(serialize_release(r, user) for r in release_qs.filter(requester=user)),
        ],
    }
