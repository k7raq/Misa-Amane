# TSBMC Leaderboard Bot — Setup

## 1. Files
- `main.py` — the bot (must stay named `main.py` for most hosting panels)
- `requirements.txt` — dependencies
- `data.json` — auto-created on first run, stores profiles/leaderboards/sets

## 2. Discord Developer Portal
1. Go to https://discord.com/developers/applications → your bot.
2. **Bot** tab → turn ON **Server Members Intent**.
3. **OAuth2 → URL Generator** → scopes: `bot`, `applications.commands`.
   Permissions: Send Messages, Embed Links, Mention Everyone (for role pings), Read Message History.
4. Invite the bot to your server with the generated link.

## 3. Environment variables
Set both of these wherever you host it (most panels have a "Secrets" or "Environment Variables" section):
- `DISCORD_TOKEN` — your bot's token
- `GUILD_ID` — your server's ID (Developer Mode on → right-click your server icon → Copy Server ID). This makes commands sync instantly instead of taking up to an hour globally.

## 4. Install & run
```
pip install -r requirements.txt
python main.py
```
On startup you should see:
```
[on_ready] Logged in as YourBot#0000 — synced 11 command(s): sendlb, createprofile, ...
```

## 5. Roles & channels to double check
`GUILD_ID` is now an environment variable (see step 3), not a code edit. These other ones are still constants at the top of `main.py` — update them if anything changes:
- `LB_ROLE_ID` — can use profile/spot/sendlb commands
- `ANNOUNCE_ROLE_ID` — can use set/score announcement commands
- `SET_ANNOUNCE_CHANNEL_ID` / `SET_ANNOUNCE_ROLE_ID`
- `SCORE_ANNOUNCE_CHANNEL_ID` / `SCORE_ANNOUNCE_ROLE_ID`

## 6. Commands
| Command | What it does |
|---|---|
| `/sendlb` | Posts the Top 10 / Top 20 / Top 30 / Top 10 Mobile leaderboard |
| `/createprofile` | Registers a new player (discord user, roblox name, flag, nickname) — auto-assigns the lowest free profile ID |
| `/deleteprofile` | Deletes a profile; its ID becomes vacant and reusable |
| `/editprofile` | Edits any field on an existing profile |
| `/scan` | Looks up a player's profile — reply is private (only you see it) |
| `/editspot` | Places a profile + stage into a specific leaderboard spot |
| `/clearspot` | Wipes an entire leaderboard back to vacant |
| `/setannouncement` | Announces an upcoming set (pings both players + role in the set-announcement channel) |
| `/scoreannouncement` | Announces a result, pulling the full matchup from the set ID (pings both players + role in the score channel) |

### Notes on the numbering
- Top 10 → spots 1–10
- Top 20 → spots 11–20 (continues on from Top 10)
- Top 30 → spots 21–30
- Top 10 Mobile → its own separate 1–10

### Notes on player mentions in the leaderboard
Players are tagged with `<@id>` inside the embed, so their name renders as a clickable mention — but embed mentions don't trigger a notification ping, so refreshing the leaderboard won't spam everyone. `/setannouncement` and `/scoreannouncement` ping for real (they're in the message content, not the embed) since those are one-off events people should be notified about.
