# -*- coding: utf-8 -*-
import xbmc
from lib.common import jsonrpc_request, log

# 单次补全窗口限制为当前集前后各 10 集，减少 JSON-RPC 次数。
MAX_PLAYLIST_ITEMS_BEFORE = 10
MAX_PLAYLIST_ITEMS_AFTER = 10
MAX_DELETE_LOWER_EPISODES_BELOW = 10
# 插入/删除播放列表项后等待 300ms，给 Kodi 足够时间处理更新并避免过快连续操作导致的异常。
PLAYLIST_MUTATION_DELAY_MS = 300


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


def get_playlist_items(playlist_id):
    # 读取 Kodi 实际播放列表，并转换成仅包含补全所需的轻量结构。
    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "Playlist.GetItems",
        "params": {
            "playlistid": playlist_id,
            "properties": ["tvshowid", "season", "episode"],
        },
        "id": "Playlist.GetItems",
    }) or {}
    playlist = result.get("items") or []
    for idx, itm in enumerate(playlist):
        itm["position"] = idx

    return playlist


def get_season_episode(tvshow_id, season):
    if tvshow_id in (None, -1) or season in (None, -1):
        return None

    result = jsonrpc_request({
        "jsonrpc": "2.0",
        "method": "VideoLibrary.GetEpisodes",
        "params": {
            "tvshowid": int(tvshow_id),
            "season": int(season),
            "properties": ["episode"],
            "sort": {"method": "episode", "order": "ascending"},
        },
        "id": "VideoLibrary.GetEpisodes",
    }) or {}
    episodes = result.get("episodes") or []
    
    if not episodes:
        return None
    for itm in episodes:
        itm["tvshowid"] = int(tvshow_id)
        itm["season"] = int(season)
        itm["id"] = itm.get("episodeid")

    return {
        "tvshowid": int(tvshow_id),
        "season": int(season),
        "episodes": episodes,
    }


class EpisodePlayList:
    PLAYLIST_ID = 1

    def __init__(self, current_episode, current_season):
        self.current_episode = int(current_episode)
        self.current_season = current_season

        if not isinstance(self.current_season, dict):
            raise ValueError("current_season should be a dict of season info")
        if self.current_season.get("season") in (None, -1) or self.current_season.get("tvshowid") in (None, -1):
            raise ValueError(f"current_season should have valid 'season' and 'tvshowid', got: season={self.current_season.get('season')}, tvshowid={self.current_season.get('tvshowid')}")
        if not self.current_season.get("episodes") or (not isinstance(self.current_season.get("episodes"), list)):
            raise ValueError(f"current_season should have valid 'episodes' list, got: {self.current_season.get('episodes')}")

        # 仅缓存当前播放列表，以及当前播放集在列表中的首个匹配项引用。
        self.playlist_items = get_playlist_items(self.PLAYLIST_ID)
        # 简化策略：按 episode（第几集）匹配第一个，作为当前播放集。
        self.current_play = self._find_current_play()

    def _find_current_play(self):
        for item in self.playlist_items:
            if item.get("episode") == self.current_episode and self.current_season.get("season") == item.get("season") \
                and self.current_season.get("tvshowid") == item.get("tvshowid"):
                # 直接返回列表项引用，避免不必要拷贝。
                return item
        log(
            "Current playing episode not found in playlist: "
            f"current_episode={self.current_episode}, current_season={self.current_season}", xbmc.LOGERROR
        )

    def _reindex_items(self):
        for idx, item in enumerate(self.playlist_items):
            item["position"] = idx

    def insert(self, position, episode_item):

        result = jsonrpc_request({
            "jsonrpc": "2.0",
            "method": "Playlist.Insert",
            "params": {
                "playlistid": self.PLAYLIST_ID,
                "position": int(position),
                "item": {"episodeid": episode_item.get("id")},
            },
            "id": "Playlist.Insert",
        })
        if result != "OK":
            return False

        position = int(position)
        if position < 0:
            position = 0
        if position > len(self.playlist_items):
            position = len(self.playlist_items)

        # RPC 成功后同步更新本地缓存，避免再次全量读取播放列表。
        self.playlist_items.insert(position, {
            "position": position,
            "type": "episode",
            "episode": episode_item.get("episode"),
            "id": episode_item.get("id"),
            "season": episode_item.get("season"),
            "tvshowid": episode_item.get("tvshowid"),
        })
        self._reindex_items()
        xbmc.sleep(PLAYLIST_MUTATION_DELAY_MS)
        return True

    def remove(self, position):
        try:
            position = int(position)
        except (TypeError, ValueError):
            return False

        current_position = self.current_play.get("position") if isinstance(self.current_play, dict) else None
        if isinstance(current_position, int) and position == current_position:
            log(
                "Skip removing current playing item: "
                f"position={position}, playlistid={self.PLAYLIST_ID}"
            )
            return False

        result = jsonrpc_request({
            "jsonrpc": "2.0",
            "method": "Playlist.Remove",
            "params": {
                "playlistid": self.PLAYLIST_ID,
                "position": position,
            },
            "id": "Playlist.Remove",
        })
        if result != "OK":
            return False

        if 0 <= position < len(self.playlist_items):
            self.playlist_items.pop(position)
        self._reindex_items()
        xbmc.sleep(PLAYLIST_MUTATION_DELAY_MS)

        return True

    def _remove_incorrect_order_episodes(self):
        remove_items = []

        if not self.current_play:
            return 0

        # 仅处理“当前集后方出现更早剧集”的乱序场景，最多删除 5 条。
        for item in self.playlist_items[self.current_play["position"] + 1:]:
            # 只删除同季剧集
            is_c_tvshow = item.get("tvshowid") == self.current_season.get("tvshowid")
            is_c_season = is_c_tvshow and item.get("season") == self.current_season.get("season")
            if not is_c_season:
                continue

            if item['episode'] < self.current_play["episode"]:
                remove_items.append(item)
                if len(remove_items) >= MAX_DELETE_LOWER_EPISODES_BELOW:
                    break

        if remove_items:
            log(
                "Playlist remove plan: "
                f"current_episode={self.current_episode}, "
                f"remove_after={[item.get('episode') for item in remove_items]}, "
                f"playlistid={self.PLAYLIST_ID}"
            )

        removed = 0
        # 倒序删除，避免位置前移导致后续下标失真。
        for item in sorted(remove_items, key=lambda candidate: candidate.get("position", -1), reverse=True):
            pos = item.get("position")
            if not isinstance(pos, int):
                continue

            if self.remove(pos):
                removed += 1
                log(
                    "Removed incorrect order item: "
                    f"episode={item.get('episode')}, id={item.get('id')}, "
                    f"position={pos}, playlistid={self.PLAYLIST_ID}"
                )
        return removed


    def _fill_neighbors_around_current(self):
        insert_before = 0
        insert_after = 0
        if not self.current_play:
            return insert_before, insert_after

        season_episodes = self.current_season.get("episodes")
        if not isinstance(season_episodes, list):
            return insert_before, insert_after

        current_episode_idx = -1
        current_play_id = self.current_play.get("id")
        for idx, item in enumerate(season_episodes):
            if not isinstance(item, dict):
                continue
            if item.get("id") == current_play_id:
                current_episode_idx = idx
                break

        if current_episode_idx < 0:
            return insert_before, insert_after

        current_tvshowid = self.current_season.get("tvshowid")
        current_season_id = self.current_season.get("season")
        existing_ids = {
            item.get("id")
            for item in self.playlist_items
            if item.get("tvshowid") == current_tvshowid
            and item.get("season") == current_season_id
            and item.get("id") is not None
        }

        desired_before = season_episodes[max(0, current_episode_idx - MAX_PLAYLIST_ITEMS_BEFORE):current_episode_idx]
        desired_after = season_episodes[current_episode_idx + 1:current_episode_idx + 1 + MAX_PLAYLIST_ITEMS_AFTER]
        missing_before = [item for item in desired_before if item.get("id") not in existing_ids]
        missing_after = [item for item in desired_after if item.get("id") not in existing_ids]

        if missing_before or missing_after:
            log(
                "Playlist fill plan: "
                f"current_episode={self.current_episode}, "
                f"missing_before={[item.get('episode') for item in missing_before]}, "
                f"missing_after={[item.get('episode') for item in missing_after]}, "
                f"playlistid={self.PLAYLIST_ID}"
            )

        def get_insert_position(target_episode):
            if not isinstance(target_episode, int):
                return None

            last_same_season_position = None
            for item in self.playlist_items:
                is_same_tvshow = item.get("tvshowid") == current_tvshowid
                is_same_season = is_same_tvshow and item.get("season") == current_season_id
                if not is_same_season:
                    continue

                position = item.get("position")
                last_same_season_position = position

                item_episode = item.get("episode")
                if item_episode > target_episode:
                    return position

            if isinstance(last_same_season_position, int):
                return last_same_season_position + 1
            return len(self.playlist_items)

        for episode_item in missing_before:
            insert_pos = get_insert_position(episode_item.get("episode"))
            if not isinstance(insert_pos, int):
                continue

            if self.insert(insert_pos, episode_item):
                insert_before += 1
                existing_ids.add(episode_item.get("id"))
                log(
                    "Inserted missing before item: "
                    f"episode={episode_item.get('episode')}, id={episode_item.get('id')}, "
                    f"position={insert_pos}, playlistid={self.PLAYLIST_ID}"
                )

        for episode_item in missing_after:
            insert_pos = get_insert_position(episode_item.get("episode"))
            if not isinstance(insert_pos, int):
                continue

            if self.insert(insert_pos, episode_item):
                insert_after += 1
                existing_ids.add(episode_item.get("id"))
                log(
                    "Inserted missing after item: "
                    f"episode={episode_item.get('episode')}, id={episode_item.get('id')}, "
                    f"position={insert_pos}, playlistid={self.PLAYLIST_ID}"
                )

        return insert_before, insert_after


    def fix_playlist(self):
        try:
            int(self.current_episode)
        except (TypeError, ValueError):
            return

        if not isinstance(self.current_play, dict):
            return

        season = self.current_season if isinstance(self.current_season, dict) else {}
        tvshow_id = season.get("tvshowid")
        season_id = season.get("season")
        is_scraped_tvshow = tvshow_id not in (None, -1) and season_id not in (None, -1)
        if not is_scraped_tvshow:
            return

        removed_below = self._remove_incorrect_order_episodes()
        inserted_before, inserted_after = self._fill_neighbors_around_current()

        if removed_below or inserted_before or inserted_after:
            log(
                "Synced season playlist: "
                f"removed_below={removed_below}, before={inserted_before}, after={inserted_after}, "
                f"playlistid={self.PLAYLIST_ID}"
            )
