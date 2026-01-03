import requests
import re
import concurrent.futures
import datetime
import urllib3

# 1. 屏蔽 SSL 警告 (防止日志刷屏)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区域 ---
URLS = [
    # --- 国内优质源 (利用你的电信IPv6) ---
    "https://raw.githubusercontent.com/dongyubin/IPTV/master/IPTV.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", # 范明明 IPv6 神源
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
    
    # --- 国际精选源 (利用你的 Shadowrocket) ---
    "https://iptv-org.github.io/iptv/countries/sg.m3u", # 新加坡 (优质)
    "https://iptv-org.github.io/iptv/countries/jp.m3u", # 日本
    "https://iptv-org.github.io/iptv/countries/gb.m3u", # 英国
    "https://iptv-org.github.io/iptv/countries/us.m3u"  # 美国
]

OUTPUT_FILE = "playlist.m3u"
MAX_WORKERS = 30 # 并发线程数
TIMEOUT = 3      # 检测超时时间(秒)

# --- 分类规则 (关键词匹配) ---
CATEGORY_RULES = {
    # 1. 本地置顶 (成都电信专属)
    "四川频道": ["四川", "成都", "Sichuan", "Chengdu", "康巴", "熊猫"],
    
    # 2. 核心中文
    "央视频道": ["CCTV", "央视", "CGTN"],
    "卫视频道": ["卫视"],
    "香港频道": ["翡翠", "TVB", "凤凰", "HK", "明珠", "J2", "Viu"],
    "台湾频道": ["中天", "东森", "民视", "TVBS", "台视", "华视", "公视"],
    
    # 3. 纪录片 (你的新增需求)
    "纪录片": ["纪录", "纪实", "科教", "档案", "地理", "Documentary", "Discovery", "Nat Geo", "History", "Animal", "Planet", "Earth", "Wild"],

    # 4. 国际精选
    "新加坡频道": ["Singtel", "StarHub", "Mediacorp", "Channel 5", "Channel 8", "CNA"],
    "日本频道": ["NHK", "Fuji", "TBS", "Asahi", "Nippon", "Tokyo"],
    "国际新闻": ["BBC", "CNN", "Fox News", "Sky News", "Al Jazeera", "Bloomberg"],
    "国际影视": ["HBO", "Movies", "Cinema", "Film", "Drama", "Warner", "Sony", "AXN"],
    
    # 5. 体育与数字
    "体育频道": ["体育", "Sports", "ESPN", "NBA", "Football", "Soccer", "F1"],
    "数字频道": ["CHC", "家庭影院", "剧场"]
}

# 本地源保护名单 (跳过检测，防止误删)
KEEP_KEYWORDS = ["四川", "成都", "Sichuan", "Chengdu"]

# 垃圾过滤黑名单
BLACKLIST = ["购物", "备用", "测试", "Loop", "VOD", "宣传", "卖药", "Church", "God", "Religion", "Parliament"]

# --- 核心逻辑 ---

def get_category(name):
    upper_name = name.upper()
    for category, keywords in CATEGORY_RULES.items():
        if not keywords: continue
        for keyword in keywords:
            if keyword.upper() in upper_name:
                return category
    if re.search(r'[\u4e00-\u9fa5]', name): return "其他中文"
    return "国际其他"

def parse_m3u_line(line, current_header):
    try:
        original_name = current_header.split(",")[-1].strip()
        if any(b in original_name for b in BLACKLIST): return None
        new_group = get_category(original_name)
        logo_match = re.search(r'tvg-logo="([^"]+)"', current_header)
        logo_part = f' tvg-logo="{logo_match.group(1)}"' if logo_match else ""
        new_header = f'#EXTINF:-1 group-title="{new_group}" tvg-name="{original_name}"{logo_part},{original_name}'
        return {
            'name': original_name, 'url': line.strip(), 'header': new_header,
            'is_local': any(k in original_name for k in KEEP_KEYWORDS)
        }
    except: return None

def get_channel_items(url):
    channels = []
    try:
        print(f"正在抓取: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # verify=False 忽略证书错误
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            lines = response.text.splitlines()
            current_header = ""
            for line in lines:
                line = line.strip()
                if not line: continue
                if line.startswith("#EXTINF"): current_header = line
                elif not line.startswith("#") and current_header:
                    item = parse_m3u_line(line, current_header)
                    if item: channels.append(item)
                    current_header = ""
    except Exception as e: print(f"抓取失败 {url}: {e}")
    return channels

def check_stream(channel):
    # 1. 本地源免死 (四川/成都)
    if channel['is_local']: return channel
    # 2. 其他源检测
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(channel['url'], stream=True, headers=headers, timeout=TIMEOUT, verify=False) as response:
            if response.status_code in [200, 302, 405]: return channel
    except: pass
    return None

def main():
    print("🚀 任务开始...")
    all_channels = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(get_channel_items, url) for url in URLS]
        for future in concurrent.futures.as_completed(futures): all_channels.extend(future.result())

    if not all_channels: return

    # 去重
    unique_channels = {}
    for ch in all_channels:
        url = ch['url']
        if url not in unique_channels: unique_channels[url] = ch
        else:
            if ("HD" in ch['name']) and ("HD" not in unique_channels[url]['name']): unique_channels[url] = ch
    
    work_list = list(unique_channels.values())
    print(f"✅ 去重完成，共 {len(work_list)} 个频道。开始检测...")

    valid_channels = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {executor.submit(check_stream, ch): ch for ch in work_list}
        for future in concurrent.futures.as_completed(future_to_channel):
            res = future.result()
            if res: valid_channels.append(res)

    # 排序优先级
    group_priority = ["四川频道", "央视频道", "卫视频道", "纪录片", "香港频道", "新加坡频道", "台湾频道", "体育频道", "日本频道", "国际新闻", "国际影视"]
    
    def sort_key(ch):
        g_match = re.search(r'group-title="([^"]+)"', ch['header'])
        group = g_match.group(1) if g_match else "其他频道"
        try: g_score = group_priority.index(group)
        except: g_score = 99
        is_ipv6 = 0 if ('[' in ch['url'] or ch['url'].count(':') > 2) else 1
        return (g_score, is_ipv6, len(ch['name']))

    valid_channels.sort(key=sort_key)

    if len(valid_channels) < 10: return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # 写入 EPG 地址
        f.write('#EXTM3U x-tvg-url="http://epg.51zmt.top:8000/e.xml"\n')
        f.write(f"# Updated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for channel in valid_channels:
            f.write(f"{channel['header']}\n")
            f.write(f"{channel['url']}\n")
    
    print(f"🎉 成功！生成 {len(valid_channels)} 个频道。")

if __name__ == "__main__":
    main()
