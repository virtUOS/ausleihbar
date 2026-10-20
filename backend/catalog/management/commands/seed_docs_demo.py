# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Synthetic demo data for the website screenshots — docs database only.

Builds the data set of the website spec ("Screenshot pipeline"): fictional
users, three pools, sections/categories, product types with properties,
products and items, the "Interview-Set", and bookings relative to today in
every state the borrower and desk views show (incl. past returned loans for
the statistics), a blocked borrower, strikes, blocks and a multi-pool cart.

Refuses to run unless the database name ends with ``_docs``
(``common.docs_guard``), so the dev or production data is never touched.

Idempotent: the catalog structure and users are upserted by natural key; the
activity data (bookings, strikes, blocks, favourites, defects) is rebuilt on
every run, so dates always follow today. ``--reset`` wipes the app data first.

The last stdout line is a JSON summary the screenshot script navigates by:
``{"users": {...}, "pools": {...}, "categories": {...}, "products": {...},
"resources": {...}, "sets": {...}, "bookings": {label: code}}``.

Usage: python manage.py seed_docs_demo [--reset]
"""
import json
from datetime import date, datetime, time, timedelta

import holidays
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test.utils import override_settings
from django.utils import timezone, translation
from django.utils.text import slugify

from accounts import roles
from accounts.models import AccessGroup, Strike
from accounts.strikes import issue_strike
from catalog.inventory import default_qr_code_id
from catalog.models import (
    Category,
    Favorite,
    Product,
    ProductSet,
    ProductSetItem,
    ProductType,
    Resource,
    ResourceDefect,
    ResourcePool,
    Section,
)
from catalog.serializers import (
    clean_attribute_values,
    device_attributes,
    normalize_attribute,
    product_attributes,
)
from common.docs_guard import require_docs_database
from lending.models import Block, Booking, BookingItem, HolidaySetting
from lending.services import add_to_cart, create_reservation, mark_resource_defective

DAYS = Product.LendingType.DAYS
HOURS = Product.LendingType.HOURS
ONSITE = Product.UseType.ONSITE

USERS = [
    # username, first, last, extra
    ("alex", "Alex", "Beispiel", {"claims": {"eduPersonAffiliation": ["student"]}}),
    ("kim", "Kim", "Verleih", {"claims": {"eduPersonAffiliation": ["employee"]}}),
    ("sam", "Sam", "Admin", {"is_staff": True, "claims": {"eduPersonAffiliation": ["employee"]}}),
    ("robin", "Robin", "Gesperrt", {"claims": {"eduPersonAffiliation": ["student"]}}),
    ("jona", "Jona", "Muster", {"claims": {"eduPersonAffiliation": ["student"]}}),
    ("mika", "Mika", "Probe", {"claims": {"eduPersonAffiliation": ["student"]}}),
    ("lea", "Lea", "Lernfeld", {"claims": {"eduPersonAffiliation": ["faculty"]}}),
]
# Users named in the summary (the shot script logs in as these).
SUMMARY_USERS = ("alex", "kim", "sam", "robin")

_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _hours(start, end):
    """The same hours on every day (docs data: "today" always works, and
    every seeded hourly booking lies inside them)."""
    return {key: [[start, end]] for key in _WEEKDAY_KEYS}


POOLS = [
    {
        "pool_id": "MED",
        "name": "Medienlabor", "name_en": "Media Lab",
        "room": "Raum 1.12", "room_en": "Room 1.12",
        "address": "Beispielstraße 1\n49069 Osnabrück",
        "description": "<p>Kameras, Stative, Mikrofone und Schnittplätze für "
                       "Lehre, Studium und Projekte.</p>",
        "description_en": "<p>Cameras, tripods, microphones and editing "
                          "workstations for teaching, study and projects.</p>",
        "email": "medienlabor@example.org", "phone": "+49 541 000-1112",
        "accent_color": "amber",
        "opening_hours": _hours("09:00", "17:00"),
    },
    {
        "pool_id": "POD",
        "name": "Podcast-Studio", "name_en": "Podcast Studio",
        "room": "Raum 0.05", "room_en": "Room 0.05",
        "address": "Beispielstraße 1\n49069 Osnabrück",
        "description": "<p>Schallgedämmter Aufnahmeraum mit Mikrofonen und "
                       "Rekordern für Podcasts und Interviews.</p>",
        "description_en": "<p>Sound-proofed recording room with microphones and "
                          "recorders for podcasts and interviews.</p>",
        "email": "podcast@example.org", "phone": "+49 541 000-1005",
        "accent_color": "sky",
        "opening_hours": _hours("08:00", "20:00"),
    },
    {
        "pool_id": "MAK",
        "name": "Makerspace", "name_en": "Makerspace",
        "room": "Werkstatt 0.20", "room_en": "Workshop 0.20",
        "address": "Musterweg 7\n49074 Osnabrück",
        "description": "<p>3D-Drucker und Werkzeug für eigene Projekte – nach "
                       "einer Einweisung.</p>",
        "description_en": "<p>3D printers and tools for your own projects – "
                          "after an induction.</p>",
        "email": "makerspace@example.org", "phone": "+49 541 000-2020",
        "accent_color": "emerald",
        "opening_hours": _hours("09:00", "17:00"),
    },
]


def _attr(key, de, en, attr_type="short_text", scope="product", **extra):
    return normalize_attribute({
        "key": key, "label": {"de": de, "en": en}, "type": attr_type,
        "scope": scope, "visible": True, "required": False, "default": "", **extra,
    })


PRODUCT_TYPES = {
    "kamera": ("Kamera", "Camera", [
        _attr("sensor", "Sensor", "Sensor"),
        _attr("aufloesung", "Auflösung", "Resolution"),
        _attr("video", "Video", "Video"),
        _attr("letzte_wartung", "Letzte Wartung", "Last maintenance", "date", "device"),
    ]),
    "stativ": ("Stativ", "Tripod", [
        _attr("max_hoehe", "Max. Höhe (cm)", "Max. height (cm)", "number"),
        _attr("traglast", "Traglast", "Load capacity"),
    ]),
    "mikrofon": ("Mikrofon", "Microphone", [
        _attr("anschluss", "Anschluss", "Connector"),
        _attr("richtcharakteristik", "Richtcharakteristik", "Polar pattern"),
    ]),
    "rekorder": ("Audiorekorder", "Audio recorder", [
        _attr("spuren", "Spuren", "Tracks", "number"),
        _attr("speicher", "Speicher", "Storage"),
    ]),
    "raum": ("Raum", "Room", [
        _attr("plaetze", "Plätze", "Seats", "number"),
        _attr("ausstattung", "Ausstattung", "Equipment", "long_text"),
    ]),
    "arbeitsplatz": ("Arbeitsplatz", "Workstation", [
        _attr("software", "Software", "Software", "long_text"),
    ]),
    "drucker": ("3D-Drucker", "3D printer", [
        _attr("bauraum", "Bauraum", "Build volume"),
        _attr("material", "Material", "Material"),
        _attr("duese", "Düse", "Nozzle", scope="device"),
    ]),
}

# (section de, section en, [(top category de, en, desc de, [(child de, en)])])
NAVIGATION = [
    ("Medientechnik", "Media equipment", [
        ("Foto & Video", "Photo & video", "Kameras und Zubehör für Fotos und Filme.",
         [("Kameras", "Cameras"), ("Stative", "Tripods")]),
        ("Audio", "Audio", "Mikrofone und Rekorder für saubere Tonaufnahmen.",
         [("Mikrofone", "Microphones"), ("Aufnahmegeräte", "Recorders")]),
    ]),
    ("Räume & Arbeitsplätze", "Rooms & workspaces", [
        ("Studios", "Studios", "Räume und Arbeitsplätze zur Nutzung vor Ort.", []),
        ("Werkstatt", "Workshop", "Maschinen im Makerspace – mit Einweisung.", []),
    ]),
]


def _t(text):
    return {"de": text, "en": ""}


def _tt(de, en):
    return {"de": de, "en": en}


# slug key, data. ``units``: (pool_id, count). ``category``: leaf category name.
PRODUCTS = [
    ("sony-alpha-7-iv", {
        "title": "Sony Alpha 7 IV", "type": "kamera", "category": "Kameras",
        "lending_type": DAYS, "max_duration": 7,
        "short": ("Vollformat-Systemkamera für Foto und Video",
                  "Full-frame mirrorless camera for photo and video"),
        "description": ("<p>Vielseitige Vollformatkamera mit 33 Megapixeln und 4K-Video. "
                        "Ausgeliehen wird sie mit Standardzoom 28–70 mm, zwei Akkus, "
                        "Ladegerät und 128-GB-Speicherkarte.</p>",
                        "<p>Versatile full-frame camera with 33 megapixels and 4K video. "
                        "Comes with a 28–70 mm zoom, two batteries, a charger and a "
                        "128 GB memory card.</p>"),
        "return_info": "<p>Akkus, Ladegerät und Speicherkarte vollständig? "
                       "Objektiv und Sensor auf Staub prüfen.</p>",
        "attributes": {"sensor": _tt("Vollformat", "Full frame"), "aufloesung": _t("33 MP"),
                       "video": _t("4K 60p")},
        "units": ("MED", 3),
    }),
    ("canon-eos-r6-mark-ii", {
        "title": "Canon EOS R6 Mark II", "type": "kamera", "category": "Kameras",
        "lending_type": DAYS, "max_duration": 7,
        "short": ("Lichtstarke Kamera für Interviews und Reportagen",
                  "Low-light camera for interviews and reportage"),
        "description": ("<p>Spiegellose Vollformatkamera mit sehr gutem Autofokus – ideal "
                        "für Interviews bei wenig Licht. Mit RF 24–105 mm und zwei Akkus.</p>",
                        "<p>Mirrorless full-frame camera with excellent autofocus – ideal "
                        "for interviews in low light. With RF 24–105 mm and two batteries.</p>"),
        "attributes": {"sensor": _tt("Vollformat", "Full frame"), "aufloesung": _t("24 MP"),
                       "video": _t("4K 60p")},
        "units": ("MED", 2),
    }),
    ("gopro-hero12-black", {
        "title": "GoPro HERO12 Black", "type": "kamera", "category": "Kameras",
        "lending_type": HOURS, "max_duration": 8,
        "short": ("Action-Kamera, stundenweise buchbar", "Action camera, bookable by the hour"),
        "description": ("<p>Robuste Action-Kamera für Aufnahmen in Bewegung, wasserdicht bis "
                        "10 m. Mit Halterungen und Ersatzakku.</p>",
                        "<p>Rugged action camera for shots on the move, waterproof to "
                        "10 m. With mounts and a spare battery.</p>"),
        "attributes": {"sensor": _t("1/1,9\""), "aufloesung": _t("27 MP"), "video": _t("5,3K 60p")},
        "units": ("MED", 2),
    }),
    ("manfrotto-190-stativ", {
        "title": "Manfrotto 190 Stativ", "type": "stativ", "category": "Stative",
        "lending_type": DAYS, "max_duration": 14,
        "short": ("Stabiles Aluminium-Stativ mit Videokopf", "Sturdy aluminium tripod with video head"),
        "description": ("<p>Dreibeinstativ mit Fluid-Videokopf für ruhige Schwenks. "
                        "Inklusive Tragetasche.</p>",
                        "<p>Tripod with a fluid video head for smooth pans. "
                        "Carrying bag included.</p>"),
        "attributes": {"max_hoehe": 160, "traglast": _t("7 kg")},
        "units": ("MED", 4),
    }),
    ("rode-wireless-go-ii", {
        "title": "RØDE Wireless GO II", "type": "mikrofon", "category": "Mikrofone",
        "lending_type": DAYS, "max_duration": 7,
        "short": ("Funkstrecke mit zwei Ansteckmikrofonen", "Wireless kit with two clip-on mics"),
        "description": ("<p>Kompaktes Funkmikrofon-Set mit zwei Sendern und einem Empfänger – "
                        "für Interviews mit zwei Personen.</p>",
                        "<p>Compact wireless microphone kit with two transmitters and one "
                        "receiver – for interviews with two people.</p>"),
        "attributes": {"anschluss": _t("3,5 mm / USB-C"),
                       "richtcharakteristik": _tt("Kugel", "Omnidirectional")},
        "units": ("MED", 3),
    }),
    ("zoom-h6", {
        "title": "Zoom H6", "type": "rekorder", "category": "Aufnahmegeräte",
        "lending_type": DAYS, "max_duration": 7,
        "short": ("Mobiler Sechsspur-Rekorder", "Portable six-track recorder"),
        "description": ("<p>Handlicher Rekorder mit wechselbaren Mikrofonkapseln und vier "
                        "XLR-Eingängen. Mit SD-Karte und Windschutz.</p>",
                        "<p>Handy recorder with interchangeable microphone capsules and four "
                        "XLR inputs. With SD card and windscreen.</p>"),
        "attributes": {"spuren": 6, "speicher": _t("SD-Karte, 32 GB")},
        "units": ("MED", 2),
    }),
    ("videoschnittplatz", {
        "title": "Videoschnittplatz", "type": "arbeitsplatz", "category": "Studios",
        "lending_type": HOURS, "use_type": ONSITE, "requires_handout": False,
        "max_duration": 4,
        "short": ("Schnitt-PC im Medienlabor, Nutzung vor Ort", "Editing PC at the Media Lab, on site"),
        "description": ("<p>Leistungsstarker Rechner mit zwei Monitoren für Video- und "
                        "Tonschnitt. Du buchst ein Zeitfenster und arbeitest vor Ort.</p>",
                        "<p>Powerful computer with two monitors for video and audio editing. "
                        "Book a time slot and work on site.</p>"),
        "attributes": {"software": _tt("DaVinci Resolve, Audacity",
                                       "DaVinci Resolve, Audacity")},
        "units": ("MED", 2),
    }),
    ("podcast-raum", {
        "title": "Podcast-Raum", "title_en": "Podcast room", "type": "raum", "category": "Studios",
        "lending_type": HOURS, "use_type": ONSITE, "requires_handout": False,
        "min_duration": 1, "max_duration": 4,
        "short": ("Aufnahmeraum für bis zu vier Personen", "Recording room for up to four people"),
        "description": ("<p>Schallgedämmter Raum mit Tisch, vier Mikrofonen und Mischpult. "
                        "Die Tür öffnet sich zu deinem gebuchten Zeitfenster.</p>",
                        "<p>Sound-proofed room with a table, four microphones and a mixer. "
                        "The door opens for your booked time slot.</p>"),
        "attributes": {"plaetze": 4,
                       "ausstattung": _tt("4 Mikrofone, Mischpult, Kopfhörer, Akustikelemente",
                                          "4 microphones, mixer, headphones, acoustic panels")},
        "units": ("POD", 1),
    }),
    ("shure-sm7b", {
        "title": "Shure SM7B", "type": "mikrofon", "category": "Mikrofone",
        "lending_type": DAYS, "max_duration": 14,
        "short": ("Dynamisches Sprechermikrofon", "Dynamic broadcast microphone"),
        "description": ("<p>Klassisches Studiomikrofon für Sprache und Podcasts, unempfindlich "
                        "gegen Raumhall. Mit XLR-Kabel.</p>",
                        "<p>Classic studio microphone for speech and podcasts, robust against "
                        "room echo. With XLR cable.</p>"),
        "attributes": {"anschluss": _t("XLR"), "richtcharakteristik": _tt("Niere", "Cardioid")},
        "units": ("POD", 4),
    }),
    ("zoom-podtrak-p4", {
        "title": "Zoom PodTrak P4", "type": "rekorder", "category": "Aufnahmegeräte",
        "lending_type": DAYS, "max_duration": 7, "new": True,
        "short": ("Podcast-Rekorder für vier Mikrofone", "Podcast recorder for four microphones"),
        "description": ("<p>Kompakter Podcast-Rekorder mit vier Mikrofoneingängen, "
                        "Kopfhörerausgängen und Soundpads.</p>",
                        "<p>Compact podcast recorder with four microphone inputs, headphone "
                        "outputs and sound pads.</p>"),
        "attributes": {"spuren": 4, "speicher": _t("microSD, 32 GB")},
        "units": ("POD", 2),
    }),
    ("prusa-mk4", {
        "title": "Prusa MK4", "type": "drucker", "category": "Werkstatt",
        "lending_type": HOURS, "use_type": ONSITE, "requires_handout": True,
        "max_duration": 8,
        "short": ("3D-Drucker, Nutzung vor Ort mit Einweisung",
                  "3D printer, on-site use after an induction"),
        "description": ("<p>Zuverlässiger FDM-Drucker für PLA und PETG. Das Team gibt dir "
                        "den Drucker an der Theke frei und nimmt ihn nach dem Druck ab.</p>",
                        "<p>Reliable FDM printer for PLA and PETG. The team releases the "
                        "printer to you at the desk and checks it after printing.</p>"),
        "return_info": "<p>Druckplatte gereinigt? Filament ausgefahren und Reste entsorgt?</p>",
        "attributes": {"bauraum": _t("25 × 21 × 22 cm"), "material": _t("PLA, PETG")},
        "units": ("MAK", 2),
    }),
]

COMPLEMENTS = {
    "sony-alpha-7-iv": ["manfrotto-190-stativ", "rode-wireless-go-ii"],
    "shure-sm7b": ["zoom-podtrak-p4"],
}


class Command(BaseCommand):
    help = "Seed the synthetic website demo data (docs database only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Wipe the app data of the docs database first.",
        )

    def handle(self, *args, reset=False, **options):
        require_docs_database()
        # No mails from strikes/defects while seeding (console noise otherwise).
        with translation.override("de"), override_settings(
            EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend"
        ):
            with transaction.atomic():
                if reset:
                    self._wipe()
                summary = self._seed()
        self.stdout.write(
            f"Docs demo data ready: {len(summary['products'])} products, "
            f"{len(summary['bookings'])} labelled bookings."
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False))

    # ------------------------------------------------------------------ wipe

    def _wipe(self):
        """Delete the app data (keeps settings singletons, pages, superusers)."""
        Session.objects.all().delete()
        self._clear_activity()
        ProductSet.all_objects.all().delete()
        Resource.all_objects.all().delete()
        Product.all_objects.all().delete()
        while Category.all_objects.exists():
            Category.all_objects.filter(children__isnull=True).delete()
        Section.all_objects.all().delete()
        ProductType.all_objects.all().delete()
        AccessGroup.objects.filter(system_pool__isnull=True, system_admin=False).delete()
        ResourcePool.all_objects.all().delete()
        get_user_model().objects.filter(is_superuser=False).delete()
        roles.invalidate_cache()

    def _clear_activity(self):
        """Activity data, rebuilt on every run so its dates follow today."""
        Strike.objects.all().delete()
        BookingItem.objects.all().delete()
        Booking.objects.all().delete()
        Block.objects.all().delete()
        Favorite.objects.all().delete()
        ResourceDefect.objects.all().delete()

    # ------------------------------------------------------------------ seed

    def _seed(self):
        self.now = timezone.now()
        self.today = timezone.localdate()
        self.users = self._users()
        self.pools = self._pools()
        self._groups()
        self.types = self._product_types()
        self.categories, self.sections = self._navigation()
        self.products, self.units = self._products()
        self.product_set = self._set()

        self._clear_activity()
        self._reset_user_blocks()
        HolidaySetting.objects.update_or_create(pk=1, defaults={"country": "DE", "subdivision": "NI"})
        self._defect()
        self.bookings = {}
        self._history()
        self._current_bookings()
        self._cart()
        self._strikes()
        self._blocks()
        for slug in ("sony-alpha-7-iv", "shure-sm7b", "podcast-raum"):
            Favorite.objects.create(user=self.users["alex"], product=self.products[slug])
        roles.invalidate_cache()
        return self._summary()

    # ------------------------------------------------------------ dates

    def _day(self, offset):
        """``today + offset`` days on a weekday (Mon–Fri): weekend dates move
        away from today (forward for future, back for past). Today stays."""
        day = self.today + timedelta(days=offset)
        if offset == 0:
            return day
        step = 1 if offset > 0 else -1
        while day.weekday() >= 5:
            day += timedelta(days=step)
        return day

    def _at(self, day, hour, minute=0):
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def _days(self, first, last):
        """Full-day period [first 00:00, last+1 00:00) as day loans use."""
        return self._at(first, 0), self._at(last + timedelta(days=1), 0)

    # ------------------------------------------------------------ catalog

    @staticmethod
    def _upsert(manager, lookup, values):
        obj = manager.filter(**lookup).first()
        if obj is None:
            return manager.create(**lookup, **values)
        for field, value in values.items():
            setattr(obj, field, value)
        if hasattr(obj, "deleted_at"):
            obj.deleted_at = None
        obj.save()
        return obj

    def _users(self):
        User = get_user_model()
        users = {}
        for username, first, last, extra in USERS:
            user = self._upsert(User.objects, {"username": username}, {
                "first_name": first, "last_name": last,
                "email": f"{username}@example.org", "language": "de",
                "is_active": True, "is_staff": extra.get("is_staff", False),
                "claims": extra.get("claims", {}),
            })
            if user.has_usable_password() or not user.password:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            users[username] = user
        return users

    def _reset_user_blocks(self):
        get_user_model().objects.filter(pk__in=[u.pk for u in self.users.values()]).update(
            blocked_until=None, blocked_permanently=False
        )
        for user in self.users.values():
            user.refresh_from_db()

    def _pools(self):
        pools = {}
        for position, data in enumerate(POOLS):
            data = dict(data)
            pool_id = data.pop("pool_id")
            pools[pool_id] = self._upsert(ResourcePool.all_objects, {"pool_id": pool_id}, {
                **data, "closed_weekdays": [], "lead_time_hours": 0,
                "position": position, "is_active": True,
                "default_max_days": 14, "default_max_hours": 8,
            })
        return pools

    def _groups(self):
        kim = self.users["kim"]
        for pool_id in ("MED", "POD"):
            roles.ensure_pool_lender_group(self.pools[pool_id]).members.add(kim)
        roles.admin_group().members.add(self.users["sam"])
        teachers = self._upsert(AccessGroup.objects, {"name": "Lehrende"}, {
            "description": "Lehrende und Mitarbeitende mit Makerspace-Einweisung.",
            "claim_key": "eduPersonAffiliation",
            "claim_values": ["faculty", "employee"],
        })
        teachers.pools.set([self.pools["MAK"]])
        teachers.members.add(self.users["alex"])

    def _product_types(self):
        types = {}
        for key, (de, en, schema) in PRODUCT_TYPES.items():
            types[key] = self._upsert(ProductType.all_objects, {"name": de}, {
                "name_en": en, "attribute_schema": schema,
            })
        return types

    def _navigation(self):
        categories, sections = {}, {}
        for position, (title, title_en, tops) in enumerate(NAVIGATION):
            section = self._upsert(Section.all_objects, {"title": title}, {
                "title_en": title_en, "position": position,
            })
            sections[title] = section
            order = []
            for top_position, (name, name_en, desc, children) in enumerate(tops):
                top = self._upsert(
                    Category.all_objects, {"name": name, "parent": None},
                    {"name_en": name_en, "description": desc, "position": top_position},
                )
                categories[name] = top
                order.append(top.id)
                section.categories.add(top)
                for child_position, (child, child_en) in enumerate(children):
                    categories[child] = self._upsert(
                        Category.all_objects, {"name": child, "parent": top},
                        {"name_en": child_en, "position": child_position},
                    )
            section.category_order = order
            section.save(update_fields=["category_order"])
        return categories, sections

    def _products(self):
        products, units = {}, {}
        counters = {pool_id: 0 for pool_id in self.pools}
        for index, (slug, data) in enumerate(PRODUCTS):
            product_type = self.types[data["type"]]
            schema = product_type.attribute_schema
            attributes = clean_attribute_values(
                product_attributes(schema), data.get("attributes", {})
            )
            description_de, description_en = data["description"]
            short_de, short_en = data["short"]
            product = self._upsert(Product.all_objects, {"title": data["title"]}, {
                "title_en": data.get("title_en", data["title"]),
                "product_type": product_type,
                "lending_type": data["lending_type"],
                "use_type": data.get("use_type", Product.UseType.LOAN),
                "requires_handout": data.get("requires_handout", True),
                "min_duration": data.get("min_duration"),
                "max_duration": data.get("max_duration"),
                "short_description": short_de, "short_description_en": short_en,
                "description": description_de, "description_en": description_en,
                "return_info": data.get("return_info", ""),
                "attributes": attributes,
            })
            product.categories.set([self.categories[data["category"]]])
            products[slug] = product
            # Only one product counts as "new" in the shop (ShopSetting days).
            created = self.now - (timedelta(days=4) if data.get("new")
                                  else timedelta(days=60 + 7 * index))
            Product.all_objects.filter(pk=product.pk).update(created_at=created)

            pool_id, count = data["units"]
            pool = self.pools[pool_id]
            device_schema = device_attributes(schema)
            units[slug] = []
            for unit in range(1, count + 1):
                counters[pool_id] += 1
                number = f"{pool_id}-{counters[pool_id]:04d}"
                device_values = {}
                if any(a["key"] == "letzte_wartung" for a in device_schema):
                    device_values["letzte_wartung"] = (
                        self.today - timedelta(days=30 * unit + index)
                    ).isoformat()
                if any(a["key"] == "duese" for a in device_schema):
                    device_values["duese"] = _t("0,4 mm")
                resource = Resource.all_objects.filter(inventory_number=number).first()
                values = {
                    "product": product, "resource_pool": pool,
                    "status": Resource.Status.AVAILABLE, "defect_note": "",
                    "serial_number": f"SN-{pool_id}{index:02d}{unit:03d}",
                    "storage_location": f"Schrank {chr(64 + 1 + index % 4)}, Fach {unit}",
                    "procurement_date": date(self.today.year - 2, 1 + index % 12, 1 + unit),
                    "attributes": clean_attribute_values(device_schema, device_values),
                }
                if resource is None:
                    resource = Resource.objects.create(
                        inventory_number=number, qr_code_id=default_qr_code_id(number),
                        **values,
                    )
                else:
                    self._upsert(Resource.all_objects, {"pk": resource.pk}, values)
                    resource.refresh_from_db()
                units[slug].append(resource)
        for slug, complements in COMPLEMENTS.items():
            product = products[slug]
            product.complementary_products.set([products[c] for c in complements])
            product.complementary_order = [products[c].id for c in complements]
            product.save(update_fields=["complementary_order"])
        return products, units

    def _set(self):
        product_set = self._upsert(ProductSet.all_objects, {"name": "Interview-Set"}, {
            "name_en": "Interview kit",
            "resource_pool": self.pools["MED"],
            "description": "<p>Alles für ein Interview mit zwei Personen: Kamera, "
                           "Funkmikrofone und Stativ – zusammen gebucht und abgeholt.</p>",
            "description_en": "<p>Everything for an interview with two people: camera, "
                              "wireless microphones and tripod – booked and picked up "
                              "together.</p>",
        })
        ProductSetItem.objects.filter(product_set=product_set).delete()
        for position, slug in enumerate(
            ("canon-eos-r6-mark-ii", "rode-wireless-go-ii", "manfrotto-190-stativ")
        ):
            ProductSetItem.objects.create(
                product_set=product_set, product=self.products[slug], position=position
            )
        product_set.categories.set([self.categories["Foto & Video"]])
        section = self.sections["Medientechnik"]
        section.sets.add(product_set)
        section.set_order = [product_set.id]
        section.save(update_fields=["set_order"])
        return product_set

    # ------------------------------------------------------------ activity

    def _defect(self):
        """One long-standing defect (desk "Defekte" view)."""
        resource = self.units["sony-alpha-7-iv"][2]
        mark_resource_defective(resource, note="Sucher zeigt Pixelfehler, Reparatur angefragt.")
        ResourceDefect.objects.filter(resource=resource).update(
            created_at=self.now - timedelta(days=24)
        )

    def _book(self, label, borrower, items, state, created_days_ago=2, note=""):
        """Create a booking in ``state`` (pending / confirmed / handed_out /
        returned / cancelled) with ``items`` = [(resource, start, end)]."""
        booking = create_reservation(self.users[borrower], items)
        if note:
            booking.note = note
            booking.save(update_fields=["note"])
        if state != "pending" and state != "cancelled":
            booking.confirm()
        if state == "cancelled":
            booking.cancel()
        if state in ("handed_out", "returned"):
            booking.hand_out_items()
            handed = max(items[0][1], self._at(timezone.localtime(items[0][1]).date(), 9, 40))
            booking.items.update(handed_out_at=handed)
        created = self.now - timedelta(days=created_days_ago)
        Booking.objects.filter(pk=booking.pk).update(
            created_at=created,
            confirmed_at=created + timedelta(hours=3) if booking.confirmed_at else None,
        )
        booking.refresh_from_db()
        if label:
            self.bookings[label] = booking.code
        return booking

    def _return(self, booking, returned_at):
        booking.return_items()
        booking.items.update(returned_at=returned_at)

    def _history(self):
        """Past returned loans so the statistics are not empty (some late)."""
        loans = [
            "sony-alpha-7-iv", "rode-wireless-go-ii", "manfrotto-190-stativ",
            "shure-sm7b", "canon-eos-r6-mark-ii", "gopro-hero12-black", "zoom-h6",
            "zoom-podtrak-p4",
        ]
        borrowers = ["jona", "mika", "lea", "alex", "robin"]
        self.history = {}
        for i in range(28):
            slug = loans[i % len(loans)]
            product = self.products[slug]
            units = self.units[slug]
            resource = units[i % min(len(units), 2)]
            first = self._day(-(9 + i * 4))
            late = i % 4 == 0
            if product.lending_type == HOURS:
                start, end = self._at(first, 10), self._at(first, 13)
                returned = end + (timedelta(minutes=50) if late else timedelta(minutes=-10))
            else:
                last = first + timedelta(days=1 + i % 3)
                start, end = self._days(first, last)
                returned = (end + timedelta(hours=11)) if late else self._at(last, 15, 30)
            borrower = borrowers[i % len(borrowers)]
            booking = self._book(None, borrower, [(resource, start, end)], "handed_out",
                                 created_days_ago=(self.today - first).days + 5)
            self._return(booking, returned)
            if late:
                self.history.setdefault(borrower, []).append(booking)
        # Alex's own returned loan, easy to find in "Meine Buchungen".
        canon = self.units["canon-eos-r6-mark-ii"][0]
        booking = self._book("alex_returned", "alex",
                             [(canon, *self._days(self._day(-20), self._day(-17)))],
                             "handed_out", created_days_ago=25,
                             note="Dreh für das Seminar Dokumentarfilm")
        self._return(booking, self._at(self._day(-17), 14, 10))

    def _current_bookings(self):
        today = self.today
        u = self.units
        # --- Alex: one booking per state -----------------------------------
        self._book("alex_pending", "alex",
                   [(u["sony-alpha-7-iv"][0], *self._days(self._day(7), self._day(9)))],
                   "pending", created_days_ago=0,
                   note="Für das Seminar Medienpraxis")
        self._book("alex_pickup_today", "alex",
                   [(u["zoom-h6"][0], *self._days(today, self._day(2)))], "confirmed",
                   created_days_ago=3)
        self._book("alex_return_today", "alex",
                   [(u["rode-wireless-go-ii"][0], *self._days(self._day(-3), today))],
                   "handed_out", created_days_ago=6)
        self._book("alex_overdue", "alex",
                   [(u["manfrotto-190-stativ"][0], *self._days(self._day(-6), self._day(-2)))],
                   "handed_out", created_days_ago=9)
        gopro_day = self._day(3)
        self._book("alex_cancelled", "alex",
                   [(u["gopro-hero12-black"][0], self._at(gopro_day, 10), self._at(gopro_day, 13))],
                   "cancelled", created_days_ago=4)
        self._book("alex_onsite_today", "alex",
                   [(u["podcast-raum"][0], self._at(today, 10), self._at(today, 12))],
                   "confirmed", created_days_ago=2)
        # --- other borrowers: desk lists -----------------------------------
        self._book("jona_pickup_today", "jona",
                   [(u["sony-alpha-7-iv"][1], *self._days(today, self._day(2)))], "confirmed",
                   created_days_ago=4)
        self._book("mika_return_today", "mika",
                   [(u["shure-sm7b"][1], *self._days(self._day(-4), today))], "handed_out",
                   created_days_ago=8)
        self._book("lea_pending", "lea",
                   [(u["canon-eos-r6-mark-ii"][1], *self._days(self._day(3), self._day(5)))],
                   "pending", created_days_ago=1,
                   note="Aufnahmen für die Vorlesung Mediengestaltung")
        missed = self._book("jona_missed_pickup", "jona",
                            [(u["shure-sm7b"][0], *self._days(self._day(-2), self._day(1)))],
                            "confirmed", created_days_ago=5)
        self.bookings["strike_target"] = missed.code
        set_first, set_last = self._day(5), self._day(6)
        self._book("mika_multi_item", "mika", [
            (u["canon-eos-r6-mark-ii"][0], *self._days(set_first, set_last)),
            (u["rode-wireless-go-ii"][1], *self._days(set_first, set_last)),
            (u["manfrotto-190-stativ"][1], *self._days(set_first, set_last)),
        ], "confirmed", created_days_ago=2, note="Interview für das Campusradio")
        self._book("lea_onsite_today", "lea",
                   [(u["videoschnittplatz"][0], self._at(today, 13), self._at(today, 17))],
                   "confirmed", created_days_ago=1)
        self._book("lea_makerspace_today", "lea",
                   [(u["prusa-mk4"][0], self._at(today, 13), self._at(today, 16))],
                   "confirmed", created_days_ago=2)
        tomorrow = self._day(1)
        self._book("jona_gopro", "jona",
                   [(u["gopro-hero12-black"][1], self._at(tomorrow, 9), self._at(tomorrow, 12))],
                   "confirmed", created_days_ago=1)
        self._book("jona_podcast", "jona",
                   [(u["podcast-raum"][0], self._at(tomorrow, 9), self._at(tomorrow, 11))],
                   "confirmed", created_days_ago=1)
        self._book("mika_podcast", "mika",
                   [(u["podcast-raum"][0], self._at(tomorrow, 14), self._at(tomorrow, 16))],
                   "confirmed", created_days_ago=1)

    def _cart(self):
        """Alex's current cart: one item each from Medienlabor and Podcast-Studio."""
        alex = self.users["alex"]
        start, end = self._days(self._day(12), self._day(14))
        add_to_cart(alex, self.products["sony-alpha-7-iv"], start, end)
        cart = add_to_cart(alex, self.products["shure-sm7b"], start, end)
        # Outlive a full screenshot run (the default hold is 30 minutes).
        Booking.objects.filter(pk=cart.pk).update(expires_at=self.now + timedelta(hours=3))
        self.bookings["alex_cart"] = cart.code

    def _strikes(self):
        kim = self.users["kim"]
        jona_late = self.history.get("jona", [None])[0]
        issue_strike(self.users["jona"], "Rückgabe einen Tag zu spät.", kim, booking=jona_late)
        robin_late = self.history.get("robin", [])
        reasons = [
            "Reservierung nicht abgeholt.",
            "Rückgabe einen Tag zu spät.",
            "Zubehör unvollständig zurückgegeben (Ladegerät fehlte).",
        ]
        for index, reason in enumerate(reasons):
            booking = robin_late[index] if index < len(robin_late) else None
            issue_strike(self.users["robin"], reason, kim, booking=booking)
        Strike.objects.filter(user=self.users["robin"]).update(
            created_at=self.now - timedelta(days=2)
        )

    def _blocks(self):
        """A public holiday (system-wide) and a pool closure, both after every
        seeded future booking so nothing collides with them."""
        start_from = self.today + timedelta(days=30)
        calendar = holidays.country_holidays(
            "DE", subdiv="NI", years=[start_from.year, start_from.year + 1], language="de"
        )
        upcoming = sorted(d for d in calendar if d >= start_from)[:2]
        for day in upcoming:
            Block.objects.create(
                period=self._days_range(day, day), reason=calendar.get(day),
            )
        closure = self._day(21)
        Block.objects.create(
            period=self._days_range(closure, closure + timedelta(days=1)),
            reason="Inventur", resource_pool=self.pools["MED"],
        )
        # A closed weekday soon, so the product calendar's first months show a
        # blocked day — on a day no seeded Medienlabor booking touches.
        outing = self._free_pool_weekday(self.pools["MED"], 10, 18)
        Block.objects.create(
            period=self._days_range(outing, outing),
            reason="Betriebsausflug", resource_pool=self.pools["MED"],
        )

    def _free_pool_weekday(self, pool, first_offset, last_offset):
        """The first Mon–Fri in ``today + [first_offset, last_offset]`` days on
        which no booking item (any state) of ``pool`` overlaps."""
        for offset in range(first_offset, last_offset + 1):
            day = self.today + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            taken = BookingItem.objects.filter(
                resource__resource_pool=pool, period__overlap=self._days_range(day, day)
            ).exists()
            if not taken:
                return day
        return self._day(last_offset)

    def _days_range(self, first, last):
        return DateTimeTZRange(*self._days(first, last))

    # ------------------------------------------------------------ summary

    def _summary(self):
        return {
            "users": {name: self.users[name].id for name in SUMMARY_USERS},
            "pools": {slugify(p.name_de or p.name): p.id for p in self.pools.values()},
            "categories": {slugify(name): c.id for name, c in self.categories.items()},
            "products": {slug: p.id for slug, p in self.products.items()},
            "resources": {
                r.inventory_number: {"id": r.id, "qr": r.qr_code_id}
                for units in self.units.values() for r in units
            },
            "sets": {"interview-set": self.product_set.id},
            "bookings": dict(self.bookings),
        }
