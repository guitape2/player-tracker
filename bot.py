import discord
import asyncio
import os
import time
import json
from mcstatus import JavaServer
from collections import defaultdict

TOKEN = os.environ["DISCORD_TOKEN"]
MC_HOST = os.environ["MC_HOST"]
MC_PORT = int(os.environ.get("MC_PORT", 25565))

CHANNEL_ALERTES = 1499796586014707885
CHANNEL_RAPPORTS = 1499796588200198286
CHANNEL_COMMANDES = 1499796590112538874
CHANNEL_JOUEURS_SURVEILLES = 1499796600728326436
CHANNEL_STATISTIQUES = 1499796592188854292
CHANNEL_GRAPHIQUES = 1500582748770009108

SAVE_FILE = "data.json"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

previously_online = set()
session_start = {}

trackers = {}
hourly_subscribers = []
players_this_hour = set()
connexions_par_joueur = defaultdict(int)
connexions_par_heure = defaultdict(int)
temps_total_par_joueur = defaultdict(float)

def sauvegarder():
    data = {
        "trackers": {k: v for k, v in trackers.items()},
        "hourly_subscribers": hourly_subscribers,
        "connexions_par_joueur": dict(connexions_par_joueur),
        "connexions_par_heure": {str(k): v for k, v in connexions_par_heure.items()},
        "temps_total_par_joueur": dict(temps_total_par_joueur),
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f)

def charger():
    global trackers, hourly_subscribers
    if not os.path.exists(SAVE_FILE):
        return
    with open(SAVE_FILE, "r") as f:
        data = json.load(f)
    trackers = {k: [tuple(e) for e in v] for k, v in data.get("trackers", {}).items()}
    hourly_subscribers = [tuple(e) for e in data.get("hourly_subscribers", [])]
    for k, v in data.get("connexions_par_joueur", {}).items():
        connexions_par_joueur[k] = v
    for k, v in data.get("connexions_par_heure", {}).items():
        connexions_par_heure[int(k)] = v
    for k, v in data.get("temps_total_par_joueur", {}).items():
        temps_total_par_joueur[k] = v

async def get_players():
    try:
        server = JavaServer(MC_HOST, MC_PORT)
        status = await asyncio.to_thread(server.status)
        if status.players.sample:
            return {p.name for p in status.players.sample}, status.players.online
        return set(), status.players.online
    except Exception:
        return set(), 0

def format_duree(secondes):
    secondes = int(secondes)
    h = secondes // 3600
    m = (secondes % 3600) // 60
    s = secondes % 60
    if h > 0:
        return f"{h}h{m:02d}m"
    elif m > 0:
        return f"{m}m{s:02d}s"
    else:
        return f"{s}s"

def generer_barchart_ascii(data, titre, max_width=20):
    if not data:
        return f"**{titre}**\nAucune donnée"
    max_val = max(data.values())
    lignes = [f"**{titre}**"]
    for label, val in sorted(data.items(), key=lambda x: x[1], reverse=True):
        if max_val > 0:
            barre = "█" * int((val / max_val) * max_width)
        else:
            barre = ""
        lignes.append(f"`{str(label).rjust(10)}` {barre} {val}")
    return "\n".join(lignes)

async def envoyer_graphiques():
    channel = client.get_channel(CHANNEL_GRAPHIQUES)
    if not channel:
        return

    await channel.send("📊 **Graphiques des statistiques**\n─────────────────────")

    # Graphique 1 : connexions par joueur
    if connexions_par_joueur:
        top = dict(sorted(connexions_par_joueur.items(), key=lambda x: x[1], reverse=True)[:10])
        msg = generer_barchart_ascii(top, "Connexions par joueur")
        await channel.send(msg)
    else:
        await channel.send("**Connexions par joueur**\nAucune donnée")

    # Graphique 2 : temps de jeu par joueur
    if temps_total_par_joueur:
        top_temps = dict(sorted(temps_total_par_joueur.items(), key=lambda x: x[1], reverse=True)[:10])
        max_val = max(top_temps.values())
        lignes = ["**Temps de jeu par joueur**"]
        for p, t in top_temps.items():
            barre = "█" * int((t / max_val) * 20) if max_val > 0 else ""
            lignes.append(f"`{p.rjust(10)}` {barre} {format_duree(t)}")
        await channel.send("\n".join(lignes))
    else:
        await channel.send("**Temps de jeu par joueur**\nAucune donnée")

    # Graphique 3 : activité par heure
    if connexions_par_heure:
        heures_completes = {h: connexions_par_heure.get(h, 0) for h in range(24)}
        max_val = max(heures_completes.values()) if heures_completes else 1
        lignes = ["**Activité par heure de la journée**"]
        for h in range(24):
            val = heures_completes[h]
            barre = "█" * int((val / max_val) * 20) if max_val > 0 else ""
            lignes.append(f"`{str(h).zfill(2)}h` {barre} {val}")
        await channel.send("\n".join(lignes))
    else:
        await channel.send("**Activité par heure**\nAucune donnée")

    await channel.send("─────────────────────")

async def envoyer_stats_quotidiennes():
    channel_stats = client.get_channel(CHANNEL_STATISTIQUES)
    if not channel_stats:
        return

    if connexions_par_joueur:
        top_joueurs = sorted(connexions_par_joueur.items(), key=lambda x: x[1], reverse=True)[:5]
        top_str = "\n".join(f"**{i+1}.** {p} — {n} connexion(s)" for i, (p, n) in enumerate(top_joueurs))
    else:
        top_str = "Aucune donnée"

    if connexions_par_heure:
        top_heures = sorted(connexions_par_heure.items(), key=lambda x: x[1], reverse=True)[:3]
        heures_str = "\n".join(f"**{h}h00** — {n} connexion(s)" for h, n in top_heures)
    else:
        heures_str = "Aucune donnée"

    if temps_total_par_joueur:
        top_temps = sorted(temps_total_par_joueur.items(), key=lambda x: x[1], reverse=True)[:5]
        temps_str = "\n".join(f"**{i+1}.** {p} — {format_duree(t)}" for i, (p, t) in enumerate(top_temps))
    else:
        temps_str = "Aucune donnée"

    total = sum(connexions_par_joueur.values())

    embed = discord.Embed(title="Rapport quotidien", color=0x5865F2)
    embed.add_field(name="Joueurs les plus actifs", value=top_str, inline=False)
    embed.add_field(name="Temps de jeu total", value=temps_str, inline=False)
    embed.add_field(name="Heures de pointe", value=heures_str, inline=False)
    embed.add_field(name="Total connexions aujourd'hui", value=f"**{total}** connexion(s)", inline=False)

    await channel_stats.send(embed=embed)
    await envoyer_graphiques()

    connexions_par_joueur.clear()
    connexions_par_heure.clear()
    temps_total_par_joueur.clear()
    sauvegarder()

async def monitor_loop():
    global previously_online, players_this_hour
    await client.wait_until_ready()
    last_hour_report = time.time()
    last_day_report = time.time()

    channel_alertes = client.get_channel(CHANNEL_ALERTES)
    channel_rapports = client.get_channel(CHANNEL_RAPPORTS)

    while not client.is_closed():
        current_players, count = await get_players()
        new_players = current_players - previously_online
        left_players = previously_online - current_players

        players_this_hour.update(new_players)

        heure_actuelle = int(time.strftime("%H"))
        for player in new_players:
            connexions_par_joueur[player] += 1
            connexions_par_heure[heure_actuelle] += 1
            session_start[player] = time.time()
            sauvegarder()

            for key, entries in trackers.items():
                if player.lower() == key:
                    for (user_id, _) in entries:
                        if channel_alertes:
                            await channel_alertes.send(
                                f"<@{user_id}> **{player}** vient de se connecter ! "
                                f"({count} joueur(s) en ligne)"
                            )

        for player in left_players:
            if player in session_start:
                duree = time.time() - session_start[player]
                temps_total_par_joueur[player] += duree
                del session_start[player]
                sauvegarder()
                if channel_alertes:
                    await channel_alertes.send(
                        f"**{player}** a quitté le serveur — session : **{format_duree(duree)}**"
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

        if time.time() - last_day_report >= 86400:
            last_day_report = time.time()
            await envoyer_stats_quotidiennes()

        await asyncio.sleep(30)

@client.event
async def on_ready():
    charger()
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
            lines = []
            for p in sorted(players):
                if p in session_start:
                    duree = time.time() - session_start[p]
                    lines.append(f"• {p} — connecté depuis **{format_duree(duree)}**")
                else:
                    lines.append(f"• {p}")
            await channel_commandes.send(f"**{count}** joueur(s) en ligne :\n" + "\n".join(lines))

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
        sauvegarder()
        await channel_commandes.send(f"Tu seras pingé quand **{pseudo}** se connecte.")
        if channel_joueurs:
            await channel_joueurs.send(f"+ **{pseudo}** ajouté au tracking par <@{message.author.id}>")

    elif content.startswith("!untrack "):
        pseudo = content[9:].strip()
        key = pseudo.lower()
        if key in trackers:
            trackers[key] = [e for e in trackers[key] if e[0] != message.author.id]
        sauvegarder()
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
            sauvegarder()
            await channel_commandes.send("Tu recevras un rapport toutes les heures dans #rapports.")
        else:
            await channel_commandes.send("Tu es déjà abonné au rapport horaire.")

    elif content == "!stoprapport":
        entry = (message.author.id, message.channel.id)
        if entry in hourly_subscribers:
            hourly_subscribers.remove(entry)
            sauvegarder()
            await channel_commandes.send("Rapport horaire désactivé.")
        else:
            await channel_commandes.send("Tu n'étais pas abonné.")

    elif content == "!stats":
        await envoyer_stats_quotidiennes()
        await channel_commandes.send("Stats envoyées dans #statistiques !")

    elif content == "!graphique":
        await envoyer_graphiques()
        await channel_commandes.send("Graphiques envoyés dans #graphiques !")

    elif content == "!aide":
        aide = (
            "**Commandes disponibles :**\n"
            "`!joueurs` → voir qui est connecté + depuis combien de temps\n"
            "`!tracker <pseudo>` → être pingé quand ce joueur se connecte\n"
            "`!untrack <pseudo>` → arrêter de suivre ce joueur\n"
            "`!trackers` → voir tes alertes actives\n"
            "`!rapport` → activer le rapport horaire\n"
            "`!stoprapport` → désactiver le rapport horaire\n"
            "`!stats` → envoyer le rapport quotidien dans #statistiques\n"
            "`!graphique` → envoyer les graphiques dans #graphiques"
        )
        await channel_commandes.send(aide)

client.run(TOKEN)
