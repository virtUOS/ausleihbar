---
title: Alle Buchungen und Strikes
description: Jede Buchung deiner Pools finden und bearbeiten, Strikes vergeben und das Profil einer ausleihenden Person ansehen.
---

# Alle Buchungen und Strikes

Die Tagesübersicht zeigt, was heute ansteht. **Alle Buchungen**
(Verleihtheke → Buchungen & Ausgabe) zeigt alles – vergangene, laufende und
künftige Buchungen deiner Pools, auch stornierte.

![„Alle Buchungen“ mit dem Suchfeld, dem Schalter „Verleihbeginn | Eingang der Buchung“ und dem Zeitraum „Alle“; darunter eine Buchung von Alex Beispiel, die auf Bestätigung wartet, eine bestätigte Buchung von Mika Probe mit drei Gegenständen und dem Knopf „Aushändigen“ und eine stornierte Buchung](../bilder/theke-buchungen.png)

## Suchen und filtern

- **Suchfeld:** Buchungsnummer, Name der Person oder Produkt („Nach
  Buchungsnummer, Kunde oder Produkt suchen…“).
- **Verleihbeginn | Eingang der Buchung:** sortiert nach dem Beginn des
  Zeitraums oder danach, wann die Buchung eingegangen ist.
- **Zeitraum:** Alle, Heute, Diese Woche, Dieser Monat oder
  Benutzerdefiniert mit Von/Bis.

## Was du an einer Buchung tun kannst

Die Buchungen sehen aus wie in der Tagesübersicht und haben dieselben
Aktionen, je nach Status:

| Status | Aktionen |
| --- | --- |
| **Warten auf Bestätigung** | **Bestätigen**, optional mit Nachricht ([wie in der Tagesübersicht](tagesuebersicht.md#buchungen-bestätigen)) |
| **Bestätigt** | **Aushändigen** |
| **Abgeholt** | **Rückgabe** der ausgegebenen Gegenstände, **Aushändigen** für noch offene |

Im Menü **⋮** der Buchung:

- **Strike vergeben** – siehe [unten](#strikes-vergeben).
- **Buchung stornieren** – solange nichts ausgegeben ist. Sind Gegenstände
  draußen, nimm sie zuerst zurück. Die Gegenstände werden sofort wieder
  frei. Die Person bekommt eine Mail über die Stornierung; im Dialog kannst
  du eine **Nachricht an die Person** dazuschreiben, etwa den Grund oder
  einen Ersatzvorschlag. Die Nachricht steht nur in der Mail und wird nicht
  gespeichert.

Am einzelnen Gegenstand (kleines **⋮**): **Als defekt markieren** oder
**Als repariert markieren** ([was dann passiert](ausgabe.md#defekte-melden)).

Einen Gegenstand einer Buchung gegen einen anderen tauschen oder einen
zusätzlichen hinzufügen kannst du bei der Ausgabe auf der
[QR-Seite](ausgabe.md#ausgeben-per-scan).

!!! info "Etiketten an der Buchung"
    **Außerhalb der Ausleihdauer** – an der Theke per Direktausleihe mit
    einem Zeitraum außerhalb der Grenzen angelegt.
    **🔔 … erinnert** – die Person wurde wegen Überfälligkeit erinnert.
    **Vor Ort** – der Gegenstand wird vor Ort genutzt, **Ohne Ausgabe**
    heißt zusätzlich: ohne Theke.

## Strikes vergeben

Ein Strike ist eine Verwarnung mit Grund. Ausleihbar vergibt ihn **nie
automatisch** – ob eine Situation einen Strike rechtfertigt, entscheidest
du. Typische Gründe sind eine **deutlich verspätete Rückgabe** oder ein
**beschädigt oder verschmutzt** zurückgegebener Gegenstand; eine einzelne
verpasste Abholung ist meist keiner, wiederholtes Nichterscheinen kann einer
sein. Strikes zählen über alle Pools und verfallen nach einer festen Zeit;
ab einer bestimmten Zahl aktiver Strikes sperrt Ausleihbar das Konto
automatisch (eingestellt in den [Strike-Regeln](personen.md#strike-regeln)).
Was Ausleihende dazu sehen, steht in
[Strikes und Sperren](../anleitung/strikes.md).

1. Öffne an der Buchung **⋮** → **Strike vergeben**.
2. Trage den **Grund** ein. Er steht in der Mail und bei der Person unter
   „Deine Strikes“.
3. Optional: eine **Persönliche Nachricht an die Person**. Sie steht nur in
   der E-Mail.
4. Prüfe die **E-Mail-Vorschau** und den Hinweis darunter, was der Strike
   bewirkt – etwa „Das wird der 2. aktive Strike – noch keine Sperre.“ oder
   „… – das Konto wird bis … gesperrt.“
5. Klicke **Strike vergeben**.

![Dialog „Strike vergeben — Jona Muster“ mit dem Grund „Reservierung nicht abgeholt und nicht abgesagt“, dem leeren Feld für eine persönliche Nachricht, der E-Mail-Vorschau „Strike zu deiner Buchung R-00591“ mit Ablaufdatum, Zahl der aktiven Strikes, Sperrschwelle und Kontaktdaten des Pools, darunter „Das wird der 2. aktive Strike – noch keine Sperre.“](../bilder/theke-strike.png)

!!! note "Löschen und Entsperren macht die Administration"
    Verleihende vergeben Strikes, löschen können sie nur Admins. Auch eine
    Sperre hebt nur die Administration auf
    ([Benutzer](personen.md#benutzer)). Hat die Person keine E-Mail-Adresse,
    wird keine Mail verschickt; der Strike zählt trotzdem.

## Das Profil einer Person

Ein Klick auf den Namen an einer Buchung öffnet das Profil der Person. Dort
siehst du:

- ob das Konto gesperrt ist („Gesperrt bis …“, „Dauerhaft gesperrt“ oder
  „Nicht gesperrt“) und wie viele Strikes aktiv sind,
- alle **Strikes** mit Grund, persönlicher Nachricht, wer sie vergeben hat
  und bis wann sie zählen,
- den **Buchungsverlauf**, getrennt nach Anstehend, Ausgegeben und
  Abgeschlossen.

Auch hier kannst du **Strike vergeben** – als Verleiher für Personen, die
in einem deiner Pools gebucht haben.
