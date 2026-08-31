# Asia Leaderboard Bot

A fresh, simplified rebuild. Four boards, all Asia region: **Top 10**,
**Top 20**, **Top 30**, **Top 10 Mobile**. No dodge/protection/cooldown
system, no approval pipeline — every command acts directly and instantly.

This replaces everything before it. If you have an old `challenge_system.py`
in your repo, **delete it** — this bot is a single self-contained `bot.py`
and doesn't use it.

## 1. Create the bot on Discord

1. Go to https://discord.com/developers/applications → New Application.
2. Go to Bot → Add Bot.
3. No Privileged Gateway Intents needed (slash commands only).
4. Click Reset Token and copy it — this is your `DISCORD_BOT_TOKEN`. Never
   share this or commit it to a public repo.
5. Go to OAuth2 → URL Generator. Check scopes `bot` and
   `applications.commands`. Under bot permissions check: Send Messages,
   Embed Links, Read Message History. Copy the generated URL and open it to
   invite the bot to your server.

## 2. Host it

**On bot-hosting.net:**
1. Create a server there, select Python as the language.
2. Files tab → upload `bot.py`, `requirements.txt`, and `README.md`.
3. Rename `.env.example` to `.env`, open it, and fill in your real token and server ID:
   ```
   DISCORD_BOT_TOKEN=your-token-here
   DISCORD_GUILD_ID=your-server-id
   ```
   Upload that `.env` file too — the bot reads it automatically on startup.
   (If your panel's Startup tab has its own place to set environment
   variables, that works too and takes priority — the `.env` file is just
   a guaranteed fallback that works regardless of what your specific panel
   exposes.)
4. Startup tab → set the bot file to `bot.py`. Under "Additional Python
   packages" you can also just type `discord.py aiohttp python-dotenv` if
   it doesn't pick up `requirements.txt` automatically.
5. Start the server, check the console for `commands synced`.

**On Railway** (alternative):
```
pip install -r requirements.txt
export DISCORD_BOT_TOKEN="your-token-here"
export DISCORD_GUILD_ID="your-server-id"   # makes commands sync instantly
python bot.py
```

For always-on hosting: railway.app → New Project → Deploy from GitHub repo
→ add `DISCORD_BOT_TOKEN` and `DISCORD_GUILD_ID` as variables → deploy.

## 3. One-time setup

Post each board you want live:
```
/sendlb lb:<Top 10 / Top 20 / Top 30 / Top 10 Mobile>
```

## Commands

| Command | Who | What it does |
|---|---|---|
| `/createprofile` | LB role | Form: Discord username, Roblox username, country, nickname. Assigns a profile ID. |
| `/editprofile id:<id>` | LB role | Reopens the form pre-filled to update a profile. |
| `/deleteprofile id:<id>` | LB role | Deletes a profile. The ID is retired **permanently** — never reused, no renumbering. |
| `/scan discord_username:<name>` | LB role | Looks up a profile by Discord username. If none exists: "This player does not have a profile on file." |
| `/sendlb lb:<board>` | LB role | Posts a fresh board of vacant spots. |
| `/editspot lb board spot id stage` | LB role | Places a profile into a spot with a stage, pulling their Roblox avatar. |
| `/clearspot lb board spot` | LB role | Resets a spot back to Vacant. |
| `/setannouncement ...` | Referee role | Posts a fight announcement with an auto-incrementing set ID. |
| `/scoreannouncement id auto winner_name ...` | Referee role | Posts a set's result (auto-win + reason, or score + winner). |

`/createprofile`, `/deleteprofile`, `/editprofile`, `/scan`, `/sendlb`,
`/editspot`, `/clearspot` require the **LB role**
(`1543661239652061345` by default — override with `LB_ROLE_ID` on
Railway). `/setannouncement` and `/scoreannouncement` require the
**Referee role** (`1543661355423244348` — override with
`REFEREE_ROLE_ID`).

## Environment variables

All have working defaults baked in — only set these in Railway if you want
different roles/channels without redeploying:

`LB_ROLE_ID`, `REFEREE_ROLE_ID`, `ANNOUNCE_CHANNEL_ID`,
`ANNOUNCE_PING_ROLE_ID`, `SCORE_CHANNEL_ID`, `SCORE_PING_ROLE_ID`.

## How data is stored

JSON files in `data/`:
- `players.json` — every profile, keyed by ID.
- `id_counter.json` — the next profile ID to hand out. Never rewinds, even
  after a delete, so IDs are never reused.
- `boards.json` — for each board, which profile occupies each spot (if
  any), their stage, and the Discord message ID so the bot knows which
  embed to edit.
- `fights.json` — every announcement + its score (if scored), indexed so
  list position + 1 always equals the set's displayed ID.

Fine for a single-server bot with a modest player count.

## What's NOT in this build (by design — this was a deliberate simplification)

No dodge mechanic, no Protection/Cooldown status system, no Claim/Challenge
buttons, no private match channels, no review/approval pipeline, no
automatic winner-placement after a score. `/setannouncement` and
`/scoreannouncement` just post directly. If you want any of that back
later, it's a separate, much larger build — say so explicitly.

## Please read before relying on this in production

This could not be tested against a live Discord connection while it was
built (no network access in the build environment). Test every command in
a low-stakes channel first.
