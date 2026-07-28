# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Seed an Imprint placeholder and a Privacy draft.

Both are created **unpublished** so the placeholder/draft text never appears
live: an admin reviews and edits them (and ticks "published") before they show
in the footer. The privacy draft lists the personal data the system stores as a
starting point — it MUST be reviewed with the data protection officer and kept
in sync whenever the stored data changes.
"""
from django.db import migrations

IMPRINT_BODY = """\
> **Platzhalter – bitte ersetzen.** Dieses Impressum muss an die Vorgaben der
> Einrichtung angepasst und anschließend veröffentlicht werden.

## Angaben gemäß § 5 TMG / § 18 MStV

Universität Osnabrück
Anschrift
PLZ Ort

**Vertreten durch:** …

**Kontakt**
Telefon: …
E-Mail: …

**Verantwortlich für den Inhalt:** …
"""

PRIVACY_BODY = """\
> **Entwurf – nicht veröffentlichen, bevor die/der Datenschutzbeauftragte
> dies geprüft hat.** Dieser Text listet die im System gespeicherten
> personenbezogenen Daten auf und ist die Grundlage für die Datenschutz-
> erklärung. Er muss aktualisiert werden, sobald sich die gespeicherten Daten
> ändern.

## Welche personenbezogenen Daten werden gespeichert?

### Benutzerkonto
Beim Login über das zentrale Anmeldesystem (SSO/OIDC) werden gespeichert:

- **Benutzername**, **Vor- und Nachname**, **E-Mail-Adresse**
- ein stabiler **Identifikator** des Anmeldedienstes (OIDC „subject")
- die **Anmelde-Claims** des Identity Providers im Originalzustand (z. B.
  Gruppen-/Abteilungszugehörigkeit) – bei jeder Anmeldung aktualisiert
- bevorzugte **Sprache**
- Zeitpunkt der **Verifizierung** des Kontos
- ggf. **Sperrstatus** (befristet/dauerhaft) bei Regelverstößen

### Ausleihvorgänge (Buchungen)
- **Wer** (Bezug zum Benutzerkonto) **was**, in **welchem Pool**, **wann**
  ausleiht bzw. reserviert
- die **Buchungsnummer** und die Statuszeitpunkte (Ausgabe, Rückgabe,
  Ablauf der Reservierung)
- eine optionale **Nachricht an das Verleihteam** (Freitext, kann z. B. einen
  abholenden Namen enthalten)

### Erinnerungs-E-Mails
- ein **Versandprotokoll** für Überfälligkeits-Erinnerungen mit der
  **Empfänger-E-Mail-Adresse** und dem Versandzeitpunkt

### Rollen und Zugriff
- **Pool-Zuständigkeiten** (welche/r Mitarbeitende welchen Pool verwaltet)
- **Zugriffsgruppen** (manuelle Mitgliedschaft bzw. Zuordnung über
  Anmelde-Claims)

### Verwarnungen (Strikes)
- **Verwarnungen** mit **Begründung** (Freitext), **ausstellender Person**,
  Bezug zur betroffenen Buchung sowie Ausstellungs- und Ablaufdatum

### Technisch notwendige Daten
- **Sitzungsdaten** (Server-seitig, enthält die Benutzerkennung) zur
  Aufrechterhaltung der Anmeldung

### Was NICHT gespeichert wird
- keine Profilbilder oder von Nutzenden hochgeladene persönliche Dateien
- E-Mail-Benachrichtigungen werden versendet, aber ihr Inhalt wird – mit
  Ausnahme des oben genannten Versandprotokolls – nicht dauerhaft gespeichert

## Zweck, Rechtsgrundlage, Aufbewahrung, Rechte der Betroffenen
*(durch die/den Datenschutzbeauftragte/n zu ergänzen)*
"""


def seed_pages(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    Page.objects.get_or_create(
        slug="imprint",
        defaults={
            "title": "Impressum",
            "body": IMPRINT_BODY,
            "is_published": False,
            "show_in_footer": True,
            "footer_order": 10,
        },
    )
    Page.objects.get_or_create(
        slug="privacy",
        defaults={
            "title": "Datenschutz",
            "body": PRIVACY_BODY,
            "is_published": False,
            "show_in_footer": True,
            "footer_order": 20,
        },
    )


def unseed_pages(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    Page.objects.filter(slug__in=["imprint", "privacy"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0018_page"),
    ]

    operations = [
        migrations.RunPython(seed_pages, unseed_pages),
    ]
