import requests
from datetime import datetime, timedelta, timezone
import os

NOTION_TOKEN = os.environ['NOTION_TOKEN']
DISCORD_WEBHOOK = os.environ['DISCORD_WEBHOOK']

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

user_cache = {}

def get_user_name(user_id):
    """유저 ID를 바탕으로 노션 API에 한 번 더 접근하여 실제 이름을 가져옵니다."""
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
    except:
        return "알 수 없는 사용자"

def get_content_summary(page_id):
    """페이지 하위 블록을 최대 20개까지 읽어와 전체 텍스트 내용을 이어붙입니다."""
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=20"
        res = requests.get(url, headers=headers).json()
        blocks = res.get('results', [])
        
        texts = []
        for block in blocks:
            b_type = block.get('type')
            rich_text = block.get(b_type, {}).get('rich_text', [])
            
            if rich_text:
                plain_text = "".join([t.get('plain_text', '') for t in rich_text]).strip()
                if plain_text:
                    texts.append(plain_text)
                    
        if not texts:
            return "본문 내용 없음"
            
        # 여러 블록의 텍스트를 슬래시로 구분하여 합칩니다.
        full_text = " / ".join(texts)
        return full_text[:200] + "..." if len(full_text) > 200 else full_text
    except:
        return "본문 로드 실패"

def get_page_title(page):
    """페이지 제목 추출"""
    props = page.get('properties', {})
    title = "제목 없음"
    title_key = next((k for k, v in props.items() if v.get('type') == 'title'), None)
    if title_key:
        t_list = props[title_key].get('title', [])
        if t_list: title = t_list[0]['plain_text']
    return title

def run():
    threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    search_url = "https://api.notion.com/v1/search"
    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    
    response = requests.post(search_url, headers=headers, json=payload).json()
    results = response.get('results', [])

    for page in results:
        last_edited = datetime.fromisoformat(page['last_edited_time'].replace('Z', '+00:00'))
        
        if last_edited > threshold:
            title = get_page_title(page)
            
            # 작성자의 고유 ID를 파악한 후, 별도 함수를 통해 이름을 추출합니다.
            author_id = page.get('last_edited_by', {}).get('id')
            author = get_user_name(author_id)
            
            summary = get_content_summary(page['id'])
            page_url = page['url']
            kst_time = last_edited.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
            
            discord_msg = {
                "embeds": [{
                    "title": f"🔔 변경 감지: {title}",
                    "url": page_url,
                    "color": 3447003,
                    "fields": [
                        {"name": "👤 수정자", "value": author, "inline": True},
                        {"name": "⏰ 수정 시각 (KST)", "value": kst_time, "inline": True},
                        {"name": "📝 내용 요약", "value": summary, "inline": False}
                    ],
                    "footer": {"text": "Notion Auto Monitor"}
                }]
            }
            requests.post(DISCORD_WEBHOOK, json=discord_msg)

if __name__ == "__main__":
    run()
