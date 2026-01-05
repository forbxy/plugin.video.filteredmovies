# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import json
import datetime
import urllib.parse
import os
import time

def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[FilteredMovies] {msg}", level)

def get_filter_val(filters, key, default=None):
    if filters and key in filters:
        return filters[key]
    return default

def get_inprogress_episodes_map():
    """
    获取所有正在观看的剧集，并返回 {tvshowid: partial_progress_sum} 的映射。
    单集的进度计算方式为 (resume_position / total_duration)。
    """
    try:
        # 获取正在观看的剧集
        # 注意："inprogress" 筛选器可能并非在所有 Kodi 版本中都可用，
        # 但如果获取所有剧集，检查 "resume" 属性是可靠的。
        # 然而，获取所有剧集开销很大。
        # 如果可能，我们尝试通过 playcount=0 (未观看) 和 lastplayed (已开始) 进行筛选，
        # 或者如果可用 (Kodi 18+)，使用 "inprogress" 字段。
        
        # 使用 "inprogress" 筛选器
        flt = {"field": "inprogress", "operator": "true", "value": ""}
        
        params = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetEpisodes",
            "params": {
                "properties": ["tvshowid", "resume", "runtime"],
                "filter": flt
            },
            "id": "inprogress_eps"
        }
        
        resp = xbmc.executeJSONRPC(json.dumps(params))
        data = json.loads(resp)
        
        episodes = data.get("result", {}).get("episodes", [])
        
        progress_map = {}
        
        for ep in episodes:
            tvshow_id = ep.get("tvshowid")
            if not tvshow_id:
                continue
                
            resume = ep.get("resume", {})
            position = resume.get("position", 0)
            total = resume.get("total", 0)
            
            if total == 0:
                total = ep.get("runtime", 0)
            
            if total > 0 and position > 0:
                fraction = float(position) / float(total)
                # 上限设为 0.99，避免计为完整剧集（完整剧集应由 watchedepisodes 处理）
                if fraction > 0.99: fraction = 0.99
                
                progress_map[tvshow_id] = progress_map.get(tvshow_id, 0.0) + fraction
                
        return progress_map
        
    except Exception as e:
        xbmc.log(f"[moviefilter] Error fetching in-progress episodes: {e}", xbmc.LOGERROR)
        return {}

def build_filter(filters=None, media_type=None):
    rules = []
    
    # 类型（genre）
    genre = get_filter_val(filters, "filter.genre")
    if genre and genre != "类型": # 默认值
        if genre == "其他":
            # 静态定义的“其他”类型列表 (数据库中存在，但不在常规筛选按钮中的类型)
            # 逻辑：只要包含这些类型中的任意一个，就显示在“其他”里
            other_genres = [
                "奇幻", "家庭", "西部", "电视电影", 
                "Sci-Fi & Fantasy", "War & Politics", "惊悚"
            ]
            
            or_rules = []
            for og in other_genres:
                or_rules.append({
                    "field": "genre",
                    "operator": "contains",
                    "value": og
                })
            
            if or_rules:
                rules.append({"or": or_rules})
        else:
            # 处理特殊类型的映射 (例如 Kodi 剧集中的英文组合类型)
            search_values = [genre]
            if genre == "科幻":
                search_values.append("Sci-Fi & Fantasy")
            elif genre == "战争":
                search_values.append("War & Politics")
            
            if len(search_values) == 1:
                rules.append({
                    "field": "genre",
                    "operator": "contains", 
                    "value": genre
                })
            else:
                or_rules = []
                for v in search_values:
                    or_rules.append({
                        "field": "genre",
                        "operator": "contains",
                        "value": v
                    })
                rules.append({"or": or_rules})

    # 地区（region）
    # 尝试对所有类型应用地区筛选
    region = get_filter_val(filters, "filter.region")
    if region and region != "地区": # 默认值
        if region == "其他":
            # 排除列表中的所有已知国家/地区
            # 注意：这里要排除的是 Skin 中已有的选项对应的 Kodi 数据库值
            exclude_regions = [
                "China", "Hong Kong", "Taiwan", 
                "United States", "Japan", "South Korea", 
                "Thailand", "India", "United Kingdom", 
                "France", "Germany", "Russia", "Canada"
            ]
            for er in exclude_regions:
                if media_type == "tvshow":
                    rules.append({
                        "field": "tag",
                        "operator": "doesnotcontain",
                        "value": er
                    })
                elif media_type == "set":
                    pass # 电影集单独处理
                else:
                    rules.append({
                        "field": "country",
                        "operator": "doesnotcontain",
                        "value": er
                    })
        else:
            # 映射常见国家/地区名称差异 (Skin -> Kodi DB)
            if region == "内地": region = "China" # 或者 "China"，取决于数据库
            elif region == "中国香港": region = "Hong Kong"
            elif region == "中国台湾": region = "Taiwan"
            elif region == "美国": region = "United States"
            elif region == "日本": region = "Japan"
            elif region == "韩国": region = "South Korea"
            elif region == "泰国": region = "Thailand"
            elif region == "印度": region = "India"
            elif region == "英国": region = "United Kingdom"
            elif region == "法国": region = "France"
            elif region == "德国": region = "Germany"
            elif region == "俄罗斯": region = "Russia"
            elif region == "加拿大": region = "Canada"
            
            # 如果数据库使用 "China" 但界面发送 "内地"，则回退处理
            # 假设数据库使用英文名称，基于之前的代码 "USA" -> "United States"
            
            if media_type == "tvshow":
                rules.append({
                    "field": "tag",
                    "operator": "contains",
                    "value": region
                })
            elif media_type == "set":
                pass # 电影集单独处理
            else:
                rules.append({
                    "field": "country",
                    "operator": "contains",
                    "value": region
                })

    # 首字母（title startswith）
    letter = get_filter_val(filters, "filter.letter")
    if letter:
        rules.append({
            "field": "title",
            "operator": "startswith",
            "value": letter
        })

    # 年份（year）
    year_val = get_filter_val(filters, "filter.year")
    if year_val and year_val != "年份": # 默认值
        current_year = datetime.datetime.now().year
        if year_val == "今年":
            rules.append({"field": "year", "operator": "is", "value": str(current_year)})
        elif year_val == "2020年代":
            rules.append({"field": "year", "operator": "between", "value": ["2020", "2029"]})
        elif year_val == "2010年代":
            rules.append({"field": "year", "operator": "between", "value": ["2010", "2019"]})
        elif year_val == "2000年代":
            rules.append({"field": "year", "operator": "between", "value": ["2000", "2009"]})
        elif year_val == "90年代":
            rules.append({"field": "year", "operator": "between", "value": ["1990", "1999"]})
        elif year_val == "80年代":
            rules.append({"field": "year", "operator": "between", "value": ["1980", "1989"]})
        elif year_val == "70年代":
            rules.append({"field": "year", "operator": "between", "value": ["1970", "1979"]})
        elif year_val == "60年代":
            rules.append({"field": "year", "operator": "between", "value": ["1960", "1969"]})
        elif year_val == "更早":
            rules.append({"field": "year", "operator": "lessthan", "value": "1960"})

    # 评分 (rating) - Multi-select
    def check_rating(key):
        if filters and key in filters:
            return filters[key]
        return False

    # 定义具有连续边界的范围以避免间隙
    # (最小值, 最大值)
    selected_ranges = []
    if check_rating("filter.rating.10-9"): selected_ranges.append([9.0, 10.0])
    if check_rating("filter.rating.9-8"): selected_ranges.append([8.0, 9.0])
    if check_rating("filter.rating.8-7"): selected_ranges.append([7.0, 8.0])
    if check_rating("filter.rating.7-6"): selected_ranges.append([6.0, 7.0])
    if check_rating("filter.rating.6分以下"): selected_ranges.append([0.0, 6.0])

    rating_rules = []
    if selected_ranges:
        # 按起始值排序
        selected_ranges.sort(key=lambda x: x[0])
        
        merged = []
        curr = selected_ranges[0]
        
        for next_range in selected_ranges[1:]:
            # 如果相邻或重叠（下一个起始值 <= 当前结束值）
            if next_range[0] <= curr[1]:
                curr[1] = max(curr[1], next_range[1])
            else:
                merged.append(curr)
                curr = next_range
        merged.append(curr)
        
        for r in merged:
            if r[0] == 0.0:
                # 小于 X
                rating_rules.append({"field": "rating", "operator": "lessthan", "value": str(r[1])})
            else:
                # X 到 Y
                rating_rules.append({"field": "rating", "operator": "between", "value": [str(r[0]), str(r[1])]})
        
    if rating_rules:
        if media_type == "set":
            pass # 电影集原生不支持评分筛选，通过后处理处理
        elif len(rating_rules) == 1:
            rules.append(rating_rules[0])
        else:
            rules.append({"or": rating_rules})

    if not rules:
        return None

    return {
        "and": rules
    }

def build_sort(filters=None):
    sort_key = get_filter_val(filters, "filter.sort", "hot")

    # Map UI values to DB values
    if sort_key == "最新上线": sort_key = "latest"
    elif sort_key == "影片评分": sort_key = "rating"
    elif sort_key == "最新入库": sort_key = "dateadded"
    elif sort_key == "最近观看": sort_key = "lastplayed"
    elif sort_key == "随机": sort_key = "random"

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

def sort_items_locally(items, sort_obj):
    if not sort_obj:
        return items
    method = sort_obj.get("method")
    order = sort_obj.get("order", "descending")
    reverse = (order == "descending")
    
    def sort_key_func(m):
        val = m.get(method)
        # 次要排序键：入库时间（用于混合具有相同年份/评分的项目）
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
            # 播放次数（热度）排序也优先考虑断点续播
            has_resume = 0
            resume = m.get("resume") or {}
            if isinstance(resume, dict) and resume.get("position", 0) > 0:
                has_resume = 1
            
            # 检查剧集进度
            if m.get("media_type") == "tvshow":
                total = m.get("episode", 0)
                watched = m.get("watchedepisodes", 0)
                lp = m.get("lastplayed")
                if total > 0 and watched < total and (watched > 0 or lp):
                    has_resume = 1
            
            # 检查电影集进度
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

def get_documentary_items(limit, filters=None):
    filter_obj_movie = build_filter(filters=filters, media_type="movie")
    filter_obj_tv = build_filter(filters=filters, media_type="tvshow")
    sort_obj = build_sort(filters=filters)
    
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

    # 获取电影
    movie_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "file", "resume", "runtime", "lastplayed"]
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
    
    # 获取剧集
    tv_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "episode", "watchedepisodes", "file", "lastplayed"]
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

    # 执行批量请求
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

    # 排序合并后的结果
    items = sort_items_locally(items, sort_obj)
    
    # 合并后应用限制？
    # 如果我们分别为每个获取了 limit=500，我们最多有 1000 个。
    # 我们应该切片到限制大小。
    return items[:limit]

def get_movieset_progress_map():
    """
    获取所有属于电影集的电影，并计算每个电影集的 {setid: {'total': count, 'watched': count, 'partial': float}}
    """
    try:
        # 筛选属于任何电影集的电影 (set != "")
        flt = {"field": "set", "operator": "isnot", "value": ""}
        
        params = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": ["setid", "playcount", "resume", "runtime", "rating"],
                "filter": flt
            },
            "id": "set_movies"
        }
        
        resp = xbmc.executeJSONRPC(json.dumps(params))
        data = json.loads(resp)
        
        movies = data.get("result", {}).get("movies", [])
        
        progress_map = {}
        
        for m in movies:
            set_id = m.get("setid")
            if not set_id:
                continue
                
            if set_id not in progress_map:
                progress_map[set_id] = {"total": 0, "watched": 0, "partial": 0.0, "rating_sum": 0.0, "rating_count": 0}
            
            progress_map[set_id]["total"] += 1
            
            # Rating calculation
            rating = m.get("rating", 0.0)
            if rating > 0:
                progress_map[set_id]["rating_sum"] += rating
                progress_map[set_id]["rating_count"] += 1

            playcount = m.get("playcount", 0)
            if playcount > 0:
                progress_map[set_id]["watched"] += 1
            else:
                # 仅在未完全观看时计算部分进度
                resume = m.get("resume", {})
                position = resume.get("position", 0)
                total = resume.get("total", 0)
                if total == 0: total = m.get("runtime", 0)
                
                if total > 0 and position > 0:
                    fraction = float(position) / float(total)
                    if fraction > 0.99: fraction = 0.99 # 如果未标记为已观看，则上限为 0.99
                    progress_map[set_id]["partial"] += fraction
                
        return progress_map
        
    except Exception as e:
        log(f"Error fetching movieset progress: {e}")
        return {}

def get_items_by_ids(allowed_ids, media_type, limit):
    """
    Helper to fetch specific items by ID for a given media type (or all).
    """
    if not allowed_ids:
        return []
    
    log(f"Applying T9 ID filter {allowed_ids} for {media_type}")
    
    # Filter allowed_ids based on media_type
    filtered_ids = []
    for item_data in allowed_ids:
        if isinstance(item_data, int):
            itype = "movie"
            item_data = {"id": item_data, "type": "movie"}
        else:
            itype = item_data.get("type", "movie")
        
        if media_type == "all":
            filtered_ids.append(item_data)
        elif media_type == "movie":
            if itype == "movie": filtered_ids.append(item_data)
        elif media_type == "tvshow":
            if itype == "tvshow": filtered_ids.append(item_data)
        elif media_type == "set":
            if itype == "set": filtered_ids.append(item_data)
        elif media_type == "documentary":
            if itype in ["movie", "tvshow"]: filtered_ids.append(item_data)
        elif media_type == "concert":
            if itype == "movie": filtered_ids.append(item_data)
    
    batch_cmds = []
    items_to_fetch = filtered_ids[:limit]
    
    # Define properties
    movie_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "resume", "runtime", "lastplayed", "playcount", "genre", "file", "plot"]
    tv_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "episode", "watchedepisodes", "lastplayed", "playcount", "genre", "file", "plot"]
    set_props = ["title", "thumbnail", "art", "plot", "playcount"]
    
    for i, item_data in enumerate(items_to_fetch):
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
    
    if not batch_cmds:
        return []

    resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
    try:
        results = json.loads(resp)
    except:
        log("Failed to parse batch response")
        return []
    
    items = []
    
    # Fetch partial progress for TV shows if needed
    partial_progress_map = {}
    if any(cmd.get("method") == "VideoLibrary.GetTVShowDetails" for cmd in batch_cmds):
            partial_progress_map = get_inprogress_episodes_map()

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
                    tid = item.get("tvshowid")
                    if tid:
                        item["partial_progress"] = partial_progress_map.get(tid, 0.0)
                    items.append(item)
                elif "setdetails" in res_val:
                    item = res_val["setdetails"]
                    item["media_type"] = "set"
                    items.append(item)
    
    return items

def get_movie_items(filters, limit, allowed_ids=None):
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "movie", limit)
    else:
        filter_obj = build_filter(filters, media_type="movie")
        props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "resume", "runtime", "lastplayed", "playcount", "genre", "file", "plot"]
        
        params = {
            "jsonrpc": "2.0", "id": "movies",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": props,
                "limits": {"start": 0, "end": limit},
                "sort": sort_obj
            }
        }
        if filter_obj: params["params"]["filter"] = filter_obj
        
        resp = xbmc.executeJSONRPC(json.dumps(params))
        items = json.loads(resp).get("result", {}).get("movies", [])
        for item in items: item["media_type"] = "movie"

    return sort_items_locally(items, sort_obj)

def get_tvshow_items(filters, limit, allowed_ids=None):
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "tvshow", limit)
    else:
        filter_obj = build_filter(filters, media_type="tvshow")
        props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "episode", "watchedepisodes", "lastplayed", "playcount", "genre", "file", "plot"]
        
        params = {
            "jsonrpc": "2.0", "id": "tvshows",
            "method": "VideoLibrary.GetTVShows",
            "params": {
                "properties": props,
                "limits": {"start": 0, "end": limit},
                "sort": sort_obj
            }
        }
        if filter_obj: params["params"]["filter"] = filter_obj
        
        resp = xbmc.executeJSONRPC(json.dumps(params))
        items = json.loads(resp).get("result", {}).get("tvshows", [])
        
        # Attach partial progress
        partial_progress_map = get_inprogress_episodes_map()
        for item in items:
            item["media_type"] = "tvshow"
            tid = item.get("tvshowid")
            if tid:
                item["partial_progress"] = partial_progress_map.get(tid, 0.0)

    return sort_items_locally(items, sort_obj)

def get_set_items(filters, limit, allowed_ids=None):
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "set", limit)
    else:
        # Complex filter logic for sets
        region_val = get_filter_val(filters, "filter.region")
        rating_active = any(k.startswith("filter.rating") for k in filters.keys()) if filters else False
        genre_val = get_filter_val(filters, "filter.genre")
        year_val = get_filter_val(filters, "filter.year")
        
        has_complex = (region_val and region_val != "地区") or rating_active or (genre_val and genre_val != "类型") or (year_val and year_val != "年份")
        
        # Initial fetch
        # Always fetch a large number to allow local filtering of single-movie sets
        fetch_limit = 20000
        
        props = ["title", "thumbnail", "art", "plot", "playcount"]
        params = {
            "jsonrpc": "2.0", "id": "sets",
            "method": "VideoLibrary.GetMovieSets",
            "params": {
                "properties": props,
                "limits": {"start": 0, "end": fetch_limit},
                "sort": sort_obj
            }
        }
        
        # Basic filter (title/letter only)
        basic_filters = {}
        if filters and "filter.letter" in filters:
            basic_filters["filter.letter"] = filters["filter.letter"]
        set_basic_filter = build_filter(basic_filters, media_type="set")
        if set_basic_filter: params["params"]["filter"] = set_basic_filter
        
        resp = xbmc.executeJSONRPC(json.dumps(params))
        items = json.loads(resp).get("result", {}).get("sets", [])
        
        # Post-filter if complex
        if has_complex:
            try:
                movie_filters_dict = filters.copy() if filters else {}
                if "filter.letter" in movie_filters_dict: del movie_filters_dict["filter.letter"]
                
                movie_filter = build_filter(movie_filters_dict, media_type="movie")
                set_rule = {"field": "set", "operator": "isnot", "value": ""}
                
                if movie_filter:
                    if "and" in movie_filter: movie_filter["and"].append(set_rule)
                    else: movie_filter = {"and": [movie_filter, set_rule]}
                else:
                    movie_filter = {"and": [set_rule]}
                
                params_lookup = {
                    "jsonrpc": "2.0", "method": "VideoLibrary.GetMovies",
                    "params": {"properties": ["setid"], "filter": movie_filter},
                    "id": "set_complex_lookup"
                }
                resp_lookup = xbmc.executeJSONRPC(json.dumps(params_lookup))
                movies = json.loads(resp_lookup).get("result", {}).get("movies", [])
                valid_set_ids = {m.get("setid") for m in movies if m.get("setid")}
                
                items = [x for x in items if x.get("setid") in valid_set_ids]
                # items = items[:limit] # Don't slice here yet, wait for single-movie filter
            except Exception as e:
                log(f"Error in set complex post-filter: {e}")

        for item in items: item["media_type"] = "set"

    # Attach set progress and filter single-movie sets
    set_progress_map = get_movieset_progress_map()
    filtered_items = []
    
    for item in items:
        sid = item.get("setid")
        if sid and sid in set_progress_map:
            total = set_progress_map[sid]["total"]
            
            # Filter out sets with only 1 movie
            if total <= 1:
                continue
                
            item["total"] = total
            item["watched"] = set_progress_map[sid]["watched"]
            item["partial_progress"] = set_progress_map[sid]["partial"]
            
            # Calculate average rating
            r_sum = set_progress_map[sid].get("rating_sum", 0.0)
            r_count = set_progress_map[sid].get("rating_count", 0)
            if r_count > 0:
                item["rating"] = round(r_sum / r_count, 1)
            
            filtered_items.append(item)
            
    items = filtered_items

    return sort_items_locally(items, sort_obj)[:limit]

def get_concert_items(filters, limit, allowed_ids=None):
    # Concerts are movies with genre="Music"
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "concert", limit)
        # Strict filter for concerts in T9
        items = [x for x in items if len(x.get("genre", [])) == 1 and (x.get("genre", [])[0] == "音乐" or x.get("genre", [])[0] == "Music")]
    else:
        # Add Music genre rule
        music_rule = {"field": "genre", "operator": "is", "value": "音乐"}
        
        # 忽略传入的 genre 筛选，强制使用音乐
        temp_filters = filters.copy() if filters else {}
        if "filter.genre" in temp_filters:
            del temp_filters["filter.genre"]

        filter_obj = build_filter(temp_filters, media_type="movie") # Use movie filter base
        
        if filter_obj:
            if "and" in filter_obj: filter_obj["and"].append(music_rule)
            else: filter_obj = {"and": [filter_obj, music_rule]}
        else:
            filter_obj = {"and": [music_rule]}
            
        props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "resume", "runtime", "lastplayed", "playcount", "genre", "file", "plot"]
        params = {
            "jsonrpc": "2.0", "id": "movies",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": props,
                "limits": {"start": 0, "end": 2000}, # 扩大获取范围以便后置筛选
                "sort": sort_obj,
                "filter": filter_obj
            }
        }
        resp = xbmc.executeJSONRPC(json.dumps(params))
        items = json.loads(resp).get("result", {}).get("movies", [])
        
        # 后置筛选：严格检查类型是否仅为“音乐”
        filtered_items = []
        for item in items:
            genres = item.get("genre", [])
            if len(genres) == 1 and (genres[0] == "音乐"):
                item["media_type"] = "concert"
                filtered_items.append(item)
        items = filtered_items

    return sort_items_locally(items, sort_obj)[:limit]

def get_documentary_items(filters, limit, allowed_ids=None):
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "documentary", limit)
        # Strict filter for docs in T9
        items = [x for x in items if any(g in x.get("genre", []) for g in ["纪录", "记录", "Documentary", "纪录片"])]
    else:
        # Fetch both movies and tvshows with doc genre
        doc_rule = {
            "or": [
                {"field": "genre", "operator": "contains", "value": "纪录"},
                {"field": "genre", "operator": "contains", "value": "记录"},
                {"field": "genre", "operator": "contains", "value": "Documentary"}
            ]
        }
        
        def add_rule(f_obj, rule):
            if f_obj:
                if "and" in f_obj: f_obj["and"].append(rule)
                else: f_obj = {"and": [f_obj, rule]}
            else: f_obj = {"and": [rule]}
            return f_obj

        filter_obj_movie = add_rule(build_filter(filters, media_type="movie"), doc_rule)
        filter_obj_tv = add_rule(build_filter(filters, media_type="tvshow"), doc_rule)
        
        # Batch fetch
        movie_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "file", "resume", "runtime", "lastplayed", "plot"]
        tv_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "episode", "watchedepisodes", "file", "lastplayed", "plot"]
        
        batch_cmds = [
            {
                "jsonrpc": "2.0", "id": "movies", "method": "VideoLibrary.GetMovies",
                "params": {"properties": movie_props, "limits": {"start": 0, "end": limit}, "sort": sort_obj, "filter": filter_obj_movie}
            },
            {
                "jsonrpc": "2.0", "id": "tvshows", "method": "VideoLibrary.GetTVShows",
                "params": {"properties": tv_props, "limits": {"start": 0, "end": limit}, "sort": sort_obj, "filter": filter_obj_tv}
            }
        ]
        
        items = []
        try:
            resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
            results = json.loads(resp)
            if isinstance(results, list):
                for res in results:
                    if "result" in res:
                        if "movies" in res["result"]:
                            for m in res["result"]["movies"]:
                                m["media_type"] = "movie"
                                items.append(m)
                        elif "tvshows" in res["result"]:
                            for t in res["result"]["tvshows"]:
                                t["media_type"] = "tvshow"
                                items.append(t)
        except Exception as e:
            log(f"Error fetching doc items: {e}")

    return sort_items_locally(items, sort_obj)[:limit]

def get_mixed_items(filters, limit, allowed_ids=None):
    sort_obj = build_sort(filters)
    
    if allowed_ids is not None:
        items = get_items_by_ids(allowed_ids, "all", limit)
    else:
        # Fetch all movies and tvshows
        filter_obj_movie = build_filter(filters, media_type="movie")
        filter_obj_tv = build_filter(filters, media_type="tvshow")
        
        movie_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "file", "resume", "runtime", "lastplayed", "plot"]
        tv_props = ["title", "thumbnail", "art", "dateadded", "rating", "year", "episode", "watchedepisodes", "file", "lastplayed", "plot"]
        
        batch_cmds = [
            {
                "jsonrpc": "2.0", "id": "movies", "method": "VideoLibrary.GetMovies",
                "params": {"properties": movie_props, "limits": {"start": 0, "end": limit}, "sort": sort_obj}
            },
            {
                "jsonrpc": "2.0", "id": "tvshows", "method": "VideoLibrary.GetTVShows",
                "params": {"properties": tv_props, "limits": {"start": 0, "end": limit}, "sort": sort_obj}
            }
        ]
        if filter_obj_movie: batch_cmds[0]["params"]["filter"] = filter_obj_movie
        if filter_obj_tv: batch_cmds[1]["params"]["filter"] = filter_obj_tv
        
        items = []
        try:
            resp = xbmc.executeJSONRPC(json.dumps(batch_cmds))
            results = json.loads(resp)
            if isinstance(results, list):
                for res in results:
                    if "result" in res:
                        if "movies" in res["result"]:
                            for m in res["result"]["movies"]:
                                m["media_type"] = "movie"
                                items.append(m)
                        elif "tvshows" in res["result"]:
                            for t in res["result"]["tvshows"]:
                                t["media_type"] = "tvshow"
                                items.append(t)
        except Exception as e:
            log(f"Error fetching mixed items: {e}")

    return sort_items_locally(items, sort_obj)[:limit]

def jsonrpc_get_items(filters=None, limit=500, allowed_ids=None):
    media_type = get_filter_val(filters, "filter.mediatype", "all")

    log(f"jsonrpc_get_items: type={media_type}, allowed_ids={len(allowed_ids) if allowed_ids else 'None'}")

    if media_type == "电影":
        return get_movie_items(filters, limit, allowed_ids)
    elif media_type == "剧集":
        return get_tvshow_items(filters, limit, allowed_ids)
    elif media_type == "系列电影":
        return get_set_items(filters, limit, allowed_ids)
    elif media_type == "演唱会":
        return get_concert_items(filters, limit, allowed_ids)
    elif media_type == "纪录片":
        return get_documentary_items(filters, limit, allowed_ids)
    else:
        return get_mixed_items(filters, limit, allowed_ids)

def fix_movie_set_poster(items):
    sets_needing_art = []
    for i, item in enumerate(items):
        if item.get("media_type") == "set":
            art = item.get("art", {})
            # 检查是否需要回退（缺少海报）
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
                            # 更新原始项目
                            orig_item = items[item_index]
                            if "art" not in orig_item: orig_item["art"] = {}
                            
                            fb_art = movie.get("art", {})
                            fb_thumb = movie.get("thumbnail")
                            
                            # 合并艺术图
                            for k, v in fb_art.items():
                                if k not in orig_item["art"]:
                                    orig_item["art"][k] = v
                            
                            # 如果仍然没有缩略图，则使用电影缩略图
                            if not orig_item.get("thumbnail") and fb_thumb:
                                orig_item["thumbnail"] = fb_thumb
        except Exception as e:
            log(f"Error batch fetching set art: {e}")
            
    return items

def create_list_item(m):
    li = xbmcgui.ListItem(label=m["title"])
    li.setContentLookup(False)
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
    
    # ID 处理
    url = ""
    is_folder = False
    
    if media_type == "movie" or media_type == "documentary":
        item_id = m.get("movieid")
        # 优先使用文件路径作为 URL，确保播放器能直接播放
        if "file" in m:
            url = m["file"]
        else:
            url = f"videodb://movies/titles/{item_id}"
        is_folder = False
    elif media_type == "tvshow":
        item_id = m.get("tvshowid")
        url = f"videodb://tvshows/titles/{item_id}/"
        is_folder = True
    elif media_type == "set":
        item_id = m.get("setid")
        url = f"videodb://movies/sets/{item_id}/"
        is_folder = True
    else:
        item_id = m.get("movieid")
        if "file" in m:
            url = m["file"]
        else:
            url = f"videodb://movies/titles/{item_id}"
        is_folder = False

    if not item_id:
        return None, None, False

    # Append timestamp to force unique path (bypassing history focus)
    if url:
        sep = "&" if "?" in url else "?"
        # url = f"{url}{sep}t={time.time()}"

    # 设置 IsPlayable
    if not is_folder:
        li.setProperty("IsPlayable", "true")
        li.setIsFolder(False)
    else:
        li.setProperty("IsPlayable", "false")
        li.setIsFolder(True)
    
    

    info_tag = li.getVideoInfoTag()
    info_tag.setTitle(m["title"])
    info_tag.setYear(m.get("year", 0))
    info_tag.setRating(m.get("rating", 0.0))
    if "plot" in m:
        info_tag.setPlot(m["plot"])
    
    if "playcount" in m:
        info_tag.setPlaycount(m.get("playcount", 0))

    if "file" in m:
        info_tag.setFilenameAndPath(m["file"])
        info_tag.setPath(m["file"])
    
    # 如果可用，设置断点续播点
    resume = m.get("resume", {})
    
    if media_type == "tvshow":
        total_episodes = m.get("episode", 0)
        watched_episodes = m.get("watchedepisodes", 0)
        last_played = m.get("lastplayed", "")
        
        if total_episodes > 0:
            # 计算百分比
            # 使用已观看计数 + 来自正在观看剧集的部分进度
            partial = m.get("partial_progress", 0.0)
            val = float(watched_episodes) + partial
            
            pct = int((val / total_episodes) * 100)
            if pct > 100: pct = 100
            # 如果我们认为已开始（有部分进度或 lastplayed），则确保至少 1%
            if (partial > 0 or (watched_episodes == 0 and last_played)) and pct == 0: 
                pct = 1
            
            if pct == 100: pct = 0
            
            li.setProperty("SkinPercentPlayed", str(pct))
    
    elif media_type == "set":
        total_movies = m.get("total", 0)
        watched_movies = m.get("watched", 0)
        
        if total_movies > 0:
            # 对于电影集，使用已观看计数 + 部分进度
            partial = m.get("partial_progress", 0.0)
            val = float(watched_movies) + partial
            
            pct = int((val / total_movies) * 100)
            if pct > 100: pct = 100
            
            # 如果已开始，确保至少 1%
            if (partial > 0 or watched_movies > 0) and pct == 0:
                pct = 1

            if pct == 100: pct = 0

            li.setProperty("SkinPercentPlayed", str(pct))

    elif resume and "position" in resume and resume["position"] > 0:
        total = resume.get("total", 0)
        if total == 0:
            total = m.get("runtime", 0)
        
        if total > 0:
            info_tag.setResumePoint(resume["position"], total)
            # 如果需要，还为皮肤可见性检查设置属性
            pct = int((resume["position"] / total) * 100)
            li.setProperty("SkinPercentPlayed", str(pct))
        else:
            info_tag.setResumePoint(resume["position"])
            pass
    
    # 设置 MediaType 以便皮肤显示正确的图标/信息
    info_tag.setMediaType(media_type if media_type not in ["documentary", "concert"] else "movie")
    
    # 关键：设置 DBID，让 Kodi 知道这是数据库中的项目，从而启用原生右键菜单
    info_tag.setDbId(int(item_id))

    li.setPath(url)
    # log(f"Created ListItem: {m['title']} ({media_type}) -> {url}")

    return li, url, is_folder
