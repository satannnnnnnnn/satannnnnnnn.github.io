let currentMovieId = null;
let moviesData = [];
const currentUsername = document.getElementById('currentUsername')?.value || '';
const currentNickname = document.getElementById('currentNickname')?.value || '';
const currentUserId = document.getElementById('currentUserId')?.value || '';

// 搜索电影（无结果时提示添加）
function searchMovie() {
    const keyword = document.getElementById('searchInput')?.value.trim() || '';
    fetch(`/search?keyword=${encodeURIComponent(keyword)}`)
        .then(res => {
            if (!res.ok) throw new Error('接口请求失败');
            return res.json();
        })
        .then(movies => {
            moviesData = movies || [];
            if (movies.length === 0 && keyword) {
                if (confirm(`未找到"${keyword}"，是否添加这部电影？`)) {
                    openAddMovieModal();
                }
            } else {
                renderMovieList(movies);
            }
        })
        .catch(err => {
            console.error('搜索失败:', err);
            alert('搜索失败，请重试！');
        });
}

// 渲染电影列表（显示分类和上传者）
function renderMovieList(movies) {
    const movieList = document.getElementById('movieList');
    if (!movieList) return;

    if (movies.length === 0) {
        movieList.innerHTML = "<p style='text-align:center; color:#999;'>未找到相关电影</p>";
        return;
    }

    movieList.innerHTML = movies.map(movie => `
        <div class="movie-card" data-id="${movie.id}">
            <img class="movie-poster" 
                 src="${movie.poster_url || '/static/posters/default.jpg'}" 
                 alt="${movie.name}" 
                 onerror="this.src='/static/posters/default.jpg'">
            <div class="movie-info">
                <h3>${movie.name}</h3>
                <div>
                    <span class="category-tag ${movie.category === 'DoubanTop250' ? 'tag-douban' : 'tag-user'}">
                        ${movie.category === 'DoubanTop250' ? '豆瓣Top250' : '用户上传'}
                    </span>
                    ${movie.category === 'UserUpload' ? `<span class="uploader">由${movie.uploader_nickname}上传</span>` : ''}
                </div>
                <p>${movie.intro || '暂无简介'}</p>
                <p>初始评分: ${movie.initial_rating} | 用户评论数: ${movie.user_comment_count || 0}</p>
                
                <div class="rating-area">
                    <div>我的评分 (每星2分，满分10分):</div>
                    <div class="rating-star" onclick="selectStar(event, ${movie.id})">
                        ${[1,2,3,4,5].map(star => `
                            <span class="star ${movie.user_rating && star <= movie.user_rating/2 ? 'active' : ''}">★</span>
                        `).join('')}
                    </div>
                    <textarea class="user-comment" placeholder="写下你的评论...">${movie.user_comment || ''}</textarea>
                    <button class="submit-btn" onclick="submitRating(${movie.id})">提交评分</button>
                    <button class="view-comments-btn" onclick="openCommentModal(${movie.id})">查看评论</button>
                    
                    ${movie.user_rating ? `
                        <div class="user-rating-info" style="margin-top:10px; color:#7f8c8d;">
                            你已评分: ${movie.user_rating}分 | 评论: ${movie.user_comment || '无'}
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

// 星级选择
function selectStar(event, movieId) {
    const stars = event.currentTarget.querySelectorAll('.star');
    const index = Array.from(stars).indexOf(event.target);
    stars.forEach((star, i) => {
        star.classList.toggle('active', i <= index);
    });
}

// 提交评分
function submitRating(movieId) {
    const card = document.querySelector(`.movie-card[data-id="${movieId}"]`);
    if (!card) return;

    const activeStars = card.querySelectorAll('.star.active').length;
    const userRating = activeStars * 2;
    const userComment = card.querySelector('.user-comment')?.value || '';

    if (userRating === 0) {
        alert("请先选择评分星级");
        return;
    }

    fetch('/submit_rating', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            movie_id: movieId,
            user_rating: userRating,
            user_comment: userComment
        })
    })
    .then(res => {
        if (!res.ok) throw new Error('提交失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            searchMovie();
            alert("评分提交成功！");
        } else {
            alert("提交失败: " + (data.msg || '未知错误'));
        }
    })
    .catch(err => {
        console.error('提交评分失败:', err);
        alert('提交评分失败，请重试！');
    });
}

// 添加电影相关
function openAddMovieModal() {
    const modal = document.getElementById('addMovieModal');
    if (modal) modal.style.display = 'flex';
}

function closeAddMovieModal() {
    const modal = document.getElementById('addMovieModal');
    if (modal) {
        modal.style.display = 'none';
        document.getElementById('addMovieForm')?.reset();
    }
}

// 提交添加电影
document.getElementById('addMovieForm')?.addEventListener('submit', function(e) {
    e.preventDefault();
    const movieName = document.getElementById('movieName')?.value.trim();
    const movieIntro = document.getElementById('movieIntro')?.value.trim() || '暂无简介';
    const moviePoster = document.getElementById('moviePoster')?.files[0];

    if (!movieName) {
        alert('电影名称不能为空！');
        return;
    }

    const formData = new FormData();
    formData.append('movie_name', movieName);
    formData.append('movie_intro', movieIntro);
    if (moviePoster) formData.append('movie_poster', moviePoster);

    fetch('/add_movie', {
        method: 'POST',
        body: formData
    })
    .then(res => {
        if (!res.ok) throw new Error('添加失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            alert(data.msg);
            closeAddMovieModal();
            searchMovie();
        } else {
            alert(data.msg || '添加电影失败');
        }
    })
    .catch(err => {
        console.error('添加电影失败:', err);
        alert('添加电影失败，请重试！');
    });
}

// 评论弹窗相关
function openCommentModal(movieId) {
    currentMovieId = movieId;
    const movie = moviesData.find(m => m.id === movieId);
    if (movie) {
        document.getElementById('modalMovieName').textContent = `${movie.name} - 评论`;
    }
    loadComments(movieId);
    const modal = document.getElementById('commentModal');
    if (modal) modal.style.display = 'flex';
}

function closeCommentModal() {
    const modal = document.getElementById('commentModal');
    if (modal) modal.style.display = 'none';
    currentMovieId = null;
}

// 加载评论
function loadComments(movieId) {
    fetch(`/get_comments/${movieId}`)
        .then(res => {
            if (!res.ok) throw new Error('获取评论失败');
            return res.json();
        })
        .then(comments => {
            const commentList = document.getElementById('commentList');
            if (!commentList) return;
            commentList.innerHTML = '';

            if (!comments || comments.length === 0) {
                commentList.innerHTML = '<p style="color: #999;">暂无评论，快来抢沙发吧~</p>';
                return;
            }

            comments.forEach(comment => {
                const commentItem = document.createElement('div');
                commentItem.className = 'comment-item';
                commentItem.setAttribute('data-comment-id', comment.id);

                let commentHTML = `
                    <div class="comment-header">
                        <img src="${comment.user?.avatar || '/static/avatars/default.jpg'}" 
                             alt="${comment.user?.nickname || '用户'}" 
                             onclick="window.location.href='/profile/${comment.user?.id || 0}'"
                             onerror="this.src='/static/avatars/default.jpg'">
                        <div class="comment-user-info">
                            <div class="comment-nickname">${comment.user?.nickname || '匿名用户'}</div>
                            <div class="comment-meta">${comment.create_time || '未知时间'} · ${comment.ip_province || '未知地区'}</div>
                        </div>
                        <div class="comment-actions">
                            <button class="like-btn ${comment.is_liked ? 'liked' : ''}" onclick="toggleLike(${comment.id})">
                                ❤️ <span class="like-count">${comment.like_count || 0}</span>
                            </button>
                            <button class="reply-btn" onclick="showReplyInput(${comment.id})">回复</button>
                            ${comment.user?.username === currentUsername ? `
                                <button class="delete-btn" onclick="deleteComment(${comment.id})">删除</button>
                            ` : ''}
                        </div>
                    </div>
                    <div class="comment-content">${comment.content || ''}</div>
                    <div class="reply-area">
                        <textarea class="reply-input" data-comment-id="${comment.id}" placeholder="回复${comment.user?.nickname || '用户'}..."></textarea>
                        <button onclick="submitReply(${comment.id})">回复</button>
                    </div>
                `;

                const replyTotal = comment.reply_total || 0;
                if (replyTotal > 0) {
                    commentHTML += `<div class="reply-list" id="replies-${comment.id}">`;
                    (comment.replies || []).forEach(reply => {
                        commentHTML += `
                            <div class="reply-item" data-comment-id="${reply.id}">
                                <div class="reply-header">
                                    <img src="${reply.user?.avatar || '/static/avatars/default.jpg'}" 
                                         alt="${reply.user?.nickname || '用户'}"
                                         onclick="window.location.href='/profile/${reply.user?.id || 0}'"
                                         onerror="this.src='/static/avatars/default.jpg'">
                                    <div class="reply-user-info">
                                        <div class="reply-nickname">${reply.user?.nickname || '匿名用户'} 回复 ${reply.parent_user_nickname || '用户'}</div>
                                        <div class="reply-meta">${reply.create_time || '未知时间'} · ${reply.ip_province || '未知地区'}</div>
                                    </div>
                                    <div class="comment-actions">
                                        <button class="like-btn" onclick="toggleLike(${reply.id})">
                                            ❤️ <span class="like-count">0</span>
                                        </button>
                                        <button class="reply-btn" onclick="showReplyInput(${reply.id})">回复</button>
                                        ${reply.user?.username === currentUsername ? `
                                            <button class="delete-btn" onclick="deleteComment(${reply.id})">删除</button>
                                        ` : ''}
                                    </div>
                                </div>
                                <div class="reply-content">${reply.content || ''}</div>
                            </div>
                        `;
                    });
                    commentHTML += `</div>`;

                    if (replyTotal > 1) {
                        commentHTML += `
                            <button class="expand-replies-btn" onclick="expandReplies(${comment.id})">
                                展开${replyTotal - 1}条回复
                            </button>
                        `;
                    }
                }

                commentItem.innerHTML = commentHTML;
                commentList.appendChild(commentItem);
            });
        })
        .catch(err => {
            console.error('加载评论失败:', err);
            alert('加载评论失败，请重试！');
        });
}

// 展开全部回复
function expandReplies(commentId) {
    fetch(`/get_all_replies/${commentId}`)
        .then(res => {
            if (!res.ok) throw new Error('获取回复失败');
            return res.json();
        })
        .then(data => {
            if (data.status === 'success' && data.replies) {
                const replyList = document.getElementById(`replies-${commentId}`);
                const expandBtn = document.querySelector(`.comment-item[data-comment-id="${commentId}"] .expand-replies-btn`);
                
                if (replyList) {
                    replyList.innerHTML = '';
                    data.replies.forEach(reply => {
                        const replyItem = document.createElement('div');
                        replyItem.className = 'reply-item';
                        replyItem.setAttribute('data-comment-id', reply.id);
                        replyItem.innerHTML = `
                            <div class="reply-header">
                                <img src="${reply.user?.avatar || '/static/avatars/default.jpg'}" 
                                     alt="${reply.user?.nickname || '用户'}"
                                     onclick="window.location.href='/profile/${reply.user?.id || 0}'"
                                     onerror="this.src='/static/avatars/default.jpg'">
                                <div class="reply-user-info">
                                    <div class="reply-nickname">${reply.user?.nickname || '匿名用户'} 回复 ${reply.parent_user_nickname || '用户'}</div>
                                    <div class="reply-meta">${reply.create_time || '未知时间'} · ${reply.ip_province || '未知地区'}</div>
                                </div>
                                <div class="comment-actions">
                                    <button class="like-btn" onclick="toggleLike(${reply.id})">
                                        ❤️ <span class="like-count">0</span>
                                    </button>
                                    <button class="reply-btn" onclick="showReplyInput(${reply.id})">回复</button>
                                    ${reply.user?.username === currentUsername ? `
                                        <button class="delete-btn" onclick="deleteComment(${reply.id})">删除</button>
                                    ` : ''}
                                </div>
                            </div>
                            <div class="reply-content">${reply.content || ''}</div>
                        `;
                        replyList.appendChild(replyItem);
                    });
                }

                if (expandBtn) expandBtn.style.display = 'none';
            }
        })
        .catch(err => {
            console.error('展开回复失败:', err);
            alert('展开回复失败，请重试！');
        });
}

// 提交新评论
function submitNewComment() {
    const content = document.getElementById('newCommentContent')?.value.trim() || '';
    if (!content || !currentMovieId) {
        alert('评论内容不能为空！');
        return;
    }

    fetch('/submit_comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            movie_id: currentMovieId,
            content: content,
            parent_id: null
        })
    })
    .then(res => {
        if (!res.ok) throw new Error('提交评论失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            document.getElementById('newCommentContent').value = '';
            loadComments(currentMovieId);
            searchMovie();
        } else {
            alert(data.msg || '提交评论失败');
        }
    })
    .catch(err => {
        console.error('提交评论失败:', err);
        alert('提交评论失败，请重试！');
    });
}

// 提交根评论回复
function submitReply(parentCommentId) {
    const replyInput = document.querySelector(`.reply-input[data-comment-id="${parentCommentId}"]`);
    if (!replyInput) return;

    const content = replyInput.value.trim();
    if (!content || !currentMovieId) {
        alert('回复内容不能为空！');
        return;
    }

    fetch('/submit_comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            movie_id: currentMovieId,
            content: content,
            parent_id: parentCommentId
        })
    })
    .then(res => {
        if (!res.ok) throw new Error('提交回复失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            replyInput.value = '';
            loadComments(currentMovieId);
            searchMovie();
        } else {
            alert(data.msg || '提交回复失败');
        }
    })
    .catch(err => {
        console.error('提交回复失败:', err);
        alert('提交回复失败，请重试！');
    });
}

// 显示动态回复输入框
function showReplyInput(parentCommentId) {
    const targetElement = document.querySelector(`[data-comment-id="${parentCommentId}"]`);
    if (!targetElement) return;

    const existingInput = targetElement.querySelector('.dynamic-reply-input');
    if (existingInput) {
        existingInput.querySelector('textarea')?.focus();
        return;
    }

    const inputContainer = document.createElement('div');
    inputContainer.className = 'dynamic-reply-input';
    inputContainer.innerHTML = `
        <textarea placeholder="写下你的回复..." rows="2"></textarea>
        <button onclick="submitDynamicReply(${parentCommentId}, this)">提交回复</button>
    `;

    const contentElement = targetElement.querySelector('.comment-content') || targetElement.querySelector('.reply-content');
    if (contentElement) {
        contentElement.parentNode.insertBefore(inputContainer, contentElement.nextSibling);
        inputContainer.querySelector('textarea')?.focus();
    }
}

// 提交动态回复
function submitDynamicReply(parentCommentId, btnElement) {
    const inputContainer = btnElement.parentElement;
    const textarea = inputContainer.querySelector('textarea');
    if (!textarea) return;

    const content = textarea.value.trim();
    if (!content || !currentMovieId) {
        alert('回复内容不能为空');
        return;
    }

    fetch('/submit_comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            movie_id: currentMovieId,
            content: content,
            parent_id: parentCommentId
        })
    })
    .then(res => {
        if (!res.ok) throw new Error('提交回复失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            inputContainer.remove();
            loadComments(currentMovieId);
            searchMovie();
        } else {
            alert(data.msg || '提交回复失败');
        }
    })
    .catch(err => {
        console.error('提交回复失败:', err);
        alert('提交回复失败，请重试！');
    });
}

// 点赞/取消点赞
function toggleLike(commentId) {
    const likeBtn = document.querySelector(`[onclick="toggleLike(${commentId})"]`);
    if (!likeBtn) return;

    fetch(`/like_comment/${commentId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => {
        if (!res.ok) throw new Error('点赞操作失败');
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            const likeCountEl = likeBtn.querySelector('.like-count');
            if (likeCountEl) likeCountEl.textContent = data.like_count || 0;
            
            if (data.action === 'like') {
                likeBtn.classList.add('liked');
            } else {
                likeBtn.classList.remove('liked');
            }
        }
    })
    .catch(err => {
        console.error('点赞操作失败:', err);
        alert('点赞操作失败，请重试！');
    });
}

// 删除评论
function deleteComment(commentId) {
    if (confirm("确定要删除这条评论吗？删除后无法恢复！")) {
        fetch(`/delete_comment/${commentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(res => {
            if (!res.ok) throw new Error('删除评论失败');
            return res.json();
        })
        .then(data => {
            if (data.status === 'success') {
                loadComments(currentMovieId);
                searchMovie();
            } else {
                alert(data.msg || '删除评论失败');
            }
        })
        .catch(err => {
            console.error('删除评论失败:', err);
            alert('删除评论失败，请重试！');
        });
    }
}

// 页面初始化
window.onload = function() {
    setTimeout(() => {
        searchMovie();
        
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') searchMovie();
            });
        }
    }, 100);
};