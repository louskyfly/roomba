# ROO-LAB : récupère BLID + mot de passe local du Roomba via le cloud iRobot (méthode 2026)
# Usage : pip install requests  puis  python get_roomba_creds.py
import getpass, requests

DISC = "https://disc-prod.iot.irobotapi.com/v1/discover/endpoints?country_code=FR"
APP_ID = "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294"

email = input("E-mail compte iRobot : ").strip()
pwd = getpass.getpass("Mot de passe iRobot (masqué) : ")

# 1. Découverte des endpoints actuels (clé Gigya + serveur iRobot)
d = requests.get(DISC, timeout=15).json()
api_key = d["gigya"]["api_key"]
gigya = "https://accounts." + d["gigya"]["datacenter_domain"]
http_base = d["deployments"][d["current_deployment"]]["httpBase"]

# 2. Login Gigya (formulaire, pas JSON)
g = requests.post(f"{gigya}/accounts.login", timeout=15, data={
    "apiKey": api_key, "loginID": email, "password": pwd,
    "format": "json", "targetEnv": "mobile",
}).json()
if g.get("errorCode") != 0:
    raise SystemExit(f"Échec Gigya : {g.get('errorCode')} {g.get('errorMessage')}")

# 3. Login iRobot avec la signature Gigya -> mots de passe des robots
r = requests.post(f"{http_base}/v2/login", timeout=15, json={
    "app_id": APP_ID,
    "assume_robot_ownership": 0,
    "gigya": {"signature": g["UIDSignature"],
              "timestamp": g["signatureTimestamp"],
              "uid": g["UID"]},
})
r.raise_for_status()
for blid, rb in r.json().get("robots", {}).items():
    print(f"\n{rb.get('name')} ({rb.get('sku')})")
    print("BLID     :", blid)
    print("Password :", rb.get("password"))
