# Phase 2 — Protocole du Roomba j7+ (firmware 24.29.3)

> Synthèse vérifiée à partir du comportement réseau observé et des projets
> communautaires de référence. Les points non testés sur ce robot précis sont
> signalés comme tels. Aucune donnée n'est inventée.

## 1. Verdict de compatibilité

| Projet / approche | j7+ (j755840) | Firmware 24.29.3 | Remarque |
| --- | --- | --- | --- |
| **MQTT/TLS local (port 8883)** | ✅ | ✅ attendu | Voie retenue par ROO-LAB |
| **dorita980** (Node) | ✅ | ✅ | Séries 900 / e / i / j documentées |
| **rest980** (REST sur dorita980) | ✅ | ✅ | Même socle MQTT |
| **Roomba980-Python** | ⚠️ partiel | ⚠️ | Plus ancien, maintenance irrégulière |
| **Home Assistant — intégration iRobot** | ✅ | ✅ | **Cloud**, pas de contrôle local |
| **Valetudo** | ❌ | ❌ | iRobot n'est pas dans les robots supportés |
| **Carte / plan de sol en local** | ❌ | ❌ | Le broker local n'expose pas l'image |
| **Ancienne API port 980** | ❌ | ❌ | Absente sur le j7+ |

Conclusion : le j7+ est **contrôlable localement** via son broker MQTT/TLS,
avec la paire d'identifiants fournie par iRobot. Ce n'est pas un protocole
« ouvert » : sans BLID + mot de passe local, le broker refuse la connexion.

## 2. Ce qui est confirmé sur ce robot

Observé directement sur `192.168.1.104` (voir `01-analyse-reseau.md`) :

- un seul port applicatif : **8883/tcp**, MQTT over TLS ;
- TLS 1.3, certificat `CN=iRobot-5F0726EEE8BE491794F59E383C7A1333`,
  émis par `Robot Intermediate CA A01` (iRobot) ;
- nom mDNS `iRobot-5F0726…`, TXT `dsn=5F0726…`, service `_amzn-alexa._tcp` ;
- aucun serveur HTTP, aucun port 980, aucune API REST locale.

Non confirmé sur ce robot précis, car cela exige les identifiants :

- acceptation de la paire BLID / mot de passe par le broker ;
- publication effective des champs d'état (`batPct`, `pose`, `pmaps`…) ;
- comportement des commandes `start`, `dock`, `evac` sur le firmware 24.29.3.

## 3. Fonctionnement du protocole local

```text
PC (ROO-LAB)  ── TCP 8883 + TLS 1.3 ──▶  broker MQTT du Roomba
                       │
                       ├─ username : BLID du robot
                       ├─ password : mot de passe local (chaîne ":1:…")
                       └─ aucun certificat client
```

- **Version MQTT** : 3.1.1 (`MQTTv311`), session persistante.
- **Authentification** : `username = BLID`, `password = mot de passe local`.
  Le couple est propre au robot. Il ne s'agit ni du compte iRobot, ni du mot
  de passe Wi-Fi.
- **Certificat** : le robot présente son certificat iRobot. La chaîne n'est pas
  ancrée dans un magasin public ; ROO-LAB lit et affiche l'identité du
  certificat mais ne l'épingle pas encore (limite assumée, voir §8).
- **Une seule connexion locale** : le broker du robot n'accepte qu'un client
  à la fois. Si l'application iRobot ou une autre intégration est connectée,
  il faut la déconnecter.

### Topics utilisés

| Topic | Sens | Charge utile |
| --- | --- | --- |
| `cmd` | PC → robot | `{"command":"start","time":1700000000,"initiator":"localApp"}` |
| `delta` | PC → robot | `{"state": { … préférences … }}` |
| état (shadow) | robot → PC | `{"state":{"reported":{ … }}}` |

ROO-LAB s'abonne à `#` de façon défensive : le robot publie ses mises à jour
d'état sous forme de *shadow* (`state.reported`), et chaque message reçu est
fusionné dans l'état local. Aucune souscription supplémentaire n'est requise
en pratique.

### Commandes exposées

| Commande | Effet | Confirmation requise dans ROO-LAB |
| --- | --- | --- |
| `start` | Démarre une mission complète | **oui** |
| `pause` | Suspend la mission | non |
| `resume` | Reprend après pause | non |
| `stop` | Termine la mission | **oui** |
| `dock` | Retour à la Clean Base | **oui** |
| `find` | Signal sonore de localisation | non |
| `evac` | Vidage du bac par la station | **oui** |

L'API refuse toute commande destructrice sans `confirm: true` et journalise
chaque envoi dans SQLite. L'interface affiche une fenêtre de confirmation.

## 4. Champs d'état exploités

Le robot publie un document proche de l'API iRobot. ROO-LAB n'utilise que les
champs réellement reçus, sans les compléter :

| Champ | Usage dans l'interface |
| --- | --- |
| `name`, `sku`, `softwareVer` | identité du robot |
| `batPct` | anneau de batterie, courbe |
| `bin` | bac présent / plein |
| `dock` | station détectée |
| `cleanMissionStatus` | phase, cycle, erreur, surface, durée, n° de mission |
| `cleanSchedule` | programme hebdomadaire |
| `signal` | RSSI / SNR Wi-Fi |
| `pose` | coordonnées et cap pendant une mission |
| `pmaps` | métadonnées de cartes et pièces (si exposées) |
| `lastCommand` | dernière commande reçue |
| `bbchg3`, `bbrun`, `bbmssn` | compteurs batterie / usage / missions |
| `netinfo`, `wifistat` | réseau du robot |

Si un champ est absent, l'interface affiche « — » ou « non reçu » : elle ne
fabrique aucune valeur.

## 5. Cartographie : ce qui est réellement possible

Le j7+ **ne publie pas l'image du plan** sur son broker local. L'application
iRobot et le cloud génèrent cette image à partir de données internes.

En local, on peut espérer :

- `pose` : position et cap pendant une mission, donc une **trajectoire** ;
- `pmaps` : identifiants de cartes, versions et parfois noms de pièces.

ROO-LAB stocke les échantillons de `pose` toutes les 4 s et trace la
trajectoire observée. Il ne dessine ni murs ni pièces et n'invente aucun plan.
Si le firmware ne publie pas `pose` en local, l'onglet Carte reste vide et
l'explique.

## 6. Obtenir les identifiants locaux

Trois voies existent, par ordre de préférence.

### A. Vous les possédez déjà

Si vous utilisez déjà `dorita980`, `rest980` ou une intégration locale, le
BLID et le mot de passe sont dans sa configuration. Il suffit de les saisir
dans **Réglages → Identifiants BLID / mot de passe**. Rien ne quitte le PC.

### B. Récupération unique depuis le compte iRobot

L'outil communautaire `get-roomba-password-cloud` (dorita980) se connecte une
fois à l'API iRobot (authentification Gigya) et récupère la paire locale.
Points importants :

- il faut le **mot de passe du compte iRobot**, pas celui du Wi-Fi ;
- un compte créé via « Se connecter avec Google / Apple » peut ne pas
  fonctionner sans mot de passe local ;
- la double authentification peut bloquer la connexion ;
- le mot de passe transite vers les serveurs **iRobot uniquement**, jamais
  vers un autre service ;
- ensuite, plus aucun appel cloud n'est nécessaire : ROO-LAB parle au robot
  en MQTT/TLS sur le LAN.

Cette récupération n'est **pas encore intégrée** à ROO-LAB. Elle nécessite
l'accord explicite de l'utilisateur, car elle utilise son compte iRobot.

### C. Méthode « bouton HOME »

Historiquement, maintenir le bouton HOME permettait de lire un mot de passe
temporaire. Cette méthode **ne fonctionne plus** sur les firmwares récents,
dont 24.29.3. Elle n'est pas utilisée par ROO-LAB.

## 7. Stockage et sécurité

- Identifiants chiffrés au repos avec **DPAPI Windows** (`data/credentials.bin`),
  liés au compte Windows courant.
- Jamais renvoyés par l'API : `GET /api/robot` n'expose que `configured`,
  `has_credentials` et l'adresse IP suggérée.
- Journalisation locale des connexions, erreurs et commandes.
- Aucun firmware modifié, aucun root, aucun jailbreak, aucun contournement.
- Aucune commande de nettoyage sans confirmation explicite.
- Le mot de passe Wi-Fi n'est jamais demandé ni transmis par ROO-LAB.

## 8. Limites et risques connus

1. **Une seule connexion locale** : coupez l'application mobile iRobot pendant
   l'utilisation de ROO-LAB.
2. **Certificat non épinglé** : la liaison est chiffrée, mais ROO-LAB ne vérifie
   pas encore la chaîne iRobot. Sur un réseau local hostile, une usurpation
   resterait possible. Une épingle (empreinte SHA-256 du certificat) pourra être
   ajoutée après le premier appairage.
3. **Plan de sol absent** : seule la trajectoire `pose` est exploitable.
4. **Firmware évolutif** : une mise à jour peut modifier topics ou champs.
   ROO-LAB échoue proprement et journalise l'erreur plutôt que d'inventer.
5. **Identifiants cloud** : la récupération optionnelle dépend des serveurs
   iRobot et de leur authentification ; elle peut être indisponible.
6. **Pas de prise en charge Valetudo** : iRobot n'expose pas de mécanisme
   d'installation tierce, et ROO-LAB n'essaie pas d'en créer un.

## 9. Sources

- dorita980 — client Node du protocole local iRobot :
  <https://github.com/koalazak/dorita980>
- rest980 — API REST au-dessus de dorita980 :
  <https://github.com/koalazak/rest980>
- Roomba980-Python — implémentation Python historique :
  <https://github.com/NickWaterton/Roomba980-Python>
- Home Assistant — intégration iRobot (cloud) :
  <https://www.home-assistant.io/integrations/irobot/>
- Valetudo — liste des robots supportés (iRobot absent) :
  <https://valetudo.cloud/pages/general/supported-robots.html>
- Documentation locale : `01-analyse-reseau.md` pour les mesures réseau.

Les affirmations marquées « attendu » ou « non confirmé » ne seront validées
qu'après le premier appairage réel de ce j7+.
