import discord
import asyncio
import os
import time
from mcstatus import JavaServer

TOKEN = os.environ["DISCORD_TOKEN"]
MC_HOST = os.environ["MC_HOST"]
MC_PORT = int(os.environ.get("MC_PORT", 25565))

CHANNEL_ALERTES = 1499796586014707885
CHANNEL_RAPPORTS = 1499796588200198286
CHANNEL_COMMANDES = 1499796590112538874
CHANNEL_JOUEURS_SURVEILLES = 1499796600728326436

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

    channel_alertes = client.get_channel(CHANNEL_ALERTES)
    channel_rapports = client.get_channel(CHANNEL_RAPPORTS)

    while not client.is_closed():
        current_players, count = await get_players()
        new_players = current_players - previously_online

        players_this_hour.update(new_players)

        for player in new_players:
            for key, entries in trackers.items():
                if player.lower() == key:
                    for (user_id, _) in entries:
                        if channel_alertes:
                            await channel_alertes.send(
                                f"<@{user_id}> **{player}** vient de se connecter ! "
                                f"({count} joueur(s) en ligne)"
                            )

        previously_online = current_players

        if time.time() - last_hour_report >= 3600:
            last_hour_report = time.time()
            nb = len(players_this_hour)
            liste = ", ".join(f"**{p}**" for p in sorted(players_this_hour)) if players_this_hour else "aucun"
            for (user_id, _) in hourly_subscribers:
                if channel_rapports:
                    await channel_rapports.send(
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

    if message.channel.id != CHANNEL_COMMANDES:
        return

    content = message.content.strip()
    channel_commandes = client.get_channel(CHANNEL_COMMANDES)
    channel_joueurs = client.get_channel(CHANNEL_JOUEURS_SURVEILLES)

    if content == "!joueurs":
        players, count = await get_players()
        if count == 0:
            await channel_commandes.send("Aucun joueur connecté (ou serveur hors ligne).")
        elif not players:
            await channel_commandes.send(f"**{count}** joueur(s) en ligne (noms masqués par le serveur).")
        else:
            liste = "\n".join(f"• {p}" for p in sorted(players))
            await channel_commandes.send(f"**{count}** joueur(s) en ligne :\n{liste}")

    elif content.startswith("!tracker "):
        pseudo = content[9:].strip()
        if not pseudo:
            await channel_commandes.send("Usage : `!tracker <pseudo>`")
            return
        key = pseudo.lower()
        if key not in trackers:
            trackers[key] = []
        entry = (message.author.id, message.channel.id)
        if entry not in trackers[key]:
            trackers[key].append(entry)
        await channel_commandes.send(f"Tu seras pingé quand **{pseudo}** se connecte.")
        if channel_joueurs:
            await channel_joueurs.send(f"+ **{pseudo}** ajouté au tracking par <@{message.author.id}>")

    elif content.startswith("!untrack "):
        pseudo = content[9:].strip()
        key = pseudo.lower()
        if key in trackers:
            trackers[key] = [e for e in trackers[key] if e[0] != message.author.id]
        await channel_commandes.send(f"Alerte désactivée pour **{pseudo}**.")
        if channel_joueurs:
            await channel_joueurs.send(f"- **{pseudo}** retiré du tracking par <@{message.author.id}>")

    elif content == "!trackers":
        actifs = [k for k, v in trackers.items() if any(e[0] == message.author.id for e in v)]
        if actifs:
            await channel_commandes.send("Tes alertes actives : " + ", ".join(f"**{p}**" for p in actifs))
        else:
            await channel_commandes.send("Tu n'as aucune alerte active.")

    elif content == "!rapport":
        entry = (message.author.id, message.channel.id)
        if entry not in hourly_subscribers:
            hourly_subscribers.append(entry)
            await channel_commandes.send("Tu recevras un rapport toutes les heures dans #rapports.")
        else:
            await channel_commandes.send("Tu es déjà abonné au rapport horaire.")

    elif content == "!stoprapport":
        entry = (message.author.id, message.channel.id)
        if entry in hourly_subscribers:
            hourly_subscribers.remove(entry)
            await channel_commandes.send("Rapport horaire désactivé.")
        else:
            await channel_commandes.send("Tu n'étais pas abonné.")

    elif content == "!aide":
        aide = (
            "**Commandes disponibles :**\n"
            "`!joueurs` → voir qui est connecté\n"
            "`!tracker <pseudo>` → être pingé quand ce joueur se connecte\n"
            "`!untrack <pseudo>` → arrêter de suivre ce joueur\n"
            "`!trackers` → voir tes alertes actives\n"
            "`!rapport` → activer le rapport horaire\n"
            "`!stoprapport` → désactiver le rapport horaire"
        )
        await channel_commandes.send(aide)

client.run(TOKEN)
