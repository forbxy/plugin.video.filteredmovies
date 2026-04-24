# -*- coding: utf-8 -*-
import re
import json
import xbmc
import xbmcaddon

from .common import notification, log

_LANG_MAP = {
    'ukr': '乌克兰语', 'uk': '乌克兰语',
    'ice': '冰岛语', 'isl': '冰岛语', 'is': '冰岛语',
    'eng': '英语', 'en': '英语',
    'chi': '中文', 'zho': '中文', 'zh': '中文', 'chn': '中文',
    'jpn': '日语', 'ja': '日语',
    'kor': '韩语', 'ko': '韩语',
    'rus': '俄语', 'ru': '俄语',
    'fre': '法语', 'fra': '法语', 'fr': '法语',
    'ger': '德语', 'deu': '德语', 'de': '德语',
    'spa': '西班牙语', 'es': '西班牙语',
    'ita': '意大利语', 'it': '意大利语',
    'por': '葡萄牙语', 'pt': '葡萄牙语',
    'tha': '泰语', 'th': '泰语',
    'vie': '越南语', 'vi': '越南语',
    'ind': '印尼语', 'id': '印尼语',
    'dan': '丹麦语', 'da': '丹麦语',
    'fin': '芬兰语', 'fi': '芬兰语',
    'dut': '荷兰语', 'nld': '荷兰语', 'nl': '荷兰语',
    'nor': '挪威语', 'no': '挪威语',
    'swe': '瑞典语', 'sv': '瑞典语',
    'ara': '阿拉伯语', 'ar': '阿拉伯语',
    'arc': '阿拉姆语',
    'hrv': '克罗地亚语', 'hr': '克罗地亚语',
    'ces': '捷克语', 'cze': '捷克语', 'cs': '捷克语',
    'ell': '希腊语', 'gre': '希腊语', 'el': '希腊语',
    'heb': '希伯来语', 'he': '希伯来语',
    'hun': '匈牙利语', 'hu': '匈牙利语',
    'ron': '罗马尼亚语', 'rum': '罗马尼亚语', 'ro': '罗马尼亚语',
    'tur': '土耳其语', 'tr': '土耳其语',
    'bul': '保加利亚语', 'bg': '保加利亚语',
    'msa': '马来语', 'may': '马来语', 'ms': '马来语',
    'pol': '波兰语', 'pl': '波兰语',
    'tgl': '塔加洛语', 'tl': '塔加洛语', 'fil': '菲律宾语',
    'eus': '巴斯克语', 'baq': '巴斯克语', 'eu': '巴斯克语', 'basque': '巴斯克语',
    'cat': '加泰罗尼亚语', 'ca': '加泰罗尼亚语', 'catalan': '加泰罗尼亚语',
    'glg': '加利西亚语', 'gl': '加利西亚语', 'gallegan': '加利西亚语',
    'unk': '未知', 'und': '未知', '': '未知',
    # 英文全称
    'english': '英语', 'chinese': '中文', 'japanese': '日语', 'korean': '韩语',
    'russian': '俄语', 'french': '法语', 'german': '德语', 'spanish': '西班牙语',
    'italian': '意大利语', 'portuguese': '葡萄牙语', 'thai': '泰语', 'vietnamese': '越南语',
    'indonesian': '印尼语', 'danish': '丹麦语', 'finnish': '芬兰语', 'dutch': '荷兰语',
    'norwegian': '挪威语', 'swedish': '瑞典语', 'arabic': '阿拉伯语', 'croatian': '克罗地亚语',
    'czech': '捷克语', 'greek': '希腊语', 'hebrew': '希伯来语', 'hungarian': '匈牙利语',
    'romanian': '罗马尼亚语', 'turkish': '土耳其语', 'bulgarian': '保加利亚语', 'malay': '马来语',
    'polish': '波兰语', 'tagalog': '塔加洛语', 'filipino': '菲律宾语',
    'ukrainian': '乌克兰语', 'icelandic': '冰岛语', 'aramaic': '阿拉姆语',
}

_SUBTITLE_NAME_REPLACEMENTS = [
    (r'\bCHS/ENG\b', '简/英'),
    (r'\bCHT/ENG\b', '繁/英'),
    (r'\bCHS\b', '简体'),
    (r'\bCHT\b', '繁体'),
    (r'\bENG\b', '英语'),
    (r'Chinese\s*[\(\[\{]?Simplified[\)\]\}]?', '简体'),
    (r'Chinese\s*[\-\.]?\s*Simplified', '简体'),
    (r'Simplified\s*Chinese', '简体'),
    (r'Traditional\s*Chinese', '繁体'),
    (r'Chinese\s*[\(\[\{]?Traditional[\)\]\}]?', '繁体'),
    (r'Chinese\s*[\-\.]?\s*Traditional', '繁体'),
    (r'Chi\s*\(Simp\)', '简体'),
    (r'Chi\s*\(Trad\)', '繁体'),
    (r'Simplified', '简体'),
    (r'Traditional', '繁体'),
    (r'Mandarin', '普通话'),
    (r'Cantonese', '粤语'),
]

_AUDIO_NAME_CHANNEL_SUFFIX_RE = re.compile(r'\s+\d+\.\d+\s*$')


def _resolve_lang_name(lang_code):
    name = _LANG_MAP.get(lang_code.lower())
    if not name:
        try:
            name = xbmc.convertLanguage(lang_code, xbmc.ENGLISH_NAME)
            if name and name.lower() in ('undetermined', 'unknown', 'undefined'):
                name = '未知'
        except Exception:
            name = lang_code
    return name or '未知'


def _translate_stream_name(name):
    if not name:
        return ''

    translated_name = name
    for pattern, repl in _SUBTITLE_NAME_REPLACEMENTS:
        translated_name = re.sub(pattern, repl, translated_name, flags=re.IGNORECASE)

    parts = translated_name.split('-')
    first_part = parts[0].strip()
    mapped = _LANG_MAP.get(first_part.lower())
    if mapped:
        parts[0] = mapped
        translated_name = '-'.join(parts)

    return translated_name


def _strip_language_prefix_from_name(name, language):
    cleaned_name = (name or '').strip()
    cleaned_language = (language or '').strip()

    if not cleaned_name or not cleaned_language:
        return cleaned_name

    if cleaned_name.lower() == cleaned_language.lower():
        return ''

    lower_name = cleaned_name.lower()
    lower_language = cleaned_language.lower()
    if not lower_name.startswith(lower_language):
        return cleaned_name

    remainder = cleaned_name[len(cleaned_language):].strip()
    remainder = re.sub(r'^[\s\-_/|:：]+', '', remainder)

    bracket_pairs = (
        ('(', ')'),
        ('（', '）'),
        ('[', ']'),
        ('【', '】'),
    )
    for left_bracket, right_bracket in bracket_pairs:
        if remainder.startswith(left_bracket) and remainder.endswith(right_bracket):
            remainder = remainder[1:-1].strip()
            break

    return remainder


def _strip_audio_channel_suffix(name):
    cleaned_name = (name or '').strip()
    if not cleaned_name:
        return ''
    cleaned_name = _AUDIO_NAME_CHANNEL_SUFFIX_RE.sub('', cleaned_name).strip()
    return cleaned_name


def _format_khz(value):
    if value <= 0:
        return ''
    numeric = float(value)
    khz = numeric / 1000.0 if numeric >= 1000.0 else numeric
    if khz.is_integer():
        return f"{int(khz)}kHz"
    return f"{khz:.1f}kHz"


def _format_kbps(value):
    if value <= 0:
        return ''
    numeric = float(value)
    kbps = int(round(numeric / 1000.0 if numeric >= 1000.0 else numeric))
    return f"{kbps}kbps"


def _build_code_info(bitrate, samplerate):
    bitrate_text = _format_kbps(bitrate)
    samplerate_text = _format_khz(samplerate)

    if bitrate_text and samplerate_text:
        return f"{bitrate_text}-{samplerate_text}"
    return bitrate_text or samplerate_text


def get_subtitle_items(suppress_warning=False):
    """获取字幕列表。返回 (display_items, current_index, is_enabled, player)。"""
    log("get_subtitle_items function started")
    player = xbmc.Player()
    if not player.isPlaying():
        log("Player is not playing")
        return None, None, None, None

    try:
        log("Fetching subtitle info via JSON-RPC")
        streams = []
        current_stream = {}
        is_enabled = False

        try:
            req_str = json.dumps({
                "jsonrpc": "2.0", "method": "Player.GetProperties",
                "params": {"playerid": 1, "properties": ["subtitles", "subtitleenabled", "currentsubtitle"]}, "id": 1
            })
            r = json.loads(xbmc.executeJSONRPC(req_str))
            if 'result' in r:
                result = r['result']
                streams = result.get('subtitles', [])
                current_stream = result.get('currentsubtitle', {})
                is_enabled = result.get('subtitleenabled', False)
            else:
                raise Exception("subtitles property failed")
        except Exception:
            log("JSON-RPC subtitles exception, using fallback for streams")
            avail_streams = player.getAvailableSubtitleStreams()
            for i, name in enumerate(avail_streams):
                streams.append({"index": i, "name": name, "language": "unk"})

        for itm in streams:
            log(f"{itm['language']} {itm['name']}")

        if not streams:
            if not suppress_warning:
                notification("没有可用的字幕流")
            return None, None, None, None

        current_index = current_stream.get('index') if is_enabled else -1

        raw_items = []
        for s in streams:
            idx = s.get('index')
            lang_code = s.get('language', 'unk')
            name = s.get('name', '')

            language = _resolve_lang_name(lang_code)

            # 翻译并清理 name 字段
            translated_name = _translate_stream_name(name)
            cleaned_name = _strip_language_prefix_from_name(translated_name, language)
            # 如果 name 与语言代码相同，也清掉
            if cleaned_name and cleaned_name.lower() == lang_code.lower():
                cleaned_name = ''
            # 去掉中文括号包裹的"外挂"
            if cleaned_name:
                cleaned_name = cleaned_name.replace('（外挂）', '外挂')

            # 合并 flags
            extra_flags_parts = []
            if s.get('isdefault'):
                extra_flags_parts.append('默认')
            if s.get('isforced'):
                extra_flags_parts.append('强制')
            if s.get('isimpaired'):
                extra_flags_parts.append('解说')
            if name and ('commentary' in name.lower() or '解说' in name or 'description' in name.lower()):
                if '解说' not in extra_flags_parts:
                    extra_flags_parts.append('解说字幕')
            extra_flags = '-'.join(extra_flags_parts)

            # 构建完整 label（用于通知等场景）
            label = language
            if cleaned_name:
                label += f"-{cleaned_name}"
            if extra_flags:
                label += f" ({extra_flags})"

            is_chinese = lang_code.lower() in ['chi', 'zho', 'zh', 'chn']
            is_external = '(external)' in name.lower() or '（外挂）' in name.lower()

            raw_items.append({
                "label": label,
                "language": language,
                "name": cleaned_name,
                "extra_flags": extra_flags,
                "index": idx,
                "is_active": (is_enabled and idx == current_index),
                "is_chinese": is_chinese,
                "is_external": is_external,
                "original_order": idx,
                "lang_code": lang_code,
            })

        raw_items.sort(key=lambda x: (not x['is_external'], not x['is_chinese'], x['original_order']))

        display_items = [
            {"label": item["label"], "language": item["language"],
             "name": item["name"], "extra_flags": item["extra_flags"],
             "index": item["index"],
             "is_active": item["is_active"], "lang_code": item.get("lang_code", "unk")}
            for item in raw_items
        ]

        return display_items, current_index, is_enabled, player

    except Exception as e:
        log(f"Error in get_subtitle_items: {e}")
        notification(f"获取字幕出错: {e}", sound=True)
        return None, None, None, None


def get_audio_items(suppress_warning=False):
    """获取音轨列表。返回 (display_items, current_index)。"""
    try:
        r = json.loads(xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0", "method": "Player.GetProperties",
            "params": {"playerid": 1, "properties": ["audiostreams", "currentaudiostream"]}, "id": 1
        })))

        if 'result' not in r:
            return None, -1

        streams = r['result'].get('audiostreams', [])
        current_stream = r['result'].get('currentaudiostream', {})

        if not streams:
            if not suppress_warning:
                notification("没有可用的音轨")
            return None, -1

        current_index = current_stream.get('index', -1)
        display_items = []

        def _is_positive_number(value):
            try:
                return float(value) > 0
            except (TypeError, ValueError):
                return False

        has_known_bitrate = any(_is_positive_number(s.get('bitrate', 0)) for s in streams)

        for s in streams:
            idx = s.get('index')
            lang_code = s.get('language', 'unk')
            name = s.get('name', '')
            channels = s.get('channels', 0)
            codec = s.get('codec', '')
            bitrate = s.get('bitrate', 0)
            samplerate = s.get('samplerate', 0)

            language = _resolve_lang_name(lang_code)
            translated_name = _translate_stream_name(name)
            name_without_language = _strip_language_prefix_from_name(translated_name, language)
            name_without_language = _strip_audio_channel_suffix(name_without_language)
            if language and name_without_language:
                language_and_name = f"{language}-{name_without_language}"
            else:
                language_and_name = language or name_without_language
            code_info = _build_code_info(bitrate, samplerate)
            if not code_info and has_known_bitrate:
                code_info = '未知码率'
            channel = f"{int(channels)}声道" if channels else ''

            extra_flags_parts = []
            if s.get('isdefault'):
                extra_flags_parts.append('默认')
            if s.get('isimpaired'):
                extra_flags_parts.append('解说')
            if s.get('isoriginal'):
                extra_flags_parts.append('原始')
            extra_flags = '-'.join(extra_flags_parts)

            details = []
            if codec:
                details.append(codec)
            if code_info:
                details.append(code_info)

            if channel:
                details.append(channel)
            if extra_flags:
                details.append(extra_flags)

            label = language_and_name + (f" - {' - '.join(details)}" if details else "")

            sort_priority = 2
            if lang_code.lower() in ['chi', 'zho', 'zh', 'chn']:
                sort_priority = 0
            elif lang_code.lower() in ['eng', 'en']:
                sort_priority = 1

            display_items.append({
                "label": label,
                "language": language,
                "name": name_without_language,
                "language_and_name": language_and_name,
                "codec": codec,
                "code_info": code_info,
                "channel": channel,
                "extra_flags": extra_flags,
                "index": idx,
                "is_active": (idx == current_index),
                "sort_priority": sort_priority,
                "original_order": idx,
                "lang_code": lang_code,
            })

        display_items.sort(key=lambda x: (x['sort_priority'], x['original_order']))
        return display_items, current_index

    except Exception as e:
        log(f"Error in get_audio_items: {e}")
        if not suppress_warning:
            notification(f"获取音轨出错: {e}", sound=True)
        return None, -1
