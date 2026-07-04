# AGENTS.md

## Cursor Cloud specific instructions

### What this is
Single-process Discord bot ("Anarchy"), Python 3.11+ / `discord.py`, persisting to a local
SQLite file (`database.db`, auto-created on first run, gitignored). There is **no web server
and no listening port** — the bot makes outbound WebSocket/HTTPS connections to Discord.
Feature modules live in `cogs/` and are listed in `COGS` in `main.py`. Standard run/setup
commands are in `README.md` (German).

### Running
The update script installs dependencies into a virtualenv at `.venv`. Run the bot with:

```bash
.venv/bin/python main.py
```

### Required credentials (live run is gated on this)
`main.py` calls `Config.validate()` and **exits immediately** if `DISCORD_TOKEN` is missing or
left at the placeholder value. Provide it via a `DISCORD_TOKEN` environment variable (or a
`.env` file copied from `.env.example`). A real live run also needs the bot invited to a test
Discord guild with the **Server Members** and **Message Content** privileged intents enabled
(see `README.md`). `OWNER_ID` and `AGNES_API_KEY` (pet portrait images) are optional.

### Verifying without Discord credentials
Most of the codebase can be exercised offline (no token / no network): instantiate
`DiscordBot` from `main.py`, then `await bot.db.connect()` + `bot.db.initialize()` to build the
SQLite schema, `await bot.load_extension(...)` for each entry in `COGS`, and inspect
`bot.tree.get_commands()` to confirm the slash-command tree (currently ~54 top-level commands).
Do **not** call `bot.tree.sync()` or `bot.start()` offline — those require a live Discord login.
If you load cogs without starting the client, the `tasks.loop` background jobs (e.g.
`expire_polls`, `expire_giveaways`) raise a harmless `Client has not been properly initialised`
once the loop reaches `wait_until_ready()`; ignore it in offline harnesses.

### Lint / test
There is no test suite and no linter configuration committed in this repo.

### Harmless startup noise
`PyNaCl is not installed, voice will NOT be supported` (and a similar `davey` warning) are
expected — the bot uses no voice features.
