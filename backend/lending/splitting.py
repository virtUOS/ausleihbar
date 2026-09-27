# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Split legacy multi-pool reservations into one per pool (#26).

Takes model classes so the data migration can pass historical models. Uses no
model methods: status roll-up and codes are computed here.
"""
import uuid

CART, PENDING, CONFIRMED, HANDED_OUT, RETURNED, CANCELLED = (
    "cart", "pending", "confirmed", "handed_out", "returned", "cancelled",
)


def _rolled_up(original_status, states):
    if states and all(returned for _, returned in states):
        return RETURNED
    if any(out and not returned for out, returned in states):
        return HANDED_OUT
    if original_status in (HANDED_OUT, RETURNED):
        return CONFIRMED
    return original_status


def split_multi_pool_bookings(Booking, BookingItem, ResourcePool):
    """Backfill ``resource_pool`` and split multi-pool bookings (#26).

    Single-pool bookings just get ``resource_pool`` set; a single-pool
    booking that is already confirmed/handed-out/returned also gets
    ``confirmed_at``/``confirmation_mailed_at`` stamped (to its
    ``updated_at``) so the confirmation-mail command never mails it.

    A multi-pool booking is split into one booking per pool, linked by a
    fresh ``checkout_id``: the first pool (by pool position/name/id) keeps
    the original booking (its id, code and anything FK'd to it, e.g.
    strikes); every further pool gets a new booking with a freshly assigned
    code. Each split part's status is rolled up from its own items' handout/
    return state, and already-settled parts are stamped so they aren't
    (re)mailed either.

    Returns the number of new bookings created.
    """
    manager = getattr(ResourcePool, "all_objects", ResourcePool._base_manager)
    pool_rank = {
        pid: i for i, pid in enumerate(
            manager.order_by("position", "name", "id").values_list("id", flat=True)
        )
    }
    created = 0
    for booking in Booking.objects.exclude(status=CART).iterator():
        items = list(BookingItem.objects.filter(booking_id=booking.id)
                     .values_list("id", "resource__resource_pool_id", "handed_out_at", "returned_at"))
        pools = sorted({row[1] for row in items}, key=lambda p: pool_rank.get(p, 10**9))
        if not pools:
            continue
        confirmed_like = {CONFIRMED, HANDED_OUT, RETURNED}
        if len(pools) == 1:
            update_fields = {"resource_pool_id": pools[0]}
            if booking.status in confirmed_like:
                update_fields["confirmed_at"] = booking.updated_at
                update_fields["confirmation_mailed_at"] = booking.updated_at
            Booking.objects.filter(id=booking.id).update(**update_fields)
            continue
        checkout_id = uuid.uuid4()
        for index, pool_id in enumerate(pools):
            own = [r for r in items if r[1] == pool_id]
            status = _rolled_up(booking.status, [(r[2], r[3]) for r in own])
            stamp = booking.updated_at if status in confirmed_like else None
            if index == 0:
                Booking.objects.filter(id=booking.id).update(
                    resource_pool_id=pool_id, checkout_id=checkout_id, status=status,
                    confirmed_at=stamp, confirmation_mailed_at=stamp,
                )
                continue
            new = Booking.objects.create(
                borrower_id=booking.borrower_id, status=status, note=booking.note,
                expires_at=booking.expires_at, overdue_reminded_at=booking.overdue_reminded_at,
                resource_pool_id=pool_id, checkout_id=checkout_id,
                confirmed_at=stamp, confirmation_mailed_at=stamp,
            )
            Booking.objects.filter(id=new.id).update(
                code=f"R-{new.id:05d}", created_at=booking.created_at,
            )
            BookingItem.objects.filter(id__in=[r[0] for r in own]).update(booking_id=new.id)
            created += 1
    return created
