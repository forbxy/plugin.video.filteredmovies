# -*- coding: utf-8 -*-
from .common import log
import xbmcvfs
import xbmc
import itertools
import xbmcgui
import os
import json
import threading


_T9_MAP = {
    'A': '2', 'B': '2', 'C': '2',
    'D': '3', 'E': '3', 'F': '3',
    'G': '4', 'H': '4', 'I': '4',
    'J': '5', 'K': '5', 'L': '5',
    'M': '6', 'N': '6', 'O': '6',
    'P': '7', 'Q': '7', 'R': '7', 'S': '7',
    'T': '8', 'U': '8', 'V': '8',
    'W': '9', 'X': '9', 'Y': '9', 'Z': '9',
    '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
    '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
}

_MAX_ORIGINALTITLE_BYTES = 64 * 1024
_MAX_READINGS_PER_CHAR = 3   # 单个字符最多取几个读音
_MAX_HETERONYM_CHARS = 3     # 最多允许几个多音字参与排列组合，超出的取第一个


class T9Helper:
    UPDATE_BATCH_SIZE = 20

    def __init__(self, addon_id="plugin.video.filteredmovies"):
        self.ADDON_ID = addon_id
        self.ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{self.ADDON_ID}/")
        self.ADDON_DATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{self.ADDON_ID}/")

        if not os.path.exists(self.ADDON_DATA_PATH):
            os.makedirs(self.ADDON_DATA_PATH)

        self.CHAR_MAP_FILE = os.path.join(self.ADDON_PATH, "resources", "char_map.json")

        self.char_map = None
        self._ensure_thread = None
        self._ensure_lock = threading.Lock()

    def ensure_search_index_ready_async(self, show_progress=True, skip_check=False):
        """
        异步确保电影/剧集搜索索引已准备，避免阻塞调用方。
        若已有准备任务在运行，则跳过重复启动。
        skip_check=True 时跳过 unprepared 检查，直接全量比对更新。
        """
        with self._ensure_lock:
            if self._ensure_thread is not None and self._ensure_thread.is_alive():
                log("Search index prepare is already running. Skip duplicate ensure request.")
                return False

            self._ensure_thread = threading.Thread(
                target=self.ensure_search_index_ready,
                args=(show_progress, skip_check),
                daemon=True,
            )
            self._ensure_thread.start()

        return True

    def ensure_search_index_ready(self, show_progress=True, skip_check=False):
        """
        同步检查并确保电影/剧集搜索索引已准备。
        通过 JSON-RPC 查询 originaltitle 中是否仍存在缺少数字索引的条目来判断。
        任一类型存在未准备条目时执行电影 C16 + 剧集 C09 的准备流程。
        skip_check=True 时跳过检查，直接全量比对更新。
        """
        if not skip_check:
            movie_unprepared = self._has_unprepared_originaltitle_entries("movie")
            tvshow_unprepared = self._has_unprepared_originaltitle_entries("tvshow")

            if not movie_unprepared and not tvshow_unprepared:
                log("ensure_search_index_ready finished: query check passed, all ready.")
                return True

            missing_targets = []
            if movie_unprepared:
                missing_targets.append("movie C16")
            if tvshow_unprepared:
                missing_targets.append("tvshow C09")
            log(
                f"Detected unprepared {' and '.join(missing_targets)} via originaltitle query. "
                "Start preparing movie C16 and tvshow C09."
            )
        prepared = self._prepare_all_items(show_progress=show_progress)
        log(f"ensure_search_index_ready finished: prepared={prepared}.")
        return prepared

    def _load_char_map(self):
        """
        加载汉字转拼音/T9码的映射表。
        """
        if self.char_map is None:
            try:
                with open(self.CHAR_MAP_FILE, "r", encoding="utf-8") as f:
                    self.char_map = json.load(f)
            except Exception as e:
                log(f"ERROR load char_map: {e}", xbmc.LOGERROR)
                self.char_map = {}
    
    def _clear_char_map(self):
        """
        清除加载的汉字转拼音/T9码的映射表，释放内存。
        """
        self.char_map = None

    def _generate_t9_codes(self, title):
        """
        为完整标题生成所有可能的 T9 全拼数字串（支持多音字组合）。
        """
        process_title = title or ""

        self._load_char_map()

        full_options = []

        for char in process_title:
            char_full = set()

            # 尝试获取汉字的拼音数据
            pinyin_data = self.char_map.get(char)
            if not pinyin_data:
                pinyin_data = self.char_map.get(char.upper())

            if pinyin_data:
                # 如果是列表说明有多音字
                readings = pinyin_data if isinstance(pinyin_data, list) else [pinyin_data]
                for p in readings:
                    # 全拼处理
                    full_digits = ""
                    for pc in p:
                        pc_upper = pc.upper()
                        if pc_upper in _T9_MAP:
                            full_digits += _T9_MAP[pc_upper]
                    if full_digits:
                        char_full.add(full_digits)
            else:
                # 非汉字字符（英文/数字）直接转换，其他符号忽略
                c = char.upper()
                if c in _T9_MAP:
                    digit = _T9_MAP[c]
                    char_full.add(digit)

            if char_full:
                full_options.append(sorted(char_full)[:_MAX_READINGS_PER_CHAR])

        # 限制多音字数量，超出的只保留第一个
        heteronym_count = 0
        for i, opts in enumerate(full_options):
            if len(opts) > 1:
                heteronym_count += 1
                if heteronym_count > _MAX_HETERONYM_CHARS:
                    full_options[i] = [opts[0]]

        results = set()

        # 生成所有可能的组合
        if full_options:
            for combo in itertools.product(*full_options):
                results.add("".join(combo))

        return sorted(results)

    def _generate_initial_codes(self, title):
        """
        为完整标题生成所有可能的首字母索引串（支持多音字组合）。
        """
        process_title = title or ""

        self._load_char_map()

        initial_options = []

        for char in process_title:
            char_initials = set()

            pinyin_data = self.char_map.get(char)
            if not pinyin_data:
                pinyin_data = self.char_map.get(char.upper())

            if pinyin_data:
                readings = pinyin_data if isinstance(pinyin_data, list) else [pinyin_data]
                for p in readings:
                    if not p or not isinstance(p, str):
                        continue
                    initial = p[0].upper()
                    if "A" <= initial <= "Z":
                        char_initials.add(initial)
            else:
                c = char.upper()
                if "A" <= c <= "Z":
                    char_initials.add(c)

            # 数字字符保留数字本身
            c = char.upper()
            if "0" <= c <= "9":
                char_initials.add(c)

            if char_initials:
                initial_options.append(sorted(char_initials)[:_MAX_READINGS_PER_CHAR])

        # 限制多音字数量，超出的只保留第一个
        heteronym_count = 0
        for i, opts in enumerate(initial_options):
            if len(opts) > 1:
                heteronym_count += 1
                if heteronym_count > _MAX_HETERONYM_CHARS:
                    initial_options[i] = [opts[0]]

        results = set()
        if initial_options:
            for combo in itertools.product(*initial_options):
                results.add("".join(combo))

        return sorted(results)

    def _jsonrpc(self, payload):
        try:
            response = xbmc.executeJSONRPC(json.dumps(payload))
            result = json.loads(response)
            if isinstance(result, dict) and "error" in result:
                log(f"JSON-RPC error: {result.get('error')}")
            return result
        except Exception as e:
            log(f"JSON-RPC call failed: {e}", xbmc.LOGERROR)
            return {}

    def _jsonrpc_batch(self, payloads):
        if not payloads:
            return []
        try:
            response = xbmc.executeJSONRPC(json.dumps(payloads))
            result = json.loads(response)
            if isinstance(result, dict) and "error" in result:
                log(f"JSON-RPC batch error: {result.get('error')}")
            return result
        except Exception as e:
            log(f"JSON-RPC batch call failed: {e}", xbmc.LOGERROR)
            return {}

    def _get_all_movies_rpc(self, properties=None):
        props = properties or ["title", "originaltitle"]
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": props,
                "sort": {"method": "none"}
            },
            "id": 1
        }
        result = self._jsonrpc(json_query)
        return result.get('result', {}).get('movies', [])

    def _get_all_tvshows_rpc(self, properties=None):
        props = properties or ["title", "originaltitle"]
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetTVShows",
            "params": {
                "properties": props,
                "sort": {"method": "none"}
            },
            "id": 1
        }
        result = self._jsonrpc(json_query)
        return result.get('result', {}).get('tvshows', [])

    def _get_all_moviesets_rpc(self, properties=None):
        props = properties or ["title", "plot"]
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovieSets",
            "params": {
                "properties": props,
                "sort": {"method": "none"}
            },
            "id": 1
        }
        result = self._jsonrpc(json_query)
        return result.get('result', {}).get('sets', [])

    def _has_unprepared_originaltitle_entries(self, media_type):
        """
        检查是否存在 originaltitle 缺少数字索引的条目。
        仅拉取 1 条用于 existence check。
        """
        if media_type == "movie":
            method = "VideoLibrary.GetMovies"
            result_key = "movies"
        else:
            method = "VideoLibrary.GetTVShows"
            result_key = "tvshows"

        query = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "properties": ["title", "originaltitle"],
                "sort": {"method": "none"},
                "limits": {"start": 0, "end": 1},
                "filter": {
                    "and": [
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|0",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|1",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|2",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|3",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|4",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|5",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|6",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|7",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|8",
                        },
                        {
                            "field": "originaltitle",
                            "operator": "doesnotcontain",
                            "value": "|9",
                        },
                    ]
                },
            },
            "id": f"search_index_unprepared_{media_type}",
        }

        result = self._jsonrpc(query)
        if not isinstance(result, dict) or "error" in result:
            # 查询异常时保守处理：视为未准备，触发准备流程。
            log(f"Query unprepared {media_type} failed, fallback to prepare.", xbmc.LOGWARNING)
            return True

        entries = result.get("result", {}).get(result_key, [])
        if not entries:
            return False

        sample = entries[0] if isinstance(entries[0], dict) else {}
        sample_id_key = "movieid" if media_type == "movie" else "tvshowid"
        sample_id = sample.get(sample_id_key)
        sample_title = sample.get("title", "") or ""
        sample_original = sample.get("originaltitle", "") or ""

        log(
            f"Unprepared {media_type} sample: id={sample_id}, title={sample_title}, "
            f"originaltitle={sample_original}"
        )
        return True

    # media_type -> (rpc_method, id_param, value_param)
    _MEDIA_RPC_MAP = {
        "movie": ("VideoLibrary.SetMovieDetails", "movieid", "originaltitle"),
        "tvshow": ("VideoLibrary.SetTVShowDetails", "tvshowid", "originaltitle"),
        "set": ("VideoLibrary.SetMovieSetDetails", "setid", "plot"),
    }

    def _set_item_field(self, media_type, item_id, value):
        rpc_method, id_param, value_param = self._MEDIA_RPC_MAP[media_type]
        query = {
            "jsonrpc": "2.0",
            "method": rpc_method,
            "params": {
                id_param: int(item_id),
                value_param: value,
            },
            "id": f"set_{media_type}_{item_id}",
        }
        result = self._jsonrpc(query)
        return "error" not in result

    def _flush_field_updates(self, media_type, pending_updates):
        """
        批量提交字段更新，批量失败或单项失败时回退到单条提交。
        pending_updates: [{"id": ..., "value": ...}, ...]
        """
        if not pending_updates:
            return 0

        rpc_method, id_param, value_param = self._MEDIA_RPC_MAP[media_type]

        payloads = []
        ordered_ids = []
        for idx, item in enumerate(pending_updates):
            item_id = int(item["id"])
            req_id = f"t9_{media_type}_{item_id}_{idx}"
            ordered_ids.append(req_id)
            payloads.append(
                {
                    "jsonrpc": "2.0",
                    "method": rpc_method,
                    "params": {
                        id_param: item_id,
                        value_param: item["value"],
                    },
                    "id": req_id,
                }
            )

        updated = 0
        result = self._jsonrpc_batch(payloads)

        def fallback_one(single_item):
            return self._set_item_field(media_type, single_item["id"], single_item["value"])

        # 批量能力不可用时，整批回退单条更新。
        if not isinstance(result, list):
            log(f"Batch update unavailable for {media_type}, fallback to single updates.")
            for item in pending_updates:
                if fallback_one(item):
                    updated += 1
            return updated

        result_by_id = {}
        for entry in result:
            if isinstance(entry, dict) and "id" in entry:
                result_by_id[str(entry.get("id"))] = entry

        for idx, item in enumerate(pending_updates):
            req_id = ordered_ids[idx]
            entry = result_by_id.get(req_id)

            # 缺失响应或响应错误时，回退该条。
            if not entry or "error" in entry:
                if entry and "error" in entry:
                    log(f"Batch item error ({media_type}, id={item['id']}): {entry.get('error')}")
                if fallback_one(item):
                    updated += 1
                continue

            updated += 1

        return updated

    def _update_progress(self, dialog, processed, total, kind, title):
        if not dialog or total <= 0:
            return
        percent = int((processed * 100) / total)
        line1 = f"正在准备搜索索引: {processed}/{total}"
        line2 = f"{kind}: {title or '未知标题'}"
        try:
            dialog.update(percent, line1, line2)
        except TypeError:
            dialog.update(percent, line1)

    def _compute_target_original(self, source_title, current_original):
        generated_t9_codes = self._generate_t9_codes(source_title)
        generated_initial_codes = self._generate_initial_codes(source_title)

        existing_parts = set(current_original.split("|")) if current_original else set()

        missing_t9 = [c for c in generated_t9_codes if c not in existing_parts]
        missing_initial = [c for c in generated_initial_codes if c not in existing_parts]

        result = current_original or ""
        for part in missing_t9 + missing_initial:
            candidate = f"{result}|{part}" if result else part
            if len(candidate.encode("utf-8")) > _MAX_ORIGINALTITLE_BYTES:
                break
            result = candidate
        if result and "|" not in result:
            result = "|" + result

        if not any(f"|{d}" in result for d in "0123456789"):
            candidate = f"{result}|0" if result else "|0"
            if len(candidate.encode("utf-8")) <= _MAX_ORIGINALTITLE_BYTES:
                result = candidate

        return result

    def _prepare_all_items(self, show_progress=True):
        dialog = None
        if show_progress:
            dialog = xbmcgui.DialogProgress()
            try:
                dialog.create("搜索索引准备中", "正在准备电影、剧集和合集搜索索引...")
            except TypeError:
                dialog.create("搜索索引准备中")

        movies = self._get_all_movies_rpc(properties=["title", "originaltitle"])
        tvshows = self._get_all_tvshows_rpc(properties=["title", "originaltitle"])
        moviesets = self._get_all_moviesets_rpc(properties=["title", "plot"])

        total = len(movies) + len(tvshows) + len(moviesets)
        if total <= 0:
            if dialog:
                dialog.close()
            return True

        processed = 0
        updated = 0
        canceled = False

        # (items, id_key, media_type, kind, value_field)
        media_groups = [
            (movies, "movieid", "movie", "电影", "originaltitle"),
            (tvshows, "tvshowid", "tvshow", "剧集", "originaltitle"),
            (moviesets, "setid", "set", "合集", "plot"),
        ]

        self._load_char_map()
        try:
            for items, id_key, media_type, kind, value_field in media_groups:
                pending_updates = []
                for item in items:
                    processed += 1
                    if dialog and dialog.iscanceled():
                        canceled = True
                        break

                    item_id = item.get(id_key)
                    title = item.get("title", "") or ""
                    current_value = item.get(value_field, "") or ""
                    source_title = title.strip()

                    if item_id is not None and source_title:
                        target_value = self._compute_target_original(source_title, current_value)
                        if target_value != current_value:
                            pending_updates.append(
                                {"id": item_id, "value": target_value}
                            )
                            if len(pending_updates) >= self.UPDATE_BATCH_SIZE:
                                updated += self._flush_field_updates(media_type, pending_updates)
                                pending_updates = []

                    self._update_progress(dialog, processed, total, kind, title)

                if not canceled and pending_updates:
                    updated += self._flush_field_updates(media_type, pending_updates)
                if canceled:
                    break
        finally:
            self._clear_char_map()
            if dialog:
                dialog.close()

        if canceled:
            log("Search index prepare canceled by user.", xbmc.LOGWARNING)
            return False

        log(f"Search index prepare finished. updated={updated}, total={total}")
        return True



# Global instance
_helper = None

class HelperProxy:
    def __getattr__(self, name):
        global _helper
        if _helper is None:
            _helper = T9Helper()
        return getattr(_helper, name)

helper = HelperProxy()