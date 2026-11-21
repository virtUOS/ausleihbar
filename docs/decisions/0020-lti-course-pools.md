# 0020. LTI-Kurspools: persönliche Pools für LMS-Kurse

- **Status:** Accepted
- **Date:** 2026-11-21

## Context
Lehrende besitzen Gegenstände, die sie an die Teilnehmenden ihrer Kurse
verleihen wollen – über mehrere Kurse und Semester (im LMS meist ein Kurs pro
Semester). Für ältere Kurse wollen sie den Zugriff wieder entziehen. Ausleihbar
wird dazu ein LTI-1.3-Tool: wer das Tool aus einem verknüpften Kurs öffnet, darf
den Pool sehen und buchen. Rechte hängen in Ausleihbar an Zugriffsgruppen
(ADR-0007, ADR-0012); ein Pool ohne Gruppe ist für alle Angemeldeten offen
(§3.4). Ein zweiter Rechtepfad neben den Gruppen sollte vermieden werden.

## Decision
- **Persönlicher Pool** = normaler `ResourcePool` mit `is_personal` und
  `owner` (FK, null bei normalen Pools; `SET_NULL`, nur Anzeige und
  Bearbeitungsrecht). Der Besitzer ist Verleihender des Pools und darf nur
  dessen Einstellungen ändern (feste Feldliste); Aktivstatus, Pool-ID,
  Gruppen, Anlegen und Löschen bleiben Admins vorbehalten.
- **Eine Kursverknüpfung** (`lti.LtiCourseLink`: Plattform, Kurs, Pool,
  aktiv) besitzt **genau eine systemverwaltete Zugriffsgruppe**
  (`AccessGroup.system_course`). Sie ist nicht löschbar und nur in der
  Beschreibung bearbeitbar, nie `is_admin`, nie `lender_pools`, nie
  Claim-Regel (Modell, Serializer und DB-Constraint). Ein Start aus dem Kurs
  trägt Lernende dort ein; die Gruppe hängt am Pool, solange die Verknüpfung
  aktiv ist. Ausschalten löst sie vom Pool und behält die Mitglieder.
- **Kursgruppen öffnen oder schließen keinen Pool.** Sie gewähren nur
  Zugriff über den Mitgliedspfad. Ob ein Pool eingeschränkt ist, entscheiden
  nur gewöhnliche Gruppen (`accounts.eligibility.eligible_pool_ids`): ein
  offener Pool bleibt mit Kursverknüpfung offen, und das Ausschalten der
  letzten Verknüpfung macht keinen Pool plötzlich offen.
- **Persönliche Pools sind immer eingeschränkt** (`is_personal`, auch wenn der
  Besitzer gelöscht ist), auch ohne
  Gruppe. Dasselbe gilt für Desksharing: Kursgruppen zählen dort weder als
  Pool-Gruppe noch als Mitgliedschaft.
- **Selbstbedienung beim Anlegen hinter einem Admin-Schalter, Standard aus**
  (`LtiSetting.instructors_create_pools`). Aus: ein Admin legt den Pool an
  und macht die Person zur Verleihenden; Lehrende verknüpfen nur Kurse.
- **Gemeinsamer DB-Cache für den Launch-Zustand.** pylti1p3 hält State, Nonce
  und Launch-Daten im Cache; ein Prozess-Cache (LocMem) verliert sie bei
  mehreren gunicorn-Workern. `default` ist daher ein `DatabaseCache`
  (Tabelle `django_cache`, Migration `lti/0002`); Launch-Daten leben 300 s,
  `lti_purge_cache` (Cron) löscht abgelaufene Zeilen. Die
  Admin-Drosselungen nutzen weiter einen eigenen LocMem-Alias (`throttle`),
  weil sie ein atomares `incr()` brauchen.
- **LMS-Claims greifen nie auf Claim-Regeln.** Für LTI-Konten
  (`subject` `lti:…`) liefert `idp_claims` leer; sonst könnte eine Plattform
  über einen frei wählbaren Claim (z. B. `email`) Verleihrechte erzeugen. Ein
  per E-Mail mit einem OIDC-Konto verknüpftes Konto behält dessen IdP-Claims.
  Ein Start macht nie jemanden zum Verleihenden oder Admin, außer der
  Lehrperson, die bei eingeschaltetem Schalter ihren eigenen Pool anlegt.
- **Hand-off-Token für Starts im iframe.** Das Buchungs-UI gehört nicht in den
  LMS-Frame (empfohlen: „neues Fenster“). Wird dennoch im Frame gestartet,
  führt der Button „In Ausleihbar öffnen“ über einen einmaligen, 120 s
  gültigen Token (`/lti/continue/<token>/`, im DB-Cache, beim Einlösen
  gelöscht) in einen neuen Tab und meldet dort an – unabhängig von
  Drittanbieter-Cookies. Nur lokale Ziele sind erlaubt. `SESSION_COOKIE_SAMESITE=None`
  bleibt eine bewusste Ausnahme.
- Lernende eines nicht oder nur inaktiv verknüpften Kurses erhalten kein Konto.

## Consequences
- Ein Rechtepfad (Zugriffsgruppen); alle bestehenden Prüfungen funktionieren
  unverändert. Dafür kennt `eligible_pool_ids` die Ausnahme „Kursgruppen
  zählen nicht“, ebenso Desksharing, Gruppenlisten, Benutzerverwaltung und
  Pool-Formular (Kursgruppen werden dort ausgefiltert).
- Die Offenheit eines Pools bleibt **implizit** („keine gewöhnliche Gruppe =
  offen“). Geplant ist als Folge eine eigene Gruppe **„Alle Angemeldeten“**,
  die Offenheit ausdrücklich macht; dann entfällt die Sonderregel für
  Kursgruppen und persönliche Pools.
- Neue gespeicherte personenbezogene Daten: LTI-Kontoverknüpfung
  (Plattform-Subject), Kurstitel, Kursgruppen-Mitglieder, Launch-Daten und
  Tokens im Cache bis zur Bereinigung – die handgeschriebene
  Datenschutzseite ist zu prüfen.
- Betrieb: Backend-Image neu bauen (neue Abhängigkeit `basicbar-lti`), Caddy
  `/lti/*` an das Backend, `lti_purge_cache` täglich einplanen
  (`docs/INSTALL.md` §6.3).
- Ein Besitzer verliert seine Rechte am Pool, wenn er nicht mehr Verleihender
  ist; den Besitzer setzen Admins nur im Django-Admin.
- Das ZIP-Export/-Import trägt weder Besitzer noch Kursverknüpfungen.
- Kein Deep Linking, keine Noten, keine Teilnehmerlisten-Synchronisation:
  Mitglied wird man nur durch einen Start; der Zugriff endet, wenn keine
  aktive Verknüpfung mehr besteht. Bestehende Buchungen bleiben.

## Alternatives considered
- **Eigene LTI-Berechtigungstabelle** in `accounts.eligibility`: zweiter
  Rechtepfad, den jede Prüfung kennen müsste – verworfen.
- **Pool-Anlegen immer selbst** oder **nur durch Admins**: zu offen bzw. zu
  schwerfällig; gewählt wurde der Admin-Schalter (Standard aus).
- **Kursgruppen zählen als normale Pool-Gruppe:** ein offener Pool würde mit
  der ersten Verknüpfung für alle anderen geschlossen und mit dem Ausschalten
  wieder offen – verworfen.
- **Session-Cookie `SameSite=None` als Standard** für Frame-Starts: weitet die
  Cookie-Exposition aus; der Hand-off-Token braucht das nicht.
