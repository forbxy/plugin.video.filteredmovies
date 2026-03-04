import os
import xbmc
import xbmcgui
import xbmcvfs

ADDON_ID = 'plugin.video.filteredmovies'
ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/")
ADDON_DATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")

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
        
    return skin_name

def get_icon_path():
    return os.path.join(ADDON_PATH, "icon.png")

def notification(message, title="FilteredMovies", duration=1000, sound=False):
    xbmcgui.Dialog().notification(title, message, get_icon_path(), duration, sound)
    
def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)