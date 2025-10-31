import requests
import subprocess
import time
import os
import sys

SERVER = "http://8.215.53.178:8443"
WG_PORT = 51820

# --- [ Fungsi agar bisa memanggil file dari dalam bundle ] ---
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

TOOLS_DIR = resource_path("tools")

def find_tool(name):
    local_path = os.path.join(TOOLS_DIR, name)
    if os.path.exists(local_path):
        return local_path
    return name

WG_EXE = find_tool("wg")

def gen_keys():
    private = subprocess.check_output([WG_EXE, "genkey"]).decode().strip()
    public = subprocess.check_output([WG_EXE, "pubkey"], input=private.encode()).decode().strip()
    return private, public

def create_conf(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content.strip() + "\n")

def interface_exists(interface_name):
    try:
        output = subprocess.check_output([WG_EXE, "show"]).decode()
        return interface_name in output
    except Exception:
        return False

# --- [ Main ] ---
room_type = input("Host/Join?....").strip().capitalize()

if room_type == "Host":
    WG_INTERFACE = "wg0"
    private_key, public_key = gen_keys()
    payload = {"host": {"pubkey": public_key}}

    try:
        r = requests.post(f"{SERVER}/room/new", json=payload, timeout=10)
        r.raise_for_status()
        room_id = r.json().get("room_id")
    except Exception as e:
        print("[ERROR] Gagal membuat room:", e)
        sys.exit(1)

    print(f"[HOST] Room ID: {room_id}")

    conf = f"""
    [Interface]
    PrivateKey = {private_key}
    Address = 10.8.0.1/24
    ListenPort = {WG_PORT}
    """

    conf_path = os.path.join("tmp", f"{WG_INTERFACE}.conf")
    create_conf(conf_path, conf)

    print(f"[INFO] Config dibuat di {conf_path}. Silakan aktifkan interface {WG_INTERFACE} secara manual.")
    # Loop menunggu user menyalakan interface
    while not interface_exists(WG_INTERFACE):
        print(f"[WAIT] Menunggu interface {WG_INTERFACE} aktif...")
        time.sleep(5)

    print(f"[HOST] Interface {WG_INTERFACE} sudah aktif. Menunggu peers...")
    known_peers = set()
    while True:
        time.sleep(5)
        try:
            resp = requests.get(f"{SERVER}/room/peers/{room_id}", timeout=10)
            peers = resp.json()
            for p in peers:
                pubkey = p["pubkey"]
                ip = p["ip"]
                if pubkey not in known_peers:
                    subprocess.run([
                        WG_EXE, "set", WG_INTERFACE,
                        "peer", pubkey,
                        "allowed-ips", f"{ip}/32"
                    ])
                    known_peers.add(pubkey)
                    print(f"[HOST] Added peer {ip}")
        except Exception as e:
            print("[ERROR]", e)

elif room_type == "Join":
    WG_INTERFACE = "wg1"
    room_id = input("Enter Room ID: ").strip()
    private_key, public_key = gen_keys()
    payload = {"room_id": room_id, "peer": {"pubkey": public_key}}

    try:
        r = requests.post(f"{SERVER}/room/join", json=payload, timeout=10)
        data = r.json()
    except Exception as e:
        print("[ERROR] Gagal join room:", e)
        sys.exit(1)

    if "error" in data:
        print("Error:", data["error"])
        sys.exit(1)

    peer_ip = data["your_ip"]
    host_pub = data["host"]["pubkey"]

    conf = f"""
    [Interface]
    PrivateKey = {private_key}
    Address = {peer_ip}/24

    [Peer]
    PublicKey = {host_pub}
    AllowedIPs = 10.8.0.0/24
    Endpoint = 8.215.53.178:{WG_PORT}
    PersistentKeepalive = 25
    """

    conf_path = os.path.join("tmp", f"{WG_INTERFACE}.conf")
    create_conf(conf_path, conf)

    print(f"[INFO] Config dibuat di {conf_path}. Silakan aktifkan interface {WG_INTERFACE} secara manual.")
    while not interface_exists(WG_INTERFACE):
        print(f"[WAIT] Menunggu interface {WG_INTERFACE} aktif...")
        time.sleep(5)

    subprocess.run([
        WG_EXE, "set", WG_INTERFACE,
        "peer", host_pub,
        "allowed-ips", "10.8.0.0/24"
    ])
    print("[CLIENT] Peer host ditambahkan.")

else:
    print("Usage:\n  Host  -- Host a room\n  Join  -- Join a room")
