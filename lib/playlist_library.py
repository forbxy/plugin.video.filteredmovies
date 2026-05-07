# -*- coding: utf-8 -*-
import traceback

import xbmc

from lib.common import jsonrpc_request, log

MAX_PLAYLIST_ITEMS_BEFORE = 50
MAX_PLAYLIST_ITEMS_AFTER = 50


def get_autoplay_next_values():
    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Settings.GetSettingValue",
        "params": {
            "setting": "videoplayer.autoplaynextitem",
        },
        "id": "Settings.GetSettingValue",
    }) or {}

    value = result.get("value") if isinstance(result, dict) else None
    if isinstance(value, list):
        values = []
        for item in value:
            try:
                values.append(int(item))
            except (TypeError, ValueError):
                continue
        return values

    if isinstance(value, (int, float)):
        return [int(value)]

    if isinstance(value, str):
        values = []
        for item in value.split(','):
            item = item.strip()
            if not item:
                continue
            try:
                values.append(int(item))
            except ValueError:
                continue
        return values

    return []


def set_autoplay_next_values(values):
    normalized = sorted(set(int(v) for v in values))
    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Settings.SetSettingValue",
        "params": {
            "setting": "videoplayer.autoplaynextitem",
            "value": normalized,
        },
        "id": "Settings.SetSettingValue",
    })
    return bool(result)


def normalize_media_path(path):
    if not path:
        return ""
    normalized = str(path).split('?', 1)[0].split('#', 1)[0]
    return normalized.replace('\\', '/').rstrip('/')


def get_active_video_playlist_state():
    players = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Player.GetActivePlayers",
        "id": "Player.GetActivePlayers",
    }) or []
    video_player = next((p for p in players if p.get("type") == "video"), None)
    if not video_player:
        return None

    player_id = video_player.get("playerid")
    properties = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Player.GetProperties",
        "params": {
            "playerid": player_id,
            "properties": ["playlistid", "position"],
        },
        "id": "Player.GetProperties",
    }) or {}
    item = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Player.GetItem",
        "params": {
            "playerid": player_id,
            "properties": ["file", "tvshowid", "season", "episode", "showtitle", "title"],
        },
        "id": "Player.GetItem",
    }) or {}

    current_item = item.get("item") or {}
    playlistid = int(properties.get("playlistid") or 1)
    position = int(properties.get("position") or 0)
    # playlistid/position 为负数说明 Kodi 未将当前项加入播放列表，跳过补全
    if playlistid < 0 or position < 0:
        return None
    return {
        "playerid": player_id,
        "playlistid": playlistid,
        "position": position,
        "file": current_item.get("file") or "",
        "tvshowid": current_item.get("tvshowid"),
        "season": current_item.get("season"),
        "episode": current_item.get("episode"),
        "showtitle": current_item.get("showtitle") or "",
        "title": current_item.get("title") or "",
        "type": current_item.get("type") or "",
    }


def get_playlist_files(playlist_id):
    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Playlist.GetItems",
        "params": {
            "playlistid": playlist_id,
            "properties": ["file"],
        },
        "id": "Playlist.GetItems",
    }) or {}
    items = result.get("items") or []
    return [item.get("file") for item in items if item.get("file")]


def get_season_playlist_files(tvshow_id, season):
    if tvshow_id in (None, -1) or season in (None, -1):
        return []

    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "VideoLibrary.GetEpisodes",
        "params": {
            "tvshowid": int(tvshow_id),
            "season": int(season),
            "properties": ["file", "episode", "season", "title"],
            "sort": {"method": "episode", "order": "ascending"},
        },
        "id": "VideoLibrary.GetEpisodes",
    }) or {}
    episodes = result.get("episodes") or []
    return [item.get("file") for item in episodes if item.get("file")]


def insert_playlist_item(playlist_id, position, file_path):
    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Playlist.Insert",
        "params": {
            "playlistid": playlist_id,
            "position": position,
            "item": {"file": file_path},
        },
        "id": "Playlist.Insert",
    })
    return result == "OK"


def _sync_season_playlist(playlist_id, current_position, current_file_norm, target_norms, target_files):
    """刮削剧集：将播放列表同步为正确顺序（补全缺失 + 修正乱序，一次完成）。"""
    target_norm_to_idx = {n: i for i, n in enumerate(target_norms)}
    current_target_idx = target_norm_to_idx.get(current_file_norm, -1)
    if current_target_idx < 0:
        return

    # 确定应出现在播放列表中的集数（当前项前后各50集窗口）
    desired_before = list(zip(
        target_files[:current_target_idx], target_norms[:current_target_idx]
    ))[-MAX_PLAYLIST_ITEMS_BEFORE:]
    desired_after = list(zip(
        target_files[current_target_idx + 1:], target_norms[current_target_idx + 1:]
    ))[:MAX_PLAYLIST_ITEMS_AFTER]

    # 检查播放列表中当前项前后的季集数是否已是期望的内容和顺序
    fresh_norms = [normalize_media_path(p) for p in get_playlist_files(playlist_id)]
    season_before = [n for n in fresh_norms[:current_position] if n in target_norm_to_idx]
    season_after = [n for n in fresh_norms[current_position + 1:] if n in target_norm_to_idx]
    if season_before == [n for _, n in desired_before] and season_after == [n for _, n in desired_after]:
        return

    # 删除播放列表中所有本季集数（不含当前项），从高位到低位避免偏移
    season_positions = [i for i, n in enumerate(fresh_norms) if i != current_position and n in target_norm_to_idx]
    for pos in sorted(season_positions, reverse=True):
        jsonrpc_request({
            "jsonrpc": "2.0",
            "method": "Playlist.Remove",
            "params": {"playlistid": playlist_id, "position": pos},
            "id": "Playlist.Remove",
        })

    # 删除后当前项位置前移（删掉了多少个在它之前的项）
    new_pos = current_position - sum(1 for p in season_positions if p < current_position)

    # 将前置集数插到当前项前面，后置集数插到当前项后面
    for i, (path, _) in enumerate(desired_before):
        insert_playlist_item(playlist_id, new_pos + i, path)
    for i, (path, _) in enumerate(desired_after):
        insert_playlist_item(playlist_id, new_pos + len(desired_before) + 1 + i, path)

    log(f"Synced season playlist: before={len(desired_before)}, after={len(desired_after)}, playlistid={playlist_id}")


def autofill_playlist_for_current_video():
    try:
        _autofill_playlist_for_current_video()
    except Exception as e:
        log(f"Autofill playlist error: {e}\n{traceback.format_exc()}", xbmc.LOGERROR)


def _autofill_playlist_for_current_video():
    state = get_active_video_playlist_state()
    if not state:
        return

    # 已刮削电影不补充/修正播放列表
    if state.get("type") == "movie":
        return

    current_file = state.get("file") or ""
    current_file_norm = normalize_media_path(current_file)
    if not current_file_norm:
        return

    tvshow_id = state.get("tvshowid")
    season = state.get("season")
    is_scraped_tvshow = tvshow_id not in (None, -1) and season not in (None, -1)
    if not is_scraped_tvshow:
        return

    target_files = get_season_playlist_files(tvshow_id, season)

    target_files = [path for path in target_files if path]
    if len(target_files) <= 1:
        return

    target_norms = [normalize_media_path(path) for path in target_files]
    if current_file_norm not in target_norms:
        return

    playlist_id = state.get("playlistid", 1)
    current_position = state.get("position", 0)

    # 刮削剧集：补全缺失并修正乱序，一次完成
    _sync_season_playlist(playlist_id, current_position, current_file_norm, target_norms, target_files)