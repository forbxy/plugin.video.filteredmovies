# -*- coding: utf-8 -*-
import sys
import urllib.parse
import json
import datetime
import time

import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
import os
# import cache_manager
# import progress_helper

try:
    HANDLE = int(sys.argv[1])
except (IndexError, ValueError):
    HANDLE = -1

ADDON_PATH = xbmcvfs.translatePath("special://home/addons/plugin.video.filteredmovies/")
ADDON_DATA_PATH = xbmcvfs.translatePath("special://profile/addon_data/plugin.video.filteredmovies/")
if not os.path.exists(ADDON_DATA_PATH):
    os.makedirs(ADDON_DATA_PATH)

SKIP_DATA_FILE = os.path.join(ADDON_DATA_PATH, 'skip_intro_data.json')

def log(msg): xbmc.log(f"[moviefilter] {msg}", xbmc.LOGINFO)

def load_skip_data():
    if not os.path.exists(SKIP_DATA_FILE):
        return {}
    try:
        with open(SKIP_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"Error loading skip data: {e}")
        return {}

def save_skip_data(data):
    try:
        with open(SKIP_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        log(f"Error saving skip data: {e}")

def get_current_tvshow_info():
    try:
        # 使用 JSON-RPC 获取可靠的 ID 和标题
        json_query = {
            "jsonrpc": "2.0",
            "method": "Player.GetItem",
            "params": {
                "properties": ["tvshowid", "showtitle", "season"],
                "playerid": 1
            },
            "id": 1
        }
        json_response = xbmc.executeJSONRPC(json.dumps(json_query))
        response = json.loads(json_response)
        
        if 'result' in response and 'item' in response['result']:
            item = response['result']['item']
            tvshow_id = item.get('tvshowid')
            show_title = item.get('showtitle')
            season = item.get('season', -1)
            
            # 检查是否为有效的电视剧
            if tvshow_id and tvshow_id != -1 and show_title:
                return str(tvshow_id), show_title, str(season)
    except Exception as e:
        log(f"Error getting TV show info: {e}")
    return None, None, None

def record_skip_point():
    tvshow_id, show_title, season = get_current_tvshow_info()
    if not tvshow_id:
        xbmc.executebuiltin("Notification(跳过设置, 不适用于非剧集, 2000)")
        return

    try:
        player = xbmc.Player()
        current_time = player.getTime()
        total_time = player.getTotalTime()
        
        if total_time <= 0:
            return

        percentage = (current_time / total_time) * 100
        data = load_skip_data()
        
        if tvshow_id not in data:
            data[tvshow_id] = {"title": show_title, "seasons": {}}
        elif "time" in data[tvshow_id]:
            # 迁移旧格式
            old_time = data[tvshow_id]["time"]
            data[tvshow_id] = {"title": show_title, "seasons": {"1": {"intro": old_time}}}
            del data[tvshow_id]["time"]
        
        if "seasons" not in data[tvshow_id]:
            data[tvshow_id]["seasons"] = {}
            
        data[tvshow_id]["title"] = show_title 
        
        # 获取现有的季数据
        season_data = data[tvshow_id]["seasons"].get(season, {})
        # 处理旧格式（如果只是一个数字）
        if isinstance(season_data, (int, float)):
            season_data = {"intro": season_data}
            
        msg = ""
        if percentage < 20:
            season_data["intro"] = current_time
            m, s = divmod(int(current_time), 60)
            msg = f"已记录片头: {m:02d}:{s:02d}"
        elif percentage > 80:
            # 记录片尾时长 (总时长 - 当前时间)
            outro_duration = total_time - current_time
            season_data["outro"] = outro_duration
            m, s = divmod(int(outro_duration), 60)
            msg = f"已记录片尾时长: {m:02d}:{s:02d}"
        else:
            xbmc.executebuiltin("Notification(记录失败, 请在开头或结尾20%处调用, 2000)")
            return

        data[tvshow_id]["seasons"][season] = season_data
        save_skip_data(data)
        
        # 通知 service 重新加载数据
        xbmcgui.Window(10000).setProperty("FilteredMovies.Reload", "true")
        
        xbmc.executebuiltin(f"Notification(跳过设置, {msg} (第 {season} 季), 2000)")
        log(f"Recorded skip point for {show_title} Season {season}: {season_data}")
        
    except Exception as e:
        log(f"Error recording skip point: {e}")
        xbmc.executebuiltin("Notification(跳过设置, 记录错误, 2000)")

def delete_skip_point():
    tvshow_id, show_title, season = get_current_tvshow_info()
    if not tvshow_id:
        xbmc.executebuiltin("Notification(跳过设置, 不适用于非剧集, 2000)")
        return

    try:
        player = xbmc.Player()
        current_time = player.getTime()
        total_time = player.getTotalTime()
        
        if total_time <= 0:
            return

        percentage = (current_time / total_time) * 100
        data = load_skip_data()
        
        if tvshow_id not in data or "seasons" not in data[tvshow_id] or season not in data[tvshow_id]["seasons"]:
            xbmc.executebuiltin("Notification(跳过设置, 当前无记录, 2000)")
            return

        season_data = data[tvshow_id]["seasons"][season]
        if isinstance(season_data, (int, float)):
             season_data = {"intro": season_data}

        msg = ""
        if percentage < 20:
            if "intro" in season_data:
                del season_data["intro"]
                msg = "已删除片头记录"
            else:
                msg = "当前无片头记录"
        elif percentage > 80:
            if "outro" in season_data:
                del season_data["outro"]
                msg = "已删除片尾记录"
            else:
                msg = "当前无片尾记录"
        else:
            xbmc.executebuiltin("Notification(删除失败, 请在开头或结尾20%处调用, 2000)")
            return

        # Clean up empty dicts
        if not season_data:
            del data[tvshow_id]["seasons"][season]
        else:
            data[tvshow_id]["seasons"][season] = season_data
            
        if not data[tvshow_id]["seasons"]:
            del data[tvshow_id]

        save_skip_data(data)
        
        # 通知 service 重新加载数据
        xbmcgui.Window(10000).setProperty("FilteredMovies.Reload", "true")
        
        xbmc.executebuiltin(f"Notification(跳过设置, {msg}, 2000)")
        
    except Exception as e:
        log(f"Error deleting skip point: {e}")
        xbmc.executebuiltin("Notification(跳过设置, 删除错误, 2000)")

def open_settings_and_click(window_id, clicks=2):
    """
    打开指定窗口，并向下移动指定次数后点击
    """
    xbmc.executebuiltin(f'ActivateWindow({window_id})')
    # 稍微延迟一下，确保窗口打开
    xbmc.sleep(100)
    
    # 移动焦点
    for _ in range(clicks):
        xbmc.executebuiltin('Action(Up)')
        xbmc.sleep(20)
    
    # 点击
    xbmc.executebuiltin('Action(Select)')

def get_skin_filter(key, default=""):
    # 从皮肤变量里读状态：filter.sort / filter.genre / filter.country / filter.letter
    value = xbmc.getInfoLabel(f"Skin.String({key})")
    return value if value else default

def build_filter(media_type="movie"):
    """
    组装 JSON-RPC 的 filter 结构：
    https://kodi.wiki/view/JSON-RPC_API/v12#Video.Fields.Movie
    """
    rules = []

    # 类型（genre）
    genre = get_skin_filter("filter.genre")
    if genre and media_type not in ["set", "musicvideo"]:
        if genre == "Other":
            # 排除列表中的所有已知类型
            exclude_genres = [
                "动作", "喜剧", "爱情", "科幻", "犯罪", 
                "冒险", "恐怖", "动画", "战争", "悬疑", 
                "历史", "音乐", "纪录片"
            ]
            for eg in exclude_genres:
                rules.append({
                    "field": "genre",
                    "operator": "doesnotcontain",
                    "value": eg
                })
        else:
            rules.append({
                "field": "genre",
                "operator": "contains", # 使用 contains 以支持多类型电影 (e.g. "Action / Adventure")
                "value": genre
            })

    # 地区（country）
    # 只有电影支持地区筛选，电视剧和电影集通常不支持或数据不全
    country = get_skin_filter("filter.country")
    if country and media_type in ["movie", "documentary", "musicvideo"]:
        if country == "Other":
            # 排除列表中的所有已知国家
            # 注意：这里要排除的是 Skin 中已有的选项对应的 Kodi 数据库值
            exclude_countries = [
                "China", "Hong Kong", "Taiwan", 
                "United States", "Japan", "South Korea", 
                "Thailand", "India", "United Kingdom", 
                "France", "Germany", "Russia", "Canada"
            ]
            for ec in exclude_countries:
                rules.append({
                    "field": "country",
                    "operator": "doesnotcontain",
                    "value": ec
                })
        else:
            # 映射常见国家名称差异 (Skin -> Kodi DB)
            if country == "USA":
                country = "United States"
            elif country == "UK":
                country = "United Kingdom"
            elif country == "Korea":
                country = "South Korea"

            rules.append({
                "field": "country",
                "operator": "contains",
                "value": country
            })

    # 首字母（title startswith）
    letter = get_skin_filter("filter.letter")
    if letter:
        rules.append({
            "field": "title",
            "operator": "startswith",
            "value": letter
        })

    # 年份（year）
    year_val = get_skin_filter("filter.year")
    if year_val and year_val != "Default":
        current_year = datetime.datetime.now().year
        if year_val == "ThisYear":
            rules.append({"field": "year", "operator": "is", "value": str(current_year)})
        elif year_val == "2020s":
            rules.append({"field": "year", "operator": "between", "value": ["2020", "2029"]})
        elif year_val == "2010s":
            rules.append({"field": "year", "operator": "between", "value": ["2010", "2019"]})
        elif year_val == "2000s":
            rules.append({"field": "year", "operator": "between", "value": ["2000", "2009"]})
        elif year_val == "1990s":
            rules.append({"field": "year", "operator": "between", "value": ["1990", "1999"]})
        elif year_val == "1980s":
            rules.append({"field": "year", "operator": "between", "value": ["1980", "1989"]})
        elif year_val == "1970s":
            rules.append({"field": "year", "operator": "between", "value": ["1970", "1979"]})
        elif year_val == "1960s":
            rules.append({"field": "year", "operator": "between", "value": ["1960", "1969"]})
        elif year_val == "Earlier":
            rules.append({"field": "year", "operator": "lessthan", "value": "1960"})

    # 评分 (rating) - Multi-select
    rating_rules = []
    if xbmc.getCondVisibility("Skin.HasSetting(filter.rating.10_9)"):
        rating_rules.append({"field": "rating", "operator": "between", "value": ["9.0", "10.0"]})
    if xbmc.getCondVisibility("Skin.HasSetting(filter.rating.9_8)"):
        rating_rules.append({"field": "rating", "operator": "between", "value": ["8.0", "8.99"]})
    if xbmc.getCondVisibility("Skin.HasSetting(filter.rating.8_7)"):
        rating_rules.append({"field": "rating", "operator": "between", "value": ["7.0", "7.99"]})
    if xbmc.getCondVisibility("Skin.HasSetting(filter.rating.7_6)"):
        rating_rules.append({"field": "rating", "operator": "between", "value": ["6.0", "6.99"]})
    if xbmc.getCondVisibility("Skin.HasSetting(filter.rating.below_6)"):
        rating_rules.append({"field": "rating", "operator": "lessthan", "value": "6.0"})
        
    if rating_rules:
        if len(rating_rules) == 1:
            rules.append(rating_rules[0])
        else:
            rules.append({"or": rating_rules})

    if not rules:
        return None

    return {
        "and": rules
    }

def build_sort():
    sort_key = get_skin_filter("filter.sort", "hot")

    # 随便约定一下：
    # hot   -> 按 播放次数+最近播放 排序
    # latest-> 按 year DESC (发行年份)
    # rating-> 按 rating DESC

    if sort_key == "latest":
        return {"order": "descending", "method": "year"}
    elif sort_key == "rating":
        return {"order": "descending", "method": "rating"}
    elif sort_key == "dateadded":
        return {"order": "descending", "method": "dateadded"}
    elif sort_key == "lastplayed":
        return {"order": "descending", "method": "lastplayed"}
    elif sort_key == "random":
        return {"method": "random"}
    else:
        # “最热” 简单用 播放次数
        return {"order": "descending", "method": "playcount"}

def get_method_and_params(media_type):
    base_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "lastplayed"]
    
    if media_type == "movie" or media_type == "documentary" or media_type == "musicvideo":
        return "VideoLibrary.GetMovies", base_props + ["tagline", "resume", "runtime"], "movies", "movieid"
    elif media_type == "tvshow":
        return "VideoLibrary.GetTVShows", base_props + ["studio", "mpaa", "episode", "watchedepisodes"], "tvshows", "tvshowid"
    elif media_type == "set":
        return "VideoLibrary.GetMovieSets", ["title", "thumbnail", "art", "plot", "playcount"], "sets", "setid"
    return "VideoLibrary.GetMovies", base_props + ["resume", "runtime"], "movies", "movieid"

def sort_items_locally(items, sort_obj):
    if not sort_obj:
        return items
    method = sort_obj.get("method")
    order = sort_obj.get("order", "descending")
    reverse = (order == "descending")
    
    def sort_key_func(m):
        val = m.get(method)
        # Secondary sort key: dateadded (to mix items with same year/rating)
        date_val = m.get("dateadded", "")
        
        if method == "year":
            try: y = int(val)
            except: y = 0
            return (y, date_val)
        if method == "rating":
            try: r = float(val)
            except: r = 0.0
            return (r, date_val)
        if method == "playcount":
            try: p = int(val)
            except: p = 0
            # Also prioritize resume for playcount (Hot)
            has_resume = 0
            resume = m.get("resume") or {}
            if isinstance(resume, dict) and resume.get("position", 0) > 0:
                has_resume = 1
            
            # Check for TV Show progress
            if m.get("media_type") == "tvshow":
                total = m.get("episode", 0)
                watched = m.get("watchedepisodes", 0)
                lp = m.get("lastplayed")
                if total > 0 and watched < total and (watched > 0 or lp):
                    has_resume = 1
            
            # Check for Movie Set progress
            if m.get("media_type") == "set":
                total = m.get("total", 0)
                watched = m.get("watched", 0)
                if total > 0 and watched < total and watched > 0:
                    has_resume = 1

            return (has_resume, p, date_val)
        if method == "lastplayed":
            # 优先显示有观看进度的 (Continue Watching 逻辑)
            has_resume = 0
            resume = m.get("resume") or {}
            if isinstance(resume, dict) and resume.get("position", 0) > 0:
                has_resume = 1
            
            # Check for TV Show progress
            if m.get("media_type") == "tvshow":
                total = m.get("episode", 0)
                watched = m.get("watchedepisodes", 0)
                lp = m.get("lastplayed")
                if total > 0 and watched < total and (watched > 0 or lp):
                    has_resume = 1

            # Check for Movie Set progress
            if m.get("media_type") == "set":
                total = m.get("total", 0)
                watched = m.get("watched", 0)
                if total > 0 and watched < total and watched > 0:
                    has_resume = 1

            return (has_resume, val or "")
        if method == "dateadded":
            return val or ""
        return val or ""
        
    try:
        items.sort(key=sort_key_func, reverse=reverse)
    except Exception as e:
        log(f"Sort failed: {e}")
    return items

def get_documentary_items(limit, allowed_ids):
    filter_obj_movie = build_filter("movie")
    filter_obj_tv = build_filter("tvshow")
    sort_obj = build_sort()
    
    # Add "genre contains 纪录片" OR "genre contains Documentary" rule
    doc_rule = {
        "or": [
            {"field": "genre", "operator": "contains", "value": "纪录"},
            {"field": "genre", "operator": "contains", "value": "记录"},
            {"field": "genre", "operator": "contains", "value": "Documentary"}
        ]
    }
    
    def add_rule(f_obj, rule):
        if f_obj:
            if "and" in f_obj:
                f_obj["and"].append(rule)
            else:
                f_obj = {"and": [f_obj, rule]}
        else:
            f_obj = {"and": [rule]}
        return f_obj

    filter_obj_movie = add_rule(filter_obj_movie, doc_rule)
    filter_obj_tv = add_rule(filter_obj_tv, doc_rule)

    # Fetch Movies
    movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline", "file", "resume", "runtime", "lastplayed"]
    params_movies = {
        "jsonrpc": "2.0", "id": "movies",
        "method": "VideoLibrary.GetMovies",
        "params": {
            "properties": movie_props,
            "limits": {"start": 0, "end": limit},
            "sort": sort_obj,
            "filter": filter_obj_movie
        }
    }
    
    # Fetch TV Shows
    tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode", "watchedepisodes", "file", "lastplayed"]
    params_tv = {
        "jsonrpc": "2.0", "id": "tvshows",
        "method": "VideoLibrary.GetTVShows",
        "params": {
            "properties": tv_props,
            "limits": {"start": 0, "end": limit},
            "sort": sort_obj,
            "filter": filter_obj_tv
        }
    }

    # Execute Batch
    batch_cmds = [params_movies, params_tv]
    items = []
    
    try:
        resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
        results = json.loads(resp)
        
        if isinstance(results, list):
            for res in results:
                if "result" in res:
                    res_val = res["result"]
                    if "movies" in res_val:
                        movies = res_val["movies"]
                        for m in movies: m["media_type"] = "movie"
                        items.extend(movies)
                    elif "tvshows" in res_val:
                        tvshows = res_val["tvshows"]
                        for t in tvshows: t["media_type"] = "tvshow"
                        items.extend(tvshows)
    except Exception as e:
        log(f"Error fetching doc items batch: {e}")

    # Sort combined
    items = sort_items_locally(items, sort_obj)
    
    # Apply limit after combine? 
    # If we fetched limit=500 for each, we have up to 1000.
    # We should slice to limit.
    return items[:limit]

def get_all_items(limit):
    filter_obj_movie = build_filter("movie")
    filter_obj_tv = build_filter("tvshow")
    sort_obj = build_sort()
    
    # Fetch Movies
    movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline", "file", "resume", "runtime", "lastplayed"]
    params_movies = {
        "jsonrpc": "2.0", "id": "movies",
        "method": "VideoLibrary.GetMovies",
        "params": {
            "properties": movie_props,
            "limits": {"start": 0, "end": limit},
            "sort": sort_obj
        }
    }
    if filter_obj_movie:
        params_movies["params"]["filter"] = filter_obj_movie
    
    # Fetch TV Shows
    tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode", "watchedepisodes", "file", "lastplayed"]
    params_tv = {
        "jsonrpc": "2.0", "id": "tvshows",
        "method": "VideoLibrary.GetTVShows",
        "params": {
            "properties": tv_props,
            "limits": {"start": 0, "end": limit},
            "sort": sort_obj
        }
    }
    if filter_obj_tv:
        params_tv["params"]["filter"] = filter_obj_tv

    # Execute Batch
    batch_cmds = [params_movies, params_tv]
    items = []
    
    try:
        resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
        results = json.loads(resp)
        
        if isinstance(results, list):
            for res in results:
                if "result" in res:
                    res_val = res["result"]
                    if "movies" in res_val:
                        movies = res_val["movies"]
                        log(f"Batch: Found {len(movies)} movies")
                        if movies: log(f"First Movie: {movies[0].get('title')} ({movies[0].get('dateadded')})")
                        for m in movies: m["media_type"] = "movie"
                        items.extend(movies)
                    elif "tvshows" in res_val:
                        tvshows = res_val["tvshows"]
                        log(f"Batch: Found {len(tvshows)} tvshows")
                        if tvshows: log(f"First TV: {tvshows[0].get('title')} ({tvshows[0].get('dateadded')})")
                        for t in tvshows: t["media_type"] = "tvshow"
                        items.extend(tvshows)
    except Exception as e:
        log(f"Error fetching all items batch: {e}")

    # Sort combined
    items = sort_items_locally(items, sort_obj)
    
    return items[:limit]

def jsonrpc_get_items(limit=500, allowed_ids=None):
    import progress_helper
    media_type = get_skin_filter("filter.mediatype", "all")
    
    if media_type == "all":
        if allowed_ids is None:
            return get_all_items(limit)
        # If allowed_ids is set (T9 search), we proceed to the T9 block below
    
    if media_type == "documentary" and allowed_ids is None:
        return get_documentary_items(limit, allowed_ids)
    
    method_name, properties, result_key, id_key = get_method_and_params(media_type)
    
    filter_obj = build_filter(media_type)
    sort_obj = build_sort()
    
    # Special handling for documentary (fallback if allowed_ids is set or if we want to reuse this logic)
    if media_type == "documentary":
        doc_rule = {
            "or": [
                {"field": "genre", "operator": "contains", "value": "纪录"},
                {"field": "genre", "operator": "contains", "value": "记录"},
                {"field": "genre", "operator": "contains", "value": "Documentary"}
            ]
        }
        if filter_obj:
            if "and" in filter_obj:
                filter_obj["and"].append(doc_rule)
            else:
                filter_obj = {"and": [filter_obj, doc_rule]}
        else:
            filter_obj = {"and": [doc_rule]}

    # Special handling for musicvideo (Concerts stored as movies)
    if media_type == "musicvideo":
        music_rule = {
            "or": [
                {"field": "genre", "operator": "is", "value": "音乐"},
                {"field": "genre", "operator": "is", "value": "Music"}
            ]
        }
        if filter_obj:
            if "and" in filter_obj:
                filter_obj["and"].append(music_rule)
            else:
                filter_obj = {"and": [filter_obj, music_rule]}
        else:
            filter_obj = {"and": [music_rule]}

    log(
        f"mediatype={media_type} "
        f"sort={get_skin_filter('filter.sort')} "
        f"genre={get_skin_filter('filter.genre')} "
        f"country={get_skin_filter('filter.country')} "
        f"year={get_skin_filter('filter.year')} "
        f"letter={get_skin_filter('filter.letter')}",
    )
    log(f"filter_obj={json.dumps(filter_obj, ensure_ascii=False)}")
    
    if allowed_ids is not None:
        if not allowed_ids:
            return []
        
        log(f"Applying T9 ID filter {allowed_ids}")
        
        batch_cmds = []
        items_to_fetch = allowed_ids[:limit]
        
        # Define properties for each type
        movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline", "resume", "runtime", "lastplayed"]
        tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode", "watchedepisodes", "lastplayed"]
        set_props = ["title", "thumbnail", "art", "plot", "playcount"]
        
        for i, item_data in enumerate(items_to_fetch):
            # item_data is expected to be {"id": 123, "type": "movie"}
            # Handle legacy list of ints if necessary (though cache_manager is updated)
            if isinstance(item_data, int):
                itype = "movie"
                iid = item_data
            else:
                itype = item_data.get("type", "movie")
                iid = item_data.get("id")
            
            method = ""
            id_param = ""
            props = []
            
            if itype == "movie":
                method = "VideoLibrary.GetMovieDetails"
                id_param = "movieid"
                props = movie_props
            elif itype == "tvshow":
                method = "VideoLibrary.GetTVShowDetails"
                id_param = "tvshowid"
                props = tv_props
            elif itype == "set":
                method = "VideoLibrary.GetMovieSetDetails"
                id_param = "setid"
                props = set_props
            
            if method:
                cmd = {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": {
                        id_param: int(iid),
                        "properties": props
                    },
                    "id": str(i)
                }
                batch_cmds.append(cmd)
            
        resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
        try:
            results = json.loads(resp)
        except:
            log("Failed to parse batch response")
            return []
        
        items = []
        
        # Fetch partial progress for TV shows
        partial_progress_map = {}
        if any(cmd.get("method") == "VideoLibrary.GetTVShowDetails" for cmd in batch_cmds):
             partial_progress_map = progress_helper.get_inprogress_episodes_map()

        if isinstance(results, list):
            for res in results:
                if "result" in res:
                    res_val = res["result"]
                    if "moviedetails" in res_val:
                        item = res_val["moviedetails"]
                        item["media_type"] = "movie"
                        items.append(item)
                    elif "tvshowdetails" in res_val:
                        item = res_val["tvshowdetails"]
                        item["media_type"] = "tvshow"
                        # Attach partial progress
                        tid = item.get("tvshowid")
                        if tid:
                            item["partial_progress"] = partial_progress_map.get(tid, 0.0)
                        items.append(item)
                    elif "setdetails" in res_val:
                        item = res_val["setdetails"]
                        item["media_type"] = "set"
                        items.append(item)
        
        # Strict filtering for musicvideo (Concert) in T9 search too
        if media_type == "musicvideo":
            filtered_items = []
            for item in items:
                genres = item.get("genre", [])
                if len(genres) == 1 and (genres[0] == "Music" or genres[0] == "音乐"):
                    filtered_items.append(item)
            items = filtered_items

        log(f"Batch returned {len(items)} items")
        
        items = sort_items_locally(items, sort_obj)
                
        return items

    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method_name,
        "params": {
            "properties": properties,
            "limits": {"start": 0, "end": limit},
            "sort": sort_obj
        }
    }

    if filter_obj:
        params["params"]["filter"] = filter_obj

    resp = xbmc.executeJSONRPC(json.dumps(params))
    data = json.loads(resp)
    items = data.get("result", {}).get(result_key, [])
    
    # If fetching TV shows, enrich with partial progress
    if media_type == "tvshow":
        partial_progress_map = progress_helper.get_inprogress_episodes_map()
        for item in items:
            tid = item.get("tvshowid")
            if tid:
                item["partial_progress"] = partial_progress_map.get(tid, 0.0)
    
    # Strict filtering for musicvideo (Concert) - must ONLY have "Music" or "音乐" genre
    if media_type == "musicvideo":
        filtered_items = []
        for item in items:
            genres = item.get("genre", [])
            # Check if "Music" or "音乐" is the ONLY genre
            if len(genres) == 1 and (genres[0] == "Music" or genres[0] == "音乐"):
                filtered_items.append(item)
        items = filtered_items

    for item in items:
        item["media_type"] = media_type
        
    # Apply local sort to enforce custom logic (e.g. resume priority)
    items = sort_items_locally(items, sort_obj)

    log(f"returned {len(items)} items")
    return items

def enrich_sets_with_art(items):
    sets_needing_art = []
    for i, item in enumerate(items):
        if item.get("media_type") == "set":
            art = item.get("art", {})
            # Check if we need fallback (missing poster)
            has_poster = "poster" in art
            has_thumb = bool(item.get("thumbnail"))
            
            if not has_poster and not has_thumb:
                sets_needing_art.append((i, item["title"]))
    
    if not sets_needing_art:
        return items
        
    batch_cmds = []
    for idx, (i, set_title) in enumerate(sets_needing_art):
        flt = {"field": "set", "operator": "is", "value": set_title}
        cmd = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "filter": flt,
                "properties": ["art", "thumbnail"],
                "limits": {"end": 1}
            },
            "id": str(idx)
        }
        batch_cmds.append(cmd)
        
    if batch_cmds:
        try:
            resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
            results = json.loads(resp)
            if isinstance(results, list):
                for res in results:
                    try:
                        req_id = int(res.get("id", -1))
                    except:
                        continue
                        
                    if req_id >= 0 and req_id < len(sets_needing_art):
                        item_index = sets_needing_art[req_id][0]
                        
                        if "result" in res and "movies" in res["result"] and res["result"]["movies"]:
                            movie = res["result"]["movies"][0]
                            # Update the original item
                            orig_item = items[item_index]
                            if "art" not in orig_item: orig_item["art"] = {}
                            
                            fb_art = movie.get("art", {})
                            fb_thumb = movie.get("thumbnail")
                            
                            # Merge art
                            for k, v in fb_art.items():
                                if k not in orig_item["art"]:
                                    orig_item["art"][k] = v
                            
                            # If still no thumbnail, use movie thumbnail
                            if not orig_item.get("thumbnail") and fb_thumb:
                                orig_item["thumbnail"] = fb_thumb
        except Exception as e:
            log(f"Error batch fetching set art: {e}")
            
    return items

def list_videos():
    import cache_manager
    # 记录列表加载时间，用于防止自动播放
    xbmcgui.Window(10000).setProperty("MovieFilter_LastListTime", str(time.time()))

    t9_input = xbmc.getInfoLabel("Window.Property(t9_input)")
    
    allowed_ids = None
    if t9_input and len(t9_input) >= 3:
        allowed_ids = cache_manager.search_cache(t9_input)
        log(f"T9 Search '{t9_input}' found {len(allowed_ids)} matches in cache")
    if not allowed_ids:
        items = jsonrpc_get_items(limit=300, allowed_ids=allowed_ids)
    else:
        items = jsonrpc_get_items(limit=60, allowed_ids=allowed_ids)
    
    # Optimize: Batch fetch art for sets
    items = enrich_sets_with_art(items)
    
    filtered_items = items
        
    for m in filtered_items:
        # log(2)
        li = xbmcgui.ListItem(label=m["title"])
        # 设置海报/缩略图
        art = m.get("art", {})
        art_dict = {}
        media_type = m.get("media_type", "movie")
        
        if "poster" in art:
            art_dict["poster"] = art["poster"]
            art_dict["thumb"] = art["poster"]
        elif m.get("thumbnail"):
            art_dict["poster"] = m["thumbnail"]
            art_dict["thumb"] = m["thumbnail"]
        
        if "fanart" in art:
            art_dict["fanart"] = art["fanart"]
            
        li.setArt(art_dict)
        
        # ID handling
        if media_type == "movie" or media_type == "documentary":
            item_id = m.get("movieid")
            mode = "play"
        elif media_type == "tvshow":
            item_id = m.get("tvshowid")
            mode = "open_tvshow"
        elif media_type == "set":
            item_id = m.get("setid")
            mode = "open_set"
        elif media_type == "musicvideo":
            item_id = m.get("movieid")
            mode = "play"
        else:
            item_id = m.get("movieid")
            mode = "play"

        if not item_id:
            continue

        # Set IsPlayable to false to avoid double resume dialogs (plugin handles playback via PlayMedia)
        li.setProperty("IsPlayable", "false")
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(m["title"])
        info_tag.setYear(m.get("year", 0))
        info_tag.setGenres(m.get("genre", []))
        info_tag.setPlot(m.get("plot", ""))
        info_tag.setRating(m.get("rating", 0.0))
        
        # Set resume point if available
        resume = m.get("resume", {})
        
        if media_type == "tvshow":
            total_episodes = m.get("episode", 0)
            watched_episodes = m.get("watchedepisodes", 0)
            last_played = m.get("lastplayed", "")
            
            # Since GetTVShows doesn't return resume, we use lastplayed as a proxy
            # If watchedepisodes is 0 but lastplayed is set, it implies user has started watching.
            has_partial = 0
            if watched_episodes == 0 and last_played:
                has_partial = 1
            
            if total_episodes > 0:
                # Calculate percentage
                # Use watched count + partial progress from in-progress episodes
                partial = m.get("partial_progress", 0.0)
                val = float(watched_episodes) + partial
                
                pct = int((val / total_episodes) * 100)
                if pct > 100: pct = 100
                # Ensure at least 1% if we think it's started (has partial or lastplayed)
                if (partial > 0 or (watched_episodes == 0 and last_played)) and pct == 0: 
                    pct = 1
                
                li.setProperty("SkinPercentPlayed", str(pct))
        
        elif media_type == "set":
            total_movies = m.get("total", 0)
            watched_movies = m.get("watched", 0)
            
            if total_movies > 0:
                # For sets, we don't have lastplayed easily, so we just use watched count
                val = float(watched_movies)
                pct = int((val / total_movies) * 100)
                if pct > 100: pct = 100
                li.setProperty("SkinPercentPlayed", str(pct))

        elif resume and "position" in resume and resume["position"] > 0:
            total = resume.get("total", 0)
            if total == 0:
                total = m.get("runtime", 0)
            
            if total > 0:
                # info_tag.setResumePoint(resume["position"], total)
                # Also set property for skin visibility checks if needed
                pct = int((resume["position"] / total) * 100)
                li.setProperty("SkinPercentPlayed", str(pct))
            else:
                # info_tag.setResumePoint(resume["position"])
                pass
        
        # Set MediaType for skin to show correct icons/info
        info_tag.setMediaType(media_type if media_type not in ["documentary", "musicvideo"] else "movie")

        t = str(int(time.time()*1000000))
        url = f"plugin://plugin.video.filteredmovies/?mode={mode}&id={item_id}&t={t}"
        # isFolder=False ensures that clicking triggers the plugin action (Container.Update) instead of trying to enter a directory
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=False)

    # Set content type based on current filter
    current_media_type = get_skin_filter("filter.mediatype", "all")
    if current_media_type == "tvshow":
        xbmcplugin.setContent(HANDLE, "tvshows")
    else:
        xbmcplugin.setContent(HANDLE, "movies")

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def play_movie(movieid):
    # 检查点击时间（由 Home.xml 设置）
    click_time_str = xbmcgui.Window(10000).getProperty("MovieClickTime")
    if click_time_str:
        try:
            click_time = float(click_time_str)
            # 如果距离点击时间小于 3.0 秒，认为是自动播放误触，忽略
            if time.time() - click_time < 3.0:
                log(f"Play request ignored: too close to click time. Delta: {time.time() - click_time:.2f}s")
                return
        except ValueError:
            pass

    # 直接用 videodb 路径播放
    path = f"videodb://movies/titles/{movieid}"
    xbmc.executebuiltin(f"PlayMedia({path})")

def play_musicvideo(mvid):
    path = f"videodb://musicvideos/titles/{mvid}"
    xbmc.executebuiltin(f"PlayMedia({path})")

def open_playing_tvshow():
    # Close any open dialogs (OSD, SeekBar, Info, etc.)
    xbmc.executebuiltin("Dialog.Close(all,true)")
    xbmc.sleep(200)
    
    try:
        json_query = {
            "jsonrpc": "2.0",
            "method": "Player.GetItem",
            "params": {
                "properties": ["tvshowid"],
                "playerid": 1
            },
            "id": 1
        }
        json_response = xbmc.executeJSONRPC(json.dumps(json_query))
        response = json.loads(json_response)
        
        if 'result' in response and 'item' in response['result']:
            item = response['result']['item']
            tvshow_id = item.get('tvshowid')
            
            if tvshow_id and tvshow_id != -1:
                log(f"Opening TVShow ID: {tvshow_id}")
                path = f"videodb://tvshows/titles/{tvshow_id}/"
                xbmc.executebuiltin(f"ActivateWindow(Videos,{path},return)")
            else:
                log("Current playing item has no TV show ID")
    except Exception as e:
        log(f"Error opening playing tvshow: {e}")

def set_subtitle(index_str):
    log(f"set_subtitle called with index: {index_str}")
    try:
        if index_str is None:
            log("Error: index is None")
            return
            
        index = int(index_str)
        log(f"Setting subtitle to index: {index}")
        player = xbmc.Player()
        if not player.isPlaying(): 
            log("Player not playing, aborting")
            return
        
        # Get current state to decide toggle
        current_index = -1
        is_enabled = False
        
        try:
            r = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0", "method": "Player.GetProperties", 
                "params": {"playerid": 1, "properties": ["subtitleenabled", "currentsubtitle"]}, "id": 1
            })))
            if 'result' in r:
                is_enabled = r['result'].get('subtitleenabled', False)
                current_stream = r['result'].get('currentsubtitle', {})
                current_index = current_stream.get('index', -1)
        except: pass
        
        if is_enabled and index == current_index:
             player.showSubtitles(False)
             xbmcgui.Dialog().notification("字幕", "字幕已关闭")
        else:
             player.setSubtitleStream(index)
             player.showSubtitles(True)
        xbmcgui.Dialog().notification("字幕", "字幕已切换")

        # Refresh the list to update selection state
        populate_subtitle_list()
             
    except Exception as e:
        log(f"Error setting subtitle: {e}")

def get_subtitle_items(suppress_warning=False):
    log("get_subtitle_items function started")
    player = xbmc.Player()
    if not player.isPlaying():
        log("Player is not playing")
        return None, None, None, None

    try:
        log("Fetching subtitle info via JSON-RPC")
        
        streams = []
        current_stream = {}
        is_enabled = False
        
        # Combined request for all properties
        try:
            req_str = json.dumps({
                "jsonrpc": "2.0", "method": "Player.GetProperties", 
                "params": {"playerid": 1, "properties": ["subtitles", "subtitleenabled", "currentsubtitle"]}, "id": 1
            })
            resp_str = xbmc.executeJSONRPC(req_str)
            r = json.loads(resp_str)
            
            if 'result' in r: 
                result = r['result']
                streams = result.get('subtitles', [])
                current_stream = result.get('currentsubtitle', {})
                is_enabled = result.get('subtitleenabled', False)
            else:
                log(f"JSON-RPC subtitles failed. Response: {resp_str}")
                raise Exception("subtitles property failed")
        except:
            log("JSON-RPC subtitles exception, using fallback for streams")
            # Fallback for streams list
            avail_streams = player.getAvailableSubtitleStreams()
            for i, name in enumerate(avail_streams):
                streams.append({
                    "index": i,
                    "name": name,
                    "language": "unk"
                })
        
        if not streams:
            if not suppress_warning:
                xbmcgui.Dialog().notification("字幕", "没有可用的字幕流")
            return None, None, None, None

        # Prepare items
        display_items = []
        
        current_index = current_stream.get('index') if is_enabled else -1
        
        # First pass: Collect all items with metadata
        raw_items = []
        for s in streams:
            idx = s.get('index')
            lang_code = s.get('language', 'unk')
            name = s.get('name', '')
            
            # Language translation
            lang_map = {
                'eng': '英语', 'en': '英语',
                'chi': '中文', 'zho': '中文', 'zh': '中文', 'chn': '中文',
                'jpn': '日语', 'ja': '日语',
                'kor': '韩语', 'ko': '韩语',
                'rus': '俄语', 'ru': '俄语',
                'fre': '法语', 'fra': '法语', 'fr': '法语',
                'ger': '德语', 'deu': '德语', 'de': '德语',
                'spa': '西班牙语', 'es': '西班牙语',
                'ita': '意大利语', 'it': '意大利语',
                'por': '葡萄牙语', 'pt': '葡萄牙语',
                'tha': '泰语', 'th': '泰语',
                'vie': '越南语', 'vi': '越南语',
                'ind': '印尼语', 'id': '印尼语',
                'dan': '丹麦语', 'da': '丹麦语',
                'fin': '芬兰语', 'fi': '芬兰语',
                'dut': '荷兰语', 'nld': '荷兰语', 'nl': '荷兰语',
                'nor': '挪威语', 'no': '挪威语',
                'swe': '瑞典语', 'sv': '瑞典语',
                'unk': '未知', '': '未知'
            }
            
            lang_name = lang_map.get(lang_code.lower())
            if not lang_name:
                try:
                    lang_name = xbmc.convertLanguage(lang_code, xbmc.ENGLISH_NAME)
                except:
                    lang_name = lang_code
            
            if not lang_name: lang_name = "未知"
            
            # Build label
            label = f"{idx + 1}. {lang_name}"
            
            if name and name.lower() != lang_name.lower() and name.lower() != lang_code.lower():
                label += f" - {name}"
            
            # Add flags
            flags = []
            if s.get('isforced'): flags.append("强制")
            if s.get('isimpaired'): flags.append("解说")
            if s.get('isdefault'): flags.append("默认")
            
            if name and ('commentary' in name.lower() or '解说' in name or 'description' in name.lower()):
                flags.append("解说字幕")
            
            if flags:
                label += f" ({', '.join(flags)})"
            
            # Determine sort properties
            is_chinese = lang_code.lower() in ['chi', 'zho', 'zh', 'chn']
            # Check for external subtitles based on name
            is_external = '（外挂）' in name
            
            raw_items.append({
                "label": label,
                "index": idx,
                "is_active": (is_enabled and idx == current_index),
                "is_chinese": is_chinese,
                "is_external": is_external,
                "original_order": idx
            })

        # Sort items: External first, then Chinese, then others. Stable sort preserves original order within groups.
        # Key: (not is_external, not is_chinese, original_order)
        # False < True, so 'not True' (False) comes first.
        raw_items.sort(key=lambda x: (not x['is_external'], not x['is_chinese'], x['original_order']))
        
        # Convert to display items
        display_items = [{"label": item["label"], "index": item["index"], "is_active": item["is_active"]} for item in raw_items]
        
        return display_items, current_index, is_enabled, player

    except Exception as e:
        log(f"Error in get_subtitle_items: {e}")
        xbmcgui.Dialog().notification("错误", f"获取字幕出错: {e}")
        return None, None, None, None

def populate_subtitle_list():
    log("populate_subtitle_list function started")
    display_items, current_index, is_enabled, player = get_subtitle_items(suppress_warning=True)
    
    # Try to find the control in VideoOSD (12901)
    potential_windows = [12901, 2901]
    current_dialog = xbmcgui.getCurrentWindowDialogId()
    if current_dialog:
        potential_windows.insert(0, current_dialog)
        
    log(f"Debug Window IDs - Window: {xbmcgui.getCurrentWindowId()}, Dialog: {xbmcgui.getCurrentWindowDialogId()}")
    for win_id in potential_windows:
        try:
            win = xbmcgui.Window(win_id)
            try:
                ctrl = win.getControl(80000)
                log(f"Found OSD control 80000 in window {win_id}")
                log("Populating OSD list 80000")
                ctrl.reset()
                
                if not display_items:
                    return

                active_pos = -1
                for i, item in enumerate(display_items):
                    li = xbmcgui.ListItem(label=item['label'])
                    li.setProperty("index", str(item['index'])) # Real index
                    if item['is_active']:
                        li.setProperty("IsActive", "true")
                        li.select(True)
                        active_pos = i
                    ctrl.addItem(li)
                
                if active_pos != -1:
                    ctrl.selectItem(active_pos)

                xbmcgui.Window(10000).setProperty("OSDSubtitleListOpen", "false")
                return
            except:
                pass
        except:
            pass
    log("OSD control 80000 not found in windows 12901")

def select_subtitle():
    log("select_subtitle function started")
    display_items, current_index, is_enabled, player = get_subtitle_items()
    
    if not display_items:
        return

    # Use custom window
    log("Opening custom window")
    import window_handler
    w = window_handler.DialogSelectWindow('Custom_1112_SubtitleSelect.xml', ADDON_PATH, 'Default', '1112')
    w.setItems(display_items)
    w.doModal()
    log("Window closed")
    
    ret_index = w.selected_index
    del w
    
    if ret_index == -1:
        log("Selection cancelled")
        return # Cancelled
        
    # Find the selected item in our list
    # The window returns the index in the list, so we map it back
    if ret_index < len(display_items):
        selected_item = display_items[ret_index]
        real_index = selected_item["index"]
        log(f"Selected index: {real_index}")
        
        # Toggle off if clicking the currently active subtitle
        if is_enabled and real_index == current_index:
            player.showSubtitles(False)
            xbmcgui.Dialog().notification("字幕", "字幕已关闭")
        else:
            player.setSubtitleStream(real_index)
            player.showSubtitles(True)
            xbmcgui.Dialog().notification("字幕", f"已切换至: {selected_item['label']}")





def open_osd_subtitle_list():
    display_items, current_index, is_enabled, player = get_subtitle_items()
    if not display_items:
        return

    import window_handler
    # Use the new XML
    w = window_handler.OSDListWindow('Custom_1113_OSDSubtitleList.xml', ADDON_PATH, 'Default', '1113')
    w.setItems(display_items)
    
    def on_select(item):
        real_index = item["index"]
        # Call set_subtitle logic directly here to avoid circular dependency or re-opening
        try:
            player = xbmc.Player()
            if is_enabled and real_index == current_index:
                 player.showSubtitles(False)
                 xbmcgui.Dialog().notification("字幕", "字幕已关闭")
            else:
                 player.setSubtitleStream(real_index)
                 player.showSubtitles(True)
                 xbmcgui.Dialog().notification("字幕", f"已切换至: {item['label']}")
            
            # Close VideoOSD to hide the list and return to video
            # xbmc.executebuiltin('Dialog.Close(VideoOSD)')
            xbmcgui.Window(10000).setProperty("OSDSubtitleListOpen", "true")
        except:
            pass

    w.setCallback(on_select)
    
    # Set property to hide OSD list
    xbmcgui.Window(10000).setProperty("OSDSubtitleListOpen", "true")
    # Also try to clear the OSD list visually
    # try:
    #     xbmcgui.Window(12901).getControl(80000).reset()
    # except:
    #     pass

    w.doModal()
    
    # Clear property when closed
    # xbmcgui.Window(10000).clearProperty("OSDSubtitleListOpen")
    del w

def get_audio_items(suppress_warning=False):
    try:
        json_query = {
            "jsonrpc": "2.0",
            "method": "Player.GetProperties",
            "params": {
                "playerid": 1,
                "properties": ["audiostreams", "currentaudiostream"]
            },
            "id": 1
        }
        json_response = xbmc.executeJSONRPC(json.dumps(json_query))
        response = json.loads(json_response)
        
        if 'result' not in response:
            return None, -1

        streams = response['result'].get('audiostreams', [])
        current_stream = response['result'].get('currentaudiostream', {})
        
        if not streams:
            if not suppress_warning:
                xbmcgui.Dialog().notification("音轨", "没有可用的音轨")
            return None, -1

        # Prepare items
        display_items = []
        current_index = current_stream.get('index', -1)
        
        for s in streams:
            idx = s.get('index')
            lang_code = s.get('language', 'unk')
            name = s.get('name', '')
            channels = s.get('channels', 0)
            codec = s.get('codec', '')
            
            # Language translation (reuse map or simplify)
            lang_map = {
                'eng': '英语', 'en': '英语',
                'chi': '中文', 'zho': '中文', 'zh': '中文', 'chn': '中文',
                'jpn': '日语', 'ja': '日语',
                'kor': '韩语', 'ko': '韩语',
                'rus': '俄语', 'ru': '俄语',
                'fre': '法语', 'fra': '法语', 'fr': '法语',
                'ger': '德语', 'deu': '德语', 'de': '德语',
                'spa': '西班牙语', 'es': '西班牙语',
                'ita': '意大利语', 'it': '意大利语',
                'por': '葡萄牙语', 'pt': '葡萄牙语',
                'tha': '泰语', 'th': '泰语',
                'vie': '越南语', 'vi': '越南语',
                'ind': '印尼语', 'id': '印尼语',
                'dan': '丹麦语', 'da': '丹麦语',
                'fin': '芬兰语', 'fi': '芬兰语',
                'dut': '荷兰语', 'nld': '荷兰语', 'nl': '荷兰语',
                'nor': '挪威语', 'no': '挪威语',
                'swe': '瑞典语', 'sv': '瑞典语',
                'unk': '未知', '': '未知'
            }
            
            lang_name = lang_map.get(lang_code.lower())
            if not lang_name:
                try:
                    lang_name = xbmc.convertLanguage(lang_code, xbmc.ENGLISH_NAME)
                except:
                    lang_name = lang_code
            if not lang_name: lang_name = "未知"

            # Format label: "1. 英语 - DTS-HD MA 5.1"
            
            # Simplify codec name for display if needed
            display_codec = codec.upper()
            if 'AC3' in name.upper(): display_codec = 'AC3'
            elif 'DTS' in name.upper(): display_codec = 'DTS'
            elif 'AAC' in name.upper(): display_codec = 'AAC'
            
            # Channel layout
            ch_str = f"{channels}ch"
            if channels == 6: ch_str = "5.1"
            elif channels == 2: ch_str = "2.0"
            elif channels == 8: ch_str = "7.1"
            
            label = f"{idx + 1}. {lang_name}"
            details = []
            if name:
                details.append(name)
            else:
                details.append(f"{display_codec} {ch_str}")
                
            if s.get('isdefault'): details.append("默认")
            if s.get('isimpaired'): details.append("解说")
            
            if details:
                label += f" - {' '.join(details)}"

            # Determine sort priority
            # 0: Chinese, 1: English, 2: Others
            sort_priority = 2
            if lang_code.lower() in ['chi', 'zho', 'zh', 'chn']:
                sort_priority = 0
            elif lang_code.lower() in ['eng', 'en']:
                sort_priority = 1

            display_items.append({
                "label": label,
                "index": idx,
                "is_active": (idx == current_index),
                "sort_priority": sort_priority,
                "original_order": idx
            })
            
        # Sort items: Chinese first, then English, then others. Stable sort preserves original order within groups.
        display_items.sort(key=lambda x: (x['sort_priority'], x['original_order']))
        
        return display_items, current_index
    except Exception as e:
        log(f"Error in get_audio_items: {e}")
        if not suppress_warning:
            xbmcgui.Dialog().notification("错误", f"获取音轨出错: {e}")
        return None, -1

def select_audio():
    display_items, current_index = get_audio_items()
    
    if not display_items:
        return

    # Use custom window
    import window_handler
    w = window_handler.DialogSelectWindow('Custom_1114_AudioSelect.xml', ADDON_PATH, 'Default', '1114')
    w.setTitle("音轨")
    w.setItems(display_items)
    w.doModal()
    
    ret_index = w.selected_index
    del w
    
    if ret_index == -1:
        return
        
    if ret_index < len(display_items):
        selected_item = display_items[ret_index]
        real_index = selected_item["index"]
        
        if real_index == current_index:
            xbmcgui.Dialog().notification("音轨", "已是当前音轨")
        else:
            xbmc.Player().setAudioStream(real_index)
            xbmcgui.Dialog().notification("音轨", f"已切换至: {selected_item['label']}")

def populate_audio_list():
    log("populate_audio_list function started")
    display_items, current_index = get_audio_items(suppress_warning=True)
    
    # Try to find the control in VideoOSD (12901)
    potential_windows = [12901, 2901]
    current_dialog = xbmcgui.getCurrentWindowDialogId()
    if current_dialog:
        potential_windows.insert(0, current_dialog)
        
    for win_id in potential_windows:
        try:
            win = xbmcgui.Window(win_id)
            try:
                # Use control 80001 for audio list
                ctrl = win.getControl(80001)
                log(f"Found OSD control 80001 in window {win_id}")
                ctrl.reset()
                
                if not display_items:
                    return

                active_pos = -1
                for i, item in enumerate(display_items):
                    li = xbmcgui.ListItem(label=item['label'])
                    li.setProperty("index", str(item['index'])) # Real index
                    if item['is_active']:
                        li.setProperty("IsActive", "true")
                        li.select(True)
                        active_pos = i
                    ctrl.addItem(li)
                
                if active_pos != -1:
                    ctrl.selectItem(active_pos)

                xbmcgui.Window(10000).setProperty("OSDAudioListOpen", "false")
                return
            except:
                pass
        except:
            pass
    log("OSD control 80001 not found in windows 12901")

def open_osd_audio_list():
    display_items, current_index = get_audio_items()
    if not display_items:
        return

    import window_handler
    # Use new XML for audio list
    w = window_handler.OSDListWindow('Custom_1115_OSDAudioList.xml', ADDON_PATH, 'Default', '1115')
    w.setItems(display_items)
    
    def on_select(item):
        real_index = item["index"]
        try:
            player = xbmc.Player()
            if real_index == current_index:
                 xbmcgui.Dialog().notification("音轨", "已是当前音轨")
            else:
                 player.setAudioStream(real_index)
                 xbmcgui.Dialog().notification("音轨", f"已切换至: {item['label']}")
            
            xbmcgui.Window(10000).setProperty("OSDAudioListOpen", "true")
        except:
            pass

    w.setCallback(on_select)
    
    xbmcgui.Window(10000).setProperty("OSDAudioListOpen", "true")
    w.doModal()
    del w

def router(paramstring):
    log(f"Router called with: {paramstring}")
    if not paramstring:
        # 列表模式
        list_videos()
        return

    # 解析路径，例如 plugin://..../?mode=play&movieid=1
    params = dict(urllib.parse.parse_qsl(paramstring.lstrip('?')))
    mode = params.get("mode")
    log(f"Router mode: {mode}")
    
    if mode == "select_audio":
        select_audio()
        return

    if mode == "populate_audio_list":
        populate_audio_list()
        return

    if mode == "open_osd_audio_list":
        open_osd_audio_list()
        return

    if mode == "record_click":
        # 记录点击时间
        xbmcgui.Window(10000).setProperty("MovieClickTime", str(time.time()))
        return

    if mode == "clear":
        # 清空列表
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return

    if mode == "set_home_background":
        image = params.get("image", "")
        
        # Show dialog
        dialog = xbmcgui.Dialog()
        options = ["设为全局背景", "重置背景"] # Set as Global Background, Reset Background
        # Use contextmenu instead of select for a smaller dialog
        ret = dialog.contextmenu(options)
        
        if ret == 0:
            if image:
                xbmc.executebuiltin(f'Skin.SetString(CustomHomeBackground,{image})')
                xbmc.executebuiltin('Notification(背景已设置, 全局背景已更新)')
            else:
                xbmc.executebuiltin('Notification(错误, 无法获取当前背景图片)')
        elif ret == 1:
            xbmc.executebuiltin('Skin.SetString(CustomHomeBackground,)')
            xbmc.executebuiltin('Notification(背景已重置, 全局背景已恢复默认)')
        return

    if mode == "launch_t9":
        new_text = ""
        xbmc.executebuiltin(f'SetProperty(t9_input,{new_text},1111)')
        
        import window_handler
        # 皮肤路径，假设在 addons 下
        skin_path = xbmcvfs.translatePath("special://home/addons/skin.cpm.estuary.search/")
        # 创建并显示窗口
        w = window_handler.T9Window('Custom_1111_MovieFilter.xml', skin_path, 'Default', '1111')
        w.doModal()
        w.cleanup()
        del w
        return

    if mode == "open_sub_settings":
        open_settings_and_click('osdsubtitlesettings', clicks=4)
        return

    if mode == "open_audio_settings":
        open_settings_and_click('osdaudiosettings', clicks=3)
        return

    if mode == "open_playing_tvshow":
        open_playing_tvshow()
        return

    if mode == "record_skip_point":
        record_skip_point()
        return

    if mode == "delete_skip_point":
        delete_skip_point()
        return

    if mode == "select_subtitle":
        log("Entering select_subtitle mode")
        select_subtitle()
        return

    if mode == "open_osd_subtitle_list":
        open_osd_subtitle_list()
        return

    if mode == "populate_subtitle_list":
        log("Entering populate_subtitle_list mode")
        populate_subtitle_list()
        return

    if mode == "osd_click_handler":
        osd_click_handler()
        return

    if mode == "set_subtitle":
        index = params.get("index")
        set_subtitle(index)
        return

    if mode == "force_prev":
        # 重新播放当前视频
        pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        pos = pl.getposition()
        if pos >= 0:
            # 使用 JSON-RPC Player.GoTo 跳转到当前位置，实现重播
            json_query = {
                "jsonrpc": "2.0",
                "method": "Player.GoTo",
                "params": {
                    "playerid": 1,
                    "to": pos
                },
                "id": 1
            }
            xbmc.executeJSONRPC(json.dumps(json_query))
        return

    if mode == "play":
        play_movie(int(params.get("id", params.get("movieid"))))
    elif mode == "play_musicvideo":
        play_musicvideo(int(params["id"]))
    elif mode == "open_tvshow":
        log(f"Opening TVShow {params['id']}")
        path = f"videodb://tvshows/titles/{params['id']}/"
        xbmc.executebuiltin(f"ActivateWindow(Videos,{path},return)")
    elif mode == "open_set":
        log(f"Opening Set {params['id']}")
        path = f"videodb://movies/sets/{params['id']}/"
        xbmc.executebuiltin(f"ActivateWindow(Videos,{path},return)")
    else:
        list_videos()
    
    log("---------------------->\n\n")

def osd_click_handler():
    # 检查 VideoOSD 是否打开
    if not xbmc.getCondVisibility('Window.IsActive(videoosd)'):
        return

    window = xbmcgui.Window(12901) # VideoOSD
    try:
        focus_id = window.getFocusId()
        # 检查焦点是否在字幕列表 (80000)
        if focus_id == 80000:
            ctrl = window.getControl(80000)
            pos = ctrl.getSelectedPosition()
            item = ctrl.getListItem(pos)
            real_index = item.getProperty("index")
            if real_index:
                set_subtitle(real_index)
    except Exception as e:
        log(f"Error in osd_click_handler: {e}")

if __name__ == "__main__":
    # sys.argv[0] 是 plugin://...; sys.argv[2] 是 '?xxx'
    # log(sys.argv)
    if HANDLE != -1 and len(sys.argv) > 2:
        router(sys.argv[2])
    elif len(sys.argv) > 1:
        router(sys.argv[1])
    else:
        router("")
