import xbmc

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