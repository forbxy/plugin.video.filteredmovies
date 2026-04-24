# -*- coding: utf-8 -*-
import argparse
import base64
import json
import sys
import urllib.error
import urllib.request


def call_jsonrpc(endpoint, method, params=None, rpc_id=1, username="", password="", timeout=10):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": rpc_id,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})

    if username:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def print_block(title, obj):
    print(f"\n===== {title} =====")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="打印 Kodi 当前播放视频的字幕/音轨 JSON-RPC 原始返回"
    )
    parser.add_argument("--host", default="192.168.50.79", help="Kodi 主机地址")
    parser.add_argument("--port", type=int, default=8080, help="Kodi Web 端口")
    parser.add_argument("--user", default="", help="Kodi Web 用户名（可选）")
    parser.add_argument("--password", default="", help="Kodi Web 密码（可选）")
    parser.add_argument("--timeout", type=int, default=10, help="请求超时秒数")
    args = parser.parse_args()

    endpoint = f"http://{args.host}:{args.port}/jsonrpc"

    try:
        active_players = call_jsonrpc(
            endpoint,
            "Player.GetActivePlayers",
            rpc_id=1,
            username=args.user,
            password=args.password,
            timeout=args.timeout,
        )
        print_block("Player.GetActivePlayers 原始返回", active_players)

        players = active_players.get("result", []) if isinstance(active_players, dict) else []
        if not players:
            print("\n未检测到活动播放器。")
            return 0

        video_player = None
        for p in players:
            if p.get("type") == "video":
                video_player = p
                break

        target = video_player or players[0]
        player_id = target.get("playerid")

        if player_id is None:
            print("\n活动播放器数据缺少 playerid，无法继续。")
            return 1

        props = call_jsonrpc(
            endpoint,
            "Player.GetProperties",
            params={
                "playerid": player_id,
                "properties": [
                    "subtitles",
                    "currentsubtitle",
                    "subtitleenabled",
                    "audiostreams",
                    "currentaudiostream",
                ],
            },
            rpc_id=2,
            username=args.user,
            password=args.password,
            timeout=args.timeout,
        )
        print_block("Player.GetProperties(字幕/音轨) 原始返回", props)

        return 0

    except urllib.error.HTTPError as e:
        print(f"HTTP 错误: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        print(f"网络错误: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except Exception as e:
        print(f"未知错误: {e}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
