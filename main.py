"""
Asia Leaderboard Bot.

Four boards, all Asia region: Top 10, Top 20, Top 30, Top 10 Mobile.
No dodge/protection/cooldown system, no review/approval pipeline — every
command acts directly. Simple by design.

Commands:
  /createprofile                      - register: discord username, roblox username, country, nickname. Assigns a profile ID.
  /deleteprofile <id>                 - deletes a profile. The ID is retired permanently, never reused.
  /editprofile <id>                   - edit an existing profile.
  /scan <discord_username>            - look up a profile by Discord username.
  /sendlb <lb>                        - posts a fresh board of vacant spots.
  /editspot <lb> <spot> <id> <stage>  - places a profile into a spot with a stage, pulling their Roblox avatar.
  /clearspot <lb> <spot>              - resets a spot back to Vacant.
  /setannouncement ...                - posts a fight announcement with an auto-incrementing set ID.
  /scoreannouncement ...              - posts a fight's result for a given set ID.

Storage: simple JSON files in ./data.
"""

import json
import os
import traceback
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads a .env file in the same folder as this script, if one exists
except ImportError:
    pass

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

LB_ROLE_ID = int(os.getenv("LB_ROLE_ID", "1543661239652061345"))
REFEREE_ROLE_ID = int(os.getenv("REFEREE_ROLE_ID", "1543661355423244348"))

ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "1543599283599835246"))
ANNOUNCE_PING_ROLE_ID = int(os.getenv("ANNOUNCE_PING_ROLE_ID", "1543659597213077695"))
SCORE_CHANNEL_ID = int(os.getenv("SCORE_CHANNEL_ID", "1543599318311764029"))
SCORE_PING_ROLE_ID = int(os.getenv("SCORE_PING_ROLE_ID", "1543659626762084513"))

LB_TYPES = {
    "top10": {"label": "Top 10 (Asia)", "size": 10},
    "top20": {"label": "Top 20 (Asia)", "size": 20},
    "top30": {"label": "Top 30 (Asia)", "size": 30},
    "top10mobile": {"label": "Top 10 Mobile (Asia)", "size": 10},
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")
ID_COUNTER_FILE = os.path.join(DATA_DIR, "id_counter.json")
BOARDS_FILE = os.path.join(DATA_DIR, "boards.json")
FIGHTS_FILE = os.path.join(DATA_DIR, "fights.json")

def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_players():
    return _load(PLAYERS_FILE, {})

def save_players(data):
    _save(PLAYERS_FILE, data)

def next_player_id():
    counter = _load(ID_COUNTER_FILE, {"next_id": 1})
    pid = f"{counter['next_id']:03d}"
    counter["next_id"] += 1
    _save(ID_COUNTER_FILE, counter)
    return pid

def load_boards():
    boards = _load(BOARDS_FILE, {})
    changed = False
    for key, info in LB_TYPES.items():
        if key not in boards:
            boards[key] = {}
            changed = True
        for spot in range(1, info["size"] + 1):
            s = str(spot)
            if s not in boards[key]:
                boards[key][s] = {"player_id": None, "message_id": None, "channel_id": None, "stage": None}
                changed = True
    if changed:
        _save(BOARDS_FILE, boards)
    return boards

def save_boards(data):
    _save(BOARDS_FILE, data)

def load_fights():
    return _load(FIGHTS_FILE, [])

def save_fights(data):
    _save(FIGHTS_FILE, data)

def find_profile_by_discord_username(players, discord_username):
    q = discord_username.lower().lstrip("@")
    for pid, profile in players.items():
        if profile.get("discord_username", "").lower() == q:
            return pid, profile
    return None, None

async def fetch_roblox_avatar_url(roblox_username):
    if not roblox_username:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [roblox_username], "excludeBannedUsers": False},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("data", [])
                if not results:
                    return None
                user_id = results[0]["id"]
            async with session.get(
                "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": "false"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp2:
                if resp2.status != 200:
                    return None
                data2 = await resp2.json()
                items = data2.get("data", [])
                if not items:
                    return None
                return items[0].get("imageUrl")
    except Exception:
        return None

# ---------------------------------------------------------------------------
# EMBEDS
# ---------------------------------------------------------------------------

def profile_embed(player_id, profile):
    e = discord.Embed(title=f"Player Profile — ID {player_id}", color=discord.Color.blurple())
    e.add_field(name="Nickname", value=profile.get("nickname", "—"), inline=True)
    e.add_field(name="Discord", value=profile.get("discord_username", "—"), inline=True)
    e.add_field(name="Roblox", value=profile.get("roblox_username", "—"), inline=True)
    e.add_field(name="Country", value=profile.get("country", "—"), inline=True)
    e.set_footer(text=f"Registered {profile.get('created_at', '—')}")
    return e

def vacant_spot_embed(spot):
    e = discord.Embed(title=f"#{spot}", description="```Vacant```", color=discord.Color.dark_gray())
    e.add_field(name="Player", value="—", inline=True)
    e.add_field(name="Roblox", value="—", inline=True)
    e.add_field(name="Country", value="—", inline=True)
    e.add_field(name="Stage", value="—", inline=True)
    return e

def filled_spot_embed(spot, profile, stage, avatar_url):
    discord_id = profile.get("discord_id")
    mention = f"<@{discord_id}>" if discord_id else f"@{profile.get('discord_username', profile.get('nickname'))}"
    e = discord.Embed(title=f"#{spot} — {profile.get('nickname', 'Unknown')}", color=discord.Color.blurple())
    e.add_field(name="Player", value=mention, inline=True)
    e.add_field(name="Roblox", value=profile.get("roblox_username", "—"), inline=True)
    e.add_field(name="Country", value=profile.get("country") or "—", inline=True)
    e.add_field(name="Stage", value=stage or "—", inline=True)
    if avatar_url:
        e.set_thumbnail(url=avatar_url)
    return e

def announcement_embed(fight):
    p1, p2 = fight["player1"], fight["player2"]
    title = f"⚔️  Set #{fight['id']:03d}"
    lines = [
        f"**{p1['name']}** ({p1['spot']})  🆚  **{p2['name']}** ({p2['spot']})",
        "",
        f"• **Day:** {fight['day']}",
        f"• **Time:** {fight['timing']} ({fight['gmt']})",
    ]
    e = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.gold())
    e.set_footer(text=f"Set #{fight['id']:03d}")
    return e

def score_embed(fight):
    score = fight["score"]
    title = f"🏆  Score for Set #{fight['id']:03d}"
    lines = [f"**Winner:** {score['winner_name']}", ""]
    if score.get("auto"):
        lines.append("• **Result:** Auto-win")
        lines.append(f"• **Reason:** {score.get('reason', '—')}")
    else:
        lines.append(f"• **Score:** {score.get('score_text', '—')}")
    e = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.green())
    e.set_footer(text=f"Set #{fight['id']:03d}")
    return e

# ---------------------------------------------------------------------------
# ROLE CHECKS
# ---------------------------------------------------------------------------

def _has_role(member, role_id):
    return any(r.id == role_id for r in getattr(member, "roles", []))

def is_lb_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        return _has_role(interaction.user, LB_ROLE_ID)
    return app_commands.check(predicate)

def is_referee_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        return _has_role(interaction.user, REFEREE_ROLE_ID)
    return app_commands.check(predicate)

# ---------------------------------------------------------------------------
# BOT SETUP
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"[on_ready] Logged in as {bot.user} (id={bot.user.id})")
    print(f"[on_ready] Connected to {len(bot.guilds)} guild(s): "
          f"{', '.join(f'{g.name} ({g.id})' for g in bot.guilds)}")
    if GUILD_ID:
        target_id = int(GUILD_ID)
        if not any(g.id == target_id for g in bot.guilds):
            print(f"[on_ready] WARNING: DISCORD_GUILD_ID={target_id} does not match any "
                  f"guild this bot is currently in. Commands will sync to that ID anyway "
                  f"if Discord accepts it, but they will NOT show up in your actual server "
                  f"unless the bot is a member of guild {target_id}. Double check the ID.")
        guild = discord.Object(id=target_id)
        # Copy the commands to the guild FIRST, while they still exist in the
        # local tree, then sync. Only AFTER that do we clear + sync an empty
        # global command list, to wipe out any stale global registration from
        # before DISCORD_GUILD_ID was set — clearing first would empty the
        # local tree before copy_global_to had anything left to copy.
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        print(f"[on_ready] Synced {len(synced)} command(s) to guild {target_id}: "
              f"{', '.join(c.name for c in synced)}")
        tree.clear_commands(guild=None)
        await tree.sync()
    else:
        synced = await tree.sync()
        print(f"[on_ready] Synced {len(synced)} command(s) globally (can take up to 1 hour "
              f"to appear — set DISCORD_GUILD_ID for instant sync): "
              f"{', '.join(c.name for c in synced)}")
    print("[on_ready] Ready.")

# ---------------------------------------------------------------------------
# PROFILE MODALS
# ---------------------------------------------------------------------------

class CreateProfileModal(discord.ui.Modal, title="Create Player Profile"):
    discord_username = discord.ui.TextInput(label="Discord Username", max_length=50)
    roblox_username = discord.ui.TextInput(label="Roblox Username", max_length=50)
    country = discord.ui.TextInput(label="Country", max_length=50)
    nickname = discord.ui.TextInput(label="Nickname", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        players = load_players()
        player_id = next_player_id()
        players[player_id] = {
            "discord_username": self.discord_username.value.strip(),
            "roblox_username": self.roblox_username.value.strip(),
            "country": self.country.value.strip(),
            "nickname": self.nickname.value.strip(),
            "discord_id": None,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        save_players(players)
        await interaction.response.send_message(
            content=f"Profile created! ID **{player_id}**.",
            embed=profile_embed(player_id, players[player_id]),
            ephemeral=True,
        )

@tree.command(name="createprofile", description="(LB role) Create a player profile")
@is_lb_role()
async def createprofile_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(CreateProfileModal())

class EditProfileModal(discord.ui.Modal, title="Edit Player Profile"):
    def __init__(self, player_id, profile):
        super().__init__()
        self.player_id = player_id
        self.discord_username = discord.ui.TextInput(label="Discord Username", default=profile.get("discord_username", ""), max_length=50)
        self.roblox_username = discord.ui.TextInput(label="Roblox Username", default=profile.get("roblox_username", ""), max_length=50)
        self.country = discord.ui.TextInput(label="Country", default=profile.get("country", ""), max_length=50)
        self.nickname = discord.ui.TextInput(label="Nickname", default=profile.get("nickname", ""), max_length=50)
        for item in (self.discord_username, self.roblox_username, self.country, self.nickname):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        players = load_players()
        if self.player_id not in players:
            await interaction.response.send_message("That profile no longer exists.", ephemeral=True)
            return
        players[self.player_id].update({
            "discord_username": self.discord_username.value.strip(),
            "roblox_username": self.roblox_username.value.strip(),
            "country": self.country.value.strip(),
            "nickname": self.nickname.value.strip(),
        })
        save_players(players)
        await interaction.response.send_message(
            content=f"Profile **{self.player_id}** updated.",
            embed=profile_embed(self.player_id, players[self.player_id]),
            ephemeral=True,
        )

@tree.command(name="editprofile", description="(LB role) Edit an existing player profile")
@app_commands.describe(id="The player ID to edit")
@is_lb_role()
async def editprofile_cmd(interaction: discord.Interaction, id: str):
    players = load_players()
    profile = players.get(id)
    if not profile:
        await interaction.response.send_message(f"No profile found for ID `{id}`.", ephemeral=True)
        return
    await interaction.response.send_modal(EditProfileModal(id, profile))

@tree.command(name="deleteprofile", description="(LB role) Permanently delete a player profile")
@app_commands.describe(id="The player ID to delete")
@is_lb_role()
async def deleteprofile_cmd(interaction: discord.Interaction, id: str):
    players = load_players()
    if id not in players:
        await interaction.response.send_message(f"No profile found for ID `{id}`.", ephemeral=True)
        return
    nickname = players[id].get("nickname", id)
    del players[id]
    save_players(players)

    boards = load_boards()
    for board in boards.values():
        for spot_entry in board.values():
            if spot_entry.get("player_id") == id:
                spot_entry["player_id"] = None
                spot_entry["stage"] = None
    save_boards(boards)

    await interaction.response.send_message(
        f"Deleted profile **{id}** ({nickname}). ID **{id}** is now permanently retired — it will not be reused.",
        ephemeral=True,
    )

@tree.command(name="scan", description="(LB role) Look up a profile by Discord username")
@app_commands.describe(discord_username="The player's Discord username")
@is_lb_role()
async def scan_cmd(interaction: discord.Interaction, discord_username: str):
    players = load_players()
    pid, profile = find_profile_by_discord_username(players, discord_username)
    if not profile:
        await interaction.response.send_message("This player does not have a profile on file.", ephemeral=True)
        return
    await interaction.response.send_message(embed=profile_embed(pid, profile))

# ---------------------------------------------------------------------------
# LEADERBOARD COMMANDS
# ---------------------------------------------------------------------------

@tree.command(name="sendlb", description="(LB role) Post a fresh leaderboard")
@app_commands.describe(lb="Which leaderboard to post")
@app_commands.choices(lb=[app_commands.Choice(name=info["label"], value=key) for key, info in LB_TYPES.items()])
@is_lb_role()
async def sendlb_cmd(interaction: discord.Interaction, lb: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    boards = load_boards()
    key = lb.value
    size = LB_TYPES[key]["size"]
    for spot in range(1, size + 1):
        msg = await interaction.channel.send(embed=vacant_spot_embed(spot))
        boards[key][str(spot)] = {"player_id": None, "message_id": msg.id, "channel_id": msg.channel.id, "stage": None}
    save_boards(boards)
    await interaction.followup.send(f"Posted a fresh {LB_TYPES[key]['label']} leaderboard ({size} spots).", ephemeral=True)

async def _refresh_spot(boards, key, spot, entry, profile, avatar_url):
    if not entry.get("message_id"):
        return
    channel = bot.get_channel(entry["channel_id"]) or await bot.fetch_channel(entry["channel_id"])
    message = await channel.fetch_message(entry["message_id"])
    embed = filled_spot_embed(spot, profile, entry.get("stage"), avatar_url) if profile else vacant_spot_embed(spot)
    await message.edit(embed=embed)

@tree.command(name="editspot", description="(LB role) Place a profile into a leaderboard spot")
@app_commands.describe(lb="Which leaderboard", spot="Spot number", id="Profile ID", stage="Stage to display")
@app_commands.choices(lb=[app_commands.Choice(name=info["label"], value=key) for key, info in LB_TYPES.items()])
@is_lb_role()
async def editspot_cmd(interaction: discord.Interaction, lb: app_commands.Choice[str], spot: int, id: str, stage: str):
    key = lb.value
    size = LB_TYPES[key]["size"]
    if not (1 <= spot <= size):
        await interaction.response.send_message(f"Spot must be between 1 and {size} for {LB_TYPES[key]['label']}.", ephemeral=True)
        return
    players = load_players()
    profile = players.get(id)
    if not profile:
        await interaction.response.send_message(f"No profile found for ID `{id}`.", ephemeral=True)
        return
    boards = load_boards()
    entry = boards[key][str(spot)]
    if not entry.get("message_id"):
        await interaction.response.send_message("That leaderboard hasn't been posted yet — run `/sendlb`.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    avatar_url = await fetch_roblox_avatar_url(profile.get("roblox_username", ""))
    entry["player_id"], entry["stage"] = id, stage
    await _refresh_spot(boards, key, spot, entry, profile, avatar_url)
    save_boards(boards)
    await interaction.followup.send(f"Updated {LB_TYPES[key]['label']} spot #{spot}.", ephemeral=True)

@tree.command(name="clearspot", description="(LB role) Reset a leaderboard spot back to Vacant")
@app_commands.describe(lb="Which leaderboard", spot="Spot number")
@app_commands.choices(lb=[app_commands.Choice(name=info["label"], value=key) for key, info in LB_TYPES.items()])
@is_lb_role()
async def clearspot_cmd(interaction: discord.Interaction, lb: app_commands.Choice[str], spot: int):
    key = lb.value
    size = LB_TYPES[key]["size"]
    if not (1 <= spot <= size):
        await interaction.response.send_message(f"Spot must be between 1 and {size} for {LB_TYPES[key]['label']}.", ephemeral=True)
        return
    boards = load_boards()
    entry = boards[key][str(spot)]
    if not entry.get("message_id"):
        await interaction.response.send_message("That leaderboard hasn't been posted yet — run `/sendlb`.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    entry["player_id"], entry["stage"] = None, None
    await _refresh_spot(boards, key, spot, entry, None, None)
    save_boards(boards)
    await interaction.followup.send(f"Cleared {LB_TYPES[key]['label']} spot #{spot}.", ephemeral=True)

# ---------------------------------------------------------------------------
# ANNOUNCEMENTS / SCORES
# ---------------------------------------------------------------------------

@tree.command(name="setannouncement", description="(Referee) Announce a set")
@app_commands.describe(
    player1_user="Player 1's Discord username", player1_spot="Player 1's spot (or Unranked)",
    player2_user="Player 2's Discord username", player2_spot="Player 2's spot (or Unranked)",
    day="Day of the set", timing="Time of the set", gmt="GMT/timezone",
)
@is_referee_role()
async def setannouncement_cmd(interaction: discord.Interaction, player1_user: str, player1_spot: str,
                               player2_user: str, player2_spot: str, day: str, timing: str, gmt: str):
    fights = load_fights()
    fight = {
        "id": len(fights) + 1,
        "player1": {"name": player1_user, "spot": player1_spot},
        "player2": {"name": player2_user, "spot": player2_spot},
        "day": day, "timing": timing, "gmt": gmt,
        "referee_id": interaction.user.id,
        "score": None,
    }
    fights.append(fight)
    save_fights(fights)

    announce_ch = bot.get_channel(ANNOUNCE_CHANNEL_ID) or await bot.fetch_channel(ANNOUNCE_CHANNEL_ID)
    ping_role = interaction.guild.get_role(ANNOUNCE_PING_ROLE_ID)
    await announce_ch.send(content=ping_role.mention if ping_role else "", embed=announcement_embed(fight))
    await interaction.response.send_message(f"Set #{fight['id']:03d} announced.", ephemeral=True)

@tree.command(name="scoreannouncement", description="(Referee) Announce a set's result")
@app_commands.describe(
    id="Set ID", auto="Was it an auto-win?", winner_name="Winner's name",
    reason="Reason (required if auto-win)", score="Score in winner-loser format (required if not auto-win)",
)
@is_referee_role()
async def scoreannouncement_cmd(interaction: discord.Interaction, id: int, auto: bool, winner_name: str,
                                 reason: str = None, score: str = None):
    fights = load_fights()
    idx = id - 1
    if idx < 0 or idx >= len(fights):
        await interaction.response.send_message("No set with that ID.", ephemeral=True)
        return
    if auto and not reason:
        await interaction.response.send_message("Auto-win needs a reason.", ephemeral=True)
        return
    if not auto and not score:
        await interaction.response.send_message("Non-auto-win needs a score (winner-loser format).", ephemeral=True)
        return

    fight = fights[idx]
    fight["score"] = {"auto": auto, "winner_name": winner_name, "reason": reason, "score_text": score}
    save_fights(fights)

    score_ch = bot.get_channel(SCORE_CHANNEL_ID) or await bot.fetch_channel(SCORE_CHANNEL_ID)
    ping_role = interaction.guild.get_role(SCORE_PING_ROLE_ID)
    await score_ch.send(content=ping_role.mention if ping_role else "", embed=score_embed(fight))
    await interaction.response.send_message(f"Score for set #{id:03d} announced.", ephemeral=True)

# ---------------------------------------------------------------------------
# GLOBAL ERROR HANDLER
# One handler for every command, instead of per-command handlers. This is
# the important addition in this rebuild: if ANYTHING goes wrong in ANY
# command, it will now always (a) print a full traceback to this console,
# and (b) tell the user in Discord that something broke, instead of failing
# silently. If a command still "does nothing" after this, the console will
# now show exactly why.
# ---------------------------------------------------------------------------

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        message = "You don't have the role required to use this command."
    else:
        print(f"[COMMAND ERROR] /{interaction.command.name if interaction.command else '?'} raised:")
        traceback.print_exception(type(error), error, error.__traceback__)
        message = f"Something went wrong running that command: `{type(error).__name__}: {error}`"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set the DISCORD_BOT_TOKEN environment variable before running the bot.")
    bot.run(TOKEN)
