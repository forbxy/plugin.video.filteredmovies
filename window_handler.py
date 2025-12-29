# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import time
import threading
import queue

class T9Window(xbmcgui.WindowXML):
    def onInit(self):
        xbmc.log("[T9Window] onInit called", xbmc.LOGINFO)
        # 初始化属性，确保非空
        if not self.getProperty("t9_input"):
             self.setProperty("t9_input", "")
        
        self.input_queue = queue.Queue()
        self.running = True
        self.worker = threading.Thread(target=self._input_worker)
        self.worker.daemon = True
        self.worker.start()

    def _input_worker(self):
        pending_refresh = False
        last_input_ts = 0
        while self.running:
            try:
                timeout = 0.05
                try:
                    event = self.input_queue.get(timeout=timeout)
                except queue.Empty:
                    event = None

                if event:
                    etype, evalue = event
                    # xbmc.log(f"[T9Window] Worker received event: {etype}, {evalue}", xbmc.LOGINFO)
                    if etype == 'input':
                        self._do_append(evalue)
                        last_input_ts = time.time()
                        pending_refresh = True
                    elif etype == 'delete':
                        self._do_delete()
                        last_input_ts = time.time()
                        pending_refresh = True
                    elif etype == 'clear':
                        self._do_clear()
                        self.refresh_container()
                        pending_refresh = False
                    elif etype == 'close':
                        break
                
                if pending_refresh and (time.time() - last_input_ts > 0.1):
                    self.refresh_container()
                    pending_refresh = False
                    
            except Exception as e:
                xbmc.log(f"[T9Window] Worker error: {e}", xbmc.LOGERROR)

    def _do_append(self, text):
        current = self.getProperty("t9_input") or ""
        new_text = current + text
        self.setProperty("t9_input", new_text)
        xbmc.executebuiltin(f'SetProperty(t9_input,{new_text},1111)')

    def _do_delete(self):
        current = self.getProperty("t9_input")
        if current:
            new_text = current[:-1]
            self.setProperty("t9_input", new_text)
            xbmc.executebuiltin(f'SetProperty(t9_input,{new_text},1111)')

    def _do_clear(self):
        self.setProperty("t9_input", "")
        xbmc.executebuiltin(f'SetProperty(t9_input,,1111)')

    def cleanup(self):
        self.running = False
        self.input_queue.put(('close', None))
        if self.worker.is_alive():
            self.worker.join(timeout=1.0)

    def onAction(self, action):
        action_id = action.getId()
        button_code = action.getButtonCode()
        xbmc.log(f"[T9Window] onAction: ID={action_id} ButtonCode={button_code}", xbmc.LOGINFO)
        
        # 0-9 (Remote) -> 58-67
        if 58 <= action_id <= 67:
            self.num_input(str(action_id - 58))
            return

        # 0-9 (Numpad) -> ? (Usually mapped to Number0-9 actions if configured, or just same IDs)
        # Kodi Action IDs: https://github.com/xbmc/xbmc/blob/master/xbmc/input/actions/ActionIDs.h
        # REMOTE_0 = 58
        
        # Backspace -> 110, Delete -> 112, ItemDelete -> 80
        if action_id in [110, 112, 80]:
            self.delete_input()
            return

        # NavBack -> 92
        if action_id == 92:
            current_text = self.getProperty("t9_input")
            if current_text and len(current_text) > 0:
                self.clr_input()
            else:
                self.cleanup()
                self.close()
            return

        # Stop -> 13 (Used for Clear)
        if action_id == 13:
            self.setProperty("t9_input", "")
            self.clr_input()
            return

        # 如果是 ESC(10) 或 HOME(122)，关闭窗口
        if action_id in [10, 122]:
            self.cleanup()
            self.close()
            return

        # 其他按键交给系统处理（导航等）
        # 注意：如果不返回，默认会继续处理吗？
        # 在 WindowXML 中，如果不做处理，通常需要显式调用父类或者让它自然结束
        # 但 Python API 中没有 super().onAction() 的标准用法，通常如果不拦截，Kodi 会处理导航
        pass

    def num_input(self, key):
        self.input_queue.put(('input', key))
        

    def delete_input(self):
        self.input_queue.put(('delete', None))
            

    def clr_input(self):
        self.input_queue.put(('clear', None))
    
    def refresh_container(self):
        timestamp = str(int(time.time()*1000000))
        xbmc.executebuiltin(f'SetProperty(reload_id,{timestamp},1111)')

    def onClick(self, controlId):
        # 拦截点击事件
        if controlId == 6050:
            # 获取列表控件
            try:
                list_control = self.getControl(6050)
                selected_item = list_control.getSelectedItem()
                label = selected_item.getLabel()
                
                # 根据 label 判断操作
                if label == 'Del':
                    self.delete_input()
                elif label == 'Clr':
                    self.clr_input()
                elif label.isdigit():
                    self.num_input(label)
            except:
                pass

class DialogSelectWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, strXMLname, strFallbackPath, strDefaultName, forceFallback=0):
        super(DialogSelectWindow, self).__init__(strXMLname, strFallbackPath, strDefaultName, forceFallback)
        self.items = []
        self.selected_index = -1
        self.callback = None
        self.title = "列表"

    def setItems(self, items):
        self.items = items
        
    def setTitle(self, title):
        self.title = title
        
    def setCallback(self, callback):
        self.callback = callback

    def onInit(self):
        self.setProperty("DialogTitle", self.title)
        self.list_control = self.getControl(100)
        focus_index = 0
        for i, item in enumerate(self.items):
            # item is now a dict: {"label": "...", "index": ..., "is_active": bool}
            li = xbmcgui.ListItem(label=item["label"])
            if item["is_active"]:
                li.setProperty("IsActive", "true")
                focus_index = i
            self.list_control.addItem(li)
        
        # Set focus to the active item
        self.list_control.selectItem(focus_index)
        self.setFocus(self.list_control)

    def onClick(self, controlId):
        if controlId == 100:
            self.selected_index = self.list_control.getSelectedPosition()
            if self.callback and self.selected_index >= 0 and self.selected_index < len(self.items):
                self.callback(self.items[self.selected_index])
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
                # Don't close, just update
                self.close() # Actually close to return focus to OSD button? Or stay open?
                # Standard OSD behavior: clicking usually selects and keeps menu open or closes?
                # Let's close it to be safe and return focus to the button
            else:
                self.close()

    def onAction(self, action):
        # Handle Back/Escape
        if action.getId() in [92, 10]:
            self.close()
        # Pass through other actions if needed, or let base handle
        super(OSDListWindow, self).onAction(action)

