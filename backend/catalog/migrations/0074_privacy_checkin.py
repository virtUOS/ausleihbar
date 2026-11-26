# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Privacy-policy draft: item check-in and item door signs (ADR-0023, #271/#272).

Bookings now store when they were submitted and when each position was added;
items with check-in also store the check-in time or the automatic release of
an unstarted reservation. Door signs at single items publicly show the
reservation times and the booking number, never a name. Each edit is applied
only while the seeded wording is still present, so an admin's own changes to
the page are never overwritten (idempotent; reversible).
"""
import re

from django.db import migrations

# (anchor as seeded, replacement) — applied only if the anchor is present and
# the replacement isn't.
EDITS = [
    (
        "(Ausgabe, Rückgabe, Ablauf der Reservierung)",
        "(Absenden der Buchung, Hinzufügen einzelner Positionen, Ausgabe, Rückgabe,\n"
        "Ablauf der Reservierung)",
    ),
    (
        "zur Bestätigung der Reservierung (Freitext)</li>\n",
        "zur Bestätigung der Reservierung (Freitext)</li>\n"
        "<li>bei Gegenständen mit <strong>Check-in</strong> (z. B. 3D-Drucker zur "
        "Nutzung vor Ort): der Zeitpunkt des <strong>Check-ins</strong> bzw. der "
        "<strong>automatischen Freigabe</strong>, wenn eine Reservierung nicht "
        "rechtzeitig begonnen wurde („Nicht wahrgenommen“)</li>\n",
    ),
    (
        "<h3>Technisch notwendige Daten</h3>",
        "<h3>Türschilder an Gegenständen</h3>\n"
        "<ul>\n"
        "<li>Elektronische Schilder an einzelnen Gegenständen zeigen öffentlich "
        "lesbar, ob der Gegenstand frei, reserviert oder in Benutzung ist, die "
        "<strong>Zeiten</strong> der laufenden und der nächsten Reservierungen des "
        "Tages sowie die <strong>Buchungsnummer</strong>. <strong>Namen</strong> "
        "werden dort <strong>nie</strong> angezeigt; über die Buchungsnummer allein "
        "können Dritte keine weiteren Daten abrufen.</li>\n"
        "</ul>\n"
        "<h3>Technisch notwendige Daten</h3>",
    ),
]

FIELDS = ("body", "body_de")


def _pattern(text):
    """``text`` as a regex that matches any whitespace run where it has one:
    fresh installs keep the seed's line wraps (``Rückgabe,\n  Ablauf``),
    pages saved through the editor have single spaces."""
    return re.compile(r"\s+".join(re.escape(word) for word in text.split()))


def _apply(page, pairs, *, forward):
    """Replace each anchor once. Forward skips pairs already applied (a
    replacement may contain its anchor); backward needs the new text."""
    changed = False
    for field in FIELDS:
        value = getattr(page, field, None)
        if not value:
            continue
        for anchor, replacement in pairs:
            match = _pattern(anchor).search(value)
            if match is None or (forward and _pattern(replacement).search(value)):
                continue
            # The match ends before the anchor's trailing newline, which stays
            # in place, so the replacement's own trailing newline is dropped.
            new = replacement.rstrip("\n")
            value = value[: match.start()] + new + value[match.end():]
            changed = True
        setattr(page, field, value)
    if changed:
        page.save()


def add_checkin(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page:
        _apply(page, EDITS, forward=True)


def remove_checkin(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page:
        _apply(page, [(new, old) for old, new in EDITS], forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0073_product_checkin_release_minutes_and_more"),
    ]

    operations = [
        migrations.RunPython(add_checkin, remove_checkin),
    ]
