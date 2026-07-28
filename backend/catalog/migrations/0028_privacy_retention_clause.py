# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Add a retention/anonymization clause to the privacy-policy draft.

The data-retention feature anonymizes long-inactive accounts, so the privacy
template must describe it. Appended only if not already present, so an admin's
edits to the page are preserved (idempotent, never overwrites).
"""
from django.db import migrations

MARKER = "Aufbewahrungsfristen und Löschung inaktiver Konten"

RETENTION_CLAUSE = """

## Aufbewahrungsfristen und Löschung inaktiver Konten

Benutzerkonten, die über einen einstellbaren Zeitraum (standardmäßig **drei
Jahre**) nicht mehr verwendet wurden und **keine offenen Ausleihvorgänge** mehr
haben, werden automatisch **anonymisiert**. Dabei werden sämtliche
personenbezogenen Daten des Kontos gelöscht bzw. unkenntlich gemacht – darunter
Name, E-Mail-Adresse, der Anmelde-Identifikator und die Anmelde-Claims, die
bevorzugte Sprache, Verifizierungs- und Sperrinformationen sowie die
Empfänger-Adresse in protokollierten Erinnerungs-E-Mails.

Erhalten bleibt ausschließlich die nicht mehr personenbeziehbare **Historie**
der Geräte und Ausleihvorgänge; die betroffene Person erscheint dort nur noch
als neutraler Platzhalter („Gelöschter Nutzer"). Die Anonymisierung ist nicht
umkehrbar.
"""


def add_clause(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if not page:
        return
    for field in ("body", "body_de"):
        value = getattr(page, field, None)
        if value and MARKER not in value:
            setattr(page, field, value + RETENTION_CLAUSE)
    page.save()


def remove_clause(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if not page:
        return
    for field in ("body", "body_de"):
        value = getattr(page, field, None)
        if value and RETENTION_CLAUSE in value:
            setattr(page, field, value.replace(RETENTION_CLAUSE, ""))
    page.save()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0027_section_category_order_section_set_order"),
    ]

    operations = [
        migrations.RunPython(add_clause, remove_clause),
    ]
