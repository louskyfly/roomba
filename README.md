# ROO-LAB

Centre de contrôle local pour **iRobot Roomba j7+** (SKU `j755840`, série `J755840Y220328N101649`).

ROO-LAB se compose de :

- un **backend Python / FastAPI** qui découvre le réseau, parle au robot en MQTT/TLS local,
  stocke les historiques dans SQLite et pousse l'état en temps réel par WebSocket ;
- une **interface React + TypeScript** au style « Liquid Glass ».

## État du projet

| Phase | Contenu | État |
| --- | --- | --- |
| 1 | Analyse réseau locale (ARP, mDNS, SSDP, ports, TLS) | ✅ validée sur le réseau réel |
| 2 | Étude du protocole et de la compatibilité j7+ / 24.29.3 | ✅ documentée |
| 3 | Tableau de bord, commandes, temps réel | ✅ construit — en attente des identifiants |
| 4 | Historique, statistiques, planification, carte, alertes | ✅ construit — se remplit à l'usage |
| 5 | Intégration Python / FastAPI / React / SQLite | ✅ opérationnelle |

Le robot est identifié sur le réseau (`192.168.1.104`, MQTT/TLS 8883) et son
certificat iRobot est vérifié. **Le contrôle réel nécessite la paire BLID /
mot de passe local**, obtenue une seule fois depuis le compte iRobot.
Voir [`docs/02-protocole.md`](docs/02-protocole.md).

## Démarrage rapide

```powershell
cd roo-lab
.\start.ps1
```

Puis ouvrir <http://127.0.0.1:8000>.

Options : `-Port 8000`, `-Rebuild` (recompile l'interface), `-SkipBuild`.

Le script crée l'environnement virtuel Python, installe les dépendances,
compile le frontend si nécessaire, puis lance l'API qui sert aussi l'interface.

### Mode développement

```powershell
# terminal 1 — API
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# terminal 2 — front (Vite, proxy /api et /ws vers :8000)
cd frontend
npm run dev
```

## Structure

```
roo-lab/
├─ backend/
│  ├─ app/
│  │  ├─ discovery/     # phase 1 : ARP, mDNS, SSDP, ports, TLS, identification
│  │  ├─ roomba/        # phase 2 : client MQTT/TLS local, état, missions
│  │  ├─ data/oui.csv   # base OUI locale (constructeurs)
│  │  ├─ config.py      # chemins, réglages
│  │  ├─ db.py          # SQLite (appareils, télémétrie, missions, événements)
│  │  ├─ scheduler.py   # passages programmés (heure locale, jours)
│  │  ├─ secret_store.py# identifiants chiffrés DPAPI
│  │  ├─ ws.py          # diffusion WebSocket
│  │  └─ main.py        # application FastAPI
│  ├─ scripts/test_scan.py
│  └─ requirements.txt
├─ frontend/            # React + TS + Vite, style Liquid Glass
├─ docs/
│  ├─ 01-analyse-reseau.md
│  └─ 02-protocole.md
├─ data/                # SQLite + secrets chiffrés (créé au premier lancement)
├─ start.ps1
└─ README.md
```

## Sécurité

- Aucune donnée ne quitte le réseau local, sauf la connexion iRobot **ponctuelle**
  nécessaire pour récupérer les identifiants locaux du robot (si vous l'autorisez).
- Les identifiants sont chiffrés au repos avec **DPAPI** (Windows) et ne sont jamais renvoyés
  au navigateur.
- Les commandes de nettoyage exigent une confirmation explicite (`confirm: true`) et sont
  journalisées.
- La planification ne se substitue jamais à une confirmation : chaque déclenchement est
  journalisé et, si le robot est hors ligne à l'heure prévue, le passage est marqué
  « ignoré » sans être rejoué.
- Le certificat du robot est affiché mais pas encore épinglé : la liaison est chiffrée,
  sans validation de la chaîne iRobot.
- Aucun firmware modifié, aucun contournement d'authentification.

## Documentation

- [`docs/01-analyse-reseau.md`](docs/01-analyse-reseau.md) — résultats réels de la découverte réseau.
- [`docs/02-protocole.md`](docs/02-protocole.md) — protocole MQTT/TLS, compatibilité, limites, sources.
