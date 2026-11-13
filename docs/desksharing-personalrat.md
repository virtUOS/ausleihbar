# Desksharing in Ausleihbar – Zusammenfassung für den Personalrat

Stand: November 2026. Diese Beschreibung entspricht der Umsetzung; sie ist
keine Dienstvereinbarung, sondern Grundlage für das Gespräch.

## 1. Zweck
Abteilungen teilen sich Arbeitsplätze und Besprechungsräume. Mit
Desksharing werden diese gebucht, ungenutzte Buchungen werden
freigegeben, und die Abteilung erhält **anonyme Zahlen**, wie viele
Plätze tatsächlich gebraucht werden. Es gibt **keine** Leistungs- oder
Verhaltenskontrolle einzelner Personen; das System ist dafür nicht
gebaut und zeigt solche Auswertungen nicht an.

Desksharing wird je Abteilung eingeschaltet und ist nur für Mitglieder
der Zugriffsgruppen der Abteilung sichtbar; es gibt keine
hochschulweite Namensliste.

## 2. Was gespeichert wird
| Daten | Zweck | Wer sieht sie | Wie lange |
|---|---|---|---|
| Buchung: Person, Arbeitsplatz/Besprechungsraum, Zeitraum, ggf. Kommentar, wer gebucht hat | Buchen, Check-in, Freigabe | Mitglieder der Abteilung sehen den Namen bei Arbeitsplätzen (außer bei Opt-out); bei Besprechungsräumen immer Name und Kommentar; Abteilungsadmins sehen die Buchungen eines Tages zum Verwalten (Opt-out: „Person (verborgen)"); Betreiber siehe 4. | Nach Ende der Buchung für die Aufbewahrungsfrist der Abteilung (Standard 90 Tage), danach wird Person, Buchende/r und Kommentar entfernt; Opt-out-Arbeitsplätze sofort nach Ende |
| Check-in und Freigabe: Zeitpunkt des Check-ins, „Ich komme später" bis (Uhrzeit), Zeitpunkt und Grund einer Freigabe/Stornierung (z. B. nicht erschienen, Abwesenheit, durch Admin, Sperrtag, entzogene Berechtigung), Markierung „nicht erschienen" | Freigabe ungenutzter Buchungen, Statistik | Wie die Buchung (der Grund „Abwesenheit" nur für die Person selbst, Abteilungsadmins und Assistenz) | Wie die Buchung; danach nur noch ohne Personenbezug in Zahlen |
| Serie (wöchentliche Buchung) | Wiederkehrende Buchungen | Inhaber/in, Abteilungsadmins | Wie Buchungen (nach Ende der Serie + Aufbewahrungsfrist anonymisiert) |
| Abwesenheit (Zeitraum, Art „Urlaub"/„abwesend", wer sie eingetragen hat; **ohne Grund**) | Buchungen freigeben, feste Plätze für andere öffnen | Nur die Person selbst, Abteilungsadmins und Assistenz – nie Kolleg/innen. Die Seite „Abwesenheiten" zeigt Admins und Assistenz nur laufende und künftige; vergangene sind bis zur Löschung über die Schnittstelle (API) abrufbar | Bis zum Ende + Aufbewahrungsfrist (bei mehreren Abteilungen die kürzeste), dann gelöscht |
| Tausch- und Freigabeanfragen (wer fragt, ob der eigene Name gezeigt werden darf, Status) | Tauschen/Freigeben | Beteiligte; wer ohne Namen fragt, bleibt anonym; Anfragen an Opt-out-Personen verraten diese nicht | Gelöscht, sobald die zugrunde liegende Buchung länger als die Aufbewahrungsfrist beendet ist |
| Opt-out-Einstellung | Namen verbergen | Nur die Person selbst (Betreiber siehe 4.) | Solange das Konto besteht |
| Benachrichtigungseinstellungen | Mails je Ereignis steuern | Nur die Person selbst | Solange das Konto besteht |
| Datum der letzten täglichen Übersicht | Die Übersicht nicht doppelt senden | Niemand in der App (Betreiber siehe 4.) | Solange das Konto besteht |

Die Nutzungsstatistik enthält nur Summen (siehe 6.).

## 3. Was nicht gespeichert wird
- **Kein Abwesenheitsgrund** (insbesondere keine Krankheit); es gibt nur
  „abwesend" bzw. „Urlaub" als Zeitraum.
- **Keine Ortung** und keine automatische Anwesenheitserkennung (kein
  WLAN-Tracking, keine Sensoren). Anwesenheit entsteht nur durch eine
  bewusste Handlung der Person (Check-in) oder durch ihre Buchung.
- **Keine Einzel-Anwesenheitsstatistik** pro Person.

## 4. Opt-out
Jede Person kann unter „Benachrichtigungen" → „Datenschutz" ihren Namen
verbergen („Meinen Namen bei Arbeitsplätzen verbergen"; standardmäßig
aus, Namen sind sichtbar). Dann wird der Name bei **Arbeitsplätzen** für
alle anderen verborgen – auch für Abteilungsadmins und Assistenz –, und
zwar in Übersicht, „Mit dir im Raum", Tausch- und Freigabeanfragen
sowie Kommentaren. Angezeigt wird „Gebucht" bzw. „Person (verborgen)".
Admins können die Buchung dennoch verschieben oder löschen (sie handeln
über die Buchung, ohne den Namen zu sehen) und die Person abwesend
setzen; Personen wählen sie nur namentlich in den Formularen „Buchen für"
bzw. „Abwesend setzen" aus, wo sie die Person selbst eingeben.
Besprechungsraum-Buchungen zeigen immer Inhaber/in und Kommentar, da sie
nichts über Arbeitszeiten aussagen.

**Betreiber** (Superuser mit Zugang zur technischen Django-Administration)
sehen in den Listen der Buchungen und Serien Opt-out-Personen ebenfalls
nur als „Person (verborgen)", ebenso Personen, die ohne Namen um Freigabe
gebeten haben. Das ist **keine Zugriffssperre**: In den Detailansichten
und in der Datenbank ist die Person weiterhin gespeichert, weil sie für
Mails, Check-in und Abwesenheiten gebraucht wird; auch die
Opt-out-Einstellung selbst ist für Betreiber sichtbar. Der Zugang sollte auf
wenige technische Administratoren beschränkt sein.

## 5. Check-in und Freigabe
- Check-in per Schaltfläche in der Web-App oder per QR-Code am Platz;
  möglich ab 15 Minuten vor Beginn bis zum Ende der Buchung.
- Bei normalen Buchungen ist der Check-in nötig, damit die Buchung nicht
  freigegeben wird. Wer nicht eincheckt, verliert nur diese Buchung.
  Nutzt die feste Inhaberin bzw. der feste Inhaber den **eigenen festen
  Platz**, ist der Check-in freiwillig. Wer einen festen Platz während
  der Abwesenheit der Inhaber/in bucht, checkt wie bei jedem anderen
  Platz ein.
- Regeln je Abteilung, getrennt für Arbeitsplätze und Besprechungsräume:
  Nach der kurzen Karenzzeit (Standard 15 Minuten) wird die Buchung
  freigegeben, wenn Plätze knapp sind (weniger als eine Mindestanzahl
  frei, Standard 2). Sonst gilt sie nach der normalen Karenzzeit
  (Standard 60 Minuten) als „Potenziell frei"; die Person behält den
  Platz, auch bei späterer Ankunft. Werden Plätze später am Tag knapp,
  wird sie dann freigegeben. Mit „Ich komme später" kann die Person die
  Prüfung verschieben. Eine freigegebene oder nicht eingecheckte Buchung
  zählt einmalig als „nicht erschienen" – nur in der Summe.
- Die Person wird per Mail informiert und erhält freie Alternativen.
- Bei ganztägigen Buchungen wird je Tag geprüft.

## 6. Statistik
- **Wer sieht sie:** nur Abteilungsadmins (ihre Abteilung) und
  App-Admins.
- **Inhalt:** gebuchte, genutzte, freigegebene Stunden, nicht Erschienene
  (Anzahl/Stunden), umgebuchte Stunden, Soll-Stunden fester Plätze,
  Spitzenauslastung nach Wochentag und Uhrzeit; CSV-Export.
- **Aggregation:** Normale Arbeitsplätze und normale Besprechungsräume
  werden **nur als Quote** je Abteilung und Art ausgewiesen, nie je
  Einzelplatz; es werden keine Personen ausgelesen.
- **Sonderplätze** (z. B. Videoschnittplatz) werden einzeln ausgewiesen,
  damit Abteilungen über einen Ausbau entscheiden können.
- **Einschränkung:** Bei einem *festen Sonder-Arbeitsplatz* ergeben sich
  die angerechneten Stunden aus den Geschäftszeiten abzüglich der
  Abwesenheitstage der zugewiesenen Person. Dadurch können Abteilungsadmins
  aus den Einzelwerten dieses Platzes auf Abwesenheitstage der Person
  schließen. Dieser Fall sollte bei der Abstimmung bedacht werden (etwa
  indem feste Plätze nicht als Sonderplatz markiert werden).

## 7. Benachrichtigungen
Nur per Mail (Push ist später möglich). Je Ereignis einstellbar (Mail
oder aus): tägliche Übersicht am Morgen (nur bei Buchungen an dem Tag),
Hinweis bei fehlendem Check-in, Freigabe, Änderung durch Admins, Buchung
für Sie, Tausch-/Freigabeanfragen und Antworten, Serien-Verlängerung.
Anfragen verraten Opt-out-Personen nicht.

## 8. Befugnisse der Administration
- **Abteilungsadmins** (Verleiher der Abteilung): Plätze, Räume,
  Zugriffsregeln, Einstellungen, Statistik; Buchungen anderer in der
  Übersicht („Buchungen verwalten" bzw. in den Platzdetails) auf einen
  freien Platz derselben Art verschieben, den die Person buchen darf,
  oder – als Ausnahme, mit Pflicht-Begründung – stornieren (eine bereits
  laufende Buchung wird ab der aktuellen Stunde freigegeben); die Person
  wird jeweils benachrichtigt. Außerdem für andere buchen, Personen
  abwesend setzen und **vergangene Tage** der Übersicht einsehen.
- **Assistenz** (Sekretariat, pro Abteilung benannte Gruppe): für andere
  buchen und Personen abwesend setzen (vergangene Abwesenheiten sind bis
  zur Löschung über die Schnittstelle abrufbar, die Seite zeigt sie
  nicht); keine Verwaltung von Plätzen oder
  Rechten, keine Statistik, keine vergangenen Tage der Übersicht. Wer
  für eine andere Person gebucht hat, kann diese Buchung bzw. Serie nur
  ändern oder stornieren, solange sie/er noch Assistenz oder Admin der
  Abteilung ist; die Person wird benachrichtigt.
- **App-Admins:** alles. Für andere gebuchte Buchungen werden die
  Betroffenen benachrichtigt und können stornieren.
- Kolleg/innen sehen nur heute und künftige Tage, keine Rückschau.

## 9. Löschung und Anonymisierung
Täglich läuft ein Job: Buchungen und Serien werden nach Ablauf der
Aufbewahrungsfrist (je Abteilung, Standard 90 Tage) anonymisiert (Person,
Buchende/r, Kommentar entfernt); bei Opt-out-Arbeitsplätzen sofort nach
Ende. Abwesenheiten werden nach Ende + Aufbewahrungsfrist gelöscht,
Tausch- und Freigabeanfragen, sobald ihre Buchung länger als die
Aufbewahrungsfrist beendet ist. Statistik-
Summen bleiben, ohne Personenbezug. Verlässt eine Person das System, gelten
zusätzlich die allgemeinen Löschregeln von Ausleihbar.
