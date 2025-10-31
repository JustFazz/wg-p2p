import requests
import subprocess
import time
import os
import sys

SERVER = "http://8.215.53.178:8443"
WG_PORT = 51820

# --- [ Fungsi agar bisa memanggil file dari dalam bundle ] ---
def resource_path(relative_path):
    """Mengembalikan path absolut ke resource (support PyInstaller)."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- [ Lokasi tools (wg, wg-quick) ] ---
TOOLS_DIR = resource_path("tools")

def find_tool(name):
    """Cari binary di folder tools, fallback ke system path."""
    local_path = os.path.join(TOOLS_DIR, name)
    if os.path.exists(local_path):
        return local_path
    return name  # fallback ke PATH environment

WG_EXE = find_tool("wg")
WG_QUICK_EXE = find_tool("wg-quick")

# --- [ Fungsi bantu ] ---
def gen_keys():
    """Generate private & public key."""
    private = subprocess.check_output([WG_EXE, "genkey"]).decode().strip()
    public = subprocess.check_output(
        ["/bin/bash", "-c", f"echo {private} | {WG_EXE} pubkey"]
    ).decode().strip()
    return private, public

def create_conf(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content.strip() + "\n")

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

    subprocess.run(["sudo", WG_QUICK_EXE, "down", conf_path], check=False)
    subprocess.run(["sudo", WG_QUICK_EXE, "up", conf_path], check=False)

    print("[HOST] Interface started. Waiting for peers...")
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
                        "sudo", WG_EXE, "set", WG_INTERFACE,
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

    subprocess.run(["sudo", WG_QUICK_EXE, "down", conf_path], check=False)
    subprocess.run(["sudo", WG_QUICK_EXE, "up", conf_path], check=False)
    print("[CLIENT] Connected to host.")

else:
    print("Usage:\n  Host  -- Host a room\n  Join  -- Join a room")
