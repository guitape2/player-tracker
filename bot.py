import discord
import asyncio
import os
import time
from mcstatus import JavaServer

TOKEN = os.environ["DISCORD_TOKEN"]
MC_HOST = os.environ["MC_HOST"]
MC_PORT = int(os.environ.get("MC_PORT", 25565))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

trackers = {}
previously_online = set()
hourly_subscribers = []
players_this_hour = set()

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
    global previously_online, players_this_hour
    await client.wait_until_ready()
    last_hour_report = time.time()

    while not client.is_closed():
        current_players, count = await get_players()
        new_players = current_players - previously_online

        players_this_hour.update(new_players)

        for player in new_players:
            for key, entries in trackers.items():
                if player.lower() == key:
                    for (user_id, channel_id) in entries:
                        channel = client.get_channel(channel_id)
                        if channel:
                            await channel.send(
                                f"<@{user_id}> **{player}** vient de se connecter ! "
                                f"({count} joueur(s) en ligne)"
                            )

        previously_online = current_players

        if time.time() - last_hour_report >= 3600:
            last_hour_report = time.time()
            nb = len(players_this_hour)
            liste = ", ".join(f"**{p}**" for p in sorted(players_this_hour)) if players_this_hour else "aucun"
            for (user_id, channel_id) in hourly_subscribers:
                channel = client.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"<@{user_id}> Rapport horaire : **{nb}** joueur(s) connecté(s) cette heure → {liste}"
                    )
            players_this_hour = set()

        await asyncio.sleep(30)

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
        await message.channel.send(f"Tu seras pingé quand **{pseudo}** se connecte.")

    elif content.startswith("!untrack "):
        pseudo = content[9:].strip()
        key = pseudo.lower()
        if key in trackers:
            trackers[key] = [e for e in trackers[key] if e[0] != message.author.id]
        await message.channel.send(f"Alerte désactivée pour **{pseudo}**.")

    elif content == "!trackers":
        actifs = [k for k, v in trackers.items() if any(e[0] == message.author.id for e in v)]
        if actifs:
            await message.channel.send("Tes alertes actives : " + ", ".join(f"**{p}**" for p in actifs))
        else:
            await message.channel.send("Tu n'as aucune alerte active.")

    elif content == "!rapport":
        entry = (message.author.id, message.channel.id)
        if entry not in hourly_subscribers:
            hourly_subscribers.append(entry)
            await message.channel.send("Tu recevras un rapport toutes les heures.")
        else:
            await message.channel.send("Tu es déjà abonné au rapport horaire.")

    elif content == "!stoprapport":
        entry = (message.author.id, message.channel.id)
        if entry in hourly_subscribers:
            hourly_subscribers.remove(entry)
            await message.channel.send("Rapport horaire désactivé.")
        else:
            await message.channel.send("Tu n'étais pas abonné.")

client.run(TOKEN)
