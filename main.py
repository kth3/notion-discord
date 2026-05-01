import requests
from datetime import datetime, timedelta, timezone
import os

NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK')

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

user_cache = {}
CACHE_FILE = "last_run_time.txt"

def get_threshold():
    """
    캐시 파일에서 이전 실행 시각을 읽어옵니다.
    파일이 없거나 최초 실행일 경우, 누락을 방지하기 위해 15분 전을 기준으로 삼습니다.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return datetime.fromisoformat(f.read().strip())
        except Exception:
            pass
    return datetime.now(timezone.utc) - timedelta(minutes=15)

def save_current_time(current_time):
    """현재 실행 시각을 물리적 파일에 기록합니다."""
    try:
        with open(CACHE_FILE, "w") as f:
            f.write(current_time.isoformat())
    except Exception:
        pass

def get_user_name(user_id):
    if not user_id:
        return "익명 사용자"
    if user_id in user_cache:
        return user_cache[user_id]
    
    try:
        url = f"https://api.notion.com/v1/users/{user_id}"
        res = requests.get(url, headers=headers).json()
        name = res.get('name', '알 수 없는 사용자')
        user_cache[user_id] = name
        return name
    except Exception:
        return "알 수 없는 사용자"

def get_changed_content(page_id, threshold):
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        res = requests.get(url, headers=headers).json()
        blocks = res.get('results', [])
        
        texts = []
        recent_block_exists = False
        
        for block in blocks:
            block_edited = datetime.fromisoformat(block['last_edited_time'].replace('Z', '+00:00'))
            
            if block_edited > threshold:
                recent_block_exists = True
                b_type = block.get('type')
                rich_text = block.get(b_type, {}).get('rich_text', [])
                
                if rich_text:
                    plain_text = "".join([t.get('plain_text', '') for t in rich_text]).strip()
                    if plain_text:
                        texts.append(plain_text)
                        
        if texts:
            full_text = " / ".join(texts)
            return full_text[:200] + "..." if len(full_text) > 200 else full_text
            
        if recent_block_exists:
            return "텍스트 외 항목 변경"
            
        return "기존 내용 삭제 또는 페이지 위치 변경"
        
    except Exception:
        return "본문 로드 실패"

def get_page_title(page):
    props = page.get('properties', {})
    title = "제목 없음"
    title_key = next((k for k, v in props.items() if v.get('type') == 'title'), None)
    
    if title_key:
        t_list = props[title_key].get('title', [])
        if t_list: 
            title = t_list[0]['plain_text']
            
    return title

def run():
    now_utc = datetime.now(timezone.utc)
    threshold = get_threshold()
    
    search_url = "https://api.notion.com/v1/search"
    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    
    try:
        response = requests.post(search_url, headers=headers, json=payload).json()
        results = response.get('results', [])
    except Exception:
        results = []

    for page in results:
        last_edited = datetime.fromisoformat(page['last_edited_time'].replace('Z', '+00:00'))
        
        if last_edited > threshold:
            title = get_page_title(page)
            
            author_id = page.get('last_edited_by', {}).get('id')
            author = get_user_name(author_id)
            
            summary = get_changed_content(page['id'], threshold)
            page_url = page['url']
            
            kst_time = last_edited.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
            
            discord_msg = {
                "embeds": [{
                    "title": f"📄{title}",
                    "url": page_url,
                    "color": 3447003,
                    "fields": [
                        {"name": "👤 수정자", "value": author, "inline": True},
                        {"name": "⏰ 수정 시각 (KST)", "value": kst_time, "inline": True},
                        {"name": "📝 변경 내용 요약", "value": summary, "inline": False}
                    ],
                    "footer": {"text": "Notion Auto Monitor"}
                }]
            }
            
            try:
                requests.post(DISCORD_WEBHOOK, json=discord_msg)
            except Exception:
                pass

    # 스크립트가 정상적으로 끝난 후, 다음 번 기준점이 될 현재 시각을 파일에 덮어씁니다.
    save_current_time(now_utc)

if __name__ == "__main__":
    run()
