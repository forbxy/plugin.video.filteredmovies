import xbmc
import urllib.parse

if __name__ == '__main__':
    fanart = xbmc.getInfoLabel('ListItem.Art(fanart)')
    # 构造 default.py 的参数
    # 我们使用 default.py 路由期望的 ?mode=... 格式
    args = f"?mode=set_home_background&image={urllib.parse.quote(fanart)}"
    
    # 使用这些参数运行 default.py
    # 注意：我们使用 special://home/... 以确保绝对路径
    script_path = "special://home/addons/plugin.video.filteredmovies/default.py"
    xbmc.executebuiltin(f'RunScript({script_path}, {args})')
