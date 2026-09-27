# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Privacy-policy draft: the lender's confirmation note, and free texts in the
retention clause (#26, #38).

Since #26 the lender's optional note in a confirmation is stored on the
booking, and since #38 the anonymization also clears the booking free texts and
strike reasons. Each edit is applied only while the seeded wording is still
present, so an admin's own changes to the page are never overwritten
(idempotent; reversible).
"""
from django.db import migrations

# (anchor as seeded, replacement) — applied only if the anchor is present and
# the replacement isn't.
EDITS = [
    (
        "- eine optionale **Nachricht an das Verleihteam** (Freitext, kann z. B. einen\n"
        "  abholenden Namen enthalten)\n",
        "- eine optionale **Nachricht an das Verleihteam** (Freitext, kann z. B. einen\n"
        "  abholenden Namen enthalten)\n"
        "- eine optionale **Nachricht des Verleihteams** zur Bestätigung der\n"
        "  Reservierung (Freitext)\n",
    ),
    (
        "die\nbevorzugte Sprache, Verifizierungs- und Sperrinformationen sowie die\n"
        "Empfänger-Adresse in protokollierten Erinnerungs-E-Mails.",
        "die\nbevorzugte Sprache, Verifizierungs- und Sperrinformationen, die\n"
        "Empfänger-Adresse in protokollierten Erinnerungs-E-Mails sowie Freitexte zu\n"
        "Buchungen (Nachrichten) und die Begründungen von Verwarnungen.",
    ),
]

FIELDS = ("body", "body_de")


def _apply(page, pairs, *, forward):
    """Replace each anchor once. Forward skips pairs already applied (the new
    text of the first edit contains its anchor, so "anchor present" alone
    isn't enough); backward only needs the new text to be present."""
    changed = False
    for field in FIELDS:
        value = getattr(page, field, None)
        if not value:
            continue
        for anchor, replacement in pairs:
            if anchor not in value or (forward and replacement in value):
                continue
            value = value.replace(anchor, replacement, 1)
            changed = True
        setattr(page, field, value)
    if changed:
        page.save()


def add_free_texts(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page:
        _apply(page, EDITS, forward=True)


def remove_free_texts(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page:
        _apply(page, [(new, old) for old, new in EDITS], forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0045_notificationsetting_confirmation_send_time"),
    ]

    operations = [
        migrations.RunPython(add_free_texts, remove_free_texts),
    ]
