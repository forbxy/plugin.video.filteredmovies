# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmcvfs
import xbmc
import xbmcgui
import itertools

# Path to addon data
ADDON_ID = "plugin.video.filteredmovies"
ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/")
# USERDATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
CACHE_FILE = os.path.join(ADDON_PATH, "movie_t9_cache.json")
# xbmc.log(f"Cache file path: {CACHE_FILE}", xbmc.LOGINFO)
CHAR_MAP_FILE = os.path.join(ADDON_PATH, "char_map.json")

# if not os.path.exists(USERDATA_PATH):
#     os.makedirs(USERDATA_PATH)

CHAR_MAP = None
CACHE_VERSION = 4
CACHE_PROP_KEY = "MovieFilter_T9Cache"

def log(msg):
    xbmc.log(f"[moviefilter.cache] {msg}", xbmc.LOGINFO)

def load_char_map():
    global CHAR_MAP
    if CHAR_MAP is None:
        try:
            with open(CHAR_MAP_FILE, "r", encoding="utf-8") as f:
                CHAR_MAP = json.load(f)
        except Exception as e:
            log(f"Failed to load char_map: {e}")
            CHAR_MAP = {}

def get_t9_map():
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

def generate_t9_codes(title):
    # Limit title length to avoid combination explosion
    # Processing first 10 characters is usually enough for T9 search
    process_title = title[:10]
    
    load_char_map()
    t9_map = get_t9_map()
    
    full_options = []
    
    for char in process_title:
        char_full = set()
        
        pinyin_data = CHAR_MAP.get(char)
        if not pinyin_data:
            pinyin_data = CHAR_MAP.get(char.upper())
        
        if pinyin_data:
            readings = pinyin_data if isinstance(pinyin_data, list) else [pinyin_data]
            for p in readings:
                # Full Pinyin
                full_digits = ""
                for pc in p:
                    pc_upper = pc.upper()
                    if pc_upper in t9_map:
                        full_digits += t9_map[pc_upper]
                if full_digits:
                    char_full.add(full_digits)
        else:
            # Non-Chinese character
            c = char.upper()
            if c in t9_map:
                digit = t9_map[c]
                char_full.add(digit)
        
        # Only append if we have valid mappings for this character
        if char_full:
            full_options.append(list(char_full))
    
    results = set()
            
    # Generate Full Pinyin combinations
    if full_options:
        for combo in itertools.product(*full_options):
            results.add("".join(combo))
    
    return list(results)

def get_db_path():
    # Find MyVideos*.db
    db_path = xbmcvfs.translatePath("special://userdata/Database/")
    try:
        files = os.listdir(db_path)
    except:
        return None
        
    video_dbs = [f for f in files if f.startswith("MyVideos") and f.endswith(".db")]
    if not video_dbs:
        return None
    
    def get_ver(name):
        try:
            return int(name.replace("MyVideos", "").replace(".db", ""))
        except:
            return 0
    
    video_dbs.sort(key=get_ver, reverse=True)
    return os.path.join(db_path, video_dbs[0])

def get_cached_data():
    # Try memory first
    window = xbmcgui.Window(10000)
    prop = window.getProperty(CACHE_PROP_KEY)
    if prop:
        try:
            cache = json.loads(prop)
            if cache.get("version") == CACHE_VERSION:
                # log("Hit memory cache")
                return cache
        except:
            pass
    
    # Fallback to file/DB
    return update_and_load_cache()

def update_and_load_cache():
    db_file = get_db_path()
    if not db_file:
        log("No database found")
        return {"max_movie_id": 0, "max_tvshow_id": 0, "max_set_id": 0, "movies": {}, "tvshows": {}, "sets": {}, "version": CACHE_VERSION}

    log(f"Using DB file: {db_file}")

    # Load cache from file
    cache = {"max_movie_id": 0, "max_tvshow_id": 0, "max_set_id": 0, "movies": {}, "tvshows": {}, "sets": {}, "version": CACHE_VERSION}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                loaded_cache = json.load(f)
                # Check version
                if loaded_cache.get("version") == CACHE_VERSION:
                    cache = loaded_cache
                    # Ensure all keys exist
                    if "movies" not in cache: cache["movies"] = {}
                    if "tvshows" not in cache: cache["tvshows"] = {}
                    if "sets" not in cache: cache["sets"] = {}
                    if "max_movie_id" not in cache: cache["max_movie_id"] = cache.get("max_id", 0)
                    if "max_tvshow_id" not in cache: cache["max_tvshow_id"] = 0
                    if "max_set_id" not in cache: cache["max_set_id"] = 0
                    
                    log(f"Loaded cache with {len(cache['movies'])} movies, {len(cache['tvshows'])} tvshows, {len(cache['sets'])} sets")
                else:
                    log(f"Cache version mismatch (found {loaded_cache.get('version')}, expected {CACHE_VERSION}). Rebuilding.")
        except Exception as e:
            log(f"Failed to load existing cache: {e}")
            
    max_movie_id = cache.get("max_movie_id", 0)
    max_tvshow_id = cache.get("max_tvshow_id", 0)
    max_set_id = cache.get("max_set_id", 0)
    
    # Connect DB
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        load_char_map()
        
        # --- Movies ---
        sql = "SELECT idMovie, c00 FROM movie WHERE idMovie > ?"
        cursor.execute(sql, (max_movie_id,))
        rows = cursor.fetchall()
        if rows:
            log(f"Found {len(rows)} new movies")
            for row in rows:
                mid = row[0]
                title = row[1]
                if not title: continue
                t9_codes = generate_t9_codes(title)
                cache["movies"][str(mid)] = t9_codes
                if mid > max_movie_id: max_movie_id = mid
            cache["max_movie_id"] = max_movie_id

        # --- TV Shows ---
        try:
            sql = "SELECT idShow, c00 FROM tvshow WHERE idShow > ?"
            cursor.execute(sql, (max_tvshow_id,))
            rows = cursor.fetchall()
            if rows:
                log(f"Found {len(rows)} new tvshows")
                for row in rows:
                    mid = row[0]
                    title = row[1]
                    if not title: continue
                    t9_codes = generate_t9_codes(title)
                    cache["tvshows"][str(mid)] = t9_codes
                    if mid > max_tvshow_id: max_tvshow_id = mid
                cache["max_tvshow_id"] = max_tvshow_id
        except Exception as e:
            log(f"Error caching tvshows: {e}")

        # --- Sets ---
        try:
            # Try 'sets' table with 'strSet' column
            sql = "SELECT idSet, strSet FROM sets WHERE idSet > ?"
            cursor.execute(sql, (max_set_id,))
            rows = cursor.fetchall()
            if rows:
                log(f"Found {len(rows)} new sets")
                for row in rows:
                    mid = row[0]
                    title = row[1]
                    if not title: continue
                    t9_codes = generate_t9_codes(title)
                    cache["sets"][str(mid)] = t9_codes
                    if mid > max_set_id: max_set_id = mid
                cache["max_set_id"] = max_set_id
        except Exception as e:
            log(f"Error caching sets: {e}")
        
        # Save cache to file
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
            
        conn.close()
        log(f"Cache updated.")
        
        # Save cache to memory
        window = xbmcgui.Window(10000)
        window.setProperty(CACHE_PROP_KEY, json.dumps(cache, ensure_ascii=False))
        
        return cache
    except Exception as e:
        log(f"Error updating cache: {e}")
        return cache

def search_cache(input_seq):
    log(f"Searching cache for input: {input_seq}")
    
    cache = get_cached_data()
    if not cache:
        return []
        
    matches = []
    
    # Search Movies
    movies = cache.get("movies", {})
    for mid, codes in movies.items():
        for code in codes:
            if code.startswith(input_seq):
                matches.append({"id": int(mid), "type": "movie"})
                break
                
    # Search TV Shows
    tvshows = cache.get("tvshows", {})
    for mid, codes in tvshows.items():
        for code in codes:
            if code.startswith(input_seq):
                matches.append({"id": int(mid), "type": "tvshow"})
                break

    # Search Sets
    sets = cache.get("sets", {})
    for mid, codes in sets.items():
        for code in codes:
            if code.startswith(input_seq):
                matches.append({"id": int(mid), "type": "set"})
                break
    
    log(f"Found {len(matches)} matches")
    return matches
