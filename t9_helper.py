# -*- coding: utf-8 -*-
import os
import json
import xbmcvfs
import xbmc
import xbmcgui
import itertools
import threading

class T9Helper:
    def __init__(self, addon_id="plugin.video.filteredmovies"):
        self.ADDON_ID = addon_id
        self.ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{self.ADDON_ID}/")
        self.ADDON_DATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{self.ADDON_ID}/")
        
        if not os.path.exists(self.ADDON_DATA_PATH):
            os.makedirs(self.ADDON_DATA_PATH)

        self.CACHE_FILE = os.path.join(self.ADDON_DATA_PATH, "movie_t9_cache.json")
        self.CHAR_MAP_FILE = os.path.join(self.ADDON_PATH, "resources", "char_map.json")
        
        self.CACHE_VERSION = 4
        t = addon_id.replace('.', '_')
        self.char_map = None

        self.cached_t9_map = None

        self.synced = False

    def log(self, msg, level=xbmc.LOGINFO):
        xbmc.log(f"[T9Helper] {msg}", level)
    
    def search(self, input_seq):
        """
        根据输入的数字序列搜索匹配的电影、剧集或系列。
        返回匹配的 ID 列表。
        """
        if not self.synced:
            self.build_memory_cache_sync()
        
        cache = self._get_cached_data()
        if not cache:
            return []
        
            
        matches = []
        
        # 搜索电影
        movies = cache.get("movies", {})
        for mid, codes in movies.items():
            for code in codes:
                if code.startswith(input_seq):
                    matches.append({"id": int(mid), "type": "movie"})
                    break
                    
        # 搜索剧集
        tvshows = cache.get("tvshows", {})
        for mid, codes in tvshows.items():
            for code in codes:
                if code.startswith(input_seq):
                    matches.append({"id": int(mid), "type": "tvshow"})
                    break

        # 搜索系列
        sets = cache.get("sets", {})
        for mid, codes in sets.items():
            for code in codes:
                if code.startswith(input_seq):
                    matches.append({"id": int(mid), "type": "set"})
                    break
        
        return matches
    
    def build_memory_cache_async(self):
        """
        异步构建或更新内存缓存。
        """
        t = threading.Thread(target=self.build_memory_cache_sync)
        t.daemon = True
        t.start()
    
    def build_memory_cache_sync(self):
        """
        同步构建或更新内存缓存。
        """
        cache = self._get_cached_data()
        # 3. 如果还是空的，初始化一个新的
        if cache is None:
            cache = {"movies": {}, "tvshows": {}, "sets": {}, "version": self.CACHE_VERSION}
            
        # 与库同步（核心逻辑）
        cache = self._sync_with_library(cache)
        
        # 写回内存属性
        self.cached_t9_map = cache
        self.synced = True
    

    def rebuild_cache(self):
        """
        强制重建缓存
        """
        self.log("Forcing T9 Cache Rebuild requested.")
        if os.path.exists(self.CACHE_FILE):
            try:
                os.remove(self.CACHE_FILE)
                self.log("Deleted old T9 cache file.")
            except Exception as e:
                self.log(f"Error delete old cache file: {e}", xbmc.LOGERROR)
        self.build_memory_cache_sync()
        self.synced = True

    def _load_char_map(self):
        """
        加载汉字转拼音/T9码的映射表。
        """
        if self.char_map is None:
            try:
                with open(self.CHAR_MAP_FILE, "r", encoding="utf-8") as f:
                    self.char_map = json.load(f)
            except Exception as e:
                self.log(f"ERROR load char_map: {e}", xbmc.LOGERROR)
                self.char_map = {}
    
    def _clear_char_map(self):
        """
        清除加载的汉字转拼音/T9码的映射表，释放内存。
        """
        self.char_map = None

    def _get_t9_map(self):
        """
        获取字母到 T9 数字键的映射。
        """
        return {
            'A': '2', 'B': '2', 'C': '2',
            'D': '3', 'E': '3', 'F': '3',
            'G': '4', 'H': '4', 'I': '4',
            'J': '5', 'K': '5', 'L': '5',
            'M': '6', 'N': '6', 'O': '6',
            'P': '7', 'Q': '7', 'R': '7', 'S': '7',
            'T': '8', 'U': '8', 'V': '8',
            'W': '9', 'X': '9', 'Y': '9', 'Z': '9',
            '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
            '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
        }

    def _generate_t9_codes(self, title):
        """
        为给定的标题生成所有可能的 T9 数字序列。
        支持多音字组合。
        """
        process_title = title[:10] # 仅处理前10个字符以提高性能
        
        self._load_char_map()
        t9_map = self._get_t9_map()
        
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
                        if pc_upper in t9_map:
                            full_digits += t9_map[pc_upper]
                    if full_digits:
                        char_full.add(full_digits)
            else:
                # 非汉字字符（英文/数字）直接转换
                c = char.upper()
                if c in t9_map:
                    digit = t9_map[c]
                    char_full.add(digit)
            
            if char_full:
                full_options.append(list(char_full))
        
        results = set()
        
        # 生成所有可能的组合
        if full_options:
            for combo in itertools.product(*full_options):
                results.add("".join(combo))
        
        return list(results)

    def _get_all_movies_rpc(self):
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": ["title"],
                "sort": {"method": "none"}
            },
            "id": 1
        }
        response = xbmc.executeJSONRPC(json.dumps(json_query))
        result = json.loads(response)
        return result.get('result', {}).get('movies', [])

    def _get_all_tvshows_rpc(self):
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetTVShows",
            "params": {
                "properties": ["title"],
                "sort": {"method": "none"}
            },
            "id": 1
        }
        response = xbmc.executeJSONRPC(json.dumps(json_query))
        result = json.loads(response)
        return result.get('result', {}).get('tvshows', [])

    def _get_all_sets_rpc(self):
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovieSets",
            "params": {
                "properties": ["title"],
                "sort": {"method": "none"}
            },
            "id": 1
        }
        response = xbmc.executeJSONRPC(json.dumps(json_query))
        result = json.loads(response)
        return result.get('result', {}).get('sets', [])

    def _get_cached_data(self):
        """
        获取缓存数据，优先从内存获取，其次从文件。
        """
        if self.cached_t9_map is None:
            
            if os.path.exists(self.CACHE_FILE):
                try:
                    with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                        self.cached_t9_map = json.load(f)
                except Exception as e:
                    self.log(f"ERROR load cache from file: {e}", xbmc.LOGERROR)
        return self.cached_t9_map

    def _check_needs_update(self, item_type, cache):
        """
        Check if cache needs update by comparing count, ID sets, and a random item's T9 codes.
        Fetches all IDs/Titles first (efficient enough) to avoid unsupported sort-by-id queries.
        """
        if item_type == "movies":
            method = "VideoLibrary.GetMovies"
            id_key = "movieid"
            cache_key = "movies"
        elif item_type == "tvshows":
            method = "VideoLibrary.GetTVShows"
            id_key = "tvshowid"
            cache_key = "tvshows"
        else:
            return False

        # 1. Get ALL items (ID + Title) from Remote
        # Requesting "title" property ensures we have the raw title for T9 generation
        json_query = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "properties": ["title"],
                "sort": {"method": "dateadded", "order": "descending"} # Use a valid sort method or none
            },
            "id": "check_all"
        }
        res = json.loads(xbmc.executeJSONRPC(json.dumps(json_query)))
        
        if "error" in res:
            self.log(f"Error checking update for {item_type}: {res.get('error')}")
            return True

        remote_items = res.get("result", {}).get(cache_key, [])
        total_remote = res.get("result", {}).get("limits", {}).get("total", 0)

        # If limits not in response, use len
        if not total_remote and remote_items:
            total_remote = len(remote_items)

        # Local checks
        local_cache = cache.get(cache_key, {})
        local_total = len(local_cache)

        if total_remote == 0:
             return local_total > 0

        if local_total != total_remote:
            self.log(f"[{item_type}] Count mismatch: Remote={total_remote}, Local={local_total}")
            return True

        # Check ID Set consistency
        remote_ids = set(str(item.get(id_key)) for item in remote_items)
        local_ids = set(local_cache.keys())
        
        if remote_ids != local_ids:
            # Check for differences
            missing_in_local = remote_ids - local_ids
            missing_in_remote = local_ids - remote_ids
            
            if missing_in_local:
                 self.log(f"[{item_type}] Local cache missing IDs: {list(missing_in_local)[:5]}...")
            if missing_in_remote:
                 self.log(f"[{item_type}] Local cache has extra IDs: {list(missing_in_remote)[:5]}...")
            
            return True

        # 2. Check a random item's T9 code
        if remote_items:
            import random
            random_item = random.choice(remote_items)
            rnd_id = str(random_item.get(id_key))
            rnd_title = random_item.get("title", "")
            
            # We already confirmed ID exists in local with the set check above
            if rnd_id in local_cache:
                remote_codes = set(self._generate_t9_codes(rnd_title))
                local_codes = set(local_cache[rnd_id])
                
                if remote_codes != local_codes:
                    self.log(f"[{item_type}] T9 Code mismatch for Random ID {rnd_id} ({rnd_title})")
                    return True
        
        return False

    def _sync_with_library(self, cache):
        """
        将本地缓存与 Kodi 媒体库进行同步。
        使用由 _check_needs_update 定义的策略进行检查。
        """
        dirty = False
        self._load_char_map()

        # 检查磁盘上是否存在缓存文件。
        if not os.path.exists(self.CACHE_FILE):
             dirty = True
        
        if "movies" not in cache: cache["movies"] = {}
        if "tvshows" not in cache: cache["tvshows"] = {}
        if "sets" not in cache: cache["sets"] = {}

        # --- 电影 (Movies) ---
        try:
            if self._check_needs_update("movies", cache):
                self.log("Movies cache needs update. Rebuilding all movies and sets...")
                
                # Full rebuild for movies
                movies = self._get_all_movies_rpc()
                cache["movies"] = {} # Clear existing
                
                for m in movies:
                    mid = str(m.get("movieid"))
                    title = m.get("title", "")
                    if title:
                        cache["movies"][mid] = self._generate_t9_codes(title)
                
                self.log(f"Rebuilt {len(cache['movies'])} movies.")

                # Rebuild sets as well since movies update often implies set changes or we just do it to be safe
                sets = self._get_all_sets_rpc()
                cache["sets"] = {}
                for s in sets:
                    mid = str(s.get("setid"))
                    title = s.get("title", "")
                    if title:
                        cache["sets"][mid] = self._generate_t9_codes(title)
                self.log(f"Rebuilt {len(cache['sets'])} sets.")
                
                dirty = True
            else:
                self.log("Movies cache is up-to-date.")

        except Exception as e:
            self.log(f"Error updating movies: {e}")
            import traceback
            traceback.print_exc()

        # --- 剧集 (TV Shows) ---
        try:
            if self._check_needs_update("tvshows", cache):
                self.log("TVShows cache needs update. Rebuilding all tvshows...")
                
                # Full rebuild for tvshows
                tvshows = self._get_all_tvshows_rpc()
                cache["tvshows"] = {} # Clear existing

                for t in tvshows:
                    mid = str(t.get("tvshowid"))
                    title = t.get("title", "")
                    if title:
                        cache["tvshows"][mid] = self._generate_t9_codes(title)
                
                self.log(f"Rebuilt {len(cache['tvshows'])} tvshows.")
                dirty = True
            else:
                 self.log("TVShows cache is up-to-date.")

        except Exception as e:
            self.log(f"Error updating tvshows: {e}")

        if dirty:
            try:
                with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                    
                self.log(f"Cache updated and saved to {self.CACHE_FILE}")
            except Exception as e:
                self.log(f"Error saving cache: {e}")
        self._clear_char_map() # Clear char map from memory after use
        return cache



# Global instance
_helper = None

class HelperProxy:
    def __getattr__(self, name):
        global _helper
        if _helper is None:
            _helper = T9Helper()
        return getattr(_helper, name)

helper = HelperProxy()