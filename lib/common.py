import os
import json
import traceback
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON_ID = 'plugin.video.filteredmovies'
ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/")
ADDON_DATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")


def get_addon(addon_id=ADDON_ID):
    if addon_id:
        return xbmcaddon.Addon(id=addon_id)
    return xbmcaddon.Addon()


def get_setting(setting_id, addon_id=ADDON_ID):
    return get_addon(addon_id).getSetting(setting_id)


def jsonrpc_request(payload):
    """执行 JSON-RPC 请求。单请求返回 result，批量请求返回 list，失败返回 None。"""
    try:
        request_text = payload if isinstance(payload, str) else json.dumps(payload)
        response_text = xbmc.executeJSONRPC(request_text)
        response = json.loads(response_text)

        if isinstance(response, dict) and "error" in response:
            method = "JSON-RPC"
            if isinstance(payload, dict):
                method = payload.get("method") or method
            log(f"JSON-RPC error for {method}: {response.get('error')}", xbmc.LOGWARNING)
            return None

        # 对单请求返回 result，保留批量请求原始返回。
        if isinstance(payload, dict):
            return response.get("result") if isinstance(response, dict) else response
        return response
    except Exception as e:
        log(f"JSON-RPC call failed for {payload}: {e}", xbmc.LOGERROR)
        log(traceback.format_exc(), xbmc.LOGERROR)
        return None

def get_skin_name():
    # Skin detection logic
    current_skin_id = xbmc.getSkinDir().lower()
    
    skin_name = "other"
    if "horizon" in current_skin_id:
        skin_name = "horizon"
    elif "fuse" in current_skin_id:
        skin_name = "fuse"
    elif "estuary" in current_skin_id:
        skin_name = "estuary"
    elif "zephyr" in current_skin_id:
        skin_name = "zephyr"
    elif "minsk" in current_skin_id:
        skin_name = "minsk"
        
    return skin_name

def get_icon_path():
    return os.path.join(ADDON_PATH, "icon.png")

def notification(message, title="FilteredMovies", duration=1000, sound=False):
    xbmcgui.Dialog().notification(title, message, get_icon_path(), duration, sound)
    
def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)