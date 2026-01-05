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
        self.CACHE_PROP_KEY = f"{t}_T9Cache"
        self.char_map = None

    def log(self, msg):
        xbmc.log(f"[T9Helper] {msg}", xbmc.LOGINFO)
    
    def search(self, input_seq):
        """
        根据输入的数字序列搜索匹配的电影、剧集或系列。
        返回匹配的 ID 列表。
        """
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
        1. 尝试从内存读取
        2. 尝试从文件读取
        3. 与 Kodi 库同步（增量更新）
        4. 写回内存
        """
        # 1. 尝试从内存读取
        window = xbmcgui.Window(10000)
        prop = window.getProperty(self.CACHE_PROP_KEY)
        cache = None
        
        if prop:
            try:
                loaded = json.loads(prop)
                if loaded.get("version") == self.CACHE_VERSION:
                    cache = loaded
            except: pass
            
        # 2. 如果内存中没有，尝试从文件读取
        if cache is None:
            if os.path.exists(self.CACHE_FILE):
                try:
                    with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if loaded.get("version") == self.CACHE_VERSION:
                            cache = loaded
                except: pass
                
        # 3. 如果还是空的，初始化一个新的
        if cache is None:
            cache = {"movies": {}, "tvshows": {}, "sets": {}, "version": self.CACHE_VERSION}
            
        # 与库同步（核心逻辑）
        cache = self._sync_with_library(cache)
        
        # 写回内存属性
        window.setProperty(self.CACHE_PROP_KEY, json.dumps(cache, ensure_ascii=False))
    
    def clear_memory_cache(self):
        xbmcgui.Window(10000).clearProperty(self.CACHE_PROP_KEY)

    def _load_char_map(self):
        """
        加载汉字转拼音/T9码的映射表。
        """
        if self.char_map is None:
            try:
                with open(self.CHAR_MAP_FILE, "r", encoding="utf-8") as f:
                    self.char_map = json.load(f)
            except Exception as e:
                self.log(f"Failed to load char_map: {e}")
                self.char_map = {}

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

    def _get_library_signature(self, method, id_key, support_dateadded=True):
        """
        获取库的签名信息：总数和最新添加项的 ID。
        用于快速检测库是否发生变化。
        """
        props = []
        if support_dateadded:
            props.append("dateadded")
            
        params = {
            "properties": props,
            "limits": {"start": 0, "end": 1}
        }
        if support_dateadded:
            params["sort"] = {"method": "dateadded", "order": "descending"}
            
        json_query = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": "sig"
        }
        json_str = json.dumps(json_query)
        response = xbmc.executeJSONRPC(json_str)
        result = json.loads(response)
        
        if "error" in result:
            self.log(f"RPC Error in signature check ({method}): {result['error']}")
            return None, None
            
        total = result.get('result', {}).get('limits', {}).get('total', 0)
        
        ret_key = "movies"
        if "TVShows" in method: ret_key = "tvshows"
        elif "MovieSets" in method: ret_key = "sets"
        
        items = result.get('result', {}).get(ret_key, [])
        latest_id = 0
        if items:
            latest_id = items[0].get(id_key, 0)
            
        return total, latest_id

    def _get_cached_data(self):
        """
        获取缓存数据，优先从内存获取，其次从文件。
        """
        window = xbmcgui.Window(10000)
        prop = window.getProperty(self.CACHE_PROP_KEY)
        if prop:
            try:
                return json.loads(prop)
            except: pass
            
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
            
        return {"movies": {}, "tvshows": {}, "sets": {}}

    

    def _sync_with_library(self, cache):
        """
        将本地缓存与 Kodi 媒体库进行同步。
        使用总数和最新 ID 进行快速检查，仅在需要时进行全量更新。
        """
        dirty = False
        
        # 检查磁盘上是否存在缓存文件。如果不存在，我们最终必须保存它。
        # 但 'dirty' 标志控制我们是否写入磁盘。
        # 如果我们从内存加载但文件丢失，我们应该写入。
        if not os.path.exists(self.CACHE_FILE):
            # self.log("Cache file missing, forcing save/rebuild.")
            dirty = True
        
        if "movies" not in cache: cache["movies"] = {}
        if "tvshows" not in cache: cache["tvshows"] = {}
        if "sets" not in cache: cache["sets"] = {}
                
        # 仅在实际需要生成代码时加载字符映射表
        # self._load_char_map()
        
        # --- 电影 (Movies) ---
        try:
            remote_total, remote_latest = self._get_library_signature("VideoLibrary.GetMovies", "movieid", support_dateadded=True)
            
            if remote_total is None:
                self.log("Movies signature check failed. Forcing update.")
                remote_total = -1
                remote_latest = -1
                
            local_total = len(cache["movies"])
            local_latest = cache.get("signatures", {}).get("movies", {}).get("latest_id", 0)
            
            # 检查是否需要更新
            if remote_total != local_total or remote_latest != local_latest:
                self.log(f"Movies changed (Remote: {remote_total}/{remote_latest}, Local: {local_total}/{local_latest}). Updating...")
                self._load_char_map() # 仅在需要时加载映射表
                movies = self._get_all_movies_rpc()
                new_count = 0
                
                # 如果远程总数小于本地总数，说明有删除操作
                # 优化：仅删除不存在的项，而不是重建
                if remote_total < local_total:
                     remote_ids = set(str(m.get("movieid")) for m in movies)
                     local_ids = list(cache["movies"].keys())
                     del_count = 0
                     for mid in local_ids:
                         if mid not in remote_ids:
                             del cache["movies"][mid]
                             del_count += 1
                     if del_count > 0:
                         self.log(f"Deleted {del_count} movies from cache")
                
                for m in movies:
                    mid = str(m.get("movieid"))
                    if mid not in cache["movies"]:
                        title = m.get("title", "")
                        if title:
                            cache["movies"][mid] = self._generate_t9_codes(title)
                            new_count += 1
                
                if new_count > 0: self.log(f"Added {new_count} new movies")
                
                if remote_total != -1:
                    if "signatures" not in cache: cache["signatures"] = {}
                    if "movies" not in cache["signatures"]: cache["signatures"]["movies"] = {}
                    cache["signatures"]["movies"]["latest_id"] = remote_latest
                
                dirty = True
        except Exception as e:
            self.log(f"Error updating movies: {e}")

        # --- 剧集 (TV Shows) ---
        try:
            remote_total, remote_latest = self._get_library_signature("VideoLibrary.GetTVShows", "tvshowid", support_dateadded=True)
            
            if remote_total is None:
                self.log("TVShows signature check failed. Forcing update.")
                remote_total = -1
                remote_latest = -1
                
            local_total = len(cache["tvshows"])
            local_latest = cache.get("signatures", {}).get("tvshows", {}).get("latest_id", 0)
            
            if remote_total != local_total or remote_latest != local_latest:
                self.log(f"TVShows changed (Remote: {remote_total}/{remote_latest}, Local: {local_total}/{local_latest}). Updating...")
                self._load_char_map()
                tvshows = self._get_all_tvshows_rpc()
                
                if remote_total < local_total:
                     remote_ids = set(str(t.get("tvshowid")) for t in tvshows)
                     local_ids = list(cache["tvshows"].keys())
                     del_count = 0
                     for mid in local_ids:
                         if mid not in remote_ids:
                             del cache["tvshows"][mid]
                             del_count += 1
                     if del_count > 0:
                         self.log(f"Deleted {del_count} tvshows from cache")

                new_count = 0
                for t in tvshows:
                    mid = str(t.get("tvshowid"))
                    if mid not in cache["tvshows"]:
                        title = t.get("title", "")
                        if title:
                            cache["tvshows"][mid] = self._generate_t9_codes(title)
                            new_count += 1
                if new_count > 0: self.log(f"Added {new_count} new tvshows")
                
                if remote_total != -1:
                    if "signatures" not in cache: cache["signatures"] = {}
                    if "tvshows" not in cache["signatures"]: cache["signatures"]["tvshows"] = {}
                    cache["signatures"]["tvshows"]["latest_id"] = remote_latest
                dirty = True
        except Exception as e:
            self.log(f"Error updating tvshows: {e}")

        # --- 系列 (Sets) ---
        try:
            remote_total, _ = self._get_library_signature("VideoLibrary.GetMovieSets", "setid", support_dateadded=False)
            
            if remote_total is None:
                remote_total = -1
                
            local_total = len(cache["sets"])
            
            if remote_total != local_total:
                self.log(f"Sets count changed ({local_total} -> {remote_total}). Updating...")
                self._load_char_map()
                sets = self._get_all_sets_rpc()
                
                if remote_total < local_total:
                     remote_ids = set(str(s.get("setid")) for s in sets)
                     local_ids = list(cache["sets"].keys())
                     del_count = 0
                     for mid in local_ids:
                         if mid not in remote_ids:
                             del cache["sets"][mid]
                             del_count += 1
                     if del_count > 0:
                         self.log(f"Deleted {del_count} sets from cache")

                new_count = 0
                for s in sets:
                    mid = str(s.get("setid"))
                    if mid not in cache["sets"]:
                        title = s.get("title", "")
                        if title:
                            cache["sets"][mid] = self._generate_t9_codes(title)
                            new_count += 1
                if new_count > 0: self.log(f"Added {new_count} new sets")
                dirty = True
        except Exception as e:
            self.log(f"Error updating sets: {e}")
        
        if dirty:
            try:
                with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                    
                self.log(f"Cache updated and saved to {self.CACHE_FILE}")
            except Exception as e:
                self.log(f"Error saving cache: {e}")
            
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