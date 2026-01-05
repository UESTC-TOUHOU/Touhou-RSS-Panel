import os
import time
import datetime
import json
from collections import deque

# 第三方库
from nicegui import ui, app, run
import feedparser
from deep_translator import GoogleTranslator

# ====================================================
# 1. 配置加载与保存逻辑
# ====================================================

CONFIG_FILE = 'config.json'

# [出厂默认设置]
# 仅当 config.json 不存在时，才会使用这里的值生成文件
DEFAULT_CONFIG = {
    "rss_sources": [
        {'name': '文文新闻', 'url': '', 'category': 'news'},
        {'name': '花果子念报', 'url': '', 'category': 'eng'}
    ],
    "system_settings": {
        "refresh_interval": 1800,
        "port": 5005
    },
    "ui_settings": {
        # 默认使用 Unsplash 无版权图片
        "background_url": "",
        "banner_url": ""
    }
}

def load_config():
    """加载配置"""
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG
        except:
            return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            # 合并逻辑：防止旧配置文件缺少 ui_settings 字段导致报错
            data = json.load(f)
            if 'ui_settings' not in data:
                data['ui_settings'] = DEFAULT_CONFIG['ui_settings']
            return data
    except:
        return DEFAULT_CONFIG

def save_rss_source(new_source):
    """保存 RSS 源"""
    try:
        current_conf = load_config()
        for src in current_conf.get('rss_sources', []):
            if src['url'] == new_source['url']:
                return False, "该 URL 已存在"
        
        current_conf.setdefault('rss_sources', []).append(new_source)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_conf, f, indent=4, ensure_ascii=False)
        
        global RSS_SOURCES
        RSS_SOURCES = current_conf['rss_sources']
        return True, "添加成功"
    except Exception as e:
        return False, str(e)

# --- 初始化配置 ---
config = load_config()
RSS_SOURCES = config.get('rss_sources', DEFAULT_CONFIG['rss_sources'])
sys_settings = config.get('system_settings', DEFAULT_CONFIG['system_settings'])
# [新增] 读取图片配置
ui_conf = config.get('ui_settings', DEFAULT_CONFIG['ui_settings'])
BG_URL = ui_conf.get('background_url')
BANNER_URL = ui_conf.get('banner_url')

REFRESH_INTERVAL = sys_settings.get('refresh_interval', 1800)
PORT = sys_settings.get('port', 5005)

# ====================================================
# 2. 样式定义
# ====================================================

if not os.path.exists('static'):
    os.makedirs('static')
app.add_static_files('/static', 'static')

# 全局变量
NEWS_DATA = deque(maxlen=1000)
current_category = 'news' 
is_loading = False 

# [修改] 动态设置 body 背景图
# 这里使用 style 直接注入，因为 CSS 字符串插值容易出错
ui.query('body').style(f'''
    background-image: url('{BG_URL}');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    margin: 0;
    font-family: 'Roboto', sans-serif;
''')

# 其他 CSS (移除了 body 部分)
ui.add_head_html('''
<style>
    .glass-card {
        background: rgba(0,0,0, 0.5);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        color: white;
    }
    
    /* 输入框样式优化 */
    .my-input .q-field__native { color: white !important; }
    .my-input .q-field__label { color: rgba(255,255,255,0.7) !important; }

    /* Tabs 和滚动条 */
    .文文-tabs .q-tab { color: #ffce83; opacity: 0.7; transition: all 0.3s ease; }
    .文文-tabs .q-tab--active { color: #ffb656; opacity: 1; }
    .文文-tabs .q-tab__indicator { background-color: #ffb656 !important; height: 3px; }
    
    .custom-scrollbar::-webkit-scrollbar { width: 8px; height: 8px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: transparent; border-radius: 4px; }
    .custom-scrollbar::-webkit-scrollbar-thumb { 
        background: rgba(255, 255, 255, 0.15); 
        border-radius: 4px; border: 2px solid transparent; background-clip: content-box; 
    }
    .custom-scrollbar::-webkit-scrollbar-thumb:hover { background-color: rgba(255, 255, 255, 0.4); }
    .custom-scrollbar { scrollbar-width: thin; scrollbar-color: rgba(255, 255, 255, 0.2) transparent; }
</style>
''')

# ====================================================
# 3. 核心逻辑 (抓取)
# ====================================================

def fetch_single_source(source, existing_links):
    """后台抓取单个 RSS 源"""
    print(f"[{datetime.datetime.now()}] 正在连接: {source['name']} ...")
    cutoff_time = time.time() - (100 * 24 * 60 * 60)
    headers = {'User-Agent': 'Mozilla/5.0'}
    translator = GoogleTranslator(source='auto', target='zh-CN')
    
    entries_found = []
    try:
        feed = feedparser.parse(source['url'], request_headers=headers)
        for i, entry in enumerate(feed.entries[:30]):
            if entry.link in existing_links: continue
            
            ts = time.time()
            pub_date = "往期"
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                ts = time.mktime(entry.published_parsed)
                pub_date = time.strftime("%m-%d %H:%M", entry.published_parsed)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                ts = time.mktime(entry.updated_parsed)
                pub_date = time.strftime("%m-%d %H:%M", entry.updated_parsed)
            
            is_fresh = ts >= cutoff_time
            if not is_fresh and i != 0: continue

            trans_title = ""
            if is_fresh:
                try:
                    res = translator.translate(entry.title)
                    if res and res != entry.title:
                        trans_title = res
                except:
                    pass
            
            entries_found.append({
                'title': entry.title,
                'trans_title': trans_title,
                'link': entry.link,
                'date': f"[{source['name']}] {pub_date}",
                'timestamp': ts,
                'category': source['category']
            })
    except Exception as e:
        print(f"抓取 {source['name']} 失败: {e}")
    return entries_found

async def refresh_news_data(force=False):
    global is_loading
    if is_loading and not force: return
    is_loading = True
    if force: ui.notify('少女祈祷中... (正在刷新)', position='bottom-right')

    try:
        existing_links = {item['link'] for item in NEWS_DATA}
        total_new = 0

        for source in RSS_SOURCES:
            new_items = await run.io_bound(fetch_single_source, source, existing_links)
            if new_items:
                total_new += len(new_items)
                temp_list = list(NEWS_DATA) + new_items
                temp_list.sort(key=lambda x: x['timestamp'], reverse=True)
                NEWS_DATA.clear()
                NEWS_DATA.extend(temp_list)
                for item in new_items: existing_links.add(item['link'])
                news_list.refresh()
        
        if force:
            ui.notify(f'更新完毕，增加 {total_new} 条', type='positive' if total_new > 0 else 'info', position='bottom-right')

    except Exception as e:
        ui.notify(f'出错啦: {e}', type='negative')
    finally:
        is_loading = False
        news_list.refresh()

# ====================================================
# 4. UI 组件
# ====================================================

@ui.refreshable
def news_list():
    filtered_data = [item for item in NEWS_DATA if item.get('category') == current_category]
    current_items = filtered_data[:1000]

    if not current_items:
        with ui.column().classes('w-full items-center justify-center py-10 opacity-50'):
            if is_loading:
                ui.spinner('dots', size='lg', color='white')
                ui.label(f'正在取材中 ({current_category})...').classes('text-sm animate-pulse')
            else:
                ui.icon('inbox', size='lg', color='gray')
                ui.label(f'没有 {current_category} 类的新闻').classes('text-sm')
        return

    with ui.column().classes('w-full gap-2'):
        for item in current_items:
            with ui.link(target=item['link'], new_tab=True).classes('w-full no-underline text-gray-200 hover:text-white'):
                with ui.row().classes('w-full justify-between items-center text-sm bg-black/20 hover:bg-white/20 rounded px-3 py-2 transition-colors cursor-pointer group'):
                    with ui.row().classes('items-start gap-3 flex-1'): 
                        dot_color = 'bg-orange-400' if item['category'] == 'news' else 'bg-blue-400'
                        ui.element('div').classes(f'w-1.5 h-1.5 rounded-full {dot_color} group-hover:bg-yellow-300 transition-colors mt-2 shrink-0')
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(item['title']).classes('font-medium text-gray-100 text-sm leading-snug break-words whitespace-normal')
                            if item.get('trans_title'):
                                ui.label(item['trans_title']).classes('text-xs text-gray-400 leading-snug break-words whitespace-normal mt-1')
                    with ui.row().classes('items-center gap-2 shrink-0 ml-2'):
                        ui.label(item['date']).classes('text-[10px] text-gray-500 font-mono hidden md:block')
                        ui.icon('chevron_right', size='xs', color='gray')

# ====================================================
# 5. 主页面布局
# ====================================================

ui.page_title('文文新闻 - 百四十一季')

# 主容器
with ui.column().classes('w-full md:w-[45%] md:min-w-[800px] min-h-screen p-4 mx-auto gap-4'):

    # --- 订阅管理组件 ---
    with ui.expansion('订阅管理', icon='rss_feed').classes('w-full glass-card !p-0 overflow-hidden text-sm').props('header-class="text-orange-200"'):
        with ui.column().classes('p-4 gap-3 w-full bg-black/20'):
            with ui.row().classes('w-full items-center gap-2'):
                in_name = ui.input(label='名称').classes('flex-1 my-input').props('dark dense outlined')
                in_cat = ui.select(options={'news': '文文春新报 (news)', 'eng': '河童类聚抄 (eng)'}, value='news', label='分类') \
                    .classes('w-40 my-input').props('dark dense outlined')
            in_url = ui.input(label='RSS URL').classes('w-full my-input').props('dark dense outlined')

            async def add_feed():
                if not in_name.value or not in_url.value:
                    ui.notify('请填写完整信息', type='warning')
                    return
                new_item = {'name': in_name.value, 'url': in_url.value, 'category': in_cat.value}
                success, msg = save_rss_source(new_item)
                if success:
                    ui.notify(f'已添加: {in_name.value}', type='positive')
                    in_name.value = ''
                    in_url.value = ''
                    await refresh_news_data(force=True)
                else:
                    ui.notify(f'添加失败: {msg}', type='negative')

            with ui.row().classes('w-full justify-end'):
                ui.button('添加订阅', on_click=add_feed, icon='add').props('flat dense color=orange')

    # --- 新闻 Banner 与 Tab 区域 ---
    with ui.element('div').classes('w-full relative mt-2 rounded-xl overflow-hidden shadow-lg group bg-black min-h-[200px]'):
        
        # [修改] 使用 Config 中的 BANNER_URL
        ui.image(BANNER_URL).classes('absolute inset-0 w-full h-full object-cover object-center opacity-60 transition-transform duration-700 group-hover:scale-105') \
            .style('-webkit-mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent); mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent);')
        ui.element('div').classes('absolute inset-0 bg-black/30')

        with ui.column().classes('relative p-6 gap-4 w-full'):
            with ui.row().classes('w-full justify-between items-center pb-0 border-b border-white/10'):
                def on_tab_change(e):
                    global current_category
                    current_category = e.value
                    news_list.refresh()

                with ui.tabs().classes('bg-transparent 文文-tabs').props('no-caps dense').on_value_change(on_tab_change) as tabs:
                    with ui.tab(name='news', label='').classes('min-h-[40px] px-2'):
                        with ui.row().classes('items-center gap-2'):
                            # 小图标依然保持本地
                            ui.image('/static/ayaico.png').classes('w-6 h-6 object-contain filter drop-shadow-md')
                            ui.label('文文春新报').classes('text-lg font-bold tracking-wide')
                    
                    with ui.tab(name='eng', label='').classes('min-h-[40px] px-2'):
                        with ui.row().classes('items-center gap-2'):
                            # 小图标依然保持本地
                            ui.image('/static/kappaico.png').classes('w-6 h-6 object-contain filter drop-shadow-md')
                            ui.label('河童类聚抄').classes('text-lg font-bold tracking-wide')
                
                ui.button(icon='refresh', on_click=lambda: refresh_news_data(force=True)).props('flat round dense size=sm color=white')

            with ui.column().classes('w-full overflow-y-auto custom-scrollbar h-[850px]'):
                tabs.set_value(current_category)
                news_list()

# ====================================================
# 6. 定时器与启动
# ====================================================

ui.timer(float(REFRESH_INTERVAL), lambda: refresh_news_data(force=False))
ui.timer(1.0, lambda: refresh_news_data(force=False), once=True)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host='0.0.0.0', port=PORT, title='文文新闻 - 百四十一季', show=False, reload=False)


# 我说gemini太好用了