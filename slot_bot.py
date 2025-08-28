import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
from datetime import datetime, timedelta
from keep_alive import keep_alive
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

# ---------------- CONFIG ----------------
CATEGORY_ID = 1410401659670233110  # ID de ta catégorie
# ----------------------------------------

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# slots[channel_id] = {"user": user_id, "expire": datetime, "duration_text": str, "pings_today": int, "last_reset": datetime, "max_pings": int}
slots = {}

# ---------------- UTILS ----------------
def parse_duration(s: str):
    pattern = r'(\d+)([smhj])'
    matches = re.findall(pattern, s.lower())
    total_seconds = 0
    for value, unit in matches:
        value = int(value)
        if unit == 's':
            total_seconds += value
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 'h':
            total_seconds += value * 3600
        elif unit == 'j':
            total_seconds += value * 86400
    return total_seconds

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        await bot.tree.sync()
        print("📌 Slash commands synchronisées")
    except Exception as e:
        print(f"Erreur sync: {e}")

    # Définir l'activité du bot en streaming (seul Twitch/YouTube créent le bouton "Regarder")
    activity = discord.Streaming(
        name="by 709",
        url="https://www.twitch.tv/discord"  # doit être Twitch ou YouTube
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

# ---------------- COMMANDES ----------------
@bot.tree.command(name="createslot", description="Créer un slot temporaire pour un utilisateur")
@app_commands.checks.has_permissions(administrator=True)
async def createslot(interaction: discord.Interaction, durée: str, utilisateur: discord.Member, pings: int):
    guild = interaction.guild
    category = guild.get_channel(CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("❌ Catégorie invalide.", ephemeral=True)
        return

    duration_seconds = parse_duration(durée)
    if duration_seconds <= 0:
        await interaction.response.send_message("❌ Durée invalide.", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        utilisateur: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }

    channel = await guild.create_text_channel(
        name=f"slot-{utilisateur.name}",
        overwrites=overwrites,
        category=category
    )

    expire_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
    slots[channel.id] = {
        "user": utilisateur.id,
        "expire": expire_time,
        "duration_text": durée,
        "pings_today": 0,
        "last_reset": datetime.utcnow().date(),
        "max_pings": pings
    }

    embed = discord.Embed(
        title="🎟️ Nouveau Slot",
        description=f"{utilisateur.mention}, ton slot a été créé !",
        color=discord.Color.green()
    )
    embed.add_field(name="Durée", value=f"{durée}", inline=True)
    embed.add_field(name="Pings autorisés", value=f"{pings} @everyone/@here par jour", inline=True)
    embed.add_field(name="Propriétaire", value=f"{utilisateur.mention}", inline=True)
    embed.add_field(name="Salon", value=f"{channel.mention}", inline=True)
    embed.set_footer(text=f"Créé par {interaction.user} • Slot actif jusqu'à la fin de la durée")
    embed.set_thumbnail(url=utilisateur.display_avatar.url)

    await channel.send(content=utilisateur.mention, embed=embed)
    await interaction.response.send_message(f"✅ Slot créé pour {utilisateur.mention}", ephemeral=True)

    async def auto_delete():
        await asyncio.sleep(duration_seconds)
        if channel.id in slots:
            await channel.delete()
            del slots[channel.id]

    bot.loop.create_task(auto_delete())

@bot.tree.command(name="modifie", description="Modifier un slot existant (durée ou pings)")
@app_commands.checks.has_permissions(administrator=True)
async def modifie(interaction: discord.Interaction, channel: discord.TextChannel, durée: str = None, pings: int = None):
    if channel.id not in slots:
        await interaction.response.send_message("❌ Ce salon n’est pas un slot valide.", ephemeral=True)
        return

    slot = slots[channel.id]

    if durée:
        duration_seconds = parse_duration(durée)
        slot["expire"] = datetime.utcnow() + timedelta(seconds=duration_seconds)
        slot["duration_text"] = durée
    if pings is not None:
        slot["max_pings"] = pings

    embed = discord.Embed(
        title="✏️ Slot modifié",
        color=discord.Color.orange()
    )
    embed.add_field(name="Durée", value=f"{slot['duration_text']}", inline=True)
    embed.add_field(name="Pings autorisés", value=f"{slot['max_pings']}", inline=True)
    embed.add_field(name="Propriétaire", value=f"<@{slot['user']}>", inline=True)
    embed.set_footer(text=f"Salon : {channel.name}")
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Slot modifié pour {channel.mention}", ephemeral=True)

@bot.tree.command(name="infoslot", description="Voir les informations de ton slot")
async def infoslot(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    if channel_id not in slots:
        await interaction.response.send_message("❌ Ce salon n’est pas un slot valide.", ephemeral=True)
        return

    slot = slots[channel_id]
    if interaction.user.id != slot["user"] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu n’as pas la permission de voir ce slot.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📊 Informations Slot",
        color=discord.Color.blue()
    )
    embed.add_field(name="Propriétaire", value=f"<@{slot['user']}>", inline=True)
    embed.add_field(name="Durée", value=f"{slot['duration_text']}", inline=True)
    embed.add_field(name="Pings autorisés", value=f"{slot['max_pings']}", inline=True)
    embed.add_field(name="Pings utilisés", value=f"{slot['pings_today']}", inline=True)
    embed.add_field(name="Pings restants", value=f"{max(slot['max_pings'] - slot['pings_today'],0)}", inline=True)
    embed.add_field(name="Salon", value=f"{interaction.channel.mention}", inline=True)
    embed.set_footer(text=f"Salon : {interaction.channel.name}")
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="transfer", description="Transférer la crown d'un slot à un autre utilisateur")
@app_commands.checks.has_permissions(administrator=True)
async def transfer(interaction: discord.Interaction, channel: discord.TextChannel, utilisateur: discord.Member):
    if channel.id not in slots:
        await interaction.response.send_message("❌ Ce salon n’est pas un slot valide.", ephemeral=True)
        return
    slot = slots[channel.id]
    old_user_id = slot['user']
    if old_user_id == utilisateur.id:
        await interaction.response.send_message("❌ L'utilisateur est déjà le propriétaire.", ephemeral=True)
        return

    slot['user'] = utilisateur.id

    # Met à jour permissions
    await channel.set_permissions(discord.Object(id=old_user_id), send_messages=False)
    await channel.set_permissions(utilisateur, send_messages=True)

    embed = discord.Embed(
        title="👑 Crown transférée",
        description=f"La crown du slot a été transférée à {utilisateur.mention}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Ancien propriétaire", value=f"<@{old_user_id}>", inline=True)
    embed.add_field(name="Nouveau propriétaire", value=f"{utilisateur.mention}", inline=True)
    embed.set_footer(text=f"Salon : {channel.name}")
    embed.set_thumbnail(url=utilisateur.display_avatar.url)

    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Crown transférée à {utilisateur.mention}", ephemeral=True)

# ---------------- LIMITATION PINGS ----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    if channel_id in slots:
        slot = slots[channel_id]
        if message.author.id == slot["user"]:
            today = datetime.utcnow().date()
            if slot["last_reset"] != today:
                slot["pings_today"] = 0
                slot["last_reset"] = today

            if message.mention_everyone:
                if slot["pings_today"] + 1 > slot["max_pings"]:
                    await message.delete()
                    embed = discord.Embed(
                        title="🚫 Limite de pings atteinte",
                        description=f"Tu as atteint la limite de **{slot['max_pings']} pings @everyone/@here par jour**.",
                        color=discord.Color.red()
                    )
                    await message.channel.send(embed=embed, delete_after=8)
                    return
                else:
                    slot["pings_today"] += 1
                    rest = max(slot['max_pings'] - slot['pings_today'], 0)
                    embed = discord.Embed(
                        title="🔔 Ping effectué",
                        description=f"Tu as **{rest} pings @everyone/@here restants** aujourd'hui.",
                        color=discord.Color.green()
                    )
                    await message.channel.send(embed=embed, delete_after=8)

    await bot.process_commands(message)

# ---------------- ERREURS ----------------
@createslot.error
@modifie.error
@transfer.error
async def command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Tu n’as pas la permission d’utiliser cette commande.", ephemeral=True)


keep_alive()
bot.run(token)
