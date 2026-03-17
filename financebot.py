# 福生无量天尊
from openai import OpenAI
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import time
import pytz
import os
import base64

# 阿里云百炼 API Key
openai_api_key = os.getenv("OPENAI_API_KEY")
# WordPress 配置
wp_site_url = os.getenv("WP_SITE_URL")
wp_username = os.getenv("WP_USERNAME")
wp_app_password = os.getenv("WP_APP_PASSWORD")

if not openai_api_key:
    raise ValueError("环境变量 OPENAI_API_KEY 未设置，请在 Github Actions 中设置阿里云百炼 API Key！")
if not wp_site_url:
    raise ValueError("环境变量 WP_SITE_URL 未设置，请在 Github Actions 中设置！")
if not wp_username:
    raise ValueError("环境变量 WP_USERNAME 未设置，请在 Github Actions 中设置！")
if not wp_app_password:
    raise ValueError("环境变量 WP_APP_PASSWORD 未设置，请在 Github Actions 中设置！")

# 阿里云百炼 API 端点
openai_client = OpenAI(api_key=openai_api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

# RSS 源地址列表
rss_feeds = {
    "💲 华尔街见闻":{
        "华尔街见闻":"https://dedicated.wallstreetcn.com/rss.xml",      
    },
    "💻 36 氪":{
        "36 氪":"https://36kr.com/feed",   
        },
    "🇨🇳 中国经济": {
        "香港經濟日報":"https://www.hket.com/rss/china",
        "东方财富":"http://rss.eastmoney.com/rss_partener.xml",
        "百度股票焦点":"http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
        "中新网":"https://www.chinanews.com.cn/rss/finance.xml",
        "国家统计局 - 最新发布":"https://www.stats.gov.cn/sj/zxfb/rss.xml",
    },
      "🇺🇳 美国经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
        "华尔街日报 - 市场":"https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        "MarketWatch 美股": "https://www.marketwatch.com/rss/topstories",
        "ZeroHedge 华尔街新闻": "https://feeds.feedburner.com/zerohedge/feed",
        "ETF Trends": "https://www.etftrends.com/feed/",
    },
    "🌍 世界经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
        "BBC 全球经济": "http://feeds.bbci.co.uk/news/business/rss.xml",
    },
}

# 获取北京时间
def today_date():
    return datetime.now(pytz.timezone("Asia/Shanghai")).date()

# 爬取网页正文 (用于 AI 分析，但不展示)
def fetch_article_text(url):
    try:
        print(f"📰 正在爬取文章内容：{url}")
        article = Article(url)
        article.download()
        article.parse()
        text = article.text[:1500]  # 限制长度，防止超出 API 输入限制
        if not text:
            print(f"⚠️ 文章内容为空：{url}")
        return text
    except Exception as e:
        print(f"❌ 文章爬取失败：{url}，错误：{e}")
        return "（未能获取文章正文）"

# 添加 User-Agent 头
def fetch_feed_with_headers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    return feedparser.parse(url, request_headers=headers)


# 自动重试获取 RSS
def fetch_feed_with_retry(url, retries=3, delay=5):
    for i in range(retries):
        try:
            feed = fetch_feed_with_headers(url)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次请求 {url} 失败：{e}")
            time.sleep(delay)
    print(f"❌ 跳过 {url}, 尝试 {retries} 次后仍失败。")
    return None

# 获取 RSS 内容（爬取正文但不展示）
def fetch_rss_articles(rss_feeds, max_articles=10):
    news_data = {}
    analysis_text = ""  # 用于 AI 分析的正文内容

    for category, sources in rss_feeds.items():
        category_content = ""
        for source, url in sources.items():
            print(f"📡 正在获取 {source} 的 RSS 源：{url}")
            feed = fetch_feed_with_retry(url)
            if not feed:
                print(f"⚠️ 无法获取 {source} 的 RSS 数据")
                continue
            print(f"✅ {source} RSS 获取成功，共 {len(feed.entries)} 条新闻")

            articles = []  # 每个 source 都需要重新初始化列表
            for entry in feed.entries[:5]:
                title = entry.get('title', '无标题')
                link = entry.get('link', '') or entry.get('guid', '')
                if not link:
                    print(f"⚠️ {source} 的新闻 '{title}' 没有链接，跳过")
                    continue

                # 爬取正文用于分析（不展示）
                article_text = fetch_article_text(link)
                analysis_text += f"【{title}】\n{article_text}\n\n"

                print(f"🔹 {source} - {title} 获取成功")
                articles.append(f"- [{title}]({link})")

            if articles:
                category_content += f"### {source}\n" + "\n".join(articles) + "\n\n"

        news_data[category] = category_content

    return news_data, analysis_text

# AI 生成内容摘要（基于爬取的正文）
def summarize(text):
    completion = openai_client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": """
             你是一名专业的财经新闻分析师，请根据以下新闻内容，按照以下步骤完成任务：
             1. 提取新闻中涉及的主要行业和主题，找出近 1 天涨幅最高的 3 个行业或主题，以及近 3 天涨幅较高且此前 2 周表现平淡的 3 个行业/主题。（如新闻未提供具体涨幅，请结合描述和市场情绪推测热点）
             2. 针对每个热点，输出：
                - 催化剂：分析近期上涨的可能原因（政策、数据、事件、情绪等）。
                - 复盘：梳理过去 3 个月该行业/主题的核心逻辑、关键动态与阶段性走势。
                - 展望：判断该热点是短期炒作还是有持续行情潜力。
             3. 将以上分析整合为一篇 1500 字以内的财经热点摘要，逻辑清晰、重点突出，适合专业投资者阅读。
             """},
            {"role": "user", "content": text}
        ]
    )
    return completion.choices[0].message.content.strip()

# 发布到 WordPress
def publish_to_wordpress(title, content):
    """
    将内容发布到 WordPress 网站
    使用 WordPress REST API 创建并发布文章
    """
    # 创建认证头
    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    headers = {
        'Authorization': f'Basic {token}',
        'Content-Type': 'application/json'
    }
    
    # 将 Markdown 转换为 HTML（WordPress 使用 HTML）
    # 简单的 Markdown 转 HTML 处理
    html_content = content
    html_content = html_content.replace('\n\n', '</p><p>')
    html_content = html_content.replace('## ', '</p><h2>')
    html_content = html_content.replace('### ', '</h3><h3>')
    html_content = html_content.replace('**', '<strong>')
    html_content = html_content.replace('**', '</strong>')
    # 处理列表
    import re
    html_content = re.sub(r'^- \[(.*?)\]\((.*?)\)$', r'<li><a href="\2">\1</a></li>', html_content, flags=re.MULTILINE)
    html_content = html_content.replace('<li>', '</ul><ul><li>').replace('</li></ul>', '</li>')
    
    # 包装为完整 HTML
    html_content = f"<p>{html_content}</p>"
    html_content = html_content.replace('<p></p>', '')
    html_content = html_content.replace('<p><ul>', '<ul>').replace('</ul></p>', '</ul>')
    html_content = html_content.replace('<p><h2>', '<h2>').replace('</h2></p>', '</h2>')
    html_content = html_content.replace('<p></h3>', '</h3>').replace('</h3></p>', '</h3>')
    html_content = html_content.replace('<h2></ul>', '</h2><ul>').replace('</ul><h3>', '</ul><h3>')
    
    # WordPress API 端点
    api_url = f"{wp_site_url.rstrip('/')}/wp-json/wp/v2/posts"
    
    # 准备文章数据
    post_data = {
        "title": title,
        "content": html_content,
        "status": "publish",  # 直接发布，如需草稿改为 "draft"
        "excerpt": f"财经新闻摘要 - {today_date().strftime('%Y-%m-%d')}"
    }
    
    try:
        response = requests.post(api_url, json=post_data, headers=headers, timeout=30)
        
        if response.status_code == 201:
            post_info = response.json()
            post_url = post_info.get('link', '未知')
            post_id = post_info.get('id', '未知')
            print(f"✅ WordPress 发布成功！")
            print(f"   文章 ID: {post_id}")
            print(f"   链接：{post_url}")
            return {"success": True, "post_id": post_id, "url": post_url}
        else:
            print(f"❌ WordPress 发布失败：{response.status_code}")
            print(f"   响应：{response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        print(f"❌ WordPress 发布异常：{e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    today_str = today_date().strftime("%Y-%m-%d")

    # 每个网站获取最多 2 篇文章（测试模式）
    articles_data, analysis_text = fetch_rss_articles(rss_feeds, max_articles=2)
    
    # AI 生成摘要
    summary = summarize(analysis_text)

    # 生成仅展示标题和链接的最终消息
    final_summary = f"📅 **{today_str} 财经新闻摘要**\n\n✍️ **今日分析总结：**\n{summary}\n\n---\n\n"
    for category, content in articles_data.items():
        if content.strip():
            final_summary += f"## {category}\n{content}\n\n"

    # 发布到 WordPress
    publish_to_wordpress(
        title=f"📌 {today_str} 财经新闻摘要",
        content=final_summary
    )
