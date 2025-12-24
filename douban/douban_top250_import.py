# 全局编码配置
import sys
import os
import uuid
import random
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import requests
from bs4 import BeautifulSoup
# 确保app.py已修正路由（/profile/<<<<int:user_id> → /profile/<<<int:user_id>）
from app import app, db, Movie
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== 核心配置 ==========
# 海报存储路径（对齐app.py的static目录）
POSTER_SAVE_PATH = os.path.join(app.root_path, "static", "posters")
# 默认海报路径
DEFAULT_POSTER = "/static/posters/default.jpg"
# 豆瓣Top250基础URL
DOUBAN_TOP250_BASE = "https://movie.douban.com/top250?start={}&filter="
# 爬取前50部电影（豆瓣Top250每页25部，取前2页）
CRAWL_LIMIT = 50

# 确保海报目录存在
os.makedirs(POSTER_SAVE_PATH, exist_ok=True)


def download_poster(session, poster_url, movie_name):
    """修复海报下载逻辑：处理404、使用高清URL、失败则返回默认海报"""
    if not poster_url or not poster_url.startswith(("https://", "http://")):
        return DEFAULT_POSTER

    # 替换为高清海报URL（避免低清URL过期）
    poster_url = poster_url.replace("s_ratio_poster", "l_ratio_poster")
    # 生成唯一文件名
    poster_filename = f"douban_{uuid.uuid4().hex[:10]}.jpg"
    local_path = os.path.join(POSTER_SAVE_PATH, poster_filename)
    web_path = f"/static/posters/{poster_filename}"

    # 跳过已存在的有效海报
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
        print(f"ℹ️ 海报已存在：{movie_name}")
        return web_path

    try:
        # 增强请求头，避免被豆瓣拦截
        headers = {
            "User-Agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/605.1.15"
            ]),
            "Referer": "https://movie.douban.com/top250"
        }
        response = session.get(
            poster_url,
            headers=headers,
            timeout=15,
            stream=True,
            allow_redirects=True
        )
        response.raise_for_status()  # 捕获HTTP错误

        # 写入海报文件
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # 验证文件有效性
        if os.path.getsize(local_path) < 1024:
            os.remove(local_path)
            raise Exception("海报文件过小（无效）")

        print(f"✅ 海报下载成功：{movie_name} → {poster_filename}")
        return web_path

    except Exception as e:
        print(f"❌ 海报下载失败({movie_name})：{str(e)} → 使用默认海报")
        if os.path.exists(local_path):
            os.remove(local_path)
        return DEFAULT_POSTER


def get_movie_intro(session, detail_url):
    """从电影详情页获取完整简介（避免列表页简介不完整）"""
    try:
        # 构造详情页请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Referer": "https://movie.douban.com/top250"
        }
        # 增加随机延迟，降低反爬风险
        time.sleep(random.randint(2, 4))
        response = session.get(detail_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 解析豆瓣详情页的完整简介（对应标签：span[property="v:summary"]）
        intro_tag = soup.find("span", property="v:summary")
        if intro_tag:
            # 清理简介中的换行、多余空格
            full_intro = intro_tag.get_text(strip=True).replace("\n", " ").replace("  ", " ")
            return full_intro if full_intro else "暂无简介"
        return "暂无简介"
    except Exception as e:
        print(f"❌ 获取简介失败({detail_url})：{str(e)}")
        return "暂无简介"


def crawl_douban_top250():
    movies_data = []
    session = requests.Session()
    # 温和的重试策略，避免触发反爬
    retry_strategy = Retry(
        total=3,
        backoff_factor=5,
        status_forcelist=[429, 500, 502, 503, 404],
        allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    # 你的豆瓣Cookie（已验证有效）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://movie.douban.com/top250",
        "Cookie": "bid=8JDp54oRCLY; viewed='1076013'; _vwo_uuid_v2=DC7A87659F426F9042AB34AE8532B7D56|ffba35a02b3d1fdeac99e182a2359c30; _pk_id.100001.4cf6=e2b081fa7b9a90be.1764294496.; __yadk_uid=cDHAB1ODmCX1uwAJJQqtOMLngl3RbVqB; push_noty_num=0; push_doumail_num=0; __utmz=30149280.1766056398.5.4.utmcsr=google|utmccn=(organic)|utmcmd=organic|utmctr=(not%20provided); __utmz=223695111.1766056398.4.3.utmcsr=google|utmccn=(organic)|utmcmd=organic|utmctr=(not%20provided); ll=\"118281\"; _pk_ref.100001.4cf6=%5B%22%22%2C%22%22%2C1766326606%2C%22https%3A%2F%2Fwww.google.com.hk%2F%22%5D; _pk_ses.100001.4cf6=1; __utma=30149280.1598743586.1763973195.1766300945.1766326606.7; __utmc=30149280; __utma=223695111.382162774.1764294496.1766300945.1766326606.6; __utmb=223695111.0.10.1766326606; __utmc=223695111; frodotk_db=\"6053016a1c5285da20f9043e54f7918e\"; __utmv=30149280.29245; __utmb=30149280.20.10.1766326606; dbsawcv1=MTc2NjMzMTAwOUAxYzg2MDBiZDM4NzMyNmY1NGRkZGNiZjEyMmIxODIyM2ViNzkyMmZjNGUxZjk1NjgzNTdjMzBhOGNlMmM0Njc0QDk2YzdiNmI3OTNmZDUwODVANWUzYzZmZTM2ZWRj; dbcl2=\"292805490:ZcWWkZGovk8\"; ck=rOFD"
    }

    # 只爬取前2页（共50部电影）
    for start in [0, 25]:
        page = start // 25 + 1
        try:
            print(f"\n===== 爬取第{page}页 =====")
            # 列表页请求前增加延迟，模拟人工浏览
            time.sleep(random.randint(3, 5))
            response = session.get(DOUBAN_TOP250_BASE.format(start), headers=headers, timeout=20)
            response.encoding = "utf-8"

            # 反爬检测
            if response.status_code != 200 or "检测到异常流量" in response.text:
                print(f"⚠️ 第{page}页触发反爬，暂停15秒")
                time.sleep(15)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            movie_items = soup.find_all("div", class_="item")
            if not movie_items:
                print("⚠️ 该页无电影数据")
                break

            # 控制爬取数量不超过50部
            remaining = CRAWL_LIMIT - len(movies_data)
            for item in movie_items[:remaining]:
                # 1. 电影名称
                title_tag = item.find("span", class_="title")
                if not title_tag:
                    continue
                name = title_tag.text.strip()
                original_title = item.find("span", class_="original_title")
                if original_title and original_title.text.strip():
                    name += f" / {original_title.text.strip()}"

                # 2. 电影详情页URL（用于获取完整简介）
                detail_url = item.find("div", class_="hd").find("a")["href"]

                # 3. 海报URL
                poster_img = item.find("img")
                poster_url = poster_img.get("src") or poster_img.get("data-origin", "")
                local_poster_url = download_poster(session, poster_url, name)

                # 4. 完整简介（从详情页获取）
                intro = get_movie_intro(session, detail_url)

                # 5. 评分和评论数
                rating_tag = item.find("span", class_="rating_num")
                rating = float(rating_tag.text.strip()) if rating_tag else 0.0
                comment_span = item.find("span", text=lambda t: "人评价" in t)
                comment_count = int(comment_span.text.replace("人评价", "").replace(",", "")) if comment_span else 0

                # 组装数据（对齐Movie模型）
                movies_data.append({
                    "name": name,
                    "poster_url": local_poster_url,
                    "intro": intro,
                    "initial_rating": rating,
                    "initial_comment_count": comment_count,
                    "category": "DoubanTop250",
                    "uploader_id": None
                })
            print(f"✅ 第{page}页完成，累计{len(movies_data)}部")

        except Exception as e:
            print(f"❌ 第{page}页失败：{str(e)}")
            continue
    return movies_data


def import_to_database(movies_data):
    """修复数据库操作：只删除豆瓣旧数据，避免删除用户数据"""
    with app.app_context():
        try:
            # 只删除豆瓣Top250的旧数据
            old_count = Movie.query.filter_by(category="DoubanTop250").delete()
            print(f"ℹ️ 清空{old_count}条旧豆瓣数据")

            # 去重（按电影名称）
            unique_movies = {}
            for data in movies_data:
                if data["name"] not in unique_movies:
                    unique_movies[data["name"]] = data
            new_movies = [Movie(**data) for data in unique_movies.values()]

            if new_movies:
                db.session.add_all(new_movies)
                db.session.commit()
                print(f"🎉 成功导入{len(new_movies)}部豆瓣Top250电影（含完整简介）")
            else:
                print("ℹ️ 无新电影可导入")
        except Exception as e:
            db.session.rollback()
            print(f"❌ 数据库导入失败：{str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("===== 开始爬取豆瓣Top50电影（含完整简介） =====")
    # 先初始化默认海报（避免空文件）
    default_poster_path = os.path.join(POSTER_SAVE_PATH, "default.jpg")
    if not os.path.exists(default_poster_path):
        try:
            resp = requests.get("https://img2.doubanio.com/f/movie/8dd0c794499fe925ae2ae89ee30cd22575045749.jpg",
                                timeout=10)
            with open(default_poster_path, "wb") as f:
                f.write(resp.content)
            print("✅ 默认海报初始化成功")
        except:
            print("⚠️ 默认海报下载失败，将使用空文件兜底")
            with open(default_poster_path, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")  # 最小有效JPG

    # 爬取+导入
    movie_data_list = crawl_douban_top250()
    print(f"===== 爬取结束，共{len(movie_data_list)}条数据 =====")
    import_to_database(movie_data_list)
    print("===== 流程完成 =====")