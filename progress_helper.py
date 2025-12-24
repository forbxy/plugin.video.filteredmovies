
import xbmc
import json

def get_inprogress_episodes_map():
    """
    Fetches all in-progress episodes and returns a map of {tvshowid: partial_progress_sum}.
    Partial progress for an episode is calculated as (resume_position / total_duration).
    """
    try:
        # Fetch episodes that are in progress
        # Note: "inprogress" filter might not be available in all Kodi versions, 
        # but "resume" property check is reliable if we fetch all.
        # However, fetching ALL episodes is heavy.
        # Let's try to filter by playcount=0 (unwatched) AND lastplayed (started) if possible,
        # or use the "inprogress" field if available (Kodi 18+).
        
        # Using "inprogress" filter
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
                # Cap at 0.99 to avoid counting as full episode (which should be handled by watchedepisodes)
                if fraction > 0.99: fraction = 0.99
                
                progress_map[tvshow_id] = progress_map.get(tvshow_id, 0.0) + fraction
                
        return progress_map
        
    except Exception as e:
        xbmc.log(f"[moviefilter] Error fetching in-progress episodes: {e}", xbmc.LOGERROR)
        return {}
