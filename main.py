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

def get_changed_content(page_id, threshold):
    """페이지 내에서 최근에 수정된 1 depth 블록만 추출합니다."""
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=50"
        res = requests.get(url, headers=headers).json()
        blocks = res.get('results', [])
        
        texts = []
        for block in blocks:
            block_edited = datetime.fromisoformat(block['last_edited_time'].replace('Z', '+00:00'))
            
            # 임계 시간(최근 15분) 내에 수정된 블록만 필터링
            if block_edited > threshold:
                b_type = block.get('type')
                rich_text = block.get(b_type, {}).get('rich_text', [])
                
                if rich_text:
                    plain_text = "".join([t.get('plain_text', '') for t in rich_text]).strip()
                    if plain_text:
                        texts.append(plain_text)
                        
        if not texts:
            return "변경된 텍스트 내용 없음 (하위 계층, 이미지, 속성 등 변경)"
            
        full_text = " / ".join(texts)
        return full_text[:200] + "..." if len(full_text) > 200 else full_text
    except:
        return "본문 로드 실패"

def get_page_title(page):
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
            
            author_id = page.get('last_edited_by', {}).get('id')
            author = get_user_name(author_id)
            
            # 페이지의 변경 감지 시점인 threshold를 동일하게 전달하여 비교
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
            requests.post(DISCORD_WEBHOOK, json=discord_msg)

if __name__ == "__main__":
    run()
