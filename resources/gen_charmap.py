# -*- coding: utf-8 -*-
import json
import time

# 尝试导入 pypinyin，如果没有则提示
try:
    from pypinyin import pinyin, Style
except ImportError:
    print("请先安装 pypinyin 库: pip install pypinyin")
    exit()

def generate_char_map():
    """
    生成 汉字 -> 拼音首字母 的映射字典
    结构: {"阿": "A", "爸": "B", ...}
    这种结构在搜索过滤时查找速度最快 (O(1))
    """
    print("正在生成汉字映射表，这可能需要几秒钟...")
    start_time = time.time()
    
    char_map = {}
    
    # 1. 基础数字映射 (0-9 -> 0-9)
    for i in range(10):
        char_map[str(i)] = str(i)
        
    # 2. 汉字数字映射 (一 -> 1, 二 -> 2 ...)
    # 特殊处理：汉字数字既保留拼音首字母，也保留数字
    cn_digits = {
        '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
        '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
        '十': '1' 
    }
    
    # 3. 遍历常用汉字 (CJK Unified Ideographs)
    # 范围 0x4E00 - 0x9FA5 覆盖了绝大多数常用字
    count = 0
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
                    count += 1
                    
        except Exception:
            continue

    end_time = time.time()
    print(f"生成完成！共处理 {len(char_map)} 个字符，耗时 {end_time - start_time:.2f} 秒。")
    return char_map

def demo_t9_search(char_map):
    """
    演示：如何使用这个字典进行 T9 搜索 (支持多重映射)
    """
    print("\n--- T9 搜索逻辑演示 ---")
    
    # T9 键盘映射表
    t9_map = {
        'A': '2', 'B': '2', 'C': '2',
        'D': '3', 'E': '3', 'F': '3',
        'G': '4', 'H': '4', 'I': '4',
        'J': '5', 'K': '5', 'L': '5',
        'M': '6', 'N': '6', 'O': '6',
        'P': '7', 'Q': '7', 'R': '7', 'S': '7',
        'T': '8', 'U': '8', 'V': '8',
        'W': '9', 'X': '9', 'Y': '9', 'Z': '9',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
    }

    # 辅助函数：将字符映射值转换为可能的 T9 数字集合
    def get_t9_digits(char_val):
        digits = set()
        for c in char_val:
            if c in t9_map:
                digits.add(t9_map[c])
        return digits

    test_cases = [
        ("一路向西", "15"), # 应该匹配 (一->1)
        ("一路向西", "95"), # 应该匹配 (一->Y->9)
        ("阿凡达", "23")
    ]

    for movie_title, user_input in test_cases:
        print(f"\n电影: {movie_title}, 输入: {user_input}")
        
        # 1. 将标题转换为 T9 数字集合序列
        # 结果结构: [{'9', '1'}, {'5'}, {'9'}, {'9'}]
        title_t9_seq = []
        for char in movie_title:
            val = char_map.get(char, char) # 获取映射值 (如 "Y1")
            digits = get_t9_digits(val)    # 转换为 T9 数字集合 (如 {'9', '1'})
            if not digits:
                # 如果没有映射，尝试直接转换字符本身
                digits = get_t9_digits(char.upper())
            if digits:
                title_t9_seq.append(digits)
            else:
                 # 无法转换的字符，保留空集合或忽略
                 title_t9_seq.append(set())

        # 2. 匹配逻辑
        # 检查 user_input 是否匹配 title_t9_seq 的开头
        # (实际应用中可能需要支持任意位置匹配，这里演示从头匹配)
        is_match = True
        if len(user_input) > len(title_t9_seq):
            is_match = False
        else:
            for i, input_digit in enumerate(user_input):
                # 检查输入的数字是否在当前位置的允许集合中
                if input_digit not in title_t9_seq[i]:
                    is_match = False
                    break
        
        print(f"T9序列: {title_t9_seq}")
        print(f"匹配结果: {'成功' if is_match else '失败'}")

if __name__ == "__main__":
    # 1. 生成数据
    dictionary = generate_char_map()
    
    # 2. 保存到文件 (使用紧凑格式，减小文件体积)
    output_file = "resources/char_map.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, separators=(',', ':'))
        
    print(f"字典已保存到 {output_file}")
    
    # 3. 演示如何使用
    demo_t9_search(dictionary)
