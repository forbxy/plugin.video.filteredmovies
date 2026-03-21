# -*- coding: utf-8 -*-
import os
import sys
import urllib.parse
import json
import time
import threading
import pickle
import base64

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin

from lib.common import get_skin_name, notification, log
from lib import video_library as library

ADDON_ID = 'plugin.video.filteredmovies'
ADDON = xbmcaddon.Addon(id=ADDON_ID)
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ADDON_DATA_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
if not os.path.exists(ADDON_DATA_PATH):
    os.makedirs(ADDON_DATA_PATH)
SKIP_DATA_FILE = os.path.join(ADDON_DATA_PATH, 'skip_intro_data.json')
WINDOW_CACHE_FILE = os.path.join(ADDON_DATA_PATH, 'window_cache.pickle')
try:
    HANDLE = int(sys.argv[1])
except (IndexError, ValueError):
    HANDLE = -1


def prefetch_data_for_window():
    try:
        log("Starting window prefetch...")
        # 1. Load state from Skin
        filter_state = {}
        blob = xbmc.getInfoLabel('Skin.String(MFG.State)')
        if blob:
            try:
                decoded = base64.b64decode(blob).decode('utf-8')
                filter_state = json.loads(decoded)
            except Exception as e:
                log(f"Error loading state blob: {e}")

        # 2. Convert state to filters
        filters = {}
        for group, item in filter_state.items():
            if group == 'filter.rating':
                for obj in item:
                    val = obj.get('value')
                    if val:
                        filters[f"{group}.{val}"] = True
            else:
                val = item.get('value')
                if val is not None:
                    filters[group] = val
        
        # 3. Fetch items
        log(f"Prefetching with filters: {filters}")
        items = library.jsonrpc_get_items(filters=filters, limit=300, allowed_ids=None)
        items = library.fix_movie_set_poster(items)
        
        # 4. Save to cache
        with open(WINDOW_CACHE_FILE, 'wb') as f:
            pickle.dump(items, f)
            
        log(f"Window prefetch complete. Saved {len(items)} items.")
        
    except Exception as e:
        log(f"Error in prefetch_data_for_window: {e}")

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
                "properties": ["tvshowid", "showtitle", "season", "file"],
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
            
            # 1. 优先使用已刮削的剧集信息
            if tvshow_id and tvshow_id != -1 and show_title:
                return str(tvshow_id), show_title, str(season)

            # 2. 兼容未刮削的文件/文件夹模式
            file_path = item.get('file')
            if file_path:
                # 忽略插件流或 PVR
                if file_path.startswith("plugin://") or file_path.startswith("pvr://"):
                    return None, None, None
                    
                # 使用 os.path 处理路径 (自动适配系统分隔符)
                parent_dir = os.path.dirname(file_path)
                dir_name = os.path.basename(parent_dir)
                
                if not dir_name:
                    dir_name = "Unknown Folder"
                
                # 使用 "directory:路径" 作为 ID，如果是不同路径则视为不同剧集
                # 默认季数为 1
                return f"directory:{parent_dir}", dir_name, "1"
    except Exception as e:
        log(f"Error getting TV show info: {e}")
    return None, None, None

def record_skip_point():
    # 1. 尝试处理 ISO 电影的历史进度跳转
    try:
        player = xbmc.Player()
        if player.isPlayingVideo():
            playing_file = player.getPlayingFile()
            # 检查是否为蓝光 ISO (包含 bluray:// 和 .mpls)
            if playing_file.endswith("iso") or playing_file.endswith("ISO") or ("bluray://" in playing_file and ".mpls" in playing_file):
                # 获取当前电影 ID
                json_query = {
                    "jsonrpc": "2.0",
                    "method": "Player.GetItem",
                    "params": {"properties": ["file"], "playerid": 1},
                    "id": "get_item_db"
                }
                res = xbmc.executeJSONRPC(json.dumps(json_query))
                res_json = json.loads(res)
                
                if 'result' in res_json and 'item' in res_json['result']:
                    item = res_json['result']['item']
                    movie_id = item.get('id')
                    media_type = item.get('type')
                    
                    if movie_id and media_type == 'movie':
                        # 使用 JSON-RPC 获取历史进度
                        json_query_resume = {
                            "jsonrpc": "2.0",
                            "method": "VideoLibrary.GetMovieDetails",
                            "params": {
                                "movieid": movie_id,
                                "properties": ["resume"]
                            },
                            "id": "get_resume"
                        }
                        res_resume = xbmc.executeJSONRPC(json.dumps(json_query_resume))
                        res_resume_json = json.loads(res_resume)
                        
                        if 'result' in res_resume_json and 'moviedetails' in res_resume_json['result']:
                            details = res_resume_json['result']['moviedetails']
                            resume = details.get('resume', {})
                            position = resume.get('position', 0)
                            
                            if position > 0:
                                notification(f"跳转至历史进度 {int(position)}秒")
                                player.seekTime(position)
                                return # 成功跳转，直接返回
    except Exception as e:
        log(f"Error in ISO jump logic: {e}")

    # 2. 原有的剧集跳过逻辑
    tvshow_id, show_title, season = get_current_tvshow_info()
    if not tvshow_id:
        notification("无法识别剧集或文件夹信息", sound=True)
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
            
            notification("请在剧集前或后20%时间段内调用", sound=True)
            return

        data[tvshow_id]["seasons"][season] = season_data
        save_skip_data(data)
        
        # 通知 service 重新加载数据
        xbmcgui.Window(10000).setProperty("MFG.Reload", "true")
        
        notification(f"{msg} (第{season}季)")
        log(f"Recorded skip point for {show_title} Season {season}: {season_data}")
        
    except Exception as e:
        log(f"Error recording skip point: {e}")
        notification("无法记录请查阅日志", sound=True)

def delete_skip_point():
    tvshow_id, show_title, season = get_current_tvshow_info()
    if not tvshow_id:
        notification("无法识别剧集或文件夹信息", sound=True)
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
            notification("无片头片尾标记点", sound=True)
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
            notification("删除失败 请在剧集前或后20%时间段内调用", sound=True)
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
        xbmcgui.Window(10000).setProperty("MFG.Reload", "true")
        notification(msg)
        
    except Exception as e:
        log(f"Error deleting skip point: {e}")
        notification("删除错误", sound=True)

def open_playing_tvshow():
    # xbmc.executebuiltin("Dialog.Close(all,true)")
    # xbmc.sleep(100)
    
    try:
        if not xbmc.Player().isPlayingVideo():
            return
            
        json_query = {
            "jsonrpc": "2.0",
            "method": "Player.GetItem",
            "params": {
                "properties": ["tvshowid", "season"],
                "playerid": 1
            },
            "id": 1
        }
        json_response = xbmc.executeJSONRPC(json.dumps(json_query))
        response = json.loads(json_response)
        
        if 'result' in response and 'item' in response['result']:
            item = response['result']['item']
            tvshow_id = item.get('tvshowid')
            season = item.get('season', -1)
            item_type = item.get('type')
            
            if item_type == 'episode' and tvshow_id and tvshow_id != -1:
                if season != -1:
                    log(f"Opening TVShow ID: {tvshow_id} Season: {season}")
                    path = f"videodb://tvshows/titles/{tvshow_id}/{season}/"
                else:
                    log(f"Opening TVShow ID: {tvshow_id}")
                    path = f"videodb://tvshows/titles/{tvshow_id}/"
                xbmc.executebuiltin(f"ActivateWindow(Videos,{path},return)")
            else:
                log("Current playing item is not a TV show, opening Playlist")
                xbmc.executebuiltin("ActivateWindow(VideoPlaylist)")
    except Exception as e:
        log(f"Error opening playing tvshow: {e}")

def force_prev():
    try:
        player = xbmc.Player()
        if not player.isPlaying():
            return
        
        # 统一使用播放列表逻辑，不再单独处理剧集
        if player.isPlayingVideo():
            playlist_id = xbmc.PLAYLIST_VIDEO
        else:
            playlist_id = xbmc.PLAYLIST_MUSIC
            
        pl = xbmc.PlayList(playlist_id)
        pos = pl.getposition()
        
        if pos > 0:
            log(f"ForcePrev: Jumping to playlist pos {pos-1}")
            
            # 获取 active player id
            active_player_id = 1
            try:
                p_res = json.loads(xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Player.GetActivePlayers","id":1}'))
                if 'result' in p_res and len(p_res['result']) > 0:
                    active_player_id = p_res['result'][0]['playerid']
            except: pass

            json_query_goto = {
                "jsonrpc": "2.0",
                "method": "Player.GoTo",
                "params": {
                    "playerid": active_player_id,
                    "to": pos - 1
                },
                "id": 1
            }
            xbmc.executeJSONRPC(json.dumps(json_query_goto))
        else:
            log("ForcePrev: At start of playlist, restarting")
            notification("已是第一个")
            player.seekTime(0)

    except Exception as e:
        log(f"Error in force_prev: {e}")
        notification("操作失败", sound=True)

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
             notification("字幕已关闭")
        else:
             player.setSubtitleStream(index)
             player.showSubtitles(True)
        notification("字幕已切换")
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
        for itm in streams:
            log(f"{itm['language']} {itm['name']}")
        
        if not streams:
            if not suppress_warning:
                notification("没有可用的字幕流")
                
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
                'ukr': '乌克兰语', 'uk': '乌克兰语',
                'ice': '冰岛语', 'isl': '冰岛语', 'is': '冰岛语',
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
                'ara': '阿拉伯语', 'ar': '阿拉伯语',
                'hrv': '克罗地亚语', 'hr': '克罗地亚语',
                'ces': '捷克语', 'cze': '捷克语', 'cs': '捷克语',
                'ell': '希腊语', 'gre': '希腊语', 'el': '希腊语',
                'heb': '希伯来语', 'he': '希伯来语',
                'hun': '匈牙利语', 'hu': '匈牙利语',
                'ron': '罗马尼亚语', 'rum': '罗马尼亚语', 'ro': '罗马尼亚语',
                'tur': '土耳其语', 'tr': '土耳其语',
                'bul': '保加利亚语', 'bg': '保加利亚语',
                'msa': '马来语', 'may': '马来语', 'ms': '马来语',
                'pol': '波兰语', 'pl': '波兰语',
                'tgl': '塔加洛语', 'tl': '塔加洛语', 'fil': '菲律宾语',
                'eus': '巴斯克语', 'baq': '巴斯克语', 'eu': '巴斯克语', 'basque': '巴斯克语',
                'cat': '加泰罗尼亚语', 'ca': '加泰罗尼亚语', 'catalan': '加泰罗尼亚语',
                'glg': '加利西亚语', 'gl': '加利西亚语', 'gallegan': '加利西亚语',
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
            label = f"{idx + 1:>3}. {lang_name}"
            
            if name and name.lower() != lang_name.lower() and name.lower() != lang_code.lower():
                # Handle Chinese variations and other keywords
                import re
                replacements = [
                    (r'Chinese\s*[\(\[\{]?Simplified[\)\]\}]?', '简体'),
                    (r'Chinese\s*[\-\.]?\s*Simplified', '简体'),
                    (r'Simplified\s*Chinese', '简体'),
                    (r'Traditional\s*Chinese', '繁体'),
                    (r'Chinese\s*[\(\[\{]?Traditional[\)\]\}]?', '繁体'),
                    (r'Chinese\s*[\-\.]?\s*Traditional', '繁体'),
                    (r'Chi\s*\(Simp\)', '简体'),
                    (r'Chi\s*\(Trad\)', '繁体'),
                    (r'Simplified', '简体'),
                    (r'Traditional', '繁体'),
                    (r'Mandarin', '国语'),
                    (r'Cantonese', '粤语')
                ]
                for pattern, repl in replacements:
                    name = re.sub(pattern, repl, name, flags=re.IGNORECASE)

                # 尝试翻译 name 中的第一部分 (通常是语言全称)
                parts = name.split('-')
                first_part = parts[0].strip()
                
                # 简单的反向查找或直接映射
                translated_first_part = None
                # 遍历 lang_map 查找 value 对应的 key (这里不太准确，因为 map 是 code->name)
                # 我们直接尝试用 lang_map 匹配 first_part (假设它是英文全称或代码)
                
                # 扩展 lang_map 以包含常见的英文全称
                lang_map_extended = lang_map.copy()
                lang_map_extended.update({
                    'english': '英语', 'chinese': '中文', 'japanese': '日语', 'korean': '韩语',
                    'russian': '俄语', 'french': '法语', 'german': '德语', 'spanish': '西班牙语',
                    'italian': '意大利语', 'portuguese': '葡萄牙语', 'thai': '泰语', 'vietnamese': '越南语',
                    'indonesian': '印尼语', 'danish': '丹麦语', 'finnish': '芬兰语', 'dutch': '荷兰语',
                    'norwegian': '挪威语', 'swedish': '瑞典语', 'arabic': '阿拉伯语', 'croatian': '克罗地亚语',
                    'czech': '捷克语', 'greek': '希腊语', 'hebrew': '希伯来语', 'hungarian': '匈牙利语',
                    'romanian': '罗马尼亚语', 'turkish': '土耳其语', 'bulgarian': '保加利亚语', 'malay': '马来语',
                    'polish': '波兰语', 'tagalog': '塔加洛语', 'filipino': '菲律宾语',
                    'ukrainian': '乌克兰语', 'icelandic': '冰岛语'
                })
                
                if first_part.lower() in lang_map_extended:
                    translated_first_part = lang_map_extended[first_part.lower()]
                    # 替换第一部分
                    parts[0] = translated_first_part
                    name = "-".join(parts)
                
                label += f"-{name}"
            
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
        display_items = []
        for item in raw_items:
            label = item["label"]
            if item["is_active"]:
                label = f"✓ {label}"
            else:
                label = f"    {label}"
            display_items.append({"label": label, "index": item["index"], "is_active": item["is_active"]})
        
        return display_items, current_index, is_enabled, player

    except Exception as e:
        log(f"Error in get_subtitle_items: {e}")
        notification(f"获取字幕出错: {e}", sound=True)
        
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
    # set_skin_properties() moved to service
    display_items, current_index, is_enabled, player = get_subtitle_items()
    
    if not display_items:
        return

    # Use custom window
    log("Opening custom window")
    from lib import window_handler
    w = window_handler.DialogSelectWindow('Custom_1112_SubtitleSelect.xml', ADDON_PATH, 'Default', '1080i')
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
            notification("字幕已关闭")
            
        else:
            player.setSubtitleStream(real_index)
            player.showSubtitles(True)
            notification(f"字幕已切换至: {selected_item['label'].strip()}")


def open_osd_subtitle_list():
    # set_skin_properties() moved to service
    display_items, current_index, is_enabled, player = get_subtitle_items()
    if not display_items:
        return

    from lib import window_handler
    # Use the new XML
    w = window_handler.OSDListWindow('Custom_1113_OSDSubtitleList.xml', ADDON_PATH, 'Default', '1080i')
    w.setItems(display_items)
    
    def on_select(item):
        real_index = item["index"]
        # Call set_subtitle logic directly here to avoid circular dependency or re-opening
        try:
            player = xbmc.Player()
            if is_enabled and real_index == current_index:
                 player.showSubtitles(False)
                 notification("字幕已关闭")
            else:
                 player.setSubtitleStream(real_index)
                 player.showSubtitles(True)
                 notification(f"字幕已切换至: {item['label'].strip()}")
            
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
                notification("没有可用的音轨")
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
                'ukr': '乌克兰语', 'uk': '乌克兰语',
                'ice': '冰岛语', 'isl': '冰岛语', 'is': '冰岛语',
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
                'ara': '阿拉伯语', 'ar': '阿拉伯语',
                'hrv': '克罗地亚语', 'hr': '克罗地亚语',
                'ces': '捷克语', 'cze': '捷克语', 'cs': '捷克语',
                'ell': '希腊语', 'gre': '希腊语', 'el': '希腊语',
                'heb': '希伯来语', 'he': '希伯来语',
                'hun': '匈牙利语', 'hu': '匈牙利语',
                'ron': '罗马尼亚语', 'rum': '罗马尼亚语', 'ro': '罗马尼亚语',
                'tur': '土耳其语', 'tr': '土耳其语',
                'bul': '保加利亚语', 'bg': '保加利亚语',
                'msa': '马来语', 'may': '马来语', 'ms': '马来语',
                'pol': '波兰语', 'pl': '波兰语',
                'tgl': '塔加洛语', 'tl': '塔加洛语', 'fil': '菲律宾语',
                'eus': '巴斯克语', 'baq': '巴斯克语', 'eu': '巴斯克语', 'basque': '巴斯克语',
                'cat': '加泰罗尼亚语', 'ca': '加泰罗尼亚语', 'catalan': '加泰罗尼亚语',
                'glg': '加利西亚语', 'gl': '加利西亚语', 'gallegan': '加利西亚语',
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
            
            label = f"{idx + 1:>3}. {lang_name}"
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
        
        # Add checkmark to active item
        for item in display_items:
            if item['is_active']:
                item['label'] = f"✓ {item['label']}"
            else:
                item['label'] = f"    {item['label']}"

        return display_items, current_index
    except Exception as e:
        log(f"Error in get_audio_items: {e}")
        if not suppress_warning:
            notification(f"获取音轨出错: {e}", sound=True)
        return None, -1

def select_audio():
    # set_skin_properties() moved to service
    display_items, current_index = get_audio_items()
    
    if not display_items:
        return

    # Use custom window
    from lib import window_handler
    w = window_handler.DialogSelectWindow('Custom_1114_AudioSelect.xml', ADDON_PATH, 'Default', '1080i')
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
            notification("已是当前音轨")
        else:
            xbmc.Player().setAudioStream(real_index)
            notification(f"音轨已切换至: {selected_item['label'].strip()}")

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
    # set_skin_properties() moved to service
    display_items, current_index = get_audio_items()
    if not display_items:
        return

    from lib import window_handler
    # Use new XML for audio list
    w = window_handler.OSDListWindow('Custom_1115_OSDAudioList.xml', ADDON_PATH, 'Default', '1080i')
    w.setItems(display_items)
    
    def on_select(item):
        real_index = item["index"]
        try:
            player = xbmc.Player()
            if real_index == current_index:
                 notification("已是当前音轨")
            else:
                 player.setAudioStream(real_index)
                 notification(f"音轨已切换至: {item['label'].strip()}")
            
            xbmcgui.Window(10000).setProperty("OSDAudioListOpen", "true")
        except:
            pass

    w.setCallback(on_select)
    
    xbmcgui.Window(10000).setProperty("OSDAudioListOpen", "true")
    w.doModal()
    del w

def set_home_background(image):
    # Show dialog
    dialog = xbmcgui.Dialog()
    options = ["设为全局背景", "重置背景"] # Set as Global Background, Reset Background
    # Use contextmenu instead of select for a smaller dialog
    ret = dialog.contextmenu(options)
    
    if ret == 0:
        if image:
            xbmc.executebuiltin(f'Skin.SetString(CustomHomeBackground,{image})')
            # 使用插件图标代替默认的 info 图标
            notification("全局背景已更新")
        else:
            notification("错误:无法获取当前背景图片", sound=True)
    elif ret == 1:
        xbmc.executebuiltin('Skin.SetString(CustomHomeBackground,)')
        notification("背景已重置, 全局背景已恢复默认")

def launch_t9():
    log("Launching T9 Input Window")
    # Start prefetch thread immediately
    threading.Thread(target=prefetch_data_for_window).start()

    # Set initial ReloadID to trigger list load immediately with current state
    xbmcgui.Window(10000).setProperty("MFG.ReloadID", "first_" + str(time.time()))
    # 初始状态设为刷新中，以便窗口打开时先隐藏列表，加载完后再淡入
    # xbmcgui.Window(10000).setProperty("MFG.IsRefreshing", "true")

    skin_name = get_skin_name()

    # 3. Set Font Properties
    xml_file = 'Custom_5111_MovieFilter.xml'

    if skin_name == "horizon":
        # Horizon 2 does not have font10/font12/font13.
        # Generate a specific XML with valid fonts if it doesn't exist.
        base_dir = os.path.join(ADDON_PATH, 'resources', 'skins', 'Default', '1080i')
        horizon_xml = 'Custom_5111_MovieFilter_Horizon.xml'
        horizon_xml_path = os.path.join(base_dir, horizon_xml)
        
        if not os.path.exists(horizon_xml_path):
            log("Generating Horizon specific XML...")
            src_xml_path = os.path.join(base_dir, xml_file)
            try:
                with open(src_xml_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Replace fonts with Horizon equivalents
                content = content.replace('font10', 'font_tiny')
                content = content.replace('font12', 'font_mini')
                content = content.replace('font13', 'font_small')
                
                with open(horizon_xml_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                log(f"Generated {horizon_xml}")
            except Exception as e:
                log(f"Error generating Horizon XML: {e}")
        
        if os.path.exists(horizon_xml_path):
            xml_file = horizon_xml

    from lib import window_handler
    # 创建并显示窗口
    w = window_handler.FilterWindow(xml_file, ADDON_PATH, 'Default', '1080i')
    w.doModal()
    w.cleanup()

    del w

def filter_list(reload_param):
    # 先清空，再填充新的，保证页面永远都是显示前两行
    if reload_param.startswith("clear_"):
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return

    # Check cache if first load
    if reload_param.startswith("first_"):
        # Wait for cache file (max 1000ms)
        waited = 0
        while not os.path.exists(WINDOW_CACHE_FILE) and waited < 20:
            xbmc.sleep(50)
            waited += 1

    if reload_param.startswith("first_") and waited < 20:
        try:
            log(f"Found window cache: {WINDOW_CACHE_FILE}")
            with open(WINDOW_CACHE_FILE, 'rb') as f:
                items = pickle.load(f)

            log(f"Loaded {len(items)} items from window cache.")
            
            list_items = []
            for m in items:
                li, url, is_folder = library.create_list_item(m)
                if li:
                    list_items.append((url, li, is_folder))
            
            xbmcplugin.addDirectoryItems(HANDLE, list_items, len(list_items))
            xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
            try: os.remove(WINDOW_CACHE_FILE)
            except: pass
            return
        except Exception as e:
            log(f"Error loading window cache: {e}")
            try: os.remove(WINDOW_CACHE_FILE)
            except: pass

    import base64
    from lib import t9_helper
    
    # 1. Load state from Skin
    filter_state = {}
    blob = xbmc.getInfoLabel('Skin.String(MFG.State)')
    if blob:
        try:
            decoded = base64.b64decode(blob).decode('utf-8')
            filter_state = json.loads(decoded)
        except Exception as e:
            log(f"Error loading state blob: {e}")

    # 2. Convert state to filters
    filters = {}
    for group, item in filter_state.items():
        if group == 'filter.rating':
            for obj in item:
                val = obj['value']
                if val:
                    filters[f"{group}.{val}"] = True
        else:
            val = item['value']
            if val is not None:
                filters[group] = val

    # 3. T9 Input
    t9_input = xbmcgui.Window(10000).getProperty("MFG.T9Input")
    allowed_ids_str = xbmcgui.Window(10000).getProperty("MFG.AllowedIDs")
    allowed_ids = None
    limit=300
    if t9_input:
        if allowed_ids_str:
            try:
                allowed_ids = json.loads(allowed_ids_str)
            except Exception as e:
                log(f"Error parsing allowed_ids: {e}")
                allowed_ids = t9_helper.helper.search(t9_input)
        else:
            allowed_ids = t9_helper.helper.search(t9_input)
        limit = 24
        # 当有T9输入时，只保留影视范围
        keys_to_keep = ["filter.mediatype"]
        filters = {k: v for k, v in filters.items() if k in keys_to_keep}

    # 4. Get Items
    items = library.jsonrpc_get_items(filters=filters, limit=limit, allowed_ids=allowed_ids)
    items = library.fix_movie_set_poster(items)
    # 5. Populate List
    
    list_items = []
    for m in items:
        li, url, is_folder = library.create_list_item(m)
        if li:
            list_items.append((url, li, is_folder))
    
    xbmcplugin.addDirectoryItems(HANDLE, list_items, len(list_items))
    # cacheToDisc=False 确保每次刷新都不保留之前的焦点位置，从而回到开头
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
    
    if not reload_param.startswith("first_"):
        # 首次加载要的是快,不使用淡入效果
        # 列表加载完成，触发淡入动画
        xbmc.sleep(100)
        xbmcgui.Window(10000).setProperty("MFG.IsRefreshing", "false")
    log(f"Filtered list populated with {len(list_items)} items")

def set_vs10_mode(target_mode=None):
    try:
        raw_mode = xbmc.getInfoLabel("Player.Process(amlogic.vs10.mode.raw)")
        if not raw_mode:
            log("VS10 mode not available: amlogic.vs10.mode.raw is empty")
            notification("VS10引擎未就绪或不受支持")
            return
        log(f"Current VS10 raw mode: {raw_mode}")
        mode_names = {
            "vs10.original": "Origin",
            "vs10.sdr": "SDR",
            "vs10.hdr10": "HDR10",
            "vs10.dv": "Dolby Vision"
        }

        if target_mode and target_mode in mode_names:
            xbmc.executebuiltin(f"Action({target_mode})")
            # notification("VS10 Mode", f"Switched to {mode_names.get(target_mode)}")
            if target_mode == "vs10.original":
                message = "关闭VS10转码，使用原始输出"
            else:
                message = f"使用VS10转码为{mode_names.get(target_mode)}"
            notification(message,duration=4000)
            return

        hdr_type = xbmc.getInfoLabel("Player.Process(video.hdr.type)")
        
        available_modes = ["vs10.original"]
        
        if "SDR" in hdr_type or "HDR" in hdr_type:
            available_modes.append("vs10.dv")
            
        if "SDR" in hdr_type or "HLG" in hdr_type:
            available_modes.append("vs10.hdr10")
            
        available_modes.append("vs10.sdr")
        
        current_mode = "vs10.original"
        if raw_mode == "3":
            current_mode = "vs10.sdr"
        elif raw_mode == "2":
            current_mode = "vs10.hdr10"
        elif raw_mode in ["0", "1"]:
            if "Dolby" in hdr_type:
                current_mode = "vs10.original"
            else:
                current_mode = "vs10.dv"
        elif raw_mode == "5":
            current_mode = "vs10.original"
            
        try:
            curr_index = available_modes.index(current_mode)
            next_index = (curr_index + 1) % len(available_modes)
            next_mode = available_modes[next_index]
        except ValueError:
            next_mode = available_modes[0]
            
        xbmc.executebuiltin(f"Action({next_mode})")
        
        if next_mode == "vs10.original":
                message = "关闭VS10转码，使用原始输出"
        else:
            message = f"使用VS10转码为{mode_names.get(next_mode, next_mode)}"
        notification(message,duration=4000)
        
    except Exception as e:
        log(f"Error cycling VS10 mode: {e}")

def toggle_favourite():
    """与原生右键菜单的"添加到收藏夹/从收藏夹移除"行为一致"""
    # 从当前选中的 ListItem 读取信息，与原生 context menu 一致
    title = xbmc.getInfoLabel('ListItem.Label')
    dbid = xbmc.getInfoLabel('ListItem.DBID')
    dbtype = xbmc.getInfoLabel('ListItem.DBType')
    is_folder = xbmc.getCondVisibility('ListItem.IsFolder')
    path = xbmc.getInfoLabel('ListItem.FolderPath') if is_folder else xbmc.getInfoLabel('ListItem.FilenameAndPath')
    thumb = xbmc.getInfoLabel('ListItem.Art(poster)') or xbmc.getInfoLabel('ListItem.Thumb')
    log(f"Toggle Favourite - Title: {title}, DBID: {dbid}, DBType: {dbtype}, IsFolder: {is_folder}, Path: {path}, Thumb: {thumb}")
    if not path or not title:
        notification("无法获取项目信息", sound=True)
        return

    # script:// 路径去掉尾部斜杠，避免收藏夹中插件名多出 /
    if path.startswith("script://"):
        path = path.rstrip('/')

    # 对于库中的 folder 类型(tvshow/set)，使用 videodb 路径
    if dbid and dbid.isdigit() and int(dbid) > 0 and is_folder:
        if dbtype == "tvshow":
            path = f"videodb://tvshows/titles/{dbid}/"
        elif dbtype == "set":
            path = f"videodb://movies/sets/{dbid}/"

    # 判断收藏类型：folder 用 window，其余用 media
    if is_folder:
        fav_type = "window"
    else:
        fav_type = "media"

    # 检查是否已在收藏夹
    get_fav_query = {
        "jsonrpc": "2.0",
        "method": "Favourites.GetFavourites",
        "params": {"properties": ["path", "windowparameter"]},
        "id": 1
    }
    fav_resp = json.loads(xbmc.executeJSONRPC(json.dumps(get_fav_query)))
    favourites = fav_resp.get("result", {}).get("favourites") or []
    log(f"Current favourites: {favourites}")
    is_favourite = False
    if path.startswith("favourites://"):
        is_favourite = True
    else:
        for fav in favourites:
            fp = fav.get("path", "") or fav.get("windowparameter", "")
            if fp == path:
                is_favourite = True
                break

    # 调用 AddFavourite（内部实现为 AddOrRemove，即切换）
    add_params = {"title": title, "type": fav_type}
    if fav_type == "media":
        add_params["path"] = path
    else:
        add_params["window"] = "videos"
        add_params["windowparameter"] = path
    if thumb:
        add_params["thumbnail"] = thumb

    add_query = {
        "jsonrpc": "2.0",
        "method": "Favourites.AddFavourite",
        "params": add_params,
        "id": 1
    }
    xbmc.executeJSONRPC(json.dumps(add_query))
    if is_favourite:
        notification("已从收藏夹移除", title=title)
    else:
        notification("已添加到收藏夹", title=title)

def select_playback_speed():
    if not xbmc.getCondVisibility('Player.TempoEnabled'):
        notification("请在设置-播放器-视频中开启同步回放显示", sound=True)
        return
    
    if xbmc.getCondVisibility('Player.Paused'):
        notification("播放暂停时无法调整速度", sound=True)
        return

    # 1. Get current speed
    try:
        current_speed_str = xbmc.getInfoLabel('Player.PlaySpeed')
        current_speed = float(current_speed_str)
    except Exception as e:
        log(f"Error getting current playback speed: {e}")
        current_speed = 1.0
    log(f"Current playback speed: {current_speed}")
    # 2. Prepare items
    speeds = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    display_items = []
    
    for s in speeds:
        label = f"{s:.1f}x"
        is_active = abs(s - current_speed) < 0.05
        if is_active:
            label = f"✓ {label}"
        else:
            label = f"    {label}"
            
        display_items.append({
            "label": label,
            "speed": s,
            "is_active": is_active
        })

    # 3. Open Dialog
    from lib import window_handler
    w = window_handler.DialogSelectWindow('Custom_1116_SpeedSelect.xml', ADDON_PATH, 'Default', '1080i')
    w.setItems(display_items)
    w.doModal()
    
    ret_index = w.selected_index
    del w
    
    if ret_index == -1:
        return

    if ret_index < len(display_items):
        selected_item = display_items[ret_index]
        target_speed = selected_item["speed"]
        
        if abs(target_speed - current_speed) < 0.05:
            return # Same speed
            
        # Apply speed using PlayerControl(TempoUp/Down) logic
        diff = target_speed - current_speed
        steps = int(round(diff / 0.1))
        
        log(f"Adjusting speed: {current_speed} -> {target_speed} (steps: {steps})")
        
        if steps > 0:
            for _ in range(steps):
                xbmc.executebuiltin('PlayerControl(TempoUp)')
        elif steps < 0:
            for _ in range(abs(steps)):
                xbmc.executebuiltin('PlayerControl(TempoDown)')
                
        notification(f"{target_speed:.1f}x", title="播放速度")

def restart_linux_kodi():
    if not xbmc.getCondVisibility("System.Platform.Linux") or xbmc.getCondVisibility("System.Platform.Android"):
        notification("当前系统不支持此操作", sound=True)
        return
        
    log("Executing system level Kodi restart (kill -4 -> wait -> kill -9)")
    notification("正在发送重启指令...")
    xbmc.sleep(1000)
    
    kodi_pid = os.getpid()
    
    # 将包含kill逻辑的脚本独立出来，作为完全后台运行的命令
    # 为了避免 kodi 退出时导致 sh 进程被杀，利用 daemon 方式或双层 nohup
    kill_script = (
        f"kill -TERM {kodi_pid} 2>/dev/null; "
        f"for i in $(seq 1 10); do "
        f"  kill -0 {kodi_pid} 2>/dev/null || exit 0; "
        f"  sleep 1; "
        f"done; "
        f"kill -KILL {kodi_pid} 2>/dev/null"
    )
    
    # os.system 中让脚本后台完全脱离 kodi
    cmd = f"nohup sh -c '{kill_script}' >/dev/null 2>&1 &"
    os.system(cmd)

def reboot_from_nand():
    has_nand = os.path.exists("/dev/system") or os.path.exists("/dev/userdata") or os.path.exists("/dev/env")
    if not has_nand:
        notification("当前系统不支持或未检测到内部存储", sound=True)
        return
        
    log("Executing system level reboot from NAND")
    notification("正在从内部存储重启...")
    xbmc.sleep(1000)
    
    os.system("/usr/sbin/rebootfromnand")
    xbmc.executebuiltin("Reset")

def router(paramstring):
    log(f"Router called with: {paramstring}")
    if not paramstring:
        launch_t9()
        return

    # 解析路径，例如 plugin://..../?mode=play&movieid=1
    params = dict(urllib.parse.parse_qsl(paramstring.lstrip('?')))
    mode = params.get("mode")
    
    if mode == "select_playback_speed":
        select_playback_speed()
        return

    if mode == "select_audio":
        select_audio()
        return

    if mode == "populate_audio_list":
        populate_audio_list()
        return

    if mode == "open_osd_audio_list":
        open_osd_audio_list()
        return

    if mode == "set_home_background":
        image = params.get("image", "")
        set_home_background(image)
        return

    if mode == "launch_t9":
        launch_t9()
        return

    if mode == "filter_list":
        reload_param = params.get('reload')
        filter_list(reload_param)
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

    if mode == "restart_linux_kodi":
        restart_linux_kodi()
        return

    if mode == "reboot_from_nand":
        reboot_from_nand()
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


    if mode == "set_subtitle":
        index = params.get("index")
        set_subtitle(index)
        return

    if mode == "force_prev":
        force_prev()
        return

    if mode == "toggle_favourite":
        toggle_favourite()
        return

    if mode == "set_vs10_mode":
        target = params.get("target_mode")
        set_vs10_mode(target)
        return

if __name__ == "__main__":
    # sys.argv[0] 是 plugin://...; sys.argv[2] 是 '?xxx'
    # log(sys.argv)
    if HANDLE != -1 and len(sys.argv) > 2:
        router(sys.argv[2])
    elif len(sys.argv) > 1:
        router(sys.argv[1])
    else:
        router("")
