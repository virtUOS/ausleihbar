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
| Buchung: Person, Arbeitsplatz/Besprechungsraum, Zeitraum, ggf. Kommentar, wer gebucht hat | Buchen, Check-in, Freigabe | Mitglieder der Abteilung sehen den Namen bei Arbeitsplätzen (außer bei Opt-out); bei Besprechungsräumen immer Name und Kommentar; Abteilungsadmins/Assistenz sehen Buchungen zum Verwalten | Nach Ende der Buchung für die Aufbewahrungsfrist der Abteilung (Standard 90 Tage), danach wird Person, Buchende/r und Kommentar entfernt; Opt-out-Arbeitsplätze sofort nach Ende |
| Check-in (Zeitpunkt, Markierung „nicht erschienen", „freigegeben") | Freigabe ungenutzter Buchungen, Statistik | Wie die Buchung | Wie die Buchung; danach nur noch ohne Personenbezug in Zahlen |
| Serie (wöchentliche Buchung) | Wiederkehrende Buchungen | Inhaber/in, Abteilungsadmins | Wie Buchungen (nach Ende der Serie + Aufbewahrungsfrist anonymisiert) |
| Abwesenheit (Zeitraum; **ohne Grund**) | Buchungen freigeben, feste Plätze für andere öffnen | Nur die Person selbst, Abteilungsadmins und Assistenz – nie Kolleg/innen | Bis zum Ende + Aufbewahrungsfrist (bei mehreren Abteilungen die kürzeste) |
| Tausch- und Freigabeanfragen | Tauschen/Freigeben | Beteiligte; Anfragen an Opt-out-Personen bleiben anonym | Nach Abschluss/Ende gelöscht nach Aufbewahrungsfrist; Personenverknüpfungen beendeter Anfragen werden entfernt |
| Opt-out-Einstellung | Namen verbergen | Nur die Person selbst | Solange das Konto besteht |
| Benachrichtigungseinstellungen | Mails je Ereignis steuern | Nur die Person selbst | Solange das Konto besteht |

Die Nutzungsstatistik enthält nur Summen (siehe 6.).

## 3. Was nicht gespeichert wird
- **Kein Abwesenheitsgrund** (insbesondere keine Krankheit); es gibt nur
  „abwesend" bzw. „Urlaub" als Zeitraum.
- **Keine Ortung** und keine automatische Anwesenheitserkennung (kein
  WLAN-Tracking, keine Sensoren). Anwesenheit entsteht nur durch eine
  bewusste Handlung der Person (Check-in) oder durch ihre Buchung.
- **Keine Einzel-Anwesenheitsstatistik** pro Person.

## 4. Opt-out
Jede Person kann in den Einstellungen ihren Namen verbergen (standardmäßig
aus, Namen sind sichtbar). Dann wird der Name bei **Arbeitsplätzen** für
alle anderen verborgen – auch für Abteilungsadmins und Assistenz –, und
zwar in Übersicht, „Wer sitzt bei mir", Tausch- und Freigabeanfragen
sowie Kommentaren. Angezeigt wird „belegt" bzw. „Person (verborgen)".
Admins können die Buchung dennoch verschieben, löschen oder die Person
abwesend setzen; dazu wählen sie die Person selbst namentlich in den
Formularen „Buchen für" bzw. „Abwesend setzen" aus. Besprechungsraum-
Buchungen zeigen immer Inhaber/in und Kommentar, da sie nichts über
Arbeitszeiten aussagen.

## 5. Check-in und Freigabe
- Check-in per Schaltfläche in der Web-App oder per QR-Code am Platz;
  möglich ab 15 Minuten vor Beginn bis zum Ende der Buchung.
- Bei normalen Buchungen ist der Check-in nötig, damit die Buchung nicht
  freigegeben wird. Wer nicht eincheckt, verliert nur diese Buchung.
  Bei **festen Plätzen** ist der Check-in freiwillig.
- Regeln je Abteilung, getrennt für Arbeitsplätze und Besprechungsräume:
  Nach der kurzen Karenzzeit (Standard 15 Minuten) wird die Buchung
  freigegeben, wenn Plätze knapp sind (weniger als eine Mindestanzahl
  frei, Standard 2). Sonst gilt sie nach der normalen Karenzzeit
  (Standard 60 Minuten) als „möglicherweise frei"; die Person behält den
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
  Zugriffsregeln, Einstellungen, Statistik; Buchungen anderer
  verschieben oder – als Ausnahme, mit Begründung und Benachrichtigung –
  löschen; für andere buchen; Personen abwesend setzen; **vergangene
  Tage** der Übersicht einsehen.
- **Assistenz** (Sekretariat, pro Abteilung benannte Gruppe): für andere
  buchen und Personen abwesend setzen; keine Verwaltung von Plätzen oder
  Rechten, keine Statistik, keine vergangenen Tage.
- **App-Admins:** alles. Für andere gebuchte Buchungen werden die
  Betroffenen benachrichtigt und können stornieren.
- Kolleg/innen sehen nur heute und künftige Tage, keine Rückschau.

## 9. Löschung und Anonymisierung
Täglich läuft ein Job: Buchungen und Serien werden nach Ablauf der
Aufbewahrungsfrist (je Abteilung, Standard 90 Tage) anonymisiert (Person,
Buchende/r, Kommentar entfernt); bei Opt-out-Arbeitsplätzen sofort nach
Ende. Abwesenheiten und beendete Anfragen werden gelöscht. Statistik-
Summen bleiben, ohne Personenbezug. Verlässt eine Person das System, gelten
zusätzlich die allgemeinen Löschregeln von Ausleihbar.
