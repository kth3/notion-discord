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

def get_dynamic_threshold():
    """
    파일이나 캐시에 의존하지 않고, 현재 실행 시각과 요일을 바탕으로 
    검색해야 할 과거 임계 시간(Threshold)을 동적으로 계산
    """
    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(timezone(timedelta(hours=9)))
    
    weekday = now_kst.weekday() # 0(월) ~ 4(금), 5(토) ~ 6(일)
    hour = now_kst.hour
    
    # 깃허브 액션의 크론 지연(1~2분)을 고려해 스케줄 간격보다 2~5분 더 넉넉하게 잡습니다.
    if weekday < 5: 
        # 평일 스케줄
        if 9 <= hour < 18:
            delta_mins = 6 + 2        # 6분 간격 실행 + 2분 버퍼 (8분 전까지 탐색)
        elif 18 <= hour < 22:
            delta_mins = 30 + 5       # 30분 간격 실행 + 5분 버퍼 (35분 전까지 탐색)
        else:
            # 밤 21시 종료 후 다음 날 아침 09시에 첫 실행될 때 (전날 밤의 내역 모두 추적)
            delta_mins = 12 * 60 + 30 # 12시간 + 30분 버퍼
    else: 
        # 주말 스케줄
        if 9 <= hour < 22:
            delta_mins = 60 + 5       # 1시간 간격 실행 + 5분 버퍼 (65분 전까지 탐색)
        else:
            # 밤 21시 종료 후 다음 날 아침 09시에 첫 실행될 때
            delta_mins = 12 * 60 + 30

    return now_utc - timedelta(minutes=delta_mins)

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
            
            # 동적으로 계산된 threshold 시간과 대조합니다.
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
    # 파일이나 캐시를 읽을 필요 없이 함수 하나로 임계 시간을 결정
    threshold = get_dynamic_threshold()
    
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

if __name__ == "__main__":
    run()
