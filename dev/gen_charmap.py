# -*- coding: utf-8 -*-
import json
import time

# 尝试导入 pypinyin，如果没有则提示
try:
    from pypinyin import pinyin, Style
except ImportError:
    print("请先安装 pypinyin 库: pip install pypinyin")
    exit()

# 使用《通用规范汉字字典》(kTGHZ2013) 的拼音数据覆盖 pypinyin 默认数据
# 2013版官方标准，多音字比 kXHC1983 更精简，去掉了部分古音/罕用读音
try:
    from pypinyin_dict.pinyin_data import ktghz2013
    ktghz2013.load()
    print("已加载《通用规范汉字字典》拼音数据")
except ImportError:
    print("警告: 未安装 pypinyin-dict，将使用 pypinyin 默认拼音数据（包含非标准读音）")
    print("安装方法: pip install pypinyin-dict")

def generate_char_map():
    """
    生成 汉字 -> 拼音全拼列表 的映射字典
    结构: {"阿": ["a", "e"], "重": ["chong", "zhong"], "0": "0", ...}
    汉字值为全拼列表(支持多音字)，数字值为字符串
    """
    print("正在生成汉字映射表，这可能需要几秒钟...")
    start_time = time.time()
    
    char_map = {}
    
    # 1. 基础数字映射 (0-9 -> 0-9)
    for i in range(10):
        char_map[str(i)] = str(i)
    
    # 2. 遍历常用汉字 (CJK Unified Ideographs)
    # 范围 0x4E00 - 0x9FA5 覆盖了绝大多数常用字
    for codepoint in range(0x4E00, 0x9FA6):
        char = chr(codepoint)
        
        # 获取全拼 (Style.NORMAL: 不带声调, heteronym=True: 启用多音字)
        try:
            py_list = pinyin(char, style=Style.NORMAL, heteronym=True, errors='ignore')
            if py_list and py_list[0]:
                # py_list[0] 是一个包含该字所有读音的列表，例如 ['zhong', 'chong']
                readings = py_list[0]
                
                # 过滤非字符串和空值，并去重
                valid_readings = []
                seen = set()
                for r in readings:
                    if r and isinstance(r, str) and r not in seen:
                        valid_readings.append(r)
                        seen.add(r)
                
                if valid_readings:
                    char_map[char] = valid_readings
                    
        except Exception:
            continue

    end_time = time.time()
    print(f"生成完成！共处理 {len(char_map)} 个字符，耗时 {end_time - start_time:.2f} 秒。")
    return char_map

if __name__ == "__main__":
    # 1. 生成数据
    dictionary = generate_char_map()
    
    # 2. 保存到文件 (使用紧凑格式，减小文件体积)
    output_file = "resources/char_map.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, separators=(',', ':'))
        
    print(f"字典已保存到 {output_file}")
    
