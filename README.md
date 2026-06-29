# Discord Bot – Installationsanleitung

Produktionsbereiter Discord-Bot mit Slash Commands, Moderation, Welcome/Leave, Logs und AutoMod.

## Voraussetzungen

- **Python 3.11+**
- **PyCharm** (Community oder Professional)
- Ein **Discord Developer Account** ([Discord Developer Portal](https://discord.com/developers/applications))

---

## 1. Discord-Bot erstellen

1. Öffne https://discord.com/developers/applications
2. Klicke **New Application** und vergib einen Namen
3. Gehe zu **Bot** → **Add Bot**
4. Kopiere den **Token** (Reset Token falls nötig)
5. Aktiviere unter **Privileged Gateway Intents**:
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**
6. Gehe zu **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Administrator` (oder einzeln: Ban, Kick, Manage Channels, Manage Messages, Moderate Members, Manage Roles)
7. Lade den Bot mit der generierten URL auf deinen Server ein

---

## 2. Projekt in PyCharm öffnen

1. **File → Open** → Ordner `discord-bot` auswählen
2. **File → Settings → Project → Python Interpreter**
3. **Add Interpreter → Add Local Interpreter → Virtualenv**
4. Python 3.11+ auswählen und Virtual Environment erstellen

---

## 3. Dependencies installieren

Im PyCharm-Terminal (oder extern):

```bash
pip install -r requirements.txt
```

Installierte Pakete:

| Paket | Zweck |
|-------|-------|
| discord.py | Discord API & Slash Commands |
| aiosqlite | Asynchrone SQLite-Datenbank |
| python-dotenv | .env-Konfiguration |
| Pillow | Welcome-Bilder |
| aiofiles | Asynchroner Dateizugriff |

---

## 4. Konfiguration

```bash
copy .env.example .env
```

Bearbeite `.env` und trage deinen Token ein:

```env
DISCORD_TOKEN=dein_echter_bot_token
OWNER_ID=deine_discord_user_id
LOG_LEVEL=INFO
```

---

## 5. Bot starten

```bash
python main.py
```

Bei Erfolg siehst du:

```
Bot online als DeinBot (ID: ...)
X Slash Command(s) synchronisiert.
```

Die SQLite-Datenbank `database.db` wird beim ersten Start automatisch erstellt.

---

## 6. Ersteinrichtung auf dem Server

Führe diese Slash Commands als Administrator aus:

```
/logs setup #log-kanal
/welcome setup #welcome-kanal
/leave setup #leave-kanal
/automod enable
/automod spam enabled:true
/settings view
```

---

## Projektstruktur

```
discord-bot/
├── main.py              # Einstiegspunkt
├── config.py            # Konfiguration (.env)
├── requirements.txt     # Dependencies
├── database.db          # SQLite (auto-generiert)
├── .env.example         # Token-Vorlage
├── bot.log              # Log-Datei (auto-generiert)
├── cogs/
│   ├── moderation.py    # /ban, /kick, /warn, ...
│   ├── welcome.py       # /welcome ...
│   ├── leave.py         # /leave ...
│   ├── logs.py          # /logs ... + Event-Logging
│   ├── automod.py       # /automod ... + Filter
│   └── settings.py      # /settings view|reset
├── database/
│   ├── database.py      # SQLite-Layer
│   └── models.py        # Datenmodelle
└── utils/
    ├── embeds.py        # Embed-Design
    ├── permissions.py   # Berechtigungs-Checks
    └── helpers.py       # Platzhalter, Spam, Bilder
```

---

## Slash Commands Übersicht

### Moderation
`/ban` `/kick` `/timeout` `/untimeout` `/warn` `/unwarn` `/warnings` `/clear` `/slowmode` `/lock` `/unlock` `/nickname` `/mute` `/unmute`

### Welcome
`/welcome setup` `channel` `message` `enable` `disable` `test`

### Leave
`/leave setup` `channel` `message` `enable` `disable` `test`

### Logs
`/logs setup` `channel` `enable` `disable`

### AutoMod
`/automod enable` `disable` `spam` `invites` `links` `badwords` `punishment`

### Einstellungen
`/settings view` `/settings reset`

---

## Platzhalter (Welcome/Leave)

| Platzhalter | Bedeutung |
|-------------|-----------|
| `{user}` | Mention des Users |
| `{username}` | Anzeigename |
| `{userid}` | Discord User-ID |
| `{server}` | Servername |
| `{membercount}` | Mitgliederanzahl |

---

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| `DISCORD_TOKEN fehlt` | `.env` anlegen und Token eintragen |
| Slash Commands erscheinen nicht | Bot neu starten, 1–5 Min. warten |
| Member-Events funktionieren nicht | **Server Members Intent** aktivieren |
| AutoMod reagiert nicht | **Message Content Intent** aktivieren |
| Keine Berechtigung | Bot-Rolle über Ziel-Rollen setzen |

---

## Lizenz

Frei verwendbar für private und kommerzielle Projekte.
