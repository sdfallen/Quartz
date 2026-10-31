"""Explicit official-CLI setup for Quartz's optional Notion Custom Agent.

This console helper never accepts tokens or stores credentials. Login belongs to
the official ntn CLI and the OS keychain; model choice belongs to the agent UI.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.notion_cli import NotionCli, prepare_cli_environment, install_ntn, resolve_ntn
from core.notion_runtime import NotionRuntime


def main(argv=None):
    parser = argparse.ArgumentParser(description="Quartz — Notion ajan bağlantısı")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="Resmî CLI'yi Quartz'a özel kur")
    commands.add_parser("login", help="Resmî tarayıcı/kod ile giriş (anahtar kaydedilmez)")
    commands.add_parser("status", help="Yerel bağlantı durumu (ağ isteği yok)")
    agents = commands.add_parser("agents", help="Giriş yapılmış çalışma alanının ajanlarını listele")
    agents.add_argument("--workspace", required=True)
    select = commands.add_parser("select", help="Erişilebilir bir Custom Agent seç")
    select.add_argument("--workspace", required=True)
    select.add_argument("--agent", required=True)
    send = commands.add_parser("send", help="Mesajı stdin'den okuyup gerçek ajan yanıtını bekle")
    send.add_argument("--session", default=None)
    args = parser.parse_args(argv)
    runtime = NotionRuntime()
    try:
        if args.command == "install":
            print(json.dumps(install_ntn(), ensure_ascii=False))
        elif args.command == "login":
            env = prepare_cli_environment()
            # Foreground console, deliberately initiated by the user.
            return subprocess.run([resolve_ntn(), "login", "--no-browser"], env=env).returncode
        elif args.command == "agents":
            agents = NotionCli(args.workspace).agents()
            print(json.dumps([{"id": a.get("id"), "name": a.get("name")} for a in agents], ensure_ascii=False, indent=2))
        elif args.command == "select":
            print(json.dumps(runtime.configure(args.workspace, args.agent), ensure_ascii=False))
        elif args.command == "status":
            print(json.dumps(runtime.probe(), ensure_ascii=False))
        else:
            prompt = sys.stdin.read(64001)
            run = runtime.start(prompt, session_id=args.session)
            while run["status"] not in runtime.TERMINAL:
                time.sleep(0.2)
                run = runtime.get(run["id"])
            print(json.dumps(run, ensure_ascii=False, indent=2))
            return 0 if run["status"] == "completed" else 1
    except KeyboardInterrupt:
        try:
            runtime.shutdown()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
