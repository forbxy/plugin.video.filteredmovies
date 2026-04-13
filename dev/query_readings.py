# -*- coding: utf-8 -*-
"""
查询 char_map.json 中指定字符的读音。
支持输入单个字或一段文字，逐字显示读音。

用法:
  python dev/query_readings.py 行
  python dev/query_readings.py 大雄的南极冰冰凉
  python dev/query_readings.py        # 交互模式
"""
import json
import os
import sys


def load_char_map():
    map_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'char_map.json')
    with open(map_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def query(data, text):
    for ch in text:
        if ch in data:
            v = data[ch]
            if isinstance(v, list):
                initials = list(dict.fromkeys(p[0].upper() for p in v if p))
                print(f"  {ch}  readings={v}  initials={initials}")
            else:
                print(f"  {ch}  value={v}")
        elif ch.isspace():
            continue
        else:
            print(f"  {ch}  (not in char_map)")


def main():
    data = load_char_map()

    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
        query(data, text)
        return

    print("交互模式，输入字符查询读音，输入 q 退出")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() == 'q':
            break
        if text:
            query(data, text)


if __name__ == "__main__":
    main()
