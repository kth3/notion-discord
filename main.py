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

def get_content_summary(page_id):
    """페이지 하위 블록을 조회하여 텍스트 내용을 추출합니다."""
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=5"
        res = requests.get(url, headers=headers).json()
        blocks = res.get('results', [])
        summary = ""
        for block in blocks:
            b_type = block.get('type')
            text_data = block.get(b_type, {}).get('rich_text', [])
            if text_data:
                summary += text_data[0].get('plain_text', '') + "\n"
        return summary.strip()[:200] if summary else "본문 내용이 없거나 읽을 수 없는 형식입니다."
    except:
        return "내용 로드 실패"

def get_page_info(page):
    """작성자, 제목, 수정시간 정보를 추출합니다."""
    props = page.get('properties', {})
    
    # 제목 추출 로직
    title = "제목 없음"
    title_key = next((k for k, v in props.items() if v.get('type') == 'title'), None)
    if title_key:
        t_list = props[title_key].get('title', [])
        if t_list: title = t_list[0]['plain_text']
        
    # 작성자(마지막 수정자) 추출
    author = page.get('last_edited_by', {}).get('name', '익명 사용자')
    
    return title, author

def run():
    # 실행 주기보다 조금 더 넓게(15분) 설정하여 누락 방지
    threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    search_url = "https://api.notion.com/v1/search"
    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    
    results = requests.post(search_url, headers=headers, json=payload).json().get('results', [])

    for page in results:
        last_edited = datetime.fromisoformat(page['last_edited_time'].replace('Z', '+00:00'))
        
        if last_edited > threshold:
            title, author = get_page_info(page)
            summary = get_content_summary(page['id'])
            kst_time = last_edited.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
            
            payload = {
                "embeds": [{
                    "title": f"🔔 변경 감지: {title}",
                    "url": page['url'],
                    "color": 3447003,
                    "fields": [
                        {"name": "👤 수정자", "value": author, "inline": True},
                        {"name": "⏰ 수정 시각 (KST)", "value": kst_time, "inline": True},
                        {"name": "📝 내용 요약", "value": summary, "inline": False}
                    ],
                    "footer": {"text": "Notion Auto Monitor"}
                }]
            }
            requests.post(DISCORD_WEBHOOK, json=payload)

if __name__ == "__main__":
    run()
