# -*- coding: utf-8 -*-
from common import get_skin_name
import xbmc
import xbmcgui
import xbmcvfs
import json
import os
import time
import traceback
import threading

ADDON_ID = 'plugin.video.filteredmovies'
ADDON_PATH = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/")
ADDON_DATA_PATH = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
if not os.path.exists(ADDON_DATA_PATH):
    os.makedirs(ADDON_DATA_PATH)

SKIP_DATA_FILE = os.path.join(ADDON_DATA_PATH, 'skip_intro_data.json')

def log(msg):
    xbmc.log(f"[FilteredMoviesService] {msg}", xbmc.LOGINFO)

def warmup_xml_cache():
    try:
        # 预读取 XML 文件以利用文件系统缓存
        xml_dir = os.path.join(ADDON_PATH, 'resources', 'skins', 'Default', '1080i')
        target_files = ['Custom_5111_MovieFilter.xml', 'Custom_5111_MovieFilter_Horizon.xml']
        
        for f_name in target_files:
            f_path = os.path.join(xml_dir, f_name)
            if os.path.exists(f_path):
                with open(f_path, 'rb') as f:
                    _ = f.read()
                log(f"Warmed up cache for {f_name}")
    except Exception as e:
        log(f"-----Error warming up XML cache: {e}")

def load_skip_data():
    if not os.path.exists(SKIP_DATA_FILE):
        return {}
    try:
        with open(SKIP_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"Error loading skip data: {e}")
        return {}

def get_current_tvshow_info():
    try:
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
            
            if tvshow_id and tvshow_id != -1:
                return str(tvshow_id), show_title, str(season)
    except Exception as e:
        log(f"Error getting TV show info: {e}")
    return None, None, None

class PlayerMonitor(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)
        self.current_outro_time = None
        self.outro_triggered = False
        self.outro_countdown_start = None
        self.cancel_skip = False

    def onAVStarted(self):
        # 视频开始播放（包括切集）时触发
        # 稍微延迟一下，确保元数据已加载
        xbmc.sleep(1000)
        
        self.check_intro()
        self.update_outro_info()
        self.load_iso_subtitles()

    def update_outro_info(self):
        self.current_outro_time = None
        self.outro_triggered = False
        self.outro_countdown_start = None
        self.cancel_skip = False
        
        if not self.isPlayingVideo():
            return

        tvshow_id, show_title, season = get_current_tvshow_info()
        if not tvshow_id: return

        data = load_skip_data()
        if tvshow_id not in data: return
        
        record = data[tvshow_id]
        if "seasons" in record and season in record["seasons"]:
            s_data = record["seasons"][season]
            if isinstance(s_data, dict):
                # 获取片尾时长
                outro_duration = s_data.get("outro")
                if outro_duration:
                    try:
                        total_time = self.getTotalTime()
                        if total_time > 0:
                            # 计算触发时间点 = 总时长 - 片尾时长
                            self.current_outro_time = total_time - outro_duration
                            log(f"Outro skip set for {show_title} S{season}. Duration: {outro_duration}, Trigger at: {self.current_outro_time}")
                    except Exception as e:
                        log(f"Error calculating outro trigger: {e}")

    def check_intro(self):
        if not self.isPlayingVideo():
            return

        tvshow_id, show_title, season = get_current_tvshow_info()
        if not tvshow_id:
            return

        data = load_skip_data()
        if tvshow_id not in data:
            return

        record = data[tvshow_id]
        skip_time = 0
        
        if "seasons" in record and season in record["seasons"]:
            val = record["seasons"][season]
            if isinstance(val, dict):
                skip_time = val.get("intro", 0)
            else:
                skip_time = val
        elif "time" in record:
            skip_time = record["time"]
            
        if skip_time > 0:
            try:
                current_time = self.getTime()
                # 如果当前时间小于跳过点（说明在片头范围内），则执行跳过
                if current_time < skip_time:
                    log(f"Auto skipping intro for {show_title} S{season}. Current: {current_time}, Target: {skip_time}")
                    self.seekTime(skip_time)
                    xbmc.executebuiltin(f'Notification(FilteredMovies, 自动跳过片头 已跳转至 {int(skip_time)}秒, 2000, {os.path.join(ADDON_PATH, "icon.png")})')
            except Exception as e:
                log(f"Error during skip: {e}")

    def load_iso_subtitles(self):
        log("Checking for ISO subtitles...")
        try:
            if not self.isPlayingVideo():
                log("Not playing video, skipping ISO subtitle check.")
                return
            
            # Try to get the file path from Player.GetItem
            json_query = {
                "jsonrpc": "2.0",
                "method": "Player.GetItem",
                "params": {
                    "properties": ["file"],
                    "playerid": 1
                },
                "id": "Player.GetItem"
            }
            json_response = xbmc.executeJSONRPC(json.dumps(json_query))
            response = json.loads(json_response)
            
            playing_file = None
            if 'result' in response and 'item' in response['result']:
                item_file = response['result']['item'].get('file')
                if item_file:
                    log(f"Player.GetItem returned file: {item_file}")
                    playing_file = item_file

            if not playing_file:
                 log("No playing file found via JSONRPC, skipping ISO subtitle check.")
                 return

            # Strip query parameters if any
            if '?' in playing_file:
                playing_file = playing_file.split('?')[0]
            
            # Check if it's an ISO file
            if not playing_file.lower().endswith('.iso'):
                # log(f"Not an ISO file {playing_file}, skipping ISO subtitle check.")
                return
                
            log(f"ISO file detected: {playing_file}, checking for external subtitles...")
            
            # Get directory and base name
            # Normalize path separators
            playing_file = playing_file.replace('\\', '/')
            last_sep_idx = playing_file.rfind('/')
            
            if last_sep_idx == -1:
                return
                
            dir_path = playing_file[:last_sep_idx + 1]
            file_name = playing_file[last_sep_idx + 1:]
            base_name = file_name[:-4] # remove .iso
            
            # Common subtitle extensions
            sub_exts = ['.srt', '.ass', '.ssa', '.sub', '.smi', '.vtt']
            
            # List directory contents
            dirs, files = xbmcvfs.listdir(dir_path)
            
            # Find matching subtitles
            subtitles_to_load = []
            for f in files:
                f_lower = f.lower()
                base_lower = base_name.lower()
                if any(f_lower.endswith(ext) for ext in sub_exts):
                    if f_lower.startswith(base_lower):
                        remainder = f_lower[len(base_lower):]
                        # Check strict matching (either exact match + ext, or followed by separator)
                        # e.g. movie.srt, movie.en.srt, movie_en.srt
                        if remainder in sub_exts or remainder.startswith('.') or remainder.startswith('-') or remainder.startswith('_'):
                            sub_path = dir_path + f
                            subtitles_to_load.append(sub_path)
            
            # Sort subtitles to have deterministic loading order
            subtitles_to_load.sort()
            
            if subtitles_to_load:
                log(f"Found {len(subtitles_to_load)} external subtitles for ISO: {subtitles_to_load}")
                for sub in subtitles_to_load:
                    self.setSubtitles(sub)
                    log(f"Loaded subtitle: {sub}")
        except Exception as e:
            log(f"Error loading ISO subtitles: {e}")

class SkipCountdownWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        self.cancelled = False
        self.is_ready = False
        
    def onInit(self):
        self.is_ready = True
        
    def onAction(self, action):
        action_id = action.getId()
        # 10: ACTION_PREVIOUS_MENU, 92: ACTION_NAV_BACK
        if action_id in [10, 92]:
            self.cancelled = True
            self.close()
        # 转发常用播放控制按键 (避免被模态窗口拦截)
        elif action_id in [1, 15]: # Left, StepBack
            xbmc.executebuiltin("PlayerControl(SmallSkipBackward)")
        elif action_id in [2, 14]: # Right, StepForward
            xbmc.executebuiltin("PlayerControl(SmallSkipForward)")
        elif action_id in [3, 20]: # Up, BigStepForward
            xbmc.executebuiltin("PlayerControl(BigSkipForward)")
        elif action_id in [4, 21]: # Down, BigStepBack
            xbmc.executebuiltin("PlayerControl(BigSkipBackward)")
        elif action_id == 7: # Select/Enter -> OSD
            xbmc.executebuiltin("ActivateWindow(VideoOSD)")
        elif action_id == 77: # PlayerForward
            xbmc.executebuiltin("PlayerControl(Forward)")
        elif action_id == 78: # PlayerRewind
            xbmc.executebuiltin("PlayerControl(Rewind)")
        elif action_id == 12: # Pause/Play
             xbmc.executebuiltin("PlayerControl(Play)")
            
    def update_text(self, text):
        if not self.is_ready: return
        try:
            # 确保控件存在
            ctrl = self.getControl(100)
            if ctrl:
                ctrl.setLabel(text)
        except:
            pass

def init_skin_properties():
    # Skin detection logic
    skin_name = get_skin_name()
    # 1. Set Rounded Posters Property
    if skin_name in ["horizon", "fuse", "zephyr"]:
        xbmc.executebuiltin('SetProperty(MFG.UseRounded,true,home)')
    else:
        xbmc.executebuiltin('ClearProperty(MFG.UseRounded,home)')

    # 2. Set Progress Bar Color Property
    if skin_name == "estuary":
            xbmc.executebuiltin('SetProperty(MFG.ProgressBarColor,button_focus,home)')
            xbmc.executebuiltin('SetProperty(MFG.FocusColor,button_focus,home)')
            xbmc.executebuiltin('ClearProperty(MFG.CenterWindow,home)')
    else:
            xbmc.executebuiltin('SetProperty(MFG.ProgressBarColor,FF0097E1,home)')
            xbmc.executebuiltin('SetProperty(MFG.FocusColor,FF0097E1,home)')
            xbmc.executebuiltin('SetProperty(MFG.CenterWindow,true,home)')
    
    # 3. Initialize Return Targets for Navigation Memory
    # UP Targets (Default Down)
    xbmc.executebuiltin('SetProperty(Return_1013,6001,home)')
    xbmc.executebuiltin('SetProperty(Return_6004,2005,home)')
    xbmc.executebuiltin('SetProperty(Return_6006,2007,home)')
    xbmc.executebuiltin('SetProperty(Return_4003,5003,home)')
    xbmc.executebuiltin('SetProperty(Return_4004,5005,home)')
    xbmc.executebuiltin('SetProperty(Return_3004,2005,home)')
    xbmc.executebuiltin('SetProperty(Return_Key6,6001,home)')
    xbmc.executebuiltin('SetProperty(Return_KeyClr,4001,home)')
    
    # DOWN Targets (Default Up)
    xbmc.executebuiltin('SetProperty(Return_4005,3006,home)')
    xbmc.executebuiltin('SetProperty(Return_4007,3008,home)')
    xbmc.executebuiltin('SetProperty(Return_4010,3012,home)')

if __name__ == '__main__':
    log("Service started")
    
    # Start prefetch thread
    threading.Thread(target=warmup_xml_cache).start()

    init_skin_properties()
    monitor = xbmc.Monitor()
    player = PlayerMonitor()
    
    countdown_window = None
    countdown_thread = None
    
    # 倒计时状态
    countdown_active = False
    countdown_remaining = 0.0
    last_tick_time = time.time()
    
    # 记录上一次的皮肤 ID，用于检测皮肤切换
    last_skin = get_skin_name()

    while not monitor.abortRequested():
        # 1. 检测皮肤切换
        current_skin = get_skin_name()
        if current_skin != last_skin:
            log(f"Skin changed from {last_skin} to {current_skin}. Re-initializing properties.")
            last_skin = current_skin
            init_skin_properties()

        current_tick_time = time.time()
        dt = current_tick_time - last_tick_time
        last_tick_time = current_tick_time
        
        # 检查是否需要重新加载数据
        if xbmcgui.Window(10000).getProperty("MFG.Reload") == "true":
            xbmcgui.Window(10000).clearProperty("MFG.Reload")
            log("Reload signal received, updating info...")
            player.update_outro_info()
            # 重置倒计时状态
            countdown_active = False
            
        # 检查片尾跳过
        if player.isPlayingVideo() and player.current_outro_time:
            try:
                current_time = player.getTime()
                trigger_time = player.current_outro_time
                # 设定触发范围起点 (提前6秒)
                start_threshold = trigger_time - 6
                
                if current_time < start_threshold:
                    # 在片尾范围之前：重置所有状态，允许再次触发
                    if player.cancel_skip: 
                        player.cancel_skip = False
                    # if player.outro_triggered: 
                    #     player.outro_triggered = False
                    
                    if countdown_active:
                        countdown_active = False
                        log("Playback time before outro range. Resetting countdown.")
                    
                    if countdown_window:
                        countdown_window.close()
                        if countdown_thread: countdown_thread.join()
                        countdown_window = None
                        countdown_thread = None

                elif not player.outro_triggered and not player.cancel_skip:
                    # 检查冷却时间 (防止重复触发)


                    # 在片尾范围内，且未触发/未取消：执行倒计时
                    
                    # 如果倒计时未激活，则初始化
                    if not countdown_active:
                        countdown_active = True
                        countdown_remaining = 6.0
                        log(f"Entered outro range. Starting countdown: {countdown_remaining}s")
                    
                    # 如果未暂停，则递减倒计时
                    if not xbmc.getCondVisibility("Player.Paused"):
                        countdown_remaining -= dt
                    
                    # 初始化倒计时窗口
                    if not countdown_window:
                        countdown_window = SkipCountdownWindow("notification_overlay.xml", ADDON_PATH)
                        # 在新线程中显示窗口，以免阻塞主循环
                        countdown_thread = threading.Thread(target=countdown_window.doModal)
                        countdown_thread.start()
                    
                    # 更新提示文字
                    display_seconds = int(countdown_remaining) + 1 # 向上取整显示
                    countdown_window.update_text(f"即将跳过片尾... {display_seconds}秒 (按返回取消)")
                    
                    # 检查是否被用户取消
                    if countdown_window.cancelled:
                        player.cancel_skip = True
                        xbmc.executebuiltin(f'Notification(FilteredMovies, 自动跳过片尾 已取消, 1000, {os.path.join(ADDON_PATH, "icon.png")})')
                        # 清理窗口
                        if countdown_thread and countdown_thread.is_alive():
                            countdown_thread.join()
                        countdown_window = None
                        countdown_thread = None
                        countdown_active = False
                        continue

                    # 倒计时结束，触发跳过
                    if countdown_remaining <= 0:
                        player.outro_triggered = True
                        log("Countdown finished. Auto skipping outro -> Next episode")
                        
                        # 关闭窗口
                        if countdown_window:
                            countdown_window.close()
                            if countdown_thread and countdown_thread.is_alive():
                                countdown_thread.join()
                            countdown_window = None
                            countdown_thread = None
                            
                        xbmc.executebuiltin("PlayerControl(Next)")
                        countdown_active = False

            except Exception as e:
                log(f"Error checking outro: {e}")
                log(traceback.format_exc())
                # 出错时清理窗口
                if countdown_window:
                    countdown_window.close()
                    countdown_window = None
                countdown_active = False
        else:
            # 不满足跳过条件（如暂停、停止、已跳过、已取消），清理窗口
            if countdown_window:
                countdown_window.close()
                if countdown_thread: countdown_thread.join()
                countdown_window = None
                countdown_thread = None
            countdown_active = False
        
        if monitor.waitForAbort(0.3):
            break
