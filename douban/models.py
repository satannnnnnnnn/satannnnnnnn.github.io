from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# 用户模型
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(50), nullable=False, default='匿名用户')
    avatar = db.Column(db.String(200), default='default.jpg')  # 存储相对路径
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 关联评论
    comments = db.relationship('Comment', backref='user', lazy=True)
    ratings = db.relationship('Rating', backref='user', lazy=True)

# 电影模型
class Movie(db.Model):
    __tablename__ = 'movie'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    poster = db.Column(db.String(200), default='default.jpg')  # 海报路径
    tags = db.Column(db.String(200))
    intro = db.Column(db.Text)
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 关联评论和评分
    comments = db.relationship('Comment', backref='movie', lazy=True)
    ratings = db.relationship('Rating', backref='movie', lazy=True)

# 评分模型
class Rating(db.Model):
    __tablename__ = 'rating'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    user_rating = db.Column(db.Float, nullable=False)  # 评分（0-10）
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 联合唯一约束（一个用户只能给一个电影评一次分）
    __table_args__ = (db.UniqueConstraint('user_id', 'movie_id', name='_user_movie_rating_uc'),)

# 评论模型（支持回复）
class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)  # 父评论ID（回复用）
    create_time = db.Column(db.DateTime, default=datetime.now)
    ip_province = db.Column(db.String(50), default='未知地区')  # IP地区
    # 关联回复
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True)
    # 点赞相关
    like_count = db.Column(db.Integer, default=0)

# 点赞模型
class Like(db.Model):
    __tablename__ = 'like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)
    # 联合唯一约束（一个用户只能给一个评论点一次赞）
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='_user_comment_like_uc'),)