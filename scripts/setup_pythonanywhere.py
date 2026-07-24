"""One-off helper: provisions the bot on PythonAnywhere via their public API.

Run this LOCALLY with your own PythonAnywhere credentials. The token stays on
your machine — this script only talks straight to pythonanywhere.com, nobody
else sees it.

Usage:
    PYTHONANYWHERE_USERNAME=yourname PYTHONANYWHERE_API_TOKEN=xxx \
        python scripts/setup_pythonanywhere.py

Or just run it with no env vars set and it will prompt for both (the token
prompt is hidden, like a password prompt).

What it does, in order:
    1. Opens a bash console on PythonAnywhere and clones/updates the repo,
       then installs requirements.txt.
    2. Writes /home/<user>/wwgbot/.env there, using BOT_TOKEN / OWNER_IDS /
       WEBHOOK_SECRET from your LOCAL .env file in this repo.
    3. Creates the web app for <user>.pythonanywhere.com if it doesn't exist.
    4. Overwrites the PythonAnywhere-generated WSGI file so it imports this
       project's wsgi.py.
    5. Reloads the web app.
    6. Registers the Telegram webhook pointing at the new app.

Not battle-tested end to end (no PythonAnywhere account to run it against) —
it's built strictly from PythonAnywhere's documented API. Watch the printed
console output at each step; if something 4xx/5xxs, the response body is
printed too so it's obvious what to fix.
"""

import base64
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values  # noqa: E402

REPO_URL = "https://github.com/niwtrix/wwgbot.git"
PROJECT_DIR_NAME = "wwgbot"
PYTHON_VERSION = os.getenv("PYTHONANYWHERE_PYTHON_VERSION", "python310")


def api_request(base_url, token, method, path, data=None):
    url = f"{base_url}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Token {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw.decode(errors="replace")
        return e.code, payload


def run_console_command(base_url, token, console_id, command, wait=8):
    api_request(base_url, token, "POST", f"/consoles/{console_id}/send_input/", {"input": command + "\n"})
    time.sleep(wait)
    status, out = api_request(base_url, token, "GET", f"/consoles/{console_id}/get_latest_output/")
    text = out.get("output", "") if isinstance(out, dict) else str(out)
    print(text[-2000:])
    return text


def write_remote_file(base_url, token, console_id, remote_path, content):
    encoded = base64.b64encode(content.encode()).decode()
    run_console_command(base_url, token, console_id, f"echo {encoded} | base64 -d > {remote_path}", wait=5)


def main():
    username = os.getenv("PYTHONANYWHERE_USERNAME") or input("PythonAnywhere username: ").strip()
    token = os.getenv("PYTHONANYWHERE_API_TOKEN") or getpass.getpass("PythonAnywhere API token (hidden): ").strip()

    base_url = f"https://www.pythonanywhere.com/api/v0/user/{username}"
    domain = f"{username}.pythonanywhere.com"
    home_dir = f"/home/{username}"
    project_dir = f"{home_dir}/{PROJECT_DIR_NAME}"

    repo_root = Path(__file__).resolve().parent.parent
    local_env = dotenv_values(repo_root / ".env")
    bot_token = local_env.get("BOT_TOKEN", "")
    owner_ids = local_env.get("OWNER_IDS", "")
    webhook_secret = local_env.get("WEBHOOK_SECRET", "")
    if not bot_token or not owner_ids:
        sys.exit("Local .env is missing BOT_TOKEN/OWNER_IDS — fill those in first.")
    if not webhook_secret:
        sys.exit("Local .env is missing WEBHOOK_SECRET — add one (any random string) first.")

    print("== Verifying the token ==")
    status, _ = api_request(base_url, token, "GET", "/cpu/")
    if status == 401:
        sys.exit("PythonAnywhere rejected the token (401) — check it's correct and not expired.")
    print(f"Token check status: {status}")

    print("== Opening a bash console ==")
    status, console = api_request(base_url, token, "POST", "/consoles/", {"executable": "bash", "arguments": ""})
    if status not in (200, 201):
        sys.exit(f"Could not create console: {status} {console}")
    console_id = console["id"]
    print(f"Console id={console_id}. Waiting for it to boot...")
    time.sleep(5)

    print("== Cloning/updating the repo ==")
    run_console_command(
        base_url, token, console_id,
        f"[ -d {project_dir} ] && (cd {project_dir} && git pull) || git clone {REPO_URL} {project_dir}",
        wait=15,
    )

    print("== Installing dependencies ==")
    run_console_command(base_url, token, console_id, f"pip install --user -r {project_dir}/requirements.txt", wait=60)

    print("== Writing .env on PythonAnywhere ==")
    env_content = f"BOT_TOKEN={bot_token}\nOWNER_IDS={owner_ids}\nWEBHOOK_SECRET={webhook_secret}\n"
    write_remote_file(base_url, token, console_id, f"{project_dir}/.env", env_content)

    print("== Creating the web app (skipped if it already exists) ==")
    status, webapps = api_request(base_url, token, "GET", "/webapps/")
    existing = [w for w in (webapps or []) if w.get("domain_name") == domain] if isinstance(webapps, list) else []
    if not existing:
        status, created = api_request(
            base_url, token, "POST", "/webapps/",
            {"domain_name": domain, "python_version": PYTHON_VERSION},
        )
        if status not in (200, 201):
            sys.exit(
                f"Could not create web app: {status} {created}\n"
                f"If this complains about python_version, set PYTHONANYWHERE_PYTHON_VERSION "
                f"to one of the versions your account offers and rerun."
            )
        print("Web app created.")
    else:
        print("Web app already exists, reusing it.")

    print("== Pointing the WSGI file at our app ==")
    wsgi_path = f"/var/www/{username}_pythonanywhere_com_wsgi.py"
    wsgi_content = (
        "import sys\n"
        f"path = '{project_dir}'\n"
        "if path not in sys.path:\n"
        "    sys.path.insert(0, path)\n\n"
        "from wsgi import application\n"
    )
    write_remote_file(base_url, token, console_id, wsgi_path, wsgi_content)

    print("== Reloading the web app ==")
    status, reload_result = api_request(base_url, token, "POST", f"/webapps/{domain}/reload/", {})
    print(f"Reload status: {status} {reload_result}")

    print("== Registering the Telegram webhook ==")
    webhook_url = f"https://{domain}/webhook"
    payload = json.dumps({"url": webhook_url, "secret_token": webhook_secret}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())

    print(f"\nDone. Bot should be live at https://{domain}/")


if __name__ == "__main__":
    main()
