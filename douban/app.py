from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
import requests
from functools import wraps  # 统一导入装饰器工具

# ========== 新增：编码配置（解决控制台输出乱码） ==========
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 获取项目根目录的绝对路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "movie_rating.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = uuid.uuid4().hex  # 使用随机UUID作为密钥，更安全

# 头像/海报/背景图上传配置
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static')
# 确保目录存在
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'posters'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'bg'), exist_ok=True)  # 新增：个人主页背景目录
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)


# ========== 模型定义（完全保留原有逻辑） ==========
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nickname = db.Column(db.String(50), unique=True, nullable=False)  # 用户昵称（唯一）
    gender = db.Column(db.String(10), default='未知')
    avatar = db.Column(db.String(200), default='/static/avatars/default.jpg')
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 新增：用户角色（普通用户/管理员）
    role = db.Column(db.String(10), default='user')  # 'user'/'admin'
    # 新增：个人主页背景图
    profile_bg = db.Column(db.String(200), default='/static/bg/default_profile_bg.jpg')


class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)  # 电影名称唯一，避免重复
    poster_url = db.Column(db.String(500), default='/static/posters/default.jpg')
    intro = db.Column(db.Text, default='暂无简介')
    initial_rating = db.Column(db.Float, default=0.0)  # 初始评分（如豆瓣评分）
    initial_comment_count = db.Column(db.Integer, default=0)
    category = db.Column(db.String(20), default='UserUpload')  # DoubanTop250 / UserUpload
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 上传用户ID
    # 新增：电影审核状态（普通用户添加需审核）
    status = db.Column(db.String(10), default='approved')  # 'pending'/'approved'
    create_time = db.Column(db.DateTime, default=datetime.now)  # 新增：电影创建时间（用于排序）

    uploader = db.relationship('User', backref=db.backref('uploaded_movies', lazy=True))


class UserRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # 新增：多维度评分（0-10分）
    plot_score = db.Column(db.Float)  # 剧情
    acting_score = db.Column(db.Float)  # 演技
    visual_score = db.Column(db.Float)  # 画面
    music_score = db.Column(db.Float)  # 配乐
    rhythm_score = db.Column(db.Float)  # 节奏（新增）
    theme_score = db.Column(db.Float)  # 立意（新增）
    # 综合评分（自动计算）
    user_rating = db.Column(db.Float)  # 综合分 = (剧情+演技+画面+配乐+节奏+立意)/6
    user_comment = db.Column(db.Text)
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 唯一约束：一个用户对一部电影只能有一个评分
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id', name='_user_movie_rating_uc'),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)
    ip_province = db.Column(db.String(50), default='未知')
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    movie = db.relationship('Movie', backref=db.backref('comments', lazy=True))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True)


class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('comment_id', 'user_id', name='_comment_user_like_uc'),)


# 新增：标签表（存储所有可用标签）
class MovieTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)  # 标签名（如“催泪”）


# 新增：用户-电影-标签关联表（记录用户给电影打的标签）
class UserMovieTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('movie_tag.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id', 'tag_id', name='_user_movie_tag_uc'),)


# 新增：用户观影状态表（想看/在看/已看）
class UserMovieStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'wish'/'watching'/'watched'
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id', name='_user_movie_status_uc'),)


# 新增：用户电影收藏表
class UserMovieCollection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id', name='_user_movie_collection_uc'),)


# 新增：评论点赞/踩表
class CommentVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    vote_type = db.Column(db.String(10), nullable=False)  # 'like'/'dislike'
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='_user_comment_vote_uc'),)


# ========== 工具函数（完全保留原有逻辑） ==========
def generate_unique_nickname():
    """生成唯一昵称"""
    while True:
        nickname = uuid.uuid4().hex[:8]
        if not User.query.filter_by(nickname=nickname).first():
            return nickname


def get_ip_province(ip):
    """获取IP所在省份"""
    if ip in ['127.0.0.1', '::1'] or ip.startswith('192.168.'):
        return '本地'
    amap_key = '你的高德API Key'  # 替换为实际Key
    if not amap_key or amap_key == '你的高德API Key':
        return '未知'
    try:
        response = requests.get(
            url=f'https://restapi.amap.com/v3/ip?key={amap_key}&ip={ip}',
            timeout=5
        )
        data = response.json()
        return data.get('province', '未知') if data.get('status') == '1' else '未知'
    except Exception as e:
        print(f"IP解析失败: {str(e)}")
        return '未知'


def login_required(f):
    """登录验证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))  # 新增：记录跳转前URL
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """管理员权限验证装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if user.role != 'admin':
            flash('无管理员操作权限')
            return redirect(url_for('index'))  # 保留：跳转到原index路由
        return f(*args, **kwargs)

    return decorated_function


def allowed_file(filename):
    """验证文件格式"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def download_remote_image(url, save_subdir='posters'):
    """下载远程图片到本地静态文件夹（增加容错）"""
    if not url or not url.startswith(('http://', 'https://')):
        return f'/static/{save_subdir}/default.jpg'

    filename = f"{save_subdir}_{uuid.uuid4().hex[:12]}.jpg"
    save_dir = os.path.join(app.config['UPLOAD_FOLDER'], save_subdir)
    os.makedirs(save_dir, exist_ok=True)  # 确保目录存在
    save_path = os.path.join(save_dir, filename)
    web_path = f'/static/{save_subdir}/{filename}'

    if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
        return web_path

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            'Referer': 'https://movie.douban.com/'
        }
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if os.path.getsize(save_path) < 1024:
            os.remove(save_path)
            return f'/static/{save_subdir}/default.jpg'

        return web_path
    except Exception as e:
        print(f"下载图片失败：{url} → {str(e)}")
        if os.path.exists(save_path):
            os.remove(save_path)
        return f'/static/{save_subdir}/default.jpg'


def calculate_composite_rating(plot, acting, visual, music, rhythm, theme):
    """计算6个维度的综合评分"""
    scores = [s for s in [plot, acting, visual, music, rhythm, theme] if s is not None]
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def init_default_images():
    """初始化默认图片（头像、海报、个人主页背景）"""
    # 最小有效JPG（130字节，确保能正常显示）
    MIN_VALID_JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xfe\x00\x1fCreated by Python\x00\xff\xd9"

    # 1. 默认头像
    default_avatar = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', 'default.jpg')
    if not os.path.exists(default_avatar) or os.path.getsize(default_avatar) < 512:
        try:
            resp = requests.get('https://img-blog.csdnimg.cn/20240101150000.jpg', timeout=10)
            with open(default_avatar, 'wb') as f:
                f.write(resp.content)
            print("✅ 默认头像下载成功")
        except Exception as e:
            print(f"⚠️ 默认头像下载失败，使用占位图：{e}")
            with open(default_avatar, 'wb') as f:
                f.write(MIN_VALID_JPG)

    # 2. 默认海报
    default_poster = os.path.join(app.config['UPLOAD_FOLDER'], 'posters', 'default.jpg')
    if not os.path.exists(default_poster) or os.path.getsize(default_poster) < 512:
        try:
            resp = requests.get('https://img2.doubanio.com/f/movie/8dd0c794499fe925ae2ae89ee30cd22575045749.jpg',
                                timeout=10)
            with open(default_poster, 'wb') as f:
                f.write(resp.content)
            print("✅ 默认海报下载成功")
        except Exception as e:
            print(f"⚠️ 默认海报下载失败，使用占位图：{e}")
            with open(default_poster, 'wb') as f:
                f.write(MIN_VALID_JPG)

    # 3. 默认个人主页背景
    default_bg = os.path.join(app.config['UPLOAD_FOLDER'], 'bg', 'default_profile_bg.jpg')
    if not os.path.exists(default_bg) or os.path.getsize(default_bg) < 512:
        try:
            resp = requests.get(
                'https://img.zcool.cn/community/0117e2571b8b246ac72538120dd8a4.jpg@1280w_1l_2o_100sh.jpg',
                timeout=10)
            with open(default_bg, 'wb') as f:
                f.write(resp.content)
            print("✅ 默认个人主页背景下载成功")
        except Exception as e:
            print(f"⚠️ 默认个人主页背景下载失败，使用占位图：{e}")
            with open(default_bg, 'wb') as f:
                f.write(MIN_VALID_JPG)


def calculate_average_rating(movie_id):
    """计算电影的平均评分（过滤无效评分）"""
    ratings = UserRating.query.filter_by(movie_id=movie_id).all()
    valid_ratings = [r.user_rating for r in ratings if r.user_rating is not None]
    if not valid_ratings:
        return 0.0
    total = sum(valid_ratings)
    return round(total / len(valid_ratings), 1)


# ========== 初始化数据库（完全保留原有逻辑） ==========
with app.app_context():
    try:
        init_default_images()
        db.create_all()
        print("✅ 数据库初始化成功！")

        # 初始化管理员账号（首次运行自动创建，之后可删除）
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=generate_password_hash('admin123', method='pbkdf2:sha256'),
                nickname='管理员',
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ 管理员账号创建成功：用户名admin，密码admin123")

        if not Movie.query.first():
            sample_movies_data = [
                {
                    "name": "肖申克的救赎 / The Shawshank Redemption",
                    "poster_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p480747492.jpg",
                    "intro": "导演: 弗兰克·德拉邦特 | 主演: 蒂姆·罗宾斯 / 摩根·弗里曼 | 1994 / 美国 / 犯罪 剧情",
                    "initial_rating": 9.7,
                    "initial_comment_count": 2323092,
                    "category": 'DoubanTop250',
                    "uploader_id": None,
                    "status": 'approved'
                },
                {
                    "name": "霸王别姬 / Farewell My Concubine",
                    "poster_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2561716440.jpg",
                    "intro": "导演: 陈凯歌 | 主演: 张国荣 / 张丰毅 / 巩俐 | 1993 / 中国大陆 中国香港 / 剧情 爱情 同性",
                    "initial_rating": 9.6,
                    "initial_comment_count": 2386348,
                    "category": 'DoubanTop250',
                    "uploader_id": None,
                    "status": 'approved'
                },
                {
                    "name": "泰坦尼克号 / Titanic",
                    "poster_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p1910813120.jpg",
                    "intro": "导演: 詹姆斯·卡梅隆 | 主演: 莱昂纳多·迪卡普里奥 / 凯特·温丝莱特 | 1997 / 美国 / 剧情 爱情 灾难",
                    "initial_rating": 9.5,
                    "initial_comment_count": 1890000,
                    "category": 'DoubanTop250',
                    "uploader_id": None,
                    "status": 'approved'
                },
                {
                    "name": "阿甘正传 / Forrest Gump",
                    "poster_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2372307693.jpg",
                    "intro": "导演: 罗伯特·泽米吉斯 | 主演: 汤姆·汉克斯 / 罗宾·怀特 | 1994 / 美国 / 剧情 爱情",
                    "initial_rating": 9.5,
                    "initial_comment_count": 1780000,
                    "category": 'DoubanTop250',
                    "uploader_id": None,
                    "status": 'approved'
                },
                {
                    "name": "千与千寻 / 千と千尋の神隠し",
                    "poster_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p2557573348.jpg",
                    "intro": "导演: 宫崎骏 | 主演: 柊瑠美 / 入野自由 / 夏木真理 | 2001 / 日本 / 剧情 动画 奇幻",
                    "initial_rating": 9.4,
                    "initial_comment_count": 2000000,
                    "category": 'DoubanTop250',
                    "uploader_id": None,
                    "status": 'approved'
                }
            ]
            sample_movies = []
            for data in sample_movies_data:
                if not Movie.query.filter_by(name=data['name']).first():  # 避免重复添加
                    local_poster_url = download_remote_image(data['poster_url'], 'posters')
                    data['poster_url'] = local_poster_url
                    sample_movies.append(Movie(**data))
            if sample_movies:
                db.session.add_all(sample_movies)
                db.session.commit()
                print("✅ 豆瓣Top250示例数据添加成功！")
            else:
                print("ℹ️ 无新示例数据可添加")
    except Exception as e:
        print(f"❌ 数据库初始化失败：{str(e)}")
        import traceback

        traceback.print_exc()


# ========== 路由（核心调整：保留index，新增poster路由） ==========
# 新增：海报首页路由（无需登录，独立路由）
@app.route('/poster')
def poster_home():
    return render_template('poster_index.html')


# 新增：获取本地海报数据接口（供海报页面调用）
@app.route('/get_local_posters')
def get_local_posters():
    try:
        # 从数据库获取豆瓣Top250电影作为海报数据
        poster_movies = Movie.query.filter_by(category='DoubanTop250', status='approved').order_by(Movie.id.asc()).limit(10).all()
        posters = []
        for movie in poster_movies:
            posters.append({
                "movie_name": movie.name.split(' / ')[0] if ' / ' in movie.name else movie.name,
                "poster_url": movie.poster_url,
                "detail_url": f"/index#movie_{movie.id}"  # 跳转到原index路由对应电影
            })
        return jsonify({
            "status": "success",
            "data": posters
        })
    except Exception as e:
        print(f"获取海报数据失败：{e}")
        return jsonify({
            "status": "error",
            "msg": "获取海报数据失败",
            "data": []
        })


# 保留：原index路由（评分系统首页，需登录，完全不变）
@app.route('/index')
@login_required
def index():
    user = User.query.get(session['user_id'])
    return render_template('index.html', username=session.get('username'), nickname=user.nickname)


# 可选：设置默认访问海报页（也可保留原逻辑，访问/直接跳index）
@app.route('/')
def default_home():
    return redirect(url_for('poster_home'))  # 访问根目录跳海报页，也可改为 redirect(url_for('index'))


# 合并后的get_movies路由（支持分类、排序，完全保留原有逻辑）
@app.route('/get_movies')
@login_required
def get_movies():
    try:
        # 新增：支持分类和排序
        category = request.args.get('category')
        sort = request.args.get('sort', 'default')

        # 普通用户只能看已审核的电影，管理员可看所有
        user = User.query.get(session['user_id'])
        if user.role == 'admin':
            query = Movie.query
        else:
            query = Movie.query.filter_by(status='approved')

        # 分类筛选
        if category:
            query = query.filter_by(category=category)
        # 排序（热门=评论数多，新上线=上传时间新）
        # 排序（热门=评论数多，新上线=上传时间新）
        if sort == 'hot':
            query = query.join(Comment, isouter=True).group_by(Movie.id).order_by(db.func.count(Comment.id).desc())
        elif sort == 'new':
            query = query.order_by(Movie.create_time.desc())
        else:
            # 关键修改：id升序 = 爬取顺序（原是id.desc()）
            query = query.order_by(Movie.id.asc())

        movies = query.all()
        result = []
        user_id = session.get('user_id')
        for movie in movies:
            # 处理评论数（空值兜底）
            user_comment_count = Comment.query.filter_by(movie_id=movie.id).count() or 0
            # 处理用户评分（空值兜底）
            user_rating = UserRating.query.filter_by(user_id=user_id, movie_id=movie.id).first()
            # 上传者昵称（空值兜底）
            uploader_nickname = movie.uploader.nickname if (movie.uploader and movie.uploader.nickname) else '未知'
            # 计算平均评分
            avg_rating = calculate_average_rating(movie.id)
            display_rating = avg_rating if avg_rating > 0 else movie.initial_rating

            result.append({
                "id": movie.id,
                "name": movie.name,
                "poster_url": movie.poster_url or '/static/posters/default.jpg',  # 海报空值兜底
                "intro": movie.intro or '暂无简介',  # 简介空值兜底
                "initial_rating": movie.initial_rating or 0.0,
                "average_rating": display_rating,
                "user_comment_count": user_comment_count,
                "user_rating": user_rating.user_rating if (
                        user_rating and user_rating.user_rating is not None) else None,
                "user_comment": user_rating.user_comment if (user_rating and user_rating.user_comment) else None,
                "category": movie.category or 'UserUpload',
                "uploader_nickname": uploader_nickname,
                "status": movie.status
            })
        # 返回前端期望的格式（包含status和data）
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        print(f"❌ /get_movies 接口错误：{str(e)}")
        return jsonify({"status": "error", "msg": f"获取数据失败：{str(e)[:50]}"})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('请输入用户名和密码！')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password, password):
            flash('用户名或密码错误！')
            return redirect(url_for('login'))

        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role  # 存储用户角色

        # 保留：登录成功后跳转到index路由
        next_url = request.args.get('next', url_for('index'))
        return redirect(next_url)

    # GET请求：显示登录页面
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_pwd = request.form.get('confirm_pwd')

        if not username or not password:
            flash('用户名和密码不能为空！')
            return redirect(url_for('register'))
        if password != confirm_pwd:
            flash('两次密码不一致！')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('用户名已存在！')
            return redirect(url_for('register'))

        try:
            new_user = User(
                username=username,
                password=generate_password_hash(password, method='pbkdf2:sha256'),
                nickname=generate_unique_nickname()
            )
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功，请登录！')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'注册失败：{str(e)}')
            return redirect(url_for('register'))
    return render_template('register.html')


@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    target_user = User.query.get_or_404(user_id)
    current_user = User.query.get(session['user_id'])
    return render_template('profile.html',
                           target_user=target_user,
                           current_user=current_user)


@app.route('/profile_data/<int:user_id>')
@login_required
def profile_data(user_id):
    target_user = User.query.get_or_404(user_id)
    current_user = User.query.get(session['user_id'])

    # 1. 评分统计
    ratings = UserRating.query.filter_by(user_id=target_user.id).all()
    avg_rating = 0.0
    top_category = "无"
    if ratings:
        avg_rating = round(sum(r.user_rating for r in ratings) / len(ratings), 1)
        # 常看类型
        category_count = {}
        for r in ratings:
            movie = Movie.query.get(r.movie_id)
            if movie and movie.category:
                category_count[movie.category] = category_count.get(movie.category, 0) + 1
        if category_count:
            top_category = max(category_count.items(), key=lambda x: x[1])[0]

    # 2. 观影状态列表
    status_movies = []
    statuses = UserMovieStatus.query.filter_by(user_id=target_user.id).all()
    for s in statuses:
        movie = Movie.query.get(s.movie_id)
        if movie and movie.status == 'approved':
            status_movies.append({
                "id": movie.id,
                "name": movie.name,
                "poster_url": movie.poster_url,
                "status": s.status
            })

    # 3. 收藏列表
    collect_movies = []
    collections = UserMovieCollection.query.filter_by(user_id=target_user.id).all()
    for c in collections:
        movie = Movie.query.get(c.movie_id)
        if movie and movie.status == 'approved':
            collect_movies.append({
                "id": movie.id,
                "name": movie.name,
                "poster_url": movie.poster_url
            })

    # 4. 上传的电影（仅自己或管理员可见）
    uploaded_movies = []
    if current_user.id == target_user.id or current_user.role == 'admin':
        uploads = Movie.query.filter_by(uploader_id=target_user.id).all()
        for m in uploads:
            uploaded_movies.append({
                "id": m.id,
                "name": m.name,
                "poster_url": m.poster_url,
                "status": m.status
            })

    return jsonify({
        "status": "success",
        "data": {
            "user": {
                "id": target_user.id,
                "nickname": target_user.nickname,
                "avatar": target_user.avatar,
                "profile_bg": target_user.profile_bg,
                "create_time": target_user.create_time.strftime('%Y-%m-%d')
            },
            "rating_stats": {
                "avg_rating": avg_rating,
                "top_category": top_category
            },
            "status_movies": status_movies,
            "collect_movies": collect_movies,
            "uploaded_movies": uploaded_movies
        }
    })


@app.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
    user = User.query.get(session['user_id'])
    # 修改性别
    user.gender = request.form.get('gender') or user.gender

    # 修改头像
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"avatar_{uuid.uuid4()}_{secure_filename(file.filename)}"
            filename = filename[:50] + f'.{ext}' if len(filename) > 50 else filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', filename))
            user.avatar = f"/static/avatars/{filename}"

    # 修改个人主页背景
    if 'profile_bg' in request.files:
        file = request.files['profile_bg']
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"bg_{uuid.uuid4()}_{secure_filename(file.filename)}"
            filename = filename[:50] + f'.{ext}' if len(filename) > 50 else filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'bg', filename))
            user.profile_bg = f"/static/bg/{filename}"

    db.session.commit()
    flash('信息修改成功！')
    return redirect(url_for('profile', user_id=session['user_id']))


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('poster_home'))  # 退出后返回海报页，也可改为 redirect(url_for('index'))


@app.route('/search')
@login_required
def search_movie():
    try:
        keyword = request.args.get('keyword', '').strip()
        # 普通用户仅搜索已审核电影
        user = User.query.get(session['user_id'])
        if user.role == 'admin':
            movies = Movie.query.filter(Movie.name.like(f'%{keyword}%')).all()
        else:
            movies = Movie.query.filter(Movie.name.like(f'%{keyword}%'), Movie.status == 'approved').all()

        result = []
        user_id = session.get('user_id')
        for movie in movies:
            user_comment_count = Comment.query.filter_by(movie_id=movie.id).count() or 0
            user_rating = UserRating.query.filter_by(user_id=user_id, movie_id=movie.id).first()
            uploader_nickname = movie.uploader.nickname if (movie.uploader and movie.uploader.nickname) else '未知'
            avg_rating = calculate_average_rating(movie.id)
            display_rating = avg_rating if avg_rating > 0 else movie.initial_rating

            result.append({
                "id": movie.id,
                "name": movie.name,
                "poster_url": movie.poster_url or '/static/posters/default.jpg',
                "intro": movie.intro or '暂无简介',
                "initial_rating": movie.initial_rating or 0.0,
                "average_rating": display_rating,
                "user_comment_count": user_comment_count,
                "user_rating": user_rating.user_rating if (
                        user_rating and user_rating.user_rating is not None) else None,
                "user_comment": user_rating.user_comment if (user_rating and user_rating.user_comment) else None,
                "category": movie.category or 'UserUpload',
                "uploader_nickname": uploader_nickname
            })
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        print(f"❌ /search 接口错误：{str(e)}")
        return jsonify({"status": "error", "msg": f"搜索失败：{str(e)[:50]}"})


@app.route('/add_movie', methods=['POST'])
@login_required
def add_movie():
    name = request.form.get('movie_name').strip()
    intro = request.form.get('movie_intro', '暂无简介').strip()

    if not name:
        return jsonify({"status": "error", "msg": "电影名称不能为空"}), 400

    # 检查电影名称是否已存在
    if Movie.query.filter_by(name=name).first():
        return jsonify({"status": "error", "msg": "该电影已存在"}), 400

    poster_url = '/static/posters/default.jpg'
    if 'movie_poster' in request.files:
        file = request.files['movie_poster']
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"poster_{uuid.uuid4()}_{secure_filename(file.filename)}"
            filename = filename[:50] + f'.{ext}' if len(filename) > 50 else filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'posters', filename))
            poster_url = f"/static/posters/{filename}"

    # 管理员添加的电影直接通过，普通用户需审核
    user = User.query.get(session['user_id'])
    status = 'approved' if user.role == 'admin' else 'pending'

    new_movie = Movie(
        name=name,
        intro=intro,
        poster_url=poster_url,
        category='UserUpload',
        uploader_id=session['user_id'],
        status=status,
        create_time=datetime.now()  # 新增：记录创建时间
    )
    db.session.add(new_movie)
    db.session.commit()

    msg = "电影添加成功（已自动审核通过）" if user.role == 'admin' else "电影添加成功，等待管理员审核"
    return jsonify({"status": "success", "msg": msg, "movie_id": new_movie.id})


# 新增：星级评分接口
@app.route('/submit_star_rating', methods=['POST'])
@login_required
def submit_star_rating():
    data = request.json
    movie_id = data.get('movie_id')
    score = data.get('score')

    # 验证评分范围
    if not (0 <= score <= 10):
        return jsonify({"status": "error", "msg": "评分需在0-10之间"})

    # 验证电影存在
    movie = Movie.query.get(movie_id)
    if not movie:
        return jsonify({"status": "error", "msg": "电影不存在"})

    # 新增/更新星级评分（复用UserRating表）
    existing = UserRating.query.filter_by(user_id=session['user_id'], movie_id=movie_id).first()
    if existing:
        existing.user_rating = score
    else:
        new_rating = UserRating(
            user_id=session['user_id'],
            movie_id=movie_id,
            user_rating=score
        )
        db.session.add(new_rating)
    db.session.commit()

    return jsonify({"status": "success", "msg": "星级评分提交成功"})


# 修改：多维度评分接口（支持6个维度）
@app.route('/submit_multi_rating', methods=['POST'])
@login_required
def submit_multi_rating():
    user_id = session['user_id']
    data = request.json
    movie_id = data.get('movie_id')
    plot = data.get('plot')
    acting = data.get('acting')
    visual = data.get('visual')
    music = data.get('music')
    rhythm = data.get('rhythm')
    theme = data.get('theme')

    # 验证评分范围
    for score in [plot, acting, visual, music, rhythm, theme]:
        if score is not None:
            try:
                score_val = float(score)
                if not (0 <= score_val <= 10):
                    return jsonify({"status": "error", "msg": "评分必须在0-10之间"}), 400
            except (ValueError, TypeError):
                return jsonify({"status": "error", "msg": "评分格式错误"}), 400

    # 验证电影
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    # 新增/更新多维度评分
    existing = UserRating.query.filter_by(user_id=user_id, movie_id=movie_id).first()
    if existing:
        existing.plot_score = plot
        existing.acting_score = acting
        existing.visual_score = visual
        existing.music_score = music
        existing.rhythm_score = rhythm  # 新增
        existing.theme_score = theme  # 新增
        existing.user_rating = calculate_composite_rating(plot, acting, visual, music, rhythm, theme)
    else:
        new_rating = UserRating(
            user_id=user_id, movie_id=movie_id,
            plot_score=plot, acting_score=acting, visual_score=visual,
            music_score=music, rhythm_score=rhythm, theme_score=theme,
            user_rating=calculate_composite_rating(plot, acting, visual, music, rhythm, theme)
        )
        db.session.add(new_rating)
    db.session.commit()
    return jsonify({"status": "success", "msg": "多维度评分提交成功"})


@app.route('/add_movie_tag', methods=['POST'])
@login_required
def add_movie_tag():
    data = request.json
    movie_id = data.get('movie_id')
    tag_name = data.get('tag_name').strip()
    if not tag_name:
        return jsonify({"status": "error", "msg": "标签不能为空"}), 400

    # 验证电影存在且已审核
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    # 查找/创建标签
    tag = MovieTag.query.filter_by(name=tag_name).first()
    if not tag:
        tag = MovieTag(name=tag_name)
        db.session.add(tag)
        db.session.commit()

    # 关联用户-电影-标签
    existing = UserMovieTag.query.filter_by(
        user_id=session['user_id'], movie_id=movie_id, tag_id=tag.id
    ).first()
    if existing:
        return jsonify({"status": "error", "msg": "你已给该电影打此标签"}), 400

    new_tag = UserMovieTag(user_id=session['user_id'], movie_id=movie_id, tag_id=tag.id)
    db.session.add(new_tag)
    db.session.commit()
    return jsonify({"status": "success", "msg": "标签添加成功"})


@app.route('/update_movie_status', methods=['POST'])
@login_required
def update_movie_status():
    data = request.json
    movie_id = data.get('movie_id')
    status = data.get('status')
    if status not in ['wish', 'watching', 'watched']:
        return jsonify({"status": "error", "msg": "状态无效"}), 400

    # 验证电影存在且已审核
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    existing = UserMovieStatus.query.filter_by(user_id=session['user_id'], movie_id=movie_id).first()
    if existing:
        existing.status = status
    else:
        new_status = UserMovieStatus(user_id=session['user_id'], movie_id=movie_id, status=status)
        db.session.add(new_status)
    db.session.commit()
    return jsonify({"status": "success", "msg": "观影状态更新成功"})


@app.route('/toggle_movie_collection', methods=['POST'])
@login_required
def toggle_movie_collection():
    data = request.json
    movie_id = data.get('movie_id')

    # 验证电影存在且已审核
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    existing = UserMovieCollection.query.filter_by(user_id=session['user_id'], movie_id=movie_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "success", "msg": "已取消收藏"})
    else:
        new_collect = UserMovieCollection(user_id=session['user_id'], movie_id=movie_id)
        db.session.add(new_collect)
        db.session.commit()
        return jsonify({"status": "success", "msg": "已收藏"})


@app.route('/vote_comment', methods=['POST'])
@login_required
def vote_comment():
    data = request.json
    comment_id = data.get('comment_id')
    vote_type = data.get('vote_type')
    if vote_type not in ['like', 'dislike']:
        return jsonify({"status": "error", "msg": "投票类型无效"}), 400

    # 验证评论存在
    comment = Comment.query.get(comment_id)
    if not comment:
        return jsonify({"status": "error", "msg": "评论不存在"}), 404

    existing = CommentVote.query.filter_by(user_id=session['user_id'], comment_id=comment_id).first()
    if existing:
        if existing.vote_type == vote_type:
            db.session.delete(existing)
            db.session.commit()
            return jsonify({"status": "success", "msg": f"已取消{vote_type}"})
        else:
            existing.vote_type = vote_type
    else:
        new_vote = CommentVote(user_id=session['user_id'], comment_id=comment_id, vote_type=vote_type)
        db.session.add(new_vote)
    db.session.commit()
    # 返回当前点赞/踩数量
    like_count = CommentVote.query.filter_by(comment_id=comment_id, vote_type='like').count()
    dislike_count = CommentVote.query.filter_by(comment_id=comment_id, vote_type='dislike').count()
    return jsonify(
        {"status": "success", "msg": f"已{vote_type}", "like_count": like_count, "dislike_count": dislike_count})


@app.route('/approve_movie/<int:movie_id>', methods=['POST'])
@admin_required
def approve_movie(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        return jsonify({"status": "error", "msg": "电影不存在"}), 404
    if movie.status == 'approved':
        return jsonify({"status": "error", "msg": "该电影已审核通过"}), 400
    movie.status = 'approved'
    db.session.commit()
    return jsonify({"status": "success", "msg": "电影已审核通过"})


@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    # 统计数据
    total_movies = Movie.query.count()
    pending_movies = Movie.query.filter_by(status='pending').count()
    approved_movies = Movie.query.filter_by(status='approved').count()
    total_users = User.query.count()
    admin_users = User.query.filter_by(role='admin').count()

    # 热门电影TOP10（按评论数）
    top_movies = db.session.query(Movie, db.func.count(Comment.movie_id)) \
        .join(Comment, Movie.id == Comment.movie_id, isouter=True) \
        .filter(Movie.status == 'approved') \
        .group_by(Movie.id) \
        .order_by(db.func.count(Comment.id).desc()) \
        .limit(10).all()
    top_movies_data = [{"id": m.id, "name": m.name, "comment_count": cnt} for m, cnt in top_movies]

    # 待审核电影列表
    pending_movies_list = Movie.query.filter_by(status='pending').all()

    return render_template('admin_dashboard.html',
                           total_movies=total_movies,
                           pending_movies=pending_movies,
                           approved_movies=approved_movies,
                           total_users=total_users,
                           admin_users=admin_users,
                           top_movies=top_movies_data,
                           pending_movies_list=pending_movies_list)


@app.route('/submit_comment', methods=['POST'])
@login_required
def submit_comment():
    data = request.json
    movie_id = data.get('movie_id')
    content = data.get('content', '').strip()
    parent_id = data.get('parent_id')

    if not movie_id or not content:
        return jsonify({"status": "error", "msg": "电影ID和评论内容不能为空"})

    # 验证电影存在且已审核
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    user_ip = request.remote_addr
    province = get_ip_province(user_ip)

    new_comment = Comment(
        movie_id=movie_id,
        user_id=session['user_id'],
        content=content,
        ip_province=province,
        parent_id=parent_id if parent_id and Comment.query.get(parent_id) else None
    )
    db.session.add(new_comment)
    db.session.commit()

    user = User.query.get(session['user_id'])
    parent_user_nickname = ""
    if new_comment.parent_id:
        parent_comment = Comment.query.get(new_comment.parent_id)
        parent_user = User.query.get(parent_comment.user_id)
        parent_user_nickname = parent_user.nickname

    # 获取评论的点赞/踩数量
    like_count = CommentVote.query.filter_by(comment_id=new_comment.id, vote_type='like').count()
    dislike_count = CommentVote.query.filter_by(comment_id=new_comment.id, vote_type='dislike').count()

    return jsonify({
        "status": "success",
        "comment": {
            "id": new_comment.id,
            "content": new_comment.content,
            "create_time": new_comment.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            "ip_province": new_comment.ip_province,
            "user": {
                "id": user.id,
                "nickname": user.nickname,
                "avatar": user.avatar,
                "username": user.username
            },
            "parent_id": new_comment.parent_id,
            "parent_user_nickname": parent_user_nickname,
            "like_count": like_count,
            "dislike_count": dislike_count
        }
    })


# 修改：获取电影多维度评分平均值（支持6个维度）
@app.route('/get_multi_rating_avg/<int:movie_id>')
@login_required
def get_multi_rating_avg(movie_id):
    ratings = UserRating.query.filter_by(movie_id=movie_id).all()
    if not ratings:
        return jsonify({"status": "success", "data": {}})

    plot_total = acting_total = visual_total = music_total = rhythm_total = theme_total = 0
    count = 0
    for r in ratings:
        if r.plot_score: plot_total += r.plot_score
        if r.acting_score: acting_total += r.acting_score
        if r.visual_score: visual_total += r.visual_score
        if r.music_score: music_total += r.music_score
        if r.rhythm_score: rhythm_total += r.rhythm_score  # 新增
        if r.theme_score: theme_total += r.theme_score  # 新增
        count += 1

    return jsonify({
        "status": "success",
        "data": {
            "plot": round(plot_total / count, 1) if count else 0,
            "acting": round(acting_total / count, 1) if count else 0,
            "visual": round(visual_total / count, 1) if count else 0,
            "music": round(music_total / count, 1) if count else 0,
            "rhythm": round(rhythm_total / count, 1) if count else 0,  # 新增
            "theme": round(theme_total / count, 1) if count else 0  # 新增
        }
    })


@app.route('/get_comments/<int:movie_id>')
@login_required
def get_comments(movie_id):
    # 验证电影存在且已审核
    movie = Movie.query.get(movie_id)
    if not movie or movie.status != 'approved':
        return jsonify({"status": "error", "msg": "电影不存在或未审核通过"}), 400

    root_comments = Comment.query.filter_by(
        movie_id=movie_id,
        parent_id=None
    ).order_by(Comment.create_time.desc()).all()

    comment_list = []
    for comment in root_comments:
        reply_total = len(comment.replies)
        show_replies = comment.replies[:1]

        replies_data = []
        for reply in show_replies:
            parent_user = User.query.get(comment.user_id)
            # 获取回复的点赞/踩数量
            reply_like = CommentVote.query.filter_by(comment_id=reply.id, vote_type='like').count()
            reply_dislike = CommentVote.query.filter_by(comment_id=reply.id, vote_type='dislike').count()
            replies_data.append({
                "id": reply.id,
                "content": reply.content,
                "create_time": reply.create_time.strftime('%Y-%m-%d %H:%M:%S'),
                "ip_province": reply.ip_province,
                "user": {
                    "id": reply.user.id,
                    "nickname": reply.user.nickname,
                    "avatar": reply.user.avatar,
                    "username": reply.user.username
                },
                "parent_user_nickname": parent_user.nickname,
                "like_count": reply_like,
                "dislike_count": reply_dislike
            })

        comment_user = User.query.get(comment.user_id)
        # 获取评论的点赞/踩数量
        like_count = CommentVote.query.filter_by(comment_id=comment.id, vote_type='like').count()
        dislike_count = CommentVote.query.filter_by(comment_id=comment.id, vote_type='dislike').count()
        # 获取评论用户的评分
        user_rating_obj = UserRating.query.filter_by(
            user_id=comment.user_id,
            movie_id=movie_id
        ).first()
        user_rating = user_rating_obj.user_rating if user_rating_obj else None

        comment_list.append({
            "id": comment.id,
            "content": comment.content,
            "create_time": comment.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            "ip_province": comment.ip_province,
            "user": {
                "id": comment_user.id,
                "nickname": comment_user.nickname,
                "avatar": comment_user.avatar,
                "username": comment_user.username
            },
            "reply_total": reply_total,
            "replies": replies_data,
            "like_count": like_count,
            "dislike_count": dislike_count,
            "user_rating": user_rating
        })
    return jsonify(comment_list)


@app.route('/get_all_replies/<int:comment_id>')
@login_required
def get_all_replies(comment_id):
    root_comment = Comment.query.get(comment_id)
    if not root_comment or root_comment.parent_id is not None:
        return jsonify({"status": "error", "msg": "不是根评论"}), 400

    replies_data = []
    for reply in root_comment.replies:
        parent_user = User.query.get(root_comment.user_id)
        reply_like = CommentVote.query.filter_by(comment_id=reply.id, vote_type='like').count()
        reply_dislike = CommentVote.query.filter_by(comment_id=reply.id, vote_type='dislike').count()
        replies_data.append({
            "id": reply.id,
            "content": reply.content,
            "create_time": reply.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            "ip_province": reply.ip_province,
            "user": {
                "id": reply.user.id,
                "nickname": reply.user.nickname,
                "avatar": reply.user.avatar,
                "username": reply.user.username
            },
            "parent_user_nickname": parent_user.nickname,
            "like_count": reply_like,
            "dislike_count": reply_dislike
        })
    return jsonify({"status": "success", "replies": replies_data})


@app.route('/like_comment/<int:comment_id>', methods=['POST'])
@login_required
def like_comment(comment_id):
    # 兼容旧点赞接口，实际已被vote_comment替代
    return jsonify({"status": "error", "msg": "请使用新的投票接口"}), 400


@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get(comment_id)
    if not comment:
        return jsonify({"status": "error", "msg": "评论不存在"})

    # 仅评论作者或管理员可删除
    current_user = User.query.get(session['user_id'])
    if comment.user_id != current_user.id and current_user.role != 'admin':
        return jsonify({"status": "error", "msg": "无权删除他人评论"})

    # 删除子评论、投票、主评论
    Comment.query.filter_by(parent_id=comment_id).delete()
    CommentVote.query.filter_by(comment_id=comment_id).delete()
    db.session.delete(comment)
    db.session.commit()

    return jsonify({"status": "success", "msg": "评论删除成功"})


if __name__ == '__main__':
    app.run(debug=True)