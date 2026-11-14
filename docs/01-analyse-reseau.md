# Phase 1 — Analyse du réseau local

> Résultat d'une analyse réelle, non intrusive, exécutée depuis le PC de Lucas
> (Windows 11, interface Wi-Fi) le 14 novembre 2026.
> Le robot n'a reçu aucune commande et aucun mot de passe n'a été utilisé.

## 1. Objectif et périmètre

Cette phase répond à trois questions :

1. le Roomba j7+ est-il bien présent sur le réseau local, et à quelle adresse ?
2. quels services expose-t-il réellement sur le LAN ?
3. peut-on confirmer son identité sans se fier au seul nom annoncé ?

Toutes les opérations sont en **lecture seule** :

- un datagramme UDP par adresse pour remplir le cache ARP, puis lecture du cache ;
- des requêtes mDNS et SSDP standards ;
- une connexion TCP vers une liste courte de ports, sans envoyer de charge applicative ;
- une poignée de main TLS pour lire le certificat présenté, sans s'authentifier.

Aucun paquet forgé, aucune exploitation, aucun contournement d'authentification.

## 2. Environnement observé

| Élément | Valeur |
| --- | --- |
| Interface | `Wi-Fi` |
| Adresse du PC | `192.168.1.158/24` |
| MAC du PC | `58:1c:f8:11:ea:68` |
| Passerelle | `192.168.1.254` — Freebox Server |
| Sous-réseau | `192.168.1.0/24` |
| Diffusion | `192.168.1.255` |
| Durée de l'analyse | 6,7 s |
| Hôtes découverts | 16 |

## 3. Inventaire des appareils

| IP | MAC | Constructeur | Type retenu | Ports ouverts |
| --- | --- | --- | --- | --- |
| **192.168.1.104** | `50:14:79:d7:ce:f1` | **iRobot Corporation** | **Robot aspirateur** | **8883** |
| 192.168.1.11 | `30:48:7d:8b:be:c9` | Tuya Smart Inc. | Objet connecté | — |
| 192.168.1.21 | `12:9b:db:57:e5:d4` | — (MAC aléatoire) | Inconnu | — |
| 192.168.1.94 | `54:44:a3:54:fe:e0` | Samsung Electronics | Téléviseur | 8080 |
| 192.168.1.96 | `20:66:cf:0e:7c:62` | Freebox SAS | Freebox Player POP | 8008, 8443, 9000 |
| 192.168.1.99 | `a8:42:e3:77:80:e0` | Espressif Inc. | Smart AC Control (HomeKit) | 80 |
| 192.168.1.108 | `bc:35:1e:3f:cf:1a` | Tuya Smart Inc. | Objet connecté | — |
| 192.168.1.126 | `f6:fc:f4:d2:af:be` | — (MAC aléatoire) | Inconnu | — |
| 192.168.1.134 | `98:cc:f3:5d:d2:7e` | Amazon Technologies | SpotifyConnect | — |
| 192.168.1.143 | `4e:25:8f:17:2b:da` | — (MAC aléatoire) | Inconnu | — |
| 192.168.1.158 | `58:1c:f8:11:ea:68` | — | Cet ordinateur | — |
| 192.168.1.161 | `60:56:ee:1c:50:6e` | AltoBeam Inc. | Inconnu | — |
| 192.168.1.165 | `d8:fc:92:64:e5:5c` | Tuya Smart Inc. | Objet connecté | — |
| 192.168.1.166 | `c6:a0:e3:0a:42:35` | — (MAC aléatoire) | Inconnu | — |
| 192.168.1.167 | `30:48:7d:8b:f2:e4` | Tuya Smart Inc. | Objet connecté | — |
| 192.168.1.254 | `20:66:cf:73:d9:22` | Freebox SAS | Box / routeur | 53, 80, 443, 554 |

Les adresses MAC `12:…`, `f6:…`, `4e:…` et `c6:…` ont le bit
*locally administered* : ce sont des adresses aléatoires générées par les
appareils pour protéger la vie privée Wi-Fi. Le constructeur ne peut donc pas
être déduit de l'OUI, et l'interface le signale explicitement.

## 4. Identification du Roomba

L'appareil `192.168.1.104` réunit **six indices concordants** :

| Indice | Valeur observée |
| --- | --- |
| OUI | `50:14:79` → iRobot Corporation |
| Port TCP | `8883` ouvert (MQTT over TLS) |
| Certificat TLS | `CN=iRobot-5F0726EEE8BE491794F59E383C7A1333` |
| Organisation | `iRobot Corporation`, `OU=Production` |
| Émetteur | `Robot Intermediate CA A01`, valide jusqu'au **2032-01-27** |
| Nom mDNS | `iRobot-5F0726EEE8BE491794F59E383C7A1333.local` |
| TXT mDNS | `dsn=5F0726EEE8BE491794F59E383C7A1333` |

Détails TLS :

```
TLSv1.3
TLS_AES_256_GCM_SHA384
Sujet   : CN=iRobot-5F0726EEE8BE491794F59E383C7A1333,OU=Production,
          O=iRobot Corporation,L=Bedford,ST=Massachusetts,C=US
Émetteur: CN=Robot Intermediate CA A01,OU=HBU,O=iRobot Corporation,…
```

Le suffixe `5F0726EEE8BE491794F59E383C7A1333` est cohérent entre le certificat,
le nom mDNS et le TXT `dsn`. C'est l'identifiant local du robot ; il est
utilisé dans l'interface comme indice de BLID, mais **il doit être confirmé**
lors de l'appairage (voir `02-protocole.md`).

Un service mDNS `_amzn-alexa._tcp` est également annoncé sur le port 443 :

```json
{ "version": "1", "dsn": "5F0726EEE8BE491794F59E383C7A1333",
  "rid": "4c2356c2-a13c-4e0d-96b0-9a127f9e56fc" }
```

C'est le canal d'appairage Wi-Fi simplifié d'iRobot (Alexa). Le port 443
annoncé n'était **pas** joignable en TCP lors du test ; seul 8883 répond.
Ce service ne donne pas accès au contrôle du robot.

## 5. Ce que le réseau ne montre pas

- Aucun serveur HTTP local sur le robot : pas de page web, pas d'API REST ouverte.
- Aucun port 980 (ancienne API iRobot) : le j7+ utilise uniquement MQTT/TLS.
- Aucun mot de passe, jeton ou identifiant en clair dans les réponses mDNS/SSDP.
- Aucun plan de sol ni image de carte exposé sur le LAN.
- Aucun service UPnP sur le robot.

Conclusion de phase 1 : **le robot est joignable et son identité est confirmée
avec un niveau de confiance élevé**, mais toute lecture d'état ou commande
exige l'authentification MQTT (BLID + mot de passe local).

## 6. Reproduire l'analyse

```powershell
cd roo-lab\backend
..\.venv\Scripts\python.exe scripts\test_scan.py --out ..\data\scan.json
```

Ou depuis l'interface : onglet **Réseau** → **Analyser le réseau**.
Le rapport complet est conservé dans SQLite (`scans`) et rechargé au démarrage.

## 7. Choix de conception

- L'analyse est **mono-instance** : un verrou empêche deux scans simultanés.
- La résolution de constructeur en ligne (maclookup.app) est **désactivée par
  défaut**. Si elle est activée, seuls les trois premiers octets de la MAC
  (OUI) sont envoyés ; jamais l'IP, le nom ou un identifiant du robot.
- Le certificat est seulement **lu** : aucune validation de chaîne, aucune
  authentification, aucun certificat client.
- Les libellés des appareils restent factuels : un identifiant technique
  (longue chaîne hexadécimale) n'est jamais présenté comme un nom d'appareil.
