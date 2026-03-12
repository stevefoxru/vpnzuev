import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

WG_EASY_URL = os.getenv("WG_EASY_URL", "http://127.0.0.1:1240").rstrip("/")
WG_EASY_PASSWORD = os.getenv("WG_EASY_PASSWORD", "")
CONFIGS_DIR = Path(os.getenv("CONFIGS_DIR", "/root/vpn-bot/configs"))


class WGEasyAPI:
    def __init__(self):
        self.session = requests.Session()

    def login(self):
        resp = self.session.post(
            f"{WG_EASY_URL}/api/session",
            json={"password": WG_EASY_PASSWORD},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError("wg-easy login failed")

    def list_clients(self):
        resp = self.session.get(
            f"{WG_EASY_URL}/api/wireguard/client",
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def create_client(self, name: str):
        resp = self.session.post(
            f"{WG_EASY_URL}/api/wireguard/client",
            json={"name": name},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError("wg-easy create client failed")

    def find_client_by_name(self, name: str):
        clients = self.list_clients()
        for item in clients:
            if item.get("name") == name:
                return item
        raise RuntimeError(f"Client '{name}' not found after creation")

    def download_config(self, client_id: str, out_path: Path):
        resp = self.session.get(
            f"{WG_EASY_URL}/api/wireguard/client/{client_id}/configuration",
            timeout=20,
        )
        resp.raise_for_status()
        out_path.write_text(resp.text, encoding="utf-8")

    def delete_client(self, client_id: str):
        resp = self.session.delete(
            f"{WG_EASY_URL}/api/wireguard/client/{client_id}",
            timeout=20,
        )
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"wg-easy delete client failed: {resp.status_code} {resp.text}")


def provision_client(client_name: str) -> dict:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

    api = WGEasyAPI()
    api.login()
    api.create_client(client_name)

    client = api.find_client_by_name(client_name)
    client_id = client["id"]
    client_ip = client["address"]

    config_path = CONFIGS_DIR / f"{client_name}.conf"
    api.download_config(client_id, config_path)

    return {
        "client_id": client_id,
        "client_name": client_name,
        "client_ip": client_ip,
        "config_path": str(config_path),
    }


def revoke_client(wg_client_id: str):
    api = WGEasyAPI()
    api.login()
    api.delete_client(wg_client_id)
