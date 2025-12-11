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
import cache_manager

HANDLE = int(sys.argv[1])
ADDON_PATH = xbmcvfs.translatePath("special://home/addons/plugin.video.filteredmovies/")

def log(msg): xbmc.log(f"[moviefilter] {msg}", xbmc.LOGINFO)




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
    elif sort_key == "random":
        return {"method": "random"}
    else:
        # “最热” 简单用 播放次数
        return {"order": "descending", "method": "playcount"}

def get_method_and_params(media_type):
    base_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre"]
    
    if media_type == "movie" or media_type == "documentary" or media_type == "musicvideo":
        return "VideoLibrary.GetMovies", base_props + ["tagline"], "movies", "movieid"
    elif media_type == "tvshow":
        return "VideoLibrary.GetTVShows", base_props + ["studio", "mpaa", "episode"], "tvshows", "tvshowid"
    elif media_type == "set":
        return "VideoLibrary.GetMovieSets", ["title", "thumbnail", "art", "plot", "playcount"], "sets", "setid"
    return "VideoLibrary.GetMovies", base_props, "movies", "movieid"

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
            return (p, date_val)
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
    movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline", "file"]
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
    tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode", "file"]
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
    movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline", "file"]
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
    tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode", "file"]
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
        movie_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "tagline"]
        tv_props = ["title", "thumbnail", "art", "plot", "dateadded", "rating", "playcount", "year", "genre", "studio", "mpaa", "episode"]
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
    log("调用list_movies")
    
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

        li.setProperty("IsPlayable", "true" if mode in ["play", "play_musicvideo"] else "false")
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(m["title"])
        info_tag.setYear(m.get("year", 0))
        info_tag.setGenres(m.get("genre", []))
        info_tag.setPlot(m.get("plot", ""))
        info_tag.setRating(m.get("rating", 0.0))
        
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
    path = f"videodb://movies/titles/{movieid}/"
    xbmc.executebuiltin(f"PlayMedia({path})")

def play_musicvideo(mvid):
    path = f"videodb://musicvideos/titles/{mvid}/"
    xbmc.executebuiltin(f"PlayMedia({path})")

def router(paramstring):
    log("\n\n              <----------------------")
    log("调用router, paramstring=" + paramstring)
    if not paramstring:
        # 列表模式
        list_videos()
        return

    # 解析路径，例如 plugin://..../?mode=play&movieid=1
    params = dict(urllib.parse.parse_qsl(paramstring.lstrip('?')))
    mode = params.get("mode")
    log(f"解析后参数 {params}")
    
    if mode == "record_click":
        # 记录点击时间
        xbmcgui.Window(10000).setProperty("MovieClickTime", str(time.time()))
        return

    if mode == "clear":
        # 清空列表
        log(f"调用清空")
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
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
        del w
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

if __name__ == "__main__":
    # sys.argv[0] 是 plugin://...; sys.argv[2] 是 '?xxx'
    # log(sys.argv)
    router(sys.argv[2])
