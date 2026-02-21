# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import time
import threading
import queue
import json
import base64
import t9_helper

# 定义 Skin String 值到按钮 ID 的映射
# 格式: { 'SkinStringName': { 'Value': ButtonID, 'Default': ButtonID } }
FILTER_MAP = {
    'filter.sort': {
        'mapping': {
            '最新入库': 1013,
            '最近观看': 1015,
            '随机': 1014,
            '最新上线': 1011,
            '影片评分': 1012
        },
        'default': 1011 # 最新上线
    },
    'filter.mediatype': {
        'mapping': {
            '电影': 6002,
            '系列电影': 6003,
            '剧集': 6004,
            '演唱会': 6005,
            '纪录片': 6006
        },
        'default': 6001 # 全部
    },
    'filter.genre': {
        'mapping': {
            '动作': 2002,
            '喜剧': 2003,
            '爱情': 2004,
            '科幻': 2005,
            '犯罪': 2006,
            '冒险': 2007,
            '剧情': 2014,
            '恐怖': 2008,
            '动画': 2009,
            '战争': 2010,
            '悬疑': 2011,
            '历史': 2012,
            '音乐': 2013,
            '其他': 2015
        },
        'default': 2001 # 类型
    },
    'filter.region': {
        'mapping': {
            '内地': 3002,
            '中国香港': 3003,
            '中国台湾': 3004,
            '美国': 3005,
            '日本': 3006,
            '韩国': 3007,
            '泰国': 3008,
            '印度': 3009,
            '英国': 3010,
            '法国': 3011,
            '德国': 3012,
            '俄罗斯': 3014,
            '加拿大': 3015,
            '其他': 3013
        },
        'default': 3001 # 地区
    },
    'filter.year': {
        'mapping': {
            '今年': 4002,
            '2020年代': 4003,
            '2010年代': 4004,
            '2000年代': 4005,
            '90年代': 4006,
            '80年代': 4007,
            '70年代': 4008,
            '60年代': 4009,
            '更早': 4010
        },
        'default': 4001 # 年份
    },
    'filter.rating': {
        'mapping': {
            '10-9': 5002,
            '9-8': 5003,
            '8-7': 5004,
            '7-6': 5005,
            '6分以下': 5006
        },
        'default': 5001 # 评分
    }
}

# 构建 ID -> (组, 值) 的反向查找映射
FILTER_ID_TO_INFO_MAP = {}
for group, data in FILTER_MAP.items():
    # 默认按钮
    FILTER_ID_TO_INFO_MAP[data['default']] = (group, '')
    # 映射按钮
    for val, btn_id in data['mapping'].items():
        FILTER_ID_TO_INFO_MAP[btn_id] = (group, val)

class FilterWindow(xbmcgui.WindowXML):
    @classmethod
    def log(cls, msg):
        xbmc.log(f"[FilterWindow] {msg}", xbmc.LOGINFO)
    
    def _set_button_state(self, btn_id, is_selected):
        color_val = 'FFEB9E17' if is_selected else 'FFFFFFFF'
        xbmcgui.Window(10000).setProperty(f'MFG.FilterColor.{btn_id}', color_val)

    def _load_state_from_skin(self):

        self.filter_state = {}
        
        # 尝试先从单个 blob 加载
        blob = xbmc.getInfoLabel('Skin.String(MFG.State)')
        if blob:
            try:
                decoded = base64.b64decode(blob).decode('utf-8')
                loaded_state = json.loads(decoded)
                
                self.filter_state = loaded_state
                # self.log(f"Loaded state: {len(self.filter_state)} keys")
                return
            except Exception as e:
                self.log(f"Error loading state blob: {e}")
        
        # 使用默认值初始化 (ID + 值)
        for group, data in FILTER_MAP.items():
            default_id = data['default']
            _, default_val = FILTER_ID_TO_INFO_MAP[default_id]
            default_obj = {'id': default_id, 'value': default_val}
            
            if group == 'filter.rating':
                self.filter_state[group] = [default_obj]
            else:
                self.filter_state[group] = default_obj

    def _save_state_to_skin(self):
        try:
            # 序列化为 JSON 和 Base64
            json_str = json.dumps(self.filter_state)
            encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            # 保存到单个 Skin String
            xbmc.executebuiltin(f'Skin.SetString(MFG.State,{encoded})')
            self.log("Saved state to Skin.String(MFG.State)")
        except Exception as e:
            self.log(f"Error saving state: {e}")

    def update_highlights(self, target_group=None):
        """
        根据 self.filter_state 设置窗口属性以高亮显示活动按钮。
        如果提供了 target_group，则仅更新该组。
        """
        groups = [target_group] if target_group else self.filter_state.keys()

        for group in groups:
            state = self.filter_state.get(group)
            if state is None: continue

            data = FILTER_MAP.get(group)
            if not data: continue
            
            # 收集该组的所有 ID 以便先重置它们（或仅设置正确的状态）
            all_ids = list(data['mapping'].values())
            all_ids.append(data['default'])
            
            if isinstance(state, list): # 多选 (评分)
                active_ids = [x['id'] for x in state]
                for btn_id in all_ids:
                    self._set_button_state(btn_id, btn_id in active_ids)
            else: # 单选
                active_id = state['id']
                for btn_id in all_ids:
                    self._set_button_state(btn_id, btn_id == active_id)

    def onInit(self):
        # Set property to indicate window is open
        # Clear T9 input
        self.setProperty("t9_input", "")
        xbmcgui.Window(10000).setProperty("MFG.T9Open", "true")
        
        # Load state from Skin into Python memory
        self._load_state_from_skin()
        
        # 立即初始化筛选高亮
        self.update_highlights()
        
        # 初始化属性，确保非空
        xbmcgui.Window(10000).setProperty("MFG.T9Input", "")
        
        # self.refresh_container()

        self.input_queue = queue.Queue()
        self.running = True
        self.worker = threading.Thread(target=self._t9_input_worker)
        self.worker.daemon = True
        self.worker.start()
        
        self.log(f"onInit complete")

    def _t9_input_worker(self):
        # 初始状态为阻塞等待，避免空转
        empty_trigger = True
        monitor = xbmc.Monitor()
        last_input = ""
        last_refresh_time = 0
        while self.running:
            # 检查 Kodi 是否正在关闭
            if monitor.abortRequested():
                self.log("Abort requested, closing window")
                self.close()
                break

            try:
                events = []
                try:
                    # 如果有待刷新任务，需要超时来检查是否到了刷新时间
                    # 如果没有任务，可以无限阻塞等待用户输入，完全不消耗CPU
                    # 改为 1.0s 超时以便检查 abortRequested
                    timeout = 1.0 if empty_trigger else 0.2
                    # 阻塞等待第一个事件
                    events.append(self.input_queue.get(timeout=timeout))
                    # 收到事件后，进入去抖动模式（非阻塞/短超时）
                    empty_trigger = False
                    # 只要队列不为空，就一次性取出所有积压事件
                    while not self.input_queue.empty():
                        try:
                            events.append(self.input_queue.get_nowait())
                        except queue.Empty:
                            break
                except queue.Empty:
                    # 超时未收到新事件，说明输入间歇，标记为可阻塞状态
                    empty_trigger = True
                
                current_input = xbmcgui.Window(10000).getProperty("MFG.T9Input") or ""
                # current_input = last_input
                # 批量处理所有事件
                for event in events:
                    if not event: 
                        continue
                    etype, evalue = event
                    if etype == 'input':
                        current_input += evalue
                    elif etype == 'delete':
                        current_input = current_input[:-1] if current_input else ""
                    elif etype == 'clear':
                        # 清空输入立即响应
                        current_input = ""
                    elif etype == 'close':
                        self.log("close worker")
                        return
                if events:
                    xbmcgui.Window(10000).setProperty("MFG.T9Input", current_input)
                # self.log(f"{time.time()} {current_input} {last_input} {events}")

                if current_input == "9527007":
                    t9_helper.helper.rebuild_cache()
                    xbmcgui.Dialog().notification("Filtered Movies", "已重建 T9 缓存...", xbmcgui.NOTIFICATION_WARNING, 1000)
                    xbmc.log("[FilterWindow] Magic code 9527007 detected. Rebuilding T9 cache.", xbmc.LOGWARNING)
                    current_input = ""
                    xbmcgui.Window(10000).setProperty("MFG.T9Input", current_input)

                if current_input != last_input:
                    if not current_input:
                        # 输入已清空，立即刷新列表
                        self.refresh_container()
                        last_refresh_time = time.time()
                    if len(current_input) > 2 and (time.time() - last_refresh_time > 0.2):
                        self.refresh_container()
                        last_refresh_time = time.time()
                    if not events:
                        last_input = current_input
                
            except Exception as e:
                self.log(f"Worker error: {e}")

    def cleanup(self):
        self.running = False
        if hasattr(self, 'input_queue'):
            self.input_queue.put(('close', None))
        if hasattr(self, 'worker') and self.worker.is_alive():
            self.worker.join(timeout=1.0)
        self._save_state_to_skin()
        
        # 清除全局属性
        xbmcgui.Window(10000).clearProperty("MFG.T9Input")
        xbmcgui.Window(10000).setProperty("MFG.T9LastClose", str(time.time()))

    def onAction(self, action):
        action_id = action.getId()
        button_code = action.getButtonCode()
        self.log(f"onAction: ID={action_id} ButtonCode={button_code}")
        
        # 关闭/返回/ESC等必须立即处理的按键
        if action_id in [10, 122]:  # ESC, HOME
            self.close()
            return
        if action_id == 92:  # NavBack
            # 有输入情况输入，没有输入退出页面
            current_text = xbmcgui.Window(10000).getProperty("MFG.T9Input")
            if current_text and len(current_text) > 0:
                self.input_queue.put(('clear', None))
            else:
                self.close()
            return

        # 其他输入全部交给worker
        if 58 <= action_id <= 67:  # 0-9
            self.input_queue.put(('input', str(action_id - 58)))
            return
        if action_id in [110, 112, 80]:  # Backspace, Delete, ItemDelete
            self.input_queue.put(('delete', None))
            return
        if action_id == 13:  # Stop/清空
            self.input_queue.put(('clear', None))
            return

        pass
    
    def _handle_filter_click(self, controlId):
        # 检查 controlId 是否为已知的筛选按钮
        if controlId not in FILTER_ID_TO_INFO_MAP:
            return False
            
        group, val = FILTER_ID_TO_INFO_MAP[controlId]
        click_obj = {'id': controlId, 'value': val}
        
        # 处理评分筛选 (多选逻辑)
        if group == 'filter.rating':
            current_list = self.filter_state.get(group, [])
            default_id = FILTER_MAP[group]['default']
            
            # 检查当前点击的项是否已选中
            exists = False
            for x in current_list:
                if x['id'] == controlId:
                    exists = True
                    break
            
            if controlId == default_id:
                # 点击默认项（如"全部"），清空其他选项并只选中默认项
                _, def_val = FILTER_ID_TO_INFO_MAP[default_id]
                new_list = [{'id': default_id, 'value': def_val}]
            else:
                # 切换逻辑：如果已存在则移除，否则添加
                if exists:
                    new_list = [x for x in current_list if x['id'] != controlId]
                else:
                    new_list = current_list + [click_obj]
                
                # 如果选中了其他项，移除默认项
                has_default = any(x['id'] == default_id for x in new_list)
                if has_default and len(new_list) > 1:
                    new_list = [x for x in new_list if x['id'] != default_id]
                
                # 如果列表为空（取消了所有选择），自动选中默认项
                if not new_list:
                    _, def_val = FILTER_ID_TO_INFO_MAP[default_id]
                    new_list = [{'id': default_id, 'value': def_val}]
            
            self.filter_state[group] = new_list
            
            # 更新评分组所有按钮的UI状态
            # (因为多选会改变多个按钮的状态)
            self.update_highlights(group) # 优化为只更新该组
            
        else:
            # 单选逻辑 (其他筛选组)
            old_obj = self.filter_state.get(group)
            if old_obj and old_obj['id'] == controlId:
                return True # 点击已选中的项，无变化
            
            self.filter_state[group] = click_obj
            
            # 增量更新UI：取消旧的高亮，高亮新的
            if old_obj:
                self._set_button_state(old_obj['id'], False)
            self._set_button_state(controlId, True)
            
        self.refresh_container()
        return True

    def onClick(self, controlId):
        
        # 检查是否为筛选按钮 (ID 1000-6999，排除 T9 组 6000/6050)
        if 1000 <= controlId <= 6999:
            if self._handle_filter_click(controlId):
                return
            
            # 稍微延迟一点，以便 Skin.SetString (来自 XML onclick) 完成
            xbmc.sleep(50) 
            # self.update_highlights()
            # 触发容器刷新以更新列表
            self.refresh_container()

    
    def refresh_container(self, state=None):
        # 更新 ReloadID 以触发 XML 中的 content 刷新
        self.log("Refreshing container via ReloadID")
        # 触发刷新动画 (Fade Out)
        xbmcgui.Window(10000).setProperty("MFG.IsRefreshing", "true")
         # 等待淡出动画完成

        # 保存当前状态到 Skin，以便 default.py 读取
        self._save_state_to_skin()
        
        # 更新 ReloadID
        import time
        reload_id = str(time.time())
        xbmcgui.Window(10000).setProperty("MFG.ReloadID", "clear_" + reload_id)
        xbmc.sleep(100)
        reload_id = str(time.time())
        xbmcgui.Window(10000).setProperty("MFG.ReloadID", reload_id)


class DialogSelectWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, strXMLname, strFallbackPath, strDefaultName, forceFallback=0):
        super(DialogSelectWindow, self).__init__(strXMLname, strFallbackPath, strDefaultName, forceFallback)
        self.items = []
        self.selected_index = -1
        self.callback = None

    def setItems(self, items):
        self.items = items
        
    def setCallback(self, callback):
        self.callback = callback

    def onInit(self):
        self.list_control = self.getControl(100)
        focus_index = 0
        for i, item in enumerate(self.items):
            # item: {"label": "...", "index": ..., "is_active": bool}
            li = xbmcgui.ListItem(label=item["label"])
            if item["is_active"]:
                li.setProperty("IsActive", "true")
                focus_index = i
            self.list_control.addItem(li)
        
        # 将焦点设置到活动项
        self.list_control.selectItem(focus_index)
        self.setFocus(self.list_control)

    def onClick(self, controlId):
        if controlId == 100:
            self.selected_index = self.list_control.getSelectedPosition()
            if self.callback and self.selected_index >= 0 and self.selected_index < len(self.items):
                self.callback(self.items[self.selected_index])
            self.close()

    def onAction(self, action):
        # 允许的操作：方向键(1-4)，翻页(5-6)，确认(7)
        # 鼠标操作：100-107
        if action.getId() in [1, 2, 3, 4, 5, 6, 7] or (100 <= action.getId() <= 107):
            return
        self.close()

class OSDListWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, strXMLname, strFallbackPath, strDefaultName, forceFallback=0):
        super(OSDListWindow, self).__init__(strXMLname, strFallbackPath, strDefaultName, forceFallback)
        self.items = []
        self.callback = None

    def setItems(self, items):
        self.items = items
        
    def setCallback(self, callback):
        self.callback = callback

    def onInit(self):
        self.list_control = self.getControl(80000)
        focus_index = 0
        for i, item in enumerate(self.items):
            li = xbmcgui.ListItem(label=item["label"])
            if item["is_active"]:
                li.setProperty("IsActive", "true")
                focus_index = i
            self.list_control.addItem(li)
        
        self.list_control.selectItem(focus_index)
        self.setFocus(self.list_control)

    def onClick(self, controlId):
        if controlId == 80000:
            idx = self.list_control.getSelectedPosition()
            if self.callback and idx >= 0 and idx < len(self.items):
                self.callback(self.items[idx])
                # 不要关闭，仅更新
                self.close()
            else:
                self.close()

    def onAction(self, action):
        # 处理返回/退出键
        if action.getId() in [92, 10]:
            self.close()
        # 如果需要，传递其他动作，或者让基类处理
        super(OSDListWindow, self).onAction(action)

