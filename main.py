import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import json

# ============================================================
#  CONFIG
# ============================================================

DATA_FILE = "data.json"

# Your server's ID — makes slash commands sync INSTANTLY instead of waiting
# up to an hour for a global sync. Right-click your server icon in Discord
# (with Developer Mode on) → "Copy Server ID", then set it as the GUILD_ID
# environment variable wherever you host the bot (same place as DISCORD_TOKEN).
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# Role allowed to use profile / spot / sendlb commands
LB_ROLE_ID = 1543661239652061345
# Role allowed to use set / score announcement commands
ANNOUNCE_ROLE_ID = 1543661355423244348

# Set announcements
SET_ANNOUNCE_CHANNEL_ID = 1543599283599835246
SET_ANNOUNCE_ROLE_ID = 1543659597213077695

# Score announcements
SCORE_ANNOUNCE_CHANNEL_ID = 1543599318311764029
SCORE_ANNOUNCE_ROLE_ID = 1543659626762084513

BOARD_CONFIG = {
    "top10":       {"label": "Top 10 Asia",         "start": 1,  "end": 10},
    "top20":       {"label": "Top 20 Asia",         "start": 11, "end": 20},
    "top30":       {"label": "Top 30 Asia",         "start": 21, "end": 30},
    "top10mobile": {"label": "Top 10 Asia (Mobile)","start": 1,  "end": 10},
}

BOARD_CHOICES = [
    app_commands.Choice(name="Top 10 Asia", value="top10"),
    app_commands.Choice(name="Top 20 Asia", value="top20"),
    app_commands.Choice(name="Top 30 Asia", value="top30"),
    app_commands.Choice(name="Top 10 Asia (Mobile)", value="top10mobile"),
]

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

DEFAULT_DATA = {
    "profiles": {},
    "leaderboards": {k: {} for k in BOARD_CONFIG},
    "sets": {},
    "next_set_id": 1,
}

# ============================================================
#  STORAGE
# ============================================================


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return json.loads(json.dumps(DEFAULT_DATA))
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    for k, v in DEFAULT_DATA.items():
        if k not in loaded:
            loaded[k] = v
    for k in BOARD_CONFIG:
        if k not in loaded["leaderboards"]:
            loaded["leaderboards"][k] = {}
    return loaded


def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


data = load_data()


def get_next_profile_id() -> int:
    """Lowest free profile id — reuses ids left vacant by deletion."""
    existing = set(int(k) for k in data["profiles"].keys())
    i = 1
    while i in existing:
        i += 1
    return i


def find_profile_by_discord_id(discord_id: int):
    for pid, profile in data["profiles"].items():
        if profile["discord_id"] == discord_id:
            return pid, profile
    return None, None


# ============================================================
#  BOT / INTENTS
# ============================================================

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
#  PERMISSIONS
# ============================================================

def has_role(interaction: discord.Interaction, role_id: int) -> bool:
    member = interaction.user
    if isinstance(member, discord.Member):
        return member.guild_permissions.administrator or any(r.id == role_id for r in member.roles)
    return False


def lb_permission():
    def predicate(interaction: discord.Interaction) -> bool:
        return has_role(interaction, LB_ROLE_ID)
    return app_commands.check(predicate)


def announce_permission():
    def predicate(interaction: discord.Interaction) -> bool:
        return has_role(interaction, ANNOUNCE_ROLE_ID)
    return app_commands.check(predicate)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "🚫 You don't have permission to use this command."
    else:
        msg = f"⚠️ Something went wrong: `{error}`"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass
    if not isinstance(error, app_commands.CheckFailure):
        raise error


async def safe_get_channel(channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            channel = None
    return channel


# ============================================================
#  PROFILE COMMANDS
# ============================================================

@bot.tree.command(name="createprofile", description="Create a new player profile")
@lb_permission()
@app_commands.describe(
    discord_user="The discord user this profile belongs to",
    roblox_username="Roblox username",
    country_flag="Country flag emoji (e.g. 🇮🇳)",
    nickname="Nickname to show on the leaderboard",
)
async def createprofile(interaction: discord.Interaction, discord_user: discord.Member,
                         roblox_username: str, country_flag: str, nickname: str):
    pid = get_next_profile_id()
    data["profiles"][str(pid)] = {
        "discord_id": discord_user.id,
        "roblox_username": roblox_username,
        "flag": country_flag,
        "nickname": nickname,
    }
    save_data(data)

    embed = discord.Embed(title="✅ Profile Created", color=discord.Color.green())
    embed.add_field(name="Profile ID", value=f"`#{pid}`", inline=True)
    embed.add_field(name="Discord", value=discord_user.mention, inline=True)
    embed.add_field(name="Roblox", value=f"`{roblox_username}`", inline=True)
    embed.add_field(name="Country", value=country_flag, inline=True)
    embed.add_field(name="Nickname", value=nickname, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="deleteprofile", description="Delete a player profile")
@lb_permission()
@app_commands.describe(profile_id="The profile ID to delete")
async def deleteprofile(interaction: discord.Interaction, profile_id: int):
    key = str(profile_id)
    if key not in data["profiles"]:
        await interaction.response.send_message(f"❌ Profile `#{profile_id}` does not exist.", ephemeral=True)
        return

    del data["profiles"][key]
    # remove it from any leaderboard it was occupying — that spot becomes vacant
    for board in data["leaderboards"].values():
        for spot, entry in list(board.items()):
            if entry.get("profile_id") == profile_id:
                del board[spot]
    save_data(data)

    await interaction.response.send_message(
        f"🗑️ Profile `#{profile_id}` has been deleted. That ID is now vacant and can be reused.",
        ephemeral=True,
    )


@bot.tree.command(name="editprofile", description="Edit an existing player profile")
@lb_permission()
@app_commands.describe(
    profile_id="The profile ID to edit",
    discord_user="New discord user (leave blank to keep current)",
    roblox_username="New Roblox username (leave blank to keep current)",
    country_flag="New country flag (leave blank to keep current)",
    nickname="New nickname (leave blank to keep current)",
)
async def editprofile(interaction: discord.Interaction, profile_id: int,
                       discord_user: Optional[discord.Member] = None,
                       roblox_username: Optional[str] = None,
                       country_flag: Optional[str] = None,
                       nickname: Optional[str] = None):
    key = str(profile_id)
    if key not in data["profiles"]:
        await interaction.response.send_message(f"❌ Profile `#{profile_id}` does not exist.", ephemeral=True)
        return

    profile = data["profiles"][key]
    if discord_user is not None:
        profile["discord_id"] = discord_user.id
    if roblox_username is not None:
        profile["roblox_username"] = roblox_username
    if country_flag is not None:
        profile["flag"] = country_flag
    if nickname is not None:
        profile["nickname"] = nickname
    save_data(data)

    embed = discord.Embed(title=f"✏️ Profile #{profile_id} Updated", color=discord.Color.blurple())
    embed.add_field(name="Discord", value=f"<@{profile['discord_id']}>", inline=True)
    embed.add_field(name="Roblox", value=f"`{profile['roblox_username']}`", inline=True)
    embed.add_field(name="Country", value=profile["flag"], inline=True)
    embed.add_field(name="Nickname", value=profile["nickname"], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="scan", description="Look up a player's profile")
@lb_permission()
@app_commands.describe(discord_user="The discord user to scan")
async def scan(interaction: discord.Interaction, discord_user: discord.Member):
    pid, profile = find_profile_by_discord_id(discord_user.id)

    if not profile:
        embed = discord.Embed(
            title="No Profile Found",
            description=f"Unfortunately, {discord_user.mention} does not currently have a registered profile.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(title=f"🔍 Profile #{pid}", color=discord.Color.blurple())
    embed.add_field(name="Discord", value=discord_user.mention, inline=True)
    embed.add_field(name="Roblox", value=f"`{profile['roblox_username']}`", inline=True)
    embed.add_field(name="Country", value=profile["flag"], inline=True)
    embed.add_field(name="Nickname", value=profile["nickname"], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================
#  LEADERBOARD COMMANDS
# ============================================================

# Color for an occupied spot's side-bar. Vacant spots get no color (plain gray bar).
FILLED_COLOR = discord.Color.red()


def build_leaderboard_embeds(guild: Optional[discord.Guild], board_key: str) -> list[discord.Embed]:
    """One embed per rank — mirrors a classic slot-style leaderboard layout:
    title = '#rank name', description = '| @mention |' + '«««| • roblox • |»»»',
    separate Country / Stage fields, small avatar thumbnail on the side."""
    cfg = BOARD_CONFIG[board_key]
    board = data["leaderboards"].get(board_key, {})
    embeds = []

    for rank in range(cfg["start"], cfg["end"] + 1):
        entry = board.get(str(rank))
        profile = data["profiles"].get(str(entry["profile_id"])) if entry else None

        if entry and profile:
            embed = discord.Embed(
                title=f"#{rank} {profile['nickname']}",
                description=(
                    f"| <@{profile['discord_id']}> |\n"
                    f"«««| • {profile['roblox_username']} • |»»»"
                ),
                color=FILLED_COLOR,
            )
            embed.add_field(name="Country", value=profile["flag"], inline=True)
            embed.add_field(name="Stage", value=entry["stage"], inline=True)

            member = guild.get_member(profile["discord_id"]) if guild else None
            if member:
                embed.set_thumbnail(url=member.display_avatar.url)
        else:
            embed = discord.Embed(
                title=f"#{rank} Vacant",
                description="| Vacant |\n«««| • Vacant • |»»»",
                color=discord.Color.default(),
            )
            embed.add_field(name="Country", value="—", inline=True)
            embed.add_field(name="Stage", value="—", inline=True)

        embeds.append(embed)

    return embeds


@bot.tree.command(name="sendlb", description="Post a leaderboard")
@lb_permission()
@app_commands.choices(lb=BOARD_CHOICES)
async def sendlb(interaction: discord.Interaction, lb: app_commands.Choice[str]):
    embeds = build_leaderboard_embeds(interaction.guild, lb.value)
    # Each board has exactly 10 spots, and Discord allows up to 10 embeds per
    # message, so the whole board always fits in a single message.
    await interaction.response.send_message(embeds=embeds)


@bot.tree.command(name="editspot", description="Assign a profile to a leaderboard spot")
@lb_permission()
@app_commands.choices(lb=BOARD_CHOICES)
@app_commands.describe(
    spot="Spot number on this leaderboard",
    profile_id="Profile ID to place at this spot",
    stage="Stage text (e.g. '2 Mid Strong')",
)
async def editspot(interaction: discord.Interaction, lb: app_commands.Choice[str],
                    spot: int, profile_id: int, stage: str):
    cfg = BOARD_CONFIG[lb.value]
    if not (cfg["start"] <= spot <= cfg["end"]):
        await interaction.response.send_message(
            f"❌ `{cfg['label']}` only accepts spots between {cfg['start']} and {cfg['end']}.",
            ephemeral=True,
        )
        return

    if str(profile_id) not in data["profiles"]:
        await interaction.response.send_message(f"❌ Profile `#{profile_id}` does not exist.", ephemeral=True)
        return

    data["leaderboards"][lb.value][str(spot)] = {"profile_id": profile_id, "stage": stage}
    save_data(data)

    profile = data["profiles"][str(profile_id)]
    embed = discord.Embed(title=f"📌 Spot Updated — {cfg['label']}", color=discord.Color.gold())
    embed.add_field(name="Spot", value=f"#{spot}", inline=True)
    embed.add_field(name="Player", value=f"<@{profile['discord_id']}> ({profile['nickname']})", inline=True)
    embed.add_field(name="Stage", value=stage, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="clearspot", description="Clear an entire leaderboard")
@lb_permission()
@app_commands.choices(lb=BOARD_CHOICES)
async def clearspot(interaction: discord.Interaction, lb: app_commands.Choice[str]):
    data["leaderboards"][lb.value] = {}
    save_data(data)
    cfg = BOARD_CONFIG[lb.value]
    await interaction.response.send_message(
        f"🧹 `{cfg['label']}` has been cleared — every spot is now vacant.", ephemeral=True
    )


# ============================================================
#  SET / SCORE ANNOUNCEMENTS
# ============================================================

@bot.tree.command(name="setannouncement", description="Announce a new set")
@announce_permission()
@app_commands.describe(
    player1="First player",
    player1_spot="First player's leaderboard spot (e.g. 'Top 10 Asia #3')",
    player2="Second player",
    player2_spot="Second player's leaderboard spot",
    date="Date of the set (e.g. 12 Sept 2026)",
    timing="Time of the set (e.g. 8:00 PM)",
    gmt="Timezone offset (e.g. GMT+5:30)",
)
async def setannouncement(interaction: discord.Interaction, player1: discord.Member, player1_spot: str,
                           player2: discord.Member, player2_spot: str, date: str, timing: str, gmt: str):
    set_id = data["next_set_id"]
    data["next_set_id"] += 1
    data["sets"][str(set_id)] = {
        "player1_id": player1.id,
        "player1_spot": player1_spot,
        "player2_id": player2.id,
        "player2_spot": player2_spot,
        "date": date,
        "timing": timing,
        "gmt": gmt,
        "score": None,
    }
    save_data(data)

    channel = await safe_get_channel(SET_ANNOUNCE_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("❌ Couldn't find the set-announcement channel.", ephemeral=True)
        return

    embed = discord.Embed(
        title="⚔️   NEW SET ANNOUNCED   ⚔️",
        description=(
            f"# {player1.display_name}  🆚  {player2.display_name}\n\n"
            f"**{player1.mention}**\n> Spot: `{player1_spot}`\n\n"
            f"**{player2.mention}**\n> Spot: `{player2_spot}`\n\n"
            f"🗓️ **Date:** {date}\n"
            f"⏰ **Time:** {timing}  ({gmt})"
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text=f"Set ID #{set_id} • TSBMC")

    content = f"<@&{SET_ANNOUNCE_ROLE_ID}>  {player1.mention}  {player2.mention}"
    await channel.send(content=content, embed=embed)
    await interaction.response.send_message(
        f"✅ Set `#{set_id}` announced in <#{SET_ANNOUNCE_CHANNEL_ID}>.", ephemeral=True
    )


@bot.tree.command(name="scoreannouncement", description="Announce the result of a set")
@announce_permission()
@app_commands.describe(
    set_id="The ID of the set being scored",
    auto="True if this was an automatic win (forfeit/disconnect), false if it was played out",
    winner="The winner of the set",
    reason="Reason for the automatic win (required if auto = true)",
    score="Score in winner-loser format, e.g. 3-1 (required if auto = false)",
)
async def scoreannouncement(interaction: discord.Interaction, set_id: int, auto: bool,
                             winner: discord.Member,
                             reason: Optional[str] = None,
                             score: Optional[str] = None):
    key = str(set_id)
    if key not in data["sets"]:
        await interaction.response.send_message(f"❌ Set `#{set_id}` does not exist.", ephemeral=True)
        return
    if auto and not reason:
        await interaction.response.send_message("❌ `reason` is required when `auto` is true.", ephemeral=True)
        return
    if not auto and not score:
        await interaction.response.send_message("❌ `score` is required when `auto` is false.", ephemeral=True)
        return

    set_info = data["sets"][key]
    set_info["score"] = {"auto": auto, "reason": reason, "score": score, "winner_id": winner.id}
    save_data(data)

    guild = interaction.guild
    p1 = guild.get_member(set_info["player1_id"]) if guild else None
    p2 = guild.get_member(set_info["player2_id"]) if guild else None
    p1_mention = p1.mention if p1 else f"<@{set_info['player1_id']}>"
    p2_mention = p2.mention if p2 else f"<@{set_info['player2_id']}>"
    p1_name = p1.display_name if p1 else "Unknown"
    p2_name = p2.display_name if p2 else "Unknown"

    channel = await safe_get_channel(SCORE_ANNOUNCE_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("❌ Couldn't find the score-announcement channel.", ephemeral=True)
        return

    if auto:
        result_line = f"🏆 **Winner:** {winner.mention}\n⚠️ **Won by default** — {reason}"
    else:
        result_line = f"🏆 **Winner:** {winner.mention}\n📊 **Score:** `{score}`"

    embed = discord.Embed(
        title="🎉   SET RESULT   🎉",
        description=(
            f"# {p1_name}  🆚  {p2_name}\n\n"
            f"**{p1_mention}**\n> Spot: `{set_info['player1_spot']}`\n\n"
            f"**{p2_mention}**\n> Spot: `{set_info['player2_spot']}`\n\n"
            f"🗓️ {set_info['date']}  ·  ⏰ {set_info['timing']}  ({set_info['gmt']})\n\n"
            f"{result_line}"
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Set ID #{set_id} • TSBMC")

    content = f"<@&{SCORE_ANNOUNCE_ROLE_ID}>  {p1_mention}  {p2_mention}"
    await channel.send(content=content, embed=embed)
    await interaction.response.send_message(
        f"✅ Result for set `#{set_id}` announced in <#{SCORE_ANNOUNCE_CHANNEL_ID}>.", ephemeral=True
    )


# ============================================================
#  STARTUP
# ============================================================

@bot.event
async def on_ready():
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[on_ready] Logged in as {bot.user} — synced {len(synced)} command(s) "
              f"to guild {GUILD_ID}: {', '.join(c.name for c in synced)}")
    except Exception as e:
        print(f"[on_ready] Failed to sync commands to guild {GUILD_ID}: {e}")


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        raise SystemExit("❌ DISCORD_TOKEN environment variable is not set.")
    if not GUILD_ID:
        raise SystemExit("❌ GUILD_ID environment variable is not set (or is 0).")
    bot.run(TOKEN)
