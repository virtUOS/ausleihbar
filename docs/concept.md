# Konzept — Ausleihbar (Raum- und Geräteverleih)

Strukturierte Fassung der Anforderungen. Die ursprüngliche, über längere Zeit
gewachsene Version ist im Git-Verlauf (Commit `ec89952`) erhalten. Begriffe und
Rollen sind hier vereinheitlicht; die zugrunde liegenden Entscheidungen und
offene Punkte stehen in `docs/concept-review.md`. Mit ⚠️ markierte Stellen sind
**interpretierte Auflösungen, die noch zu bestätigen sind**.

> Sprachregelung: **Ressource**, **Produkt**, **Produkttyp**, **Set**,
> **Sparte**, **Ressourcenpool**; Rollen **Ausleihende**,
> **Verleihende**, **Admin**; Buchungs-Flow **Warenkorb → Buchung
> (unbestätigt → bestätigt)**.

---

## 1. Domänenmodell

### 1.1 Begriffe und Beziehungen
- **Ressource** — ein konkretes Exemplar (Gerät *oder* Raum/ortsfestes Gerät
  wie 3D-Drucker, Laser), das es genau einmal gibt.
- **Produkt** — Katalog-Eintrag; eine Gruppe gleichartiger Ressourcen.
- **Produkttyp** — Vorlage für die Eigenschaften eines Produkts
  (z. B. Raum, Kamera, 3D-Drucker) und zugleich die **mittlere Gliederungsebene**
  des Katalogs: Er fasst Produkte mit ähnlicher Funktion zusammen (z. B.
  Videokameras) und hat Bild, Beschreibung und Reihenfolge.
- **Set** — eine geordnete **Liste von Produkten mit Anzahl** (z. B. 2 ×
  Stativ), die sinnvollerweise gemeinsam ausgeliehen werden. Ein Set wird aus
  genau **einem Pool** verliehen und hat Bild und Beschreibung (formatiert).
- **Sparte** — Gruppe inhaltlich zusammengehöriger Produkttypen (z. B.
  Aufzeichnungstechnik). Die frühere Ebene „Kategorie" entfällt (ADR 0010).
- **Ressourcenpool** — Sammlung von Ressourcen mit identischem Ausgabepunkt,
  verwaltet von derselben Gruppe Verleihender.
- **Ausleihart** — *stundenweise* oder *tagesweise*.

Beziehungen:
- Eine Ressource gehört zu **genau einem** Produkt und **genau einem**
  Ressourcenpool.
- Ein Produkt gehört zu **genau einem** Produkttyp; ein Produkttyp kann in
  mehreren Sparten liegen. Gliederung: Sparte → Produkttyp → Produkt.
- Ein Ressourcenpool kann beliebig viele Sparten, Produkttypen, Produkte und
  Ressourcen enthalten.

### 1.2 Produkttyp
Definiert eine Liste dynamischer Eigenschaften. Je Eigenschaft:
- **Key** (Name) und **Value-Typ**: Kurztext, Langtext, Datum, Zeit, Zahl, URL,
  Audio/Video/PDF (als URL), Bild.
- **Default-Wert** (optional).
- **sichtbar** (Boolean) — wird Ausleihenden angezeigt.
- **Pflichtfeld** (Boolean) — muss beim Anlegen eines Produkts gesetzt werden.

Ein Produkttyp legt außerdem fest: **Bild** und **Beschreibung** (optional),
die **Sparten**, in denen er erscheint, seine **Reihenfolge** (auch die seiner
Produkte) sowie die **Ausleihart** (am Produkt überschreibbar).

### 1.3 Produkt
- Titel, Beschreibung (optional), Bild (optional)
- zugehöriger **Produkttyp** (inkl. dessen Eigenschaftswerten)
- **Ausleihart** (vom Produkttyp geerbt, überschreibbar)
- minimale/maximale Ausleihdauer (optional, s. §3.2)
- **Pufferzeit** zwischen zwei Ausleihen desselben Geräts (Tage/Stunden, z. B.
  zum Prüfen, Laden, Reinigen; nicht bei der Direktausleihe) — nicht zu
  verwechseln mit der Vorlaufzeit des Pools (§1.5)

### 1.4 Ressource
- **Inventarnummer** — eindeutig, **menschenlesbar und pool-bezogen** (laufende
  Nummer innerhalb des Pools, z. B. `DigiLab-001`; keine UUID, nicht systemweit
  fortlaufend). Beim Anlegen vorgeschlagen, editierbar; genaues Schema pro Pool.
- eindeutiger **QR-Code**
- zugehöriges **Produkt** und zugehöriger **Ressourcenpool**
- **Status**: `ausleihbar`, `gesperrt`, `defekt`, `ausgemustert`
- Lagerplatz (optional)
- Beschaffungsdatum, Garantieende, Wert (je optional)
- beschaffende Einrichtung, zugehörige Einrichtung (je optional)
- **Ausleihhistorie** inkl. künftiger Buchungen
- Ausleihart sowie min./max. Ausleihzeit (je optional, überschreiben das Produkt)

### 1.5 Ressourcenpool (maßgebliche Attributliste — R1)
- Bezeichnung, Pool-ID, Beschreibung (optional)
- Standort, Bild (optional), Wegbeschreibung (optional)
- Telefonnummer (optional), E-Mail-Adresse
- **Öffnungszeiten** inkl. definierbarer Pausen
- **Vorlaufzeit** (Stunden): so lange vor der Abholung muss spätestens gebucht
  werden (nicht bei der Direktausleihe an der Theke)
- min./max. **Default-Ausleihdauer** (je für stunden- und tagesweise)
- Liste der **Verleihenden**, die den Pool verwalten
- **Berechtigung** der Ausleihenden (s. §3.4): Kriterien (OIDC/Shibboleth-Claims)
  ⚠️ (C5) und/oder explizite Allowlist
- enthält Ressourcen, Produkte, Produkttypen, Sparten
- aktiv/inaktiv schaltbar

### 1.6 Sparte / Produkttyp
- **Sparte**: Titel, Beschreibung (optional), Bild (optional), geordnete Liste von
  Produkttypen
- **Produkttyp**: Name, Beschreibung (optional), Bild (optional), manuelle
  Reihenfolge, geordnete Liste seiner Produkte, zugeordnete Sparten (Eigenschaften
  s. §1.2)

---

## 2. Rollen & Berechtigungen

Rollen sind **nicht exklusiv** — Verleihende und Admins können zugleich
Ausleihende sein, auch in fremden Pools.

- **Ausleihende** — anmelden, Ressourcen ausleihen.
- **Verleihende** — verwalten einen oder mehrere Ressourcenpools, geben
  Ressourcen aus und nehmen sie zurück, legen Pools und Ressourcen an, vergeben
  Strikes (mit Begründung), verifizieren selbstregistrierte Ausleihende.
  Verleihende sind die (manuellen oder per Claim ermittelten) Mitglieder von
  Gruppen, deren „Verleiher für Pools" den Pool enthält; jeder Pool
  hat dafür eine Systemgruppe „Verleiher ‹Pool›".
- **Admin** — Vollzugriff über alle Pools und Tenants. Admin ist, wer das
  Systemrecht (`is_staff`/`is_superuser`, auch über die OIDC-Gruppenzuordnung)
  hat oder **manuelles** Mitglied einer Admin-Gruppe (z. B. „Administratoren")
  ist; Claims vergeben nie Admin-Rechte. Nur Admins können: Accounts zu
  Admins hochstufen und Gruppen mit Rechten pflegen, Accounts löschen, Strikes
  löschen, Tenants anlegen.

Rechte kommen damit aus **Zugriffsgruppen** (siehe ADR-0012): eine Gruppe kann
Pools freigeben (§3.4), Verleiher-Rechte für Pools und/oder Admin-Rechte
vergeben.

---

## 3. Übergreifende Konzepte

### 3.1 Online-Shop-Charakter
Das System funktioniert wie ein Onlineshop: Warenbestand nach Produkttypen,
Produktauswahl, Warenkorb. Ein Produkt ist ausleihbar, solange zum gewünschten
Zeitpunkt mindestens eine Ressource verfügbar ist. Verfügbarkeit kann auch auf
Ebene von Produkttypen/Sparten betrachtet werden.

### 3.2 Ausleihdauer — Override-Kette (R2)
Min. und max. Dauer werden getrennt aufgelöst, jeweils aus der ersten gesetzten
Stufe (Einheit = Ausleihart des Produkts, Tage oder Stunden; umgesetzt in #109):
**Gerät (Ressource) → Produkt → Pool-Default → keine Begrenzung**.
- Einen **System-Default** gibt es (noch) nicht — *nicht umgesetzt*; ohne
  Werte auf den drei Stufen ist die Dauer unbegrenzt.
- Grenzen gelten **je Gerät bzw. Pool**: Warenkorb und Ausleihe wählen ein
  freies Gerät, dessen Grenzen zum Zeitraum passen; passt keines, wird mit
  einer Meldung abgelehnt, die den erlaubten Rahmen nennt.
- Der Shop zeigt den **weitesten Rahmen** über die buchbaren Geräte (bei
  abweichenden Rahmen je Pool getrennt).
- **Sets** nutzen den Rahmen des am stärksten eingeschränkten Produkts.
- Die **Verleihtheke (Walk-in)** wird durch Ausleihdauer-Grenzen nie
  blockiert: Ein Zeitraum außerhalb der Grenzen wird als Warnung angezeigt und
  an der Buchung vermerkt (`duration_override`).
- Systemseitige Umbuchungen (Defekt, fehlendes Gerät, Sperrtag) bevorzugen
  passende Geräte, lehnen aber nie ab.

### 3.3 Verfügbarkeit & Pool-übergreifende Sicht (R4)
- Ausleihenden werden Produkte über **alle Pools** gezeigt, auf die sie Zugriff
  haben; bei identischen Produkten in mehreren Pools wird die Verfügbarkeit
  poolübergreifend aggregiert.
- Im Warenkorb und bei der Bestätigung wird je Ressource der **Pool** ausgewiesen.
- Sind mehrere Ressourcen verfügbar, wird die gebucht, die zum Zeitpunkt am
  **längsten zurückgegeben** war. Verleihende können bei der Ausgabe eine andere
  identische Ressource wählen.

### 3.4 Berechtigung (Eligibility)
Pro Ressourcenpool kann eingeschränkt werden, wer ihn sieht/nutzt — über
**OIDC/Shibboleth-Claims** (z. B. Fachbereich) und/oder eine explizite
**Allowlist** berechtigter Ausleihender.
> ⚠️ Vor der Umsetzung ist zu verifizieren, welche Claims der Uni-IdP
> tatsächlich liefert (OIDC wurde an der Uni Osnabrück erst kürzlich
> eingeführt). Details im Auth-ADR.

### 3.5 Zeit-Blockierungen
Blockierbare Zeiten auf Ebene: gesamtes System (z. B. Feiertage), Ressourcenpool
(z. B. Urlaub), Produkt, Ressource. Pro Block ist konfigurierbar, ob er die
maximale Ausleihzeit **verlängert oder verkürzt** (Buchung muss vorher enden
oder darf über den Block hinweggehen).

### 3.6 Defekt-Behandlung
Eine Ressource kann als defekt markiert werden:
- bestehende Buchungen werden — wenn möglich — auf andere Ressourcen umgebucht;
- reicht der Bestand nicht, werden betroffene Ausleihende benachrichtigt;
- Verleihende werden regelmäßig gefragt, ob die Ressource ausgemustert wird oder
  wieder verfügbar ist.

### 3.7 Benachrichtigungen (G7)
E-Mail an Ausleihende u. a. bei: vorläufiger Buchung, bestätigter Buchung
(inkl. Pool-Infos/Öffnungszeiten, Kalendereintrag ⚠️ G1, Verwaltungs-Link),
Strike/Sperrung, Umbuchung/Engpass bei Defekt. Einen Tag vor der Abholung
erinnert eine automatische E-Mail an die bestätigte Buchung (Adresse,
Öffnungszeiten, Wegbeschreibung, Kontakt; einmal je Abholtermin, nie vor der
Bestätigungsmail und erst ab einer einstellbaren Versandzeit am Vortag,
Standard 09:00 – keine Mails in der Nacht; abschaltbar und mit optionalem
Zusatztext unter Administration → Benachrichtigungen; Befehl
`send_pickup_reminders`, stündlich).

### 3.8 Nicht-funktionale Anforderungen
- **i18n:** mindestens Deutsch und Englisch, weitere Sprachen leicht ergänzbar.
- **Mobile-first:** sehr gute Bedienbarkeit auf Mobilgeräten; für Ausleih-Views
  hat die Mobilansicht Vorrang vor der Desktop-Ansicht.
- **Suche:** Ressourcen über Pools, Produkttypen und A-Z-Liste auffindbar;
  fehlertolerante Suche, priorisiert auf den Ressourcennamen, aber über alle
  Eigenschaften.
- **Skalierung:** bis zu 20.000 Nutzende, wenige gleichzeitig in Peak-Zeiten.
- **Multi-Tenancy:** unter vordefinierten URLs werden nur ausgewählte Pools
  angezeigt (Tenant-Grenze s. Review C6).
- **Open Source:** so gebaut, dass eine Installation an anderen Einrichtungen
  vertretbar einfach ist.
- **Inventarisierung:** IDs/QR-Codes für Ressourcen vergeben und scannen.

---

## 4. Ausleih-Workflow (Online-Shop, Ausleihenden-Sicht)

### 4.1 Header (immer sichtbar, auch beim Scrollen)
Startseiten-Symbol · Warenkorb (mit Anzahl-Badge) · Suchfeld (zu Lupe
verkleinerbar) · Eingabe „erster Ausleihtag" (zu Kalendersymbol verkleinerbar) ·
Filter-Symbol · Profil-Symbol.

### 4.2 Startseite & Browsing
- Kacheln der **Sparten**, in denen Produkte der verfügbaren Pools liegen
  (Vorschaubild + Titel, Beschreibung aufklappbar).
- Umschaltbar auf eine **A-Z-Liste** der Produkte (Auswahl im localStorage).
- In einer Sparte: nach Produkttypen gruppierte Produktliste mit Produktanzahl je
  Produkttyp. Gruppen sind eingeklappt ab >10 Produkten (mobil) bzw. >20
  (Desktop); Button „alles aufklappen". Innerhalb einer Gruppe stehen
  **tagesweise** Produkte vor **stundenweisen**; kommen beide vor, trennt eine
  kleine Zwischenüberschrift mit Symbol. Die Produktkarte zeigt die Ausleihart
  nur als **Symbol** (Kalender = tageweise, Uhr = stundenweise; mit Tooltip und
  Screenreader-Text).
- Bei gewähltem Startdatum: **Farbcodes** je Produkt — grün (verfügbar), gelb
  (in ≤2 Werktagen/Stunden verfügbar), rot (nicht verfügbar). Ohne Datum kein
  Hinweis.
- **„+"-Button** je Produkt (direkt buchen) und je Produkttyp (beliebige Ressource
  des Produkttyps für einen Zeitraum suchen).

### 4.3 Produkt-Detailseite
Titel · Bild · Beschreibung · Hinweise zur Ausleihe · Informationen aus dem
Produkttyp (Downloads/Links/Medien gesondert formatiert) · aufklappbarer
Infokasten zu verfügbaren Pools · min./max. Ausleihzeiten (unter Beachtung der
Verfügbarkeit). Immer sichtbarer Button **„+ zum Warenkorb hinzufügen"**.

### 4.4 Buchungsseite (Kalender)
Öffnet sich nach Klick auf „+":
- **tagesweise** → Monatskalender; **stundenweise** → Wochenkalender.
- Startwert: gewähltes Startdatum, sonst der nächste buchbare Tag. Start/Ende
  jederzeit anpassbar.
- Der Kalender zeigt je Block die Zahl verfügbarer Ressourcen; **0-Blöcke** sind
  nicht wählbar (Buchung muss davor enden oder danach beginnen).
- **Blockierte Zeiten** sind nicht wählbar; je nach Block-Einstellung darf die
  Buchung darüber hinweggehen oder muss vorher enden.
- Nach Auswahl bestätigen: Ist die Ressource eindeutig (Produkt + Pool gleich),
  wandert sie in den Warenkorb. Sonst Auswahl-Liste der Optionen
  (Produkt + Pool); Ressourcen aus bereits im Warenkorb vertretenen Pools werden
  als **„empfohlen"** markiert.
- Bei **Sets** richtet sich die Verfügbarkeit nach der knappsten enthaltenen
  Ressource; bei 0 wird angezeigt, welche Set-Ressource fehlt.

### 4.5 Warenkorb
- Zeigt reservierte Ressourcen, nach **Buchungszeiträumen** gruppiert; je
  Eintrag der **Pool** (verlinkt auf Pool-Details).
- Anzeige als **Produkt** (konkrete Ressource nur im Kleingedruckten); Klick →
  Produkt-Detailseite. Sets werden zu Einzelprodukten aufgelöst.
- Einzelprodukte entfernbar; Buchungszeitraum je Produkt änderbar (öffnet erneut
  die Buchungsseite). Ändert man einen Zeitraum für mehrere Produkte zugleich,
  werden diese als **spontanes Set** behandelt.
- Button **Buchung absenden** → Hinweis, dass die Buchung erst mit
  E-Mail-Bestätigung gilt; vorläufige Bestätigung per E-Mail; Buchung erscheint
  im Profil als **„noch nicht bestätigt"** (löschbar/änderbar).
- **Reservierung im Warenkorb:** Sobald ein Produkt im Warenkorb liegt, ist die
  konkrete Ressource für andere reserviert. Die Reservierung hat eine
  **Haltedauer** (Standard 30 Minuten, im Admin konfigurierbar), die bei jeder
  Warenkorb-Aktion neu beginnt; läuft sie ohne Absenden ab, wird die Ressource
  wieder frei (die Verfügbarkeit behandelt abgelaufene Warenkörbe sofort als
  frei; ein periodischer `release_cart_holds`-Job räumt sie zusätzlich auf).

### 4.6 Bestätigte Buchung
- Erscheint im Profil; ganze Buchungen oder einzelne Produkte entfernbar.
- E-Mail mit: Ressourcen gruppiert nach **Abholtermin und Pool** (je Pool
  Öffnungszeiten, Ort, ggf. Link zur Wegbeschreibung), **Kalendereintrag** ⚠️ G1,
  **Verwaltungs-/Storno-Link**.

---

## 5. Verwaltung (Verleihende & Admin)

### 5.1 Ressourcenpool anlegen/verwalten
Anlegen mit den Attributen aus §1.5; Pools sind aktivierbar/deaktivierbar.

### 5.2 Produkttyp anlegen/verwalten
- Eigenschaftsliste definieren (Key, Value-Typ, Default, *sichtbar*,
  *Pflichtfeld*), Bild, Beschreibung und Sparten zuordnen, Reihenfolge festlegen, Ausleihart
  festlegen.
- Nachträglich änderbar: neue Eigenschaften unproblematisch; ein Default gilt
  für alle bestehenden Produkte des Typs. Beim **Löschen** einer Eigenschaft:
  Warnhinweis (abbrechbar) inkl. Anzahl der Produkte, die diesen Wert befüllt
  haben (nicht leer / nicht nur Default).

### 5.3 Produkt anlegen/verwalten
- Produkttyp wählen; alle durch den Produkttyp definierten Felder ausfüllen.
- Alternativ ein bestehendes Produkt als **Vorlage** übernehmen.
- Optionale **Rücknahme-Information**: ein Hinweistext, den Verleihende bei der
  Rückgabe sehen (z. B. „Objektivdeckel prüfen, 2 Akkus zählen"). Für Entleiher
  nicht sichtbar; angezeigt im Rückgabeprozess (§6.3).

### 5.4 Ressource anlegen/verwalten
- Physisches Exemplar zu einem Produkt anlegen: erzeugt **Inventarnummer** und
  **QR-Code**, ordnet einen **Ressourcenpool** zu. Klonen eines bestehenden
  Exemplars (nur neue Inventarnummer) möglich.

### 5.5 Sets anlegen/verwalten
- Verleihende/Admins stellen ein **Set** als **Liste von Produkten** zusammen,
  die sinnvollerweise gemeinsam ausgeliehen werden.
- Jedes Set gehört zu genau **einem Pool** (Pflichtfeld). Verleihende wählen
  nur Pools, die sie verwalten; den bisherigen Pool eines Sets dürfen sie
  beibehalten. Sets aus der Zeit vor dieser Regel ohne Pool sind als „Pool
  fehlt" markiert und nicht buchbar, bis ein Pool gewählt ist.
- Je Produkt eine **Anzahl** (≥ 1); die Reihenfolge ist frei wählbar. Ein
  Produkt braucht mindestens einen nicht ausgemusterten Gegenstand im Pool;
  das Formular zeigt „N benötigt · M im Pool" und warnt, wenn N > M. Beim
  Pool-Wechsel werden Produkte ohne Gegenstand im neuen Pool markiert und
  müssen vor dem Speichern entfernt werden.
- Gebucht werden je Produkt so viele verschiedene Gegenstände wie die Anzahl
  (alles oder nichts); die Verfügbarkeit eines Sets ist je Produkt
  `frei // Anzahl`, das Minimum zählt.
- Ein **Bild** (zugeschnitten wie bei Sparten) und eine formatierte
  **Beschreibung** (Rich Text); beides erscheint auf Set-Karte und Set-Seite.
- Set-Liste; Sets löschbar; Produkte hinzufügbar/entfernbar.

### 5.6 Sparten & Produkttypen
Sparten anlegen, löschen und ihre Produkttypen auswählen und ordnen; die
Zuordnung ist auch in der Produkttyp-Verwaltung möglich (Produkttyp ↔ Sparten).
Eine eigene Kategorien-Verwaltung gibt es nicht mehr.

### 5.7 Inventar
Tabellarische Übersicht der **Ressourcen**, filter-/sortierbar. Spalten u. a.:
Inventarnummer, Produkttyp-Bezeichnung, Zustand, Kaufdatum, Anzahl Ausleihen.
Klick → Detailseite.

---

## 6. Verleih-Betrieb (Verleihende & Admin)

### 6.1 Tagesübersicht
Zentraler Screen: geplante Ausleihen und Rückgaben des Tages (Tag-vor/-zurück,
Datepicker). Erledigte Rückgaben/Abholungen wandern in separate „erledigt"-Listen.
Eigener Bereich: **überfällige Rückgaben** aus Vortagen. Nicht abgeholte
Ressourcen bleiben in den Folgetagen sichtbar (mit ursprünglichem Termin), bis
die Mindest-Ausleihdauer unterschritten ist — dann **Archivierung**; dabei
Abfrage an Verleihende, ob ein **Strike** vergeben wird.

### 6.2 Ausleihprozess
Ausleihende erhalten E-Mail mit kurzem alphanumerischem **Buchungscode** und
**QR-Code**, der (nur für angemeldete Ausleihende oder Verleihende) auf eine
Übersicht der Buchung führt. Dort unten ein Feld für eine **digitale
Unterschrift** (z. B. auf einem iPad).

### 6.3 Rückgabeprozess
Liste der ausgegebenen Produkte. Verleihende: fehlende Produkte markieren,
verspätete Rückgabe bestätigen, Produkte als **defekt** markieren, Kommentare
erfassen (frühere Kommentare einsehbar), Rückgabe speichern (bestätigt den
Zustand inkl. Abweichungen), ggf. **Strike** vermerken.
- Hat ein Produkt eine **Rücknahme-Information** (§5.3), erscheint beim Klick auf
  *Rückgabe* ein Prüf-Dialog: der Hinweistext wird angezeigt, und je Gerät wird
  entweder **„Alles in Ordnung"** bestätigt oder **„Defekt melden"** gewählt
  (mit Notiz). Bei Defekt gilt das Gerät als zurückgegeben **und** wird als
  defekt markiert (künftige Buchungen werden umgebucht, §3.6). Die Rückgabe lässt
  sich im Dialog auch **abbrechen**. Ohne hinterlegte Info bleibt die Rückgabe
  ein direkter Klick.

### 6.4 Spontane Ausleihen
Nur Verleihende; ohne eingestellte Vorlaufzeit. Im Warenkorb wird die
ausleihende Person festgelegt.

### 6.5 Nutzendenverifizierung ⚠️ (in Diskussion)
> ⚠️ **Noch in Diskussion** — Ablauf und Umfang sind nicht final; noch nicht
> umgesetzt.

Selbstregistrierte Ausleihende werden beim **Erstkontakt** durch Verleihende
bestätigt: vor der ersten Ausgabe wird das Profil angezeigt und die verleihende
Person bestätigt den Account. Es werden dabei **keine zusätzlichen
Ausweisdaten** erfasst.

---

## 7. Administration (Admin)

### 7.1 Identitäten & Anmeldung
- Anmeldung über **OIDC (Keycloak)** und in Teilen **Shibboleth**.
- Nutzerdatensatz entsteht **bei der ersten Anmeldung** (vorher kein Datensatz).
- **Selbstregistrierung** als von Admins abschaltbare Funktion;
  selbstregistrierte Nutzende erfordern Verifizierung (§6.5).

### 7.2 Nutzerverwaltung
Alle Accounts einsehbar (nur Admin). Hochstufen zu Verleihenden/Admins;
gesperrte Nutzende filterbar inkl. Restdauer; Zuordnung von Nutzenden
(v. a. Verleihenden) zu Ressourcenpools.

### 7.3 Strikes
- Vergabe durch Verleihende, immer **mit Begründung**; gelten **poolübergreifend**.
- Ab konfigurierbarer Anzahl: Sperre für konfigurierbaren Zeitraum; höhere
  Stufen mit längeren/dauerhaften Sperren vorkonfigurierbar.
- Ein Strike verfällt nach konfigurierbarer Zeit; **nur Admins** können Strikes
  löschen.
- Auch Verleihende (in ihrer Rolle als Ausleihende) können Strikes erhalten.
- Ausleihende werden über Strike/Sperrung benachrichtigt.

---

## 8. Offene Punkte
Die früheren Widersprüche (C1–C5) sind entschieden (s. `docs/concept-review.md`
§4). Verbleibend offen:
- **OIDC-Claims** — verfügbare Claims des Uni-IdP vor Umsetzung verifizieren (§3.4).
- **Inventarnummern-Schema** pro Pool noch festzulegen (§1.4).
- **Kalendereintrag bei mehreren Terminen** (`.ics`) — Detailfrage (§4.6).
- **Tenant-Grenze** — bewusst auf viel später vertagt (Multi-Tenancy ist Ausblick).
