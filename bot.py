import discord
import asyncio
import os
from mcstatus import JavaServer

TOKEN = os.environ["DISCORD_TOKEN"]
MC_HOST = os.environ["MC_HOST"]
MC_PORT = int(os.environ.get("MC_PORT", 25565))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# { "pseudo_lower": [(user_id, channel_id), ...] }
trackers = {}
previously_online = set()

async def get_players():
    try:
        server = JavaServer(MC_HOST, MC_PORT)
        status = await asyncio.to_thread(server.status)
        if status.players.sample:
            return {p.name for p in status.players.sample}, status.players.online
        return set(), status.players.online
    except Exception:
        return set(), 0

async def monitor_loop():
    global previously_online
    await client.wait_until_ready()
    while not client.is_closed():
        current_players, count = await get_players()

        # Joueurs qui viennent de se connecter
        new_players = current_players - previously_online

        for player in new_players:
            player_lower = player.lower()
            if player_lower in trackers:
                for (user_id, channel_id) in trackers[player_lower]:
                    channel = client.get_channel(channel_id)
                    user = client.get_user(user_id)
                    if channel and user:
                        await channel.send(
                            f"<@{user_id}> **{player}** vient de se connecter sur le serveur ! "
                            f"({count} joueur(s) en ligne)"
                        )

        previously_online = current_players
        await asyncio.sleep(30)  # vérifie toutes les 30 secondes

@client.event
async def on_ready():
    print(f"Bot connecté : {client.user}")
    client.loop.create_task(monitor_loop())

@client.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    if content == "!joueurs":
        players, count = await get_players()
        if count == 0:
            await message.channel.send("Aucun joueur connecté (ou serveur hors ligne).")
        elif not players:
            await message.channel.send(f"**{count}** joueur(s) en ligne (noms masqués par le serveur).")
        else:
            liste = "\n".join(f"• {p}" for p in sorted(players))
            await message.channel.send(f"**{count}** joueur(s) en ligne :\n{liste}")

    elif content.startswith("!tracker "):
        pseudo = content[9:].strip()
        if not pseudo:
            await message.channel.send("Usage : `!tracker <pseudo>`")
            return
        key = pseudo.lower()
        if key not in trackers:
            trackers[key] = []
        entry = (message.author.id, message.channel.id)
        if entry not in trackers[key]:
            trackers[key].append(entry)
        await message.channel.send(
            f"Tu seras ping quand **{pseudo}** se connecte."
        )

    elif content.startswith("!untrack "):
        pseudo = content[9:].strip()
        key = pseudo.lower()
        if key in trackers:
            trackers[key] = [
                e for e in trackers[key] if e[0] != message.author.id
            ]
        await message.channel.send(f"Alerte désactivée pour **{pseudo}**.")

    elif content == "!trackers":
        actifs = [k for k, v in trackers.items() if any(e[0] == message.author.id for e in v)]
        if actifs:
            await message.channel.send("Tes alertes actives : " + ", ".join(f"**{p}**" for p in actifs))
        else:
            await message.channel.send("Tu n'as aucune alerte active.")

client.run(TOKEN)
