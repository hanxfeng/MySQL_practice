from flask import Flask, request, render_template, jsonify, Response
from functools import wraps
import pymysql
import jwt
import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

db_config = {
    "host": "101.200.161.243",
    "user": "root",
    "password": "050316",
    "database": "online_learning",
    "charset": "utf8mb4"
}

SECRET_KEY = "1234"


def token_required(func):
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return jsonify({"success": False, "message": "未登录"}), 401

        token = auth.split(" ")[1]

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = payload["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "message": "Token 已过期"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "message": "无效 Token"}), 401

        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


@app.route('/api/login', methods=["POST"])
def login():
    data = request.json or {}
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"success": False, "message": "邮箱和密码不能为空"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "select id,password from users where email = %s",
            email
        )

        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "message": "用户不存在"}), 400

        user_id, user_password = user

        if user_password != password:
            return jsonify({"success": False, "message": "密码错误"}), 403

        token = jwt.encode({
            "user_id": user_id,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, SECRET_KEY, algorithm="HS256")

        return jsonify({"success": True, "token": token})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# 查询课程
@app.route('/api/course_list', methods=['POST'])
def course_list():
    data = request.json or {}

    # 获取并处理参数
    page = int(data.get("page", 1))
    limit = int(data.get("limit", 10))
    keyword = data.get("keyword", "").strip()
    teacher_id = data.get("teacher_id")
    min_price = data.get("min_price")
    max_price = data.get("max_price")
    free_only = data.get("free_only", False)  # 是否为仅免费课程
    sort_by = data.get("sort_by", "created_at")  # 排序用的字段 ： created_at, price, student_count, likes
    sort_order = data.get("sort_order", "desc")  # asc, desc 排序方式

    # 参数验证和标准化
    page = max(page, 1)
    limit = min(max(limit, 1), 50)  # 限制每页最多50条
    offset = (page - 1) * limit

    # 验证排序参数
    valid_sort_fields = ["created_at", "price", "student_count", "likes", "id"]
    if sort_by not in valid_sort_fields:
        return jsonify({"success": False, "message": "排序参数错误"}), 400

    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"

    # 处理参数冲突
    if free_only is not None and (min_price is not None or max_price is not None):
        return jsonify({"success": False, "message": "free_only 参数与 min_price 和 max_price 参数冲突"})

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 根据参数传入情况动态构建 WHERE 条件
        conditions = []
        params = []

        # 关键词搜索（标题或描述）
        if keyword:
            conditions.append("(c.title LIKE %s OR c.description LIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])  # .extend用于将一个可迭代对象的所有元素挨个添加到列表末尾

        # 按老师筛选
        if teacher_id is not None:
            conditions.append("c.teacher_id = %s")
            params.append(teacher_id)

        # 价格范围筛选
        if min_price is not None:
            conditions.append("c.price >= %s")
            params.append(float(min_price))

        if max_price is not None:
            conditions.append("c.price <= %s")
            params.append(float(max_price))

        # 仅免费课程
        if free_only:
            conditions.append("c.price = 0")

        # 构建完整的 WHERE 子句
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 构建排序子句
        order_clause = f"ORDER BY c.{sort_by} {sort_order.upper()}"

        # 构建查询语句
        base_query = """
                   SELECT 
                       c.id,
                       c.title,
                       c.description,
                       c.cover_url,
                       c.price,
                       c.teacher_id,
                       c.student_count,
                       c.likes,
                       c.created_at,
                       u.username as teacher_name
                   FROM courses c
                   LEFT JOIN users u ON c.teacher_id = u.id
               """

        # 查询数据
        cursor.execute(f"""
            {base_query}
            {where_clause}
            {order_clause}
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        courses_data = cursor.fetchall()

        # 查询总数用于分页
        cursor.execute(f"""
                   SELECT COUNT(*) 
                   FROM courses c
                   {where_clause}
               """, params)

        total = cursor.fetchone()[0]

        # 查询价格范围（用于返回筛选条件）
        cursor.execute("""
            SELECT 
                COALESCE(MIN(price), 0),
                COALESCE(MAX(price), 0)
            FROM courses
        """)
        price_min, price_max = cursor.fetchone()

        cursor.execute("""
            SELECT 
                COALESCE(MIN(student_count), 0),
                COALESCE(MAX(student_count), 0)
            FROM courses
        """)
        student_min, student_max = cursor.fetchone()

        # 处理返回数据
        courses = []
        for row in courses_data:
            course = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "cover_url": row[3],
                "price": float(row[4]),
                "teacher_id": row[5],
                "student_count": row[6],
                "likes": row[7],
                "created_at": row[8].strftime("%Y-%m-%d %H:%M:%S") if row[8] else None,
                "teacher_name": row[9]
            }
            courses.append(course)

        # 计算分页信息
        total_pages = (total + limit - 1) // limit  # 向上取整

        pagination = {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

        # 返回的筛选条件信息
        filters = {
            "price_range": {
                "min": float(price_min),
                "max": float(price_max)
            },
            "student_count_range": {
                "min": student_min,
                "max": student_max
            }
        }

        return jsonify({
            "success": True,
            "data": {
                "courses": courses,
                "pagination": pagination,
                "filters": filters
            }
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 获取热门课程
@app.route('/api/course/popular', methods=['POST'])
def popular_courses():
    data = request.json or {}
    limit = min(int(data.get("limit", 10)), 50)  # 限制最多50条
    sort_by = data.get("sort_by", "student_count")  # student_count, likes, created_at

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 根据排序字段获取热门课程
        if sort_by == "student_count":
            order_field = "c.student_count DESC"
        elif sort_by == "likes":
            order_field = "c.likes DESC"
        elif sort_by == "recent":
            order_field = "c.created_at DESC"
        else:
            order_field = "c.student_count DESC"

        cursor.execute(f"""
            SELECT 
                c.id,
                c.title,
                c.description,
                c.cover_url,
                c.price,
                c.student_count,
                c.likes,
                u.username as teacher_name
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            ORDER BY {order_field}
            LIMIT %s
        """, (limit,))

        courses_data = cursor.fetchall()

        courses = []
        for row in courses_data:
            course = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "cover_url": row[3],
                "price": float(row[4]),
                "student_count": row[5],
                "likes": row[6],
                "teacher_name": row[7]
            }
            courses.append(course)

        return jsonify({
            "success": True,
            "data": {
                "courses": courses,
                "sort_by": sort_by
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 查询课程详情
@app.route("/api/course_detail", methods=["POST"])
def class_details():
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "course_id 不能为空"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "select title,description,cover_url,price,teacher_id,student_count from courses where id = %s"
            , course_id
        )
        course = cursor.fetchone()
        if not course:
            return jsonify({"success": False, "message": "课程不存在"}), 404

        cursor.execute(
            "select username,email,phone from users where id = %s"
            , course_id[5]
        )
        teacher = cursor.fetchone()

        cursor.execute(
            "select id,title from lessons where id = %s ORDER BY sort_order ASC;"
            , course_id
        )
        lessons = cursor.fetchall()
        lessons_list = [{"id": l[0], "title": l[1]} for l in lessons]

        return jsonify({
            "success": True,
            "data": {
                "id": course[0],
                "title": course[1],
                "description": course[2],
                "cover_url": course[3],
                "price": float(course[4]),
                "student_count": course[6],
                "teacher": {
                    "id": teacher[0],
                    "username": teacher[1],
                    "email": teacher[2],
                    "phone": teacher[3]
                },
                "lessons": lessons_list
            }
        })

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "查询失败：{}".format(str(e))}), 500
    finally:
        cursor.close()
        conn.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"success": False, "message": "Token 缺失"}), 401

        # Token 格式：Bearer xxxx
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except Exception as e:
            return jsonify({"success": False, "message": "Token 无效或已过期"}), 401

        # 将 user_id 传给接口内使用
        kwargs["user_id"] = payload.get("user_id")
        return func(*args, **kwargs)

    return wrapper


# 购买课程
@app.route("/api/buy_course", methods=["POST"])
@login_required
def buy_course(user_id):
    # 获取课程id
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "course_id 不能为空"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询是否已购买课程
        cursor.execute(
            "select id from course_student where course_id = %s and user_id = %s",
            (course_id, user_id)
        )
        re = cursor.fetchone()

        if re:
            return jsonify({"success": False, "message": "该课程已购买"}), 400

        # 查询课程价格
        cursor.execute(
            "select price from courses where id = %s",
            (course_id,)
        )
        course_price = float(cursor.fetchone()[0])

        # 查询用户余额
        cursor.execute(
            "select balance from users where id = %s",
            (user_id,)
        )
        user_balance = float(cursor.fetchone()[0])

        # 确认用户余额是否足够
        if user_balance < course_price:
            return jsonify({"success": False, "message": "余额不足"}), 400

        # 建立订单
        cursor.execute(
            "insert into orders (user_id, course_id, amount, status) values (%s,%s,%s,%s)",
            (user_id, course_id, course_price, 0)
        )
        order_id = cursor.lastrowid

        # 扣除费用
        cursor.execute(
            "update users set balance = %s where id = %s",
            (user_balance - course_price, user_id)
        )

        # 修改订单状态
        cursor.execute(
            "update orders set status = %s where id = %s",
            (1, order_id)
        )

        # 添加课程权限
        cursor.execute(
            "insert into course_student (user_id,course_id) values (%s,%s)",
            (user_id, course_id)
        )

        # 添加课程进度
        cursor.execute(
            "select id from lessons where course_id = %s",
            (course_id,)
        )
        lessons_ids = cursor.fetchall()

        for row in lessons_ids:
            cursor.execute(
                "insert into learning_progress (user_id,lesson_id) values (%s,%s)",
                (user_id, row[0])
            )

        # 增加课程学生数量
        cursor.execute(
            "UPDATE courses SET student_count = student_count + 1 WHERE id=%s",
            (course_id,)
        )

        # 提交事务
        conn.commit()

        return jsonify({"success": True, "message": "购买成功"}), 200

    except Exception as e:
        # 出现异常回滚
        conn.rollback()
        return jsonify({"success": False, "message": "购买失败：{}".format(str(e))}), 500

    finally:
        cursor.close()
        conn.close()


# 查询学习进度
@app.route("/api/progress/get", methods=["POST"])
@login_required
def get_progress(user_id):
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "course_id 不能为空"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 获取所有章节
        cursor.execute(
            "SELECT id, title FROM lessons WHERE course_id = %s ORDER BY sort_order ASC",
            (course_id,)
        )
        lessons = cursor.fetchall()

        if not lessons:
            return jsonify({"success": False, "message": "该课程无章节"}), 404

        total_lessons = len(lessons)
        completed_count = 0
        lesson_progress = []

        for lesson_id, title in lessons:
            cursor.execute(
                "SELECT progress FROM learning_progress WHERE user_id=%s AND lesson_id=%s",
                (user_id, lesson_id)
            )
            row = cursor.fetchone()
            progress = row[0] if row else 0

            if progress >= 100:
                completed_count += 1

            lesson_progress.append({
                "lesson_id": lesson_id,
                "title": title,
                "progress": progress
            })

        overall_progress = round((completed_count / total_lessons) * 100, 2)

        return jsonify({
            "success": True,
            "data": {
                "overall_progress": overall_progress,
                "lesson_progress": lesson_progress
            }
        })

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 更新章节学习进度
@app.route("/api/progress/update", methods=["POST"])
@login_required
def update_progress(user_id):
    data = request.json or {}
    lesson_id = data.get("lesson_id")
    progress = data.get("progress")

    if lesson_id is None or progress is None:
        return jsonify({"success": False, "message": "缺少 lesson_id 或 progress 参数"}), 400

    # 限制为 0~100
    progress = min(max(int(progress), 0), 100)

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    try:
        # 获取章节对应的课程id
        cursor.execute(
            "select course_id from lessons where id = %s",
            (lesson_id,)
        )
        course_id = cursor.fetchone()[0]
        if not course_id:
            return jsonify({"success": False, "message": "lesson 不存在"}), 404

        # 获取该课程下的章节数量
        cursor.execute(
            "select count(id) from lessons where id = %s",
            (course_id,)
        )
        lesson_count = cursor.fetchone()[0]

        # 更新章节进度
        cursor.execute(
            """
            INSERT INTO learning_progress (user_id, lesson_id, progress)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE progress=%s, updated_at=NOW()
            """,
            (user_id, lesson_id, progress, progress)
        )

        # 计算课程进度
        if lesson_count == 0:
            course_progress = 0
        else:
            cursor.execute(
                """
                select count id 
                from learning_progress lp
                join lessons l on lp.lesson_id = l.id
                where lp.user_id = %s and l.course_id = %s and lp.progress=100
                """,
                (user_id, course_id)
            )
            completed_lessons = cursor.fetchone()[0]
            course_progress = round((completed_lessons / lesson_count) * 100)

        # 更新课程总体进度
        cursor.execute(
            """
            INSERT INTO course_progress (user_id, course_id, progress)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE progress=%s, updated_at=NOW()
            """,
            (user_id, course_id, course_progress, course_progress)
        )
        conn.commit()

        return jsonify({
            "success": True,
            "message": "进度已更新",
            "course_progress": course_progress
        }), 200


    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 添加评论
@app.route("/api/add_comment", methods=["POST"])
@login_required
def add_comment(user_id):
    data = request.json or {}
    course_id = data.get("course_id")
    rating = data.get("rating")
    content = data.get("content")

    if course_id is None or rating is None or content is None:
        return jsonify({"success": False, "message": "缺少 course_id 或 rating 或 content 参数"}), 400

    if rating < 1 or rating > 5:
        return jsonify({"success": False, "message": "评分范围为1-5"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM courses WHERE id=%s", (course_id,))
        if cursor.fetchone() is None:
            return jsonify({"success": False, "message": "课程不存在"}), 404

        cursor.execute(
            "select 1 from course_student where user_id = %s and course_id = %s",
            (user_id, course_id)
        )
        created_at = cursor.fetchone()
        if created_at is None:
            return jsonify({"success": False, "message": "未购买该课程"}), 403

        cursor.execute(
            "insert into comments (user_id,course_id,rating,content) values(%s,%s,%s,%s)",
            (user_id, course_id, rating, content)
        )

        conn.commit()

        return jsonify({"success": True, "message": "评论添加成功"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 查询评论
@app.route("/api/get_comments", methods=["POST"])
@login_required
def get_comments(user_id):
    data = request.json or {}
    course_id = data.get("course_id")
    page = int(data.get("page", 1))
    limit = 10
    offset = (page - 1) * limit

    if course_id is None or page is None:
        return jsonify({"success": False, "message": "缺少 course_id 或 page 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM courses WHERE id=%s", (course_id,))
        if cursor.fetchone() is None:
            return jsonify({"success": False, "message": "课程不存在"}), 404

        cursor.execute(
            """
              SELECT c.rating,
                     c.content,
                     c.likes,
                     c.created_at,
                     u.username 
              FROM comments AS c
              JOIN users AS u ON c.user_id = u.id
              WHERE c.course_id = %s
              ORDER BY c.created_at DESC
              LIMIT %s OFFSET %s
              """,
            (course_id, limit, offset)
        )
        results = cursor.fetchall()

        data = [
            {
                "rating": row[0],
                "content": row[1],
                "likes": row[2],
                "created_at": row[3],
                "username": row[4]
            }
            for row in results
        ]

        return jsonify({"success": True, "data": data}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 收藏接口
@app.route("/api/favorite_course", methods=["POST"])
@login_required
def favorite_course(user_id):
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "缺少 course_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 判断是否已收藏
        cursor.execute(
            "SELECT id FROM favorites WHERE user_id=%s AND course_id=%s",
            (user_id, course_id)
        )
        favorite = cursor.fetchone()

        if favorite:
            # 已收藏则取消
            cursor.execute("DELETE FROM favorites WHERE id=%s", (favorite[0],))
            conn.commit()
            return jsonify({"success": True, "message": "已取消收藏"}), 200

        else:
            # 未收藏则添加
            cursor.execute(
                "INSERT INTO favorites (user_id, course_id) VALUES (%s, %s)",
                (user_id, course_id)
            )
            conn.commit()
            return jsonify({"success": True, "message": "收藏成功"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 查询收藏课程
@app.route("/api/get_favorites", methods=["POST"])
@login_required
def get_favorites(user_id):
    data = request.json or {}
    page = int(data.get("page", 1))

    if not page:
        return jsonify({"success": False, "message": "缺少 page 参数"}), 400

    limit = 10
    offset = (page - 1) * limit

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT c.id, c.title, c.price, c.cover_url, c.student_count
            FROM favorites f
            JOIN courses c ON f.course_id = c.id
            WHERE f.user_id = %s
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s;
            """,
            (user_id, limit, offset)
        )
        courses = cursor.fetchall()

        data = [
            {
                "id": row[0],
                "title": row[1],
                "price": row[2],
                "cover_url": row[3],
                "student_count": row[4]
            } for row in courses
        ]

        return jsonify({"success": True, "data": data}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 点赞 or 取消点赞评论
@app.route("/api/like_comment", methods=["POST"])
@login_required
def like_comment(user_id):
    data = request.json or {}
    comment_id = data.get("comment_id")
    if not comment_id:
        return jsonify({"success": False, "message": "缺少 comment_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询是否已经点赞
        cursor.execute(
            "select id from comment_likes where user_id = %s and comment_id = %s",
            (user_id, comment_id)
        )
        result = cursor.fetchone()

        if result is None:
            # 未点赞则添加点赞记录
            cursor.execute(
                "insert into comment_likes (user_id,comment_id) values (%s,%s)",
                (user_id, comment_id)
            )
            # 向comments表中更新点赞数
            cursor.execute(
                "update comments set likes = likes+1 where id = %s",
                (comment_id,)
            )
            conn.commit()

            return jsonify({"success": True, "message": "点赞成功"}), 200
        else:
            # 已点赞则删除comment_likes表中的记录
            cursor.execute(
                "delete from comment_likes where user_id = %s and comment_id =%s",
                (user_id, comment_id)
            )
            # 向comments表中更新点赞数
            cursor.execute(
                "update comments set likes =  GREATEST(likes - 1, 0) where id = %s",
                (comment_id,)
            )
            conn.commit()

            return jsonify({"success": True, "message": "取消点赞成功"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 点赞 or 取消点赞课程
@app.route("/api/like_course", methods=["POST"])
@login_required
def like_course(user_id):
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "缺少 course_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询是否已经点赞
        cursor.execute(
            "select id from course_likes where user_id = %s and course_id = %s",
            (user_id, course_id)
        )
        result = cursor.fetchone()

        if result is None:
            # 未点赞则添加点赞记录
            cursor.execute(
                "insert into course_likes (user_id,course_id) values (%s,%s)",
                (user_id, course_id)
            )
            # 向comments表中更新点赞数
            cursor.execute(
                "update courses set likes = likes+1 where id = %s",
                (course_id,)
            )
            conn.commit()

            return jsonify({"success": True, "message": "点赞成功"}), 200
        else:
            # 已点赞则删除comment_likes表中的记录
            cursor.execute(
                "delete from course_likes where user_id = %s and course_id =%s",
                (user_id, course_id)
            )
            # 向comments表中更新点赞数
            cursor.execute(
                "update courses set likes =  GREATEST(likes - 1, 0) where id = %s",
                (course_id,)
            )
            conn.commit()

            return jsonify({"success": True, "message": "取消点赞成功"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/course_progress/get", methods=["POST"])
@login_required
def get_course_progress(user_id):
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "缺少 course_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询课程进度
        cursor.execute(
            "select progress from course_progress where user_id = %s and course_id = %s",
            (user_id, course_id)
        )
        row = cursor.fetchone()
        course_progress = row[0] if row else 0

        # 查询课程进度
        cursor.execute(
            """
            select l.id AS lesson_id,l.title AS lesson_title,,COALESCE(lp.progress, 0) AS progress
            from lessons l
            LEFT JOIN learning_progress lp 
                ON lp.lesson_id = l.id AND lp.user_id = %s
            WHERE l.course_id = %s
            ORDER BY l.id ASC
            """,
            (user_id, course_id)
        )
        lessons_progress = cursor.fetchall()
        result = []
        for row in lessons_progress:
            result.append({
                "lesson_id": row[0],
                "lesson_title": row[1],
                "progress": row[2]
            })

        return jsonify({"success": True, "course_progress": course_progress, "lessons": result}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 自动写入学习历史记录
@app.route("/api/lesson/get", methods=["POST"])
@login_required
def get_lesson(user_id):
    data = request.json or {}
    lesson_id = data.get("lesson_id")

    if not lesson_id:
        return jsonify({"success": False, "message": "缺少 lesson_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询 lesson 信息
        cursor.execute(
            "SELECT id, course_id, title, content FROM lessons WHERE id=%s",
            (lesson_id,)
        )
        lesson = cursor.fetchone()

        if not lesson:
            return jsonify({"success": False, "message": "缺失 lesson 参数"}), 404

        course_id = lesson[1]

        # 获取finish_at状态
        cursor.execute(
            "select finish_at from learning_history where user_id = %s and course_id = %s and lesson_id = %s ORDER BY id DESC LIMIT 1",
            (user_id, course_id, lesson_id)
        )
        finish_at = cursor.fetchone()
        record = cursor.fetchone()

        need_insert = False

        if record is None:
            # A：无记录 → 创建
            need_insert = True
        else:
            last_finish = record[1]  # finish_at
            if last_finish is not None:
                # C：有记录但已完成 → 创建新记录
                need_insert = True
            else:
                # B：有未完成的记录 → 不创建
                need_insert = False

        if need_insert:
            # 如果无记录，创建
            cursor.execute(
                """
                INSERT INTO learning_history (user_id, course_id, lesson_id)
                VALUES (%s, %s, %s)
                """,
                (user_id, course_id, lesson_id)
            )
            conn.commit()

            # 返回 lesson 内容
            return jsonify({
                "success": True,
                "lesson": {
                    "lesson_id": lesson[0],
                    "course_id": lesson[1],
                    "title": lesson[2],
                    "content": lesson[3]
                }
            }), 200


    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# 记录 finish_at 与学习时长 duration_seconds
@app.route("/api/lesson/finish", methods=["POST"])
@login_required
def finish_lesson(user_id):
    data = request.json or {}
    lesson_id = data.get("lesson_id")

    if not lesson_id:
        return jsonify({"success": False, "message": "缺少 lesson_id 参数"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 获取开始时间
        cursor.execute(
            "select id, start_at, course_id from learning_history where user_id = %s and lesson_id = %s ORDER BY id DESC LIMIT 1",
            (user_id, lesson_id)
        )
        result = cursor.fetchone()
        history_id = result[0]
        start_at = result[1]
        course_id = result[2]

        # 计算持续时间
        finish_at = datetime.datetime.now()
        duration_seconds = int((finish_at - start_at).total_seconds())

        # 更新数据
        cursor.execute(
            """
            UPDATE learning_history
            SET finish_at = %s,
                duration_seconds = %s
            WHERE id = %s
            """,
            (finish_at, duration_seconds, history_id)
        )

        # 查询progress的平均值
        cursor.execute(
            "SELECT AVG(progress) FROM learning_progress WHERE user_id=%s AND course_id=%s",
            (user_id, course_id)
        )
        avg_progress = cursor.fetchone()[0] or 0
        avg_progress = int(avg_progress)

        # 更新数据
        cursor.execute(
            """
            INSERT INTO course_progress (user_id, course_id, progress)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE progress=%s
            """,
            (user_id, course_id, avg_progress, avg_progress)
        )

        conn.commit()

        return jsonify({"success": True, "duration_seconds": duration_seconds}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# 计算连续学习天数
@app.route("/api/user/streak", methods=["GET"])
@login_required
def user_streak(user_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 判断今天是否学习
        today_start = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time.min
        )
        tomorrow_start = today_start + datetime.timedelta(days=1)
        cursor.execute(
            """
            select count(*)
            from learning_history
            where user_id = %s
            AND start_at >= %s and start_at < %s
            """,
            (user_id, today_start, tomorrow_start)
        )

        today_count = cursor.fetchone()[0]
        today_learned = today_count > 0

        # 获取所有学习过的天数
        cursor.execute(
            """
            select DISTINCT DATE(start_at)
            from learning_history
            where user_id = %s
            order by DATE(start_at) DESC
            """,
            (user_id,)
        )

        rows = cursor.fetchall()
        dates = [row[0] for row in rows]

        if not dates:
            return jsonify({
                "success": True,
                "today_learned": today_learned,
                "streak": 0,
                "last_learn_date": None
            })

        # 计算连续学习天数
        streak = 0
        today = datetime.date.today()

        # 如果今天没学习 streak 从 0 开始算
        expected = today if today_learned else today - datetime.timedelta(days=1)

        for d in dates:
            if d == expected:
                streak += 1
                expected = expected - datetime.timedelta(days=1)
            else:
                break

        return jsonify({
            "success": True,
            "today_learned": today_learned,
            "streak": streak,
            "last_learn_date": str(dates[0])
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# 查询用户学习记录
@app.route("/api/learning/history")
@login_required
def learning_history(user_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    try:
        # 获取一大堆各种各样的数据，具体见返回的字典
        cursor.execute(
            """
            select lh.id,lh.course_id,c.title,lh.lesson_id,l.title,lh.start_at,lh.finish_at,lh.duration_seconds
            from learning_history lh
            join courses c on lh.course_id = c.id
            join lessons l on lh.lesson_id = l.id
            where lh.user_id = %s
            limit 30
            ORDER BY lh.start_at DESC
            """,
            (user_id,)
        )
        result = cursor.fetchall()

        if not result:
            return jsonify({"success": True, "history": []})

        history = []
        for row in result:
            history.append({
                "history_id": row[0],
                "course_id": row[1],
                "course_title": row[2],
                "lesson_id": row[3],
                "lesson_title": row[4],
                "start_at": row[5],
                "finish_at": row[6],
                "duration_seconds": row[7]
            })

        return jsonify({"success": True, "history": history})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# 今日学习时长统计
@app.route("/api/learning/today_total", methods=["GET"])
@login_required
def today_total(user_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        today_start = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time.min
        )
        tomorrow_start = today_start + datetime.timedelta(days=1)

        # 加总当天的学习时间
        cursor.execute(
            """
            select COALESCE(SUM(duration_seconds), 0) 
            from learning_history 
            where user_id = %s and start_at >= %s and start_at < %s
            """,
            (user_id, today_start, tomorrow_start)
        )
        total_seconds = cursor.fetchone()[0]

        return jsonify({
            "success": True,
            "today_seconds": int(total_seconds)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 获取考试成绩
@app.route('/api/exam/results', methods=["POST"])
@login_required
def exam_results(user_id):
    data = request.json or {}
    page = data.get("page") or 1
    limit = data.get("limit")

    if page is None or limit is None:
        return jsonify({"success": False, "message": "缺少参数 page 或 limit"}), 400

    limit = 10
    offset = (page - 1) * limit

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            select er.exam_id,e.title,er.course_id,c.title,er.score,er.created_at
            from exam_results er
            join exams e on er.exam_id = e.id
            join courses c on er.course_id = c.id
            where user_id = %s
            ORDER BY er.created_at DESC  
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset)
        )
        result = cursor.fetchall()

        # results数组
        results = []
        scores = []
        for row in result:
            score = row[4]
            scores.append(score)
            if score >= 60:
                status = "已通过"
            else:
                status = "未通过"
            results.append({
                "exam_id": row[0],
                "exam_title": row[1],
                "course_id": row[2],
                "course_title": row[3],
                "score": score,
                "created_at": row[5],
                "status": status
            })

        # pagination数组
        cursor.execute(
            "select count(exam_id) from exam_results where user_id = %s",
            (user_id,)
        )
        from math import ceil
        total = cursor.fetchone()[0]
        total_pages = ceil(total / limit)

        if page == total_pages:
            has_next = False
        else:
            has_next = True

        if page == 1:
            has_prev = False
        else:
            has_prev = True
        pagination = {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev
        }

        # summary数组
        summary = {
            "total_exams": len(scores),
            "avg_score": sum(scores) / len(scores),
            "highest_score": max(scores),
            "lowest_score": min(scores)
        }

        data = {"results": results, "pagination": pagination, "summary": summary}
        return jsonify({"success": True, "data": data}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 获取热门课程
@app.route("/api/course/ranking", methods=["POST"])
def course_ranking():
    data = request.json or {}
    ranking_type = data.get("type", "student_count")  # 添加默认值
    limit = int(data.get("limit", 10))

    # 验证参数
    if ranking_type not in ["student_count", "likes", "sales"]:
        return jsonify({"success": False, "message": "排行榜类型错误"}), 400

    # 限制返回数量
    limit = min(max(limit, 1), 100)  # 限制1-100之间

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 根据不同类型构建SQL
        if ranking_type == "student_count":
            sql = """
                SELECT 
                    c.id,
                    c.title,
                    c.teacher_id,
                    u.username as teacher_name,
                    c.student_count,
                    c.price,
                    c.cover_url
                FROM courses c
                LEFT JOIN users u ON c.teacher_id = u.id
                ORDER BY c.student_count DESC
                LIMIT %s
            """
        elif ranking_type == "likes":
            sql = """
                SELECT 
                    c.id,
                    c.title,
                    c.teacher_id,
                    u.username as teacher_name,
                    c.likes,
                    c.price,
                    c.cover_url
                FROM courses c
                LEFT JOIN users u ON c.teacher_id = u.id
                ORDER BY c.likes DESC
                LIMIT %s
            """
        elif ranking_type == "sales":
            sql = """
                SELECT 
                    c.id,
                    c.title,
                    c.teacher_id,
                    u.username as teacher_name,
                    (c.student_count * c.price) as sales_amount,
                    c.price,
                    c.cover_url
                FROM courses c
                LEFT JOIN users u ON c.teacher_id = u.id
                ORDER BY sales_amount DESC
                LIMIT %s
            """

        cursor.execute(sql, (limit,))
        results = cursor.fetchall()

        # 构建返回数据
        courses = []
        for index, row in enumerate(results, start=1):
            course_data = {
                "rank": index,
                "course_id": row[0],
                "title": row[1],
                "teacher_id": row[2],
                "teacher_name": row[3],  # 现在有老师姓名了
                "value": float(row[4]) if row[4] is not None else 0,
                "price": float(row[5]) if row[5] is not None else 0,
                "cover_url": row[6]
            }

            courses.append(course_data)

        return jsonify({
            "success": True,
            "data": {
                "ranking_type": ranking_type,
                "courses": courses,
                "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 获取用户基本信息
@app.route("/api/user/profile",methods=["GET"])
@login_required
def user_profile(user_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "select id,username,email,phone,role,balance,created_at from users where id = %s",
            (user_id,)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({"success": False, "message": "用户不存在"}), 404

        role_map = {0: '学生', 1: '老师'}
        role = role_map.get(result[4], '未知')  # 使用get方法，避免KeyError

        data = {
            "user_id": result[0],
            "username": result[1],
            "email": result[2],
            "phone": result[3],
            "role": role,
            "balance": result[5],
            "created_at": result[6].strftime("%Y-%m-%d %H:%M:%S")
        }

        return jsonify({"success": True, "data": data}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 更新用户信息,正常应该是发验证码，但一个练习的项目没必要折腾这些，简单验证是否知道完整的手机号和邮箱即可
# 如果修改用户名则需要提供完整邮箱或手机号，修改邮箱要提供完整手机号，修改手机号要提供完整邮箱
@app.route("/api/user/profile/update", methods=["POST"])
@login_required
def update_user_profile(user_id):
    data = request.json or {}

    update_type = data.get("update_type")  # 修改类型包括 username email phone

    if update_type not in ["username", "email", "phone"] or update_type is None:
        return jsonify({"success": False, "message": "update_type 参数输入为空或输入错误"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 获取用户当前信息
        cursor.execute(
            "SELECT username, email, phone FROM users WHERE id = %s",
            (user_id,)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({"success": False, "message": "用户不存在"}), 404

        current_username, current_email, current_phone = result

        # 根据修改类型进行验证和更新
        if update_type == "username":
            new_username = data.get("new_username", "").strip()
            old_email = data.get("old_email", "").strip()
            old_phone = data.get("old_phone", "").strip()

            if not new_username:
                return jsonify({"success": False, "message": "新用户名不能为空"}), 400

            # 验证旧邮箱或旧手机号
            if old_email != current_email and old_phone != current_phone:
                return jsonify({"success": False, "message": "邮箱或手机号验证失败"}), 400

            # 检查新用户名是否已被使用（排除自己）
            cursor.execute(
                "SELECT id FROM users WHERE username = %s AND id != %s",
                (new_username, user_id)
            )
            if cursor.fetchone():
                return jsonify({"success": False, "message": "用户名已被使用"}), 400

            # 更新用户名
            cursor.execute(
                "UPDATE users SET username = %s WHERE id = %s",
                (new_username, user_id)
            )
            message = "用户名更新成功"

        elif update_type == "email":
            new_email = data.get("new_email", "").strip()
            old_phone = data.get("old_phone", "").strip()

            if not new_email:
                return jsonify({"success": False, "message": "新邮箱不能为空"}), 400

            # 验证旧手机号
            if old_phone != current_phone:
                return jsonify({"success": False, "message": "手机号验证失败"}), 400

            # 检查新邮箱是否已被使用（排除自己）
            cursor.execute(
                "SELECT id FROM users WHERE email = %s AND id != %s",
                (new_email, user_id)
            )
            if cursor.fetchone():
                return jsonify({"success": False, "message": "邮箱已被使用"}), 400

            # 更新邮箱
            cursor.execute(
                "UPDATE users SET email = %s WHERE id = %s",
                (new_email, user_id)
            )
            message = "邮箱更新成功"

        elif update_type == "phone":
            new_phone = data.get("new_phone", "").strip()
            old_email = data.get("old_email", "").strip()

            if not new_phone:
                return jsonify({"success": False, "message": "新手机号不能为空"}), 400

            # 验证旧邮箱
            if old_email != current_email:
                return jsonify({"success": False, "message": "邮箱验证失败"}), 400

            # 检查新手机号是否已被使用（排除自己）
            cursor.execute(
                "SELECT id FROM users WHERE phone = %s AND id != %s",
                (new_phone, user_id)
            )
            if cursor.fetchone():
                return jsonify({"success": False, "message": "手机号已被使用"}), 400

            # 更新手机号
            cursor.execute(
                "UPDATE users SET phone = %s WHERE id = %s",
                (new_phone, user_id)
            )
            message = "手机号更新成功"

        conn.commit()

        return jsonify({
            "success": True,
            "message": message,
            "update_type": update_type
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 修改密码
@app.route("/api/user/change-password", methods=["POST"])
@login_required
def change_password(user_id):
    data = request.json or {}
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    # 参数验证
    if old_password is None or new_password is None:
        return jsonify({"success": False, "message": "参数不能为空"}), 400

    # 新密码长度检查
    if len(new_password) < 6:
        return jsonify({"success": False, "message": "新密码最小为6位"}), 400

    # 新旧密码不能相同
    if old_password == new_password:
        return jsonify({"success": False, "message": "新旧密码不能相同"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 查询用户当前密码
        cursor.execute(
            "select password from users where id = %s",
            (user_id,)
        )

        result = cursor.fetchone()

        if not result:
            return jsonify({"success": False, "message": "用户不存在"}), 404

        # 验证原密码
        password = result[0]
        if old_password != password:
            return jsonify({"success": False, "message": "原密码输入不正确"}), 401

        # 更新密码
        cursor.execute(
            "update users set password = %s where id = %s",
            (new_password, user_id)
        )

        conn.commit()

        return jsonify({"success": True, "message": "密码修改成功"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/user/learning-overview", methods=["GET"])
@login_required
def learning_overview(user_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 获取今日时间范围
        today_start = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time.min
        )
        tomorrow_start = today_start + datetime.timedelta(days=1)

        # 本周开始时间（周一）
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())  # 本周一
        week_start_dt = datetime.datetime.combine(week_start, datetime.time.min)

        # 1. 获取总学习时长（秒）
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM learning_history WHERE user_id = %s",
            (user_id,)
        )
        total_learning_seconds = cursor.fetchone()[0] or 0

        # 2. 获取总学习天数（不重复的日期数）
        cursor.execute(
            """
            SELECT COUNT(DISTINCT DATE(start_at)) 
            FROM learning_history 
            WHERE user_id = %s AND start_at IS NOT NULL
            """,
            (user_id,)
        )
        total_learning_days = cursor.fetchone()[0] or 0

        # 3. 获取连续学习天数（复用之前的逻辑）
        # 获取所有学习过的天数
        cursor.execute(
            """
            SELECT DISTINCT DATE(start_at)
            FROM learning_history
            WHERE user_id = %s
            ORDER BY DATE(start_at) DESC
            """,
            (user_id,)
        )
        rows = cursor.fetchall()
        dates = [row[0] for row in rows]

        # 计算连续天数
        streak = 0
        today_learned = False
        if dates:
            # 检查今天是否学习
            today_date = datetime.date.today()
            today_learned = any(date == today_date for date in dates)

            # 计算连续天数
            expected = today_date if today_learned else today_date - datetime.timedelta(days=1)
            for d in dates:
                if d == expected:
                    streak += 1
                    expected -= datetime.timedelta(days=1)
                else:
                    break

        # 4. 获取已购课程总数
        cursor.execute(
            "SELECT COUNT(*) FROM course_student WHERE user_id = %s",
            (user_id,)
        )
        total_courses = cursor.fetchone()[0] or 0

        # 5. 获取已完成的课程数（progress=100）
        cursor.execute(
            "SELECT COUNT(*) FROM course_progress WHERE user_id = %s AND progress = 100",
            (user_id,)
        )
        completed_courses = cursor.fetchone()[0] or 0

        # 6. 获取进行中的课程数（0 < progress < 100）
        cursor.execute(
            "SELECT COUNT(*) FROM course_progress WHERE user_id = %s AND progress > 0 AND progress < 100",
            (user_id,)
        )
        in_progress_courses = cursor.fetchone()[0] or 0

        # 7. 计算未开始课程数
        not_started_courses = max(0, total_courses - completed_courses - in_progress_courses)

        # 8. 计算课程完成率（防止除零）
        completion_rate = 0.0
        if total_courses > 0:
            completion_rate = round((completed_courses / total_courses) * 100, 2)

        # 9. 计算平均每天学习时长（防止除零）
        avg_daily_learning_seconds = 0
        if total_learning_days > 0:
            avg_daily_learning_seconds = round(total_learning_seconds / total_learning_days)

        # 10. 计算平均每门课程学习时长（防止除零）
        avg_learning_per_course = 0
        if total_courses > 0:
            avg_learning_per_course = round(total_learning_seconds / total_courses)

        # 11. 获取今日学习时长
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0) 
            FROM learning_history 
            WHERE user_id = %s AND start_at >= %s AND start_at < %s
            """,
            (user_id, today_start, tomorrow_start)
        )
        today_learning_seconds = cursor.fetchone()[0] or 0

        # 12. 获取本周学习时长
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0) 
            FROM learning_history 
            WHERE user_id = %s AND start_at >= %s
            """,
            (user_id, week_start_dt)
        )
        week_learning_seconds = cursor.fetchone()[0] or 0

        # 13. 获取最后一次学习日期和课程
        cursor.execute(
            """
            SELECT DATE(lh.finish_at), c.title
            FROM learning_history lh
            JOIN courses c ON lh.course_id = c.id
            WHERE lh.user_id = %s AND lh.finish_at IS NOT NULL
            ORDER BY lh.finish_at DESC
            LIMIT 1
            """,
            (user_id,)
        )
        last_learning = cursor.fetchone()
        last_learning_date = last_learning[0].strftime("%Y-%m-%d") if last_learning and last_learning[0] else None
        last_learning_course = last_learning[1] if last_learning else None

        # 14. 时间格式化
        total_hours = round(total_learning_seconds / 3600, 2)
        today_learning_minutes = today_learning_seconds // 60
        today_learning_hours = round(today_learning_seconds / 3600, 2)
        week_learning_hours = round(week_learning_seconds / 3600, 2)

        # 格式化天时分
        days = total_learning_seconds // (24 * 3600)
        hours = (total_learning_seconds % (24 * 3600)) // 3600
        minutes = (total_learning_seconds % 3600) // 60
        days_hours_minutes = f"{days}天{hours}小时{minutes}分钟"

        # 构建返回数据
        learning_statistics = {
            "total_learning_seconds": int(total_learning_seconds),
            "total_learning_days": int(total_learning_days),
            "current_streak": int(streak),
            "total_courses": int(total_courses),
            "completed_courses": int(completed_courses),
            "in_progress_courses": int(in_progress_courses),
            "not_started_courses": int(not_started_courses),
            "completion_rate": completion_rate,
            "avg_daily_learning_seconds": int(avg_daily_learning_seconds),
            "avg_learning_per_course": int(avg_learning_per_course)
        }

        recent_activity = {
            "today_learning_seconds": int(today_learning_seconds),
            "today_learning_minutes": int(today_learning_minutes),
            "today_learning_hours": today_learning_hours,
            "week_learning_seconds": int(week_learning_seconds),
            "week_learning_hours": week_learning_hours,
            "last_learning_date": last_learning_date,
            "last_learning_course": last_learning_course
        }

        progress_distribution = {
            "completed": int(completed_courses),
            "in_progress": int(in_progress_courses),
            "not_started": int(not_started_courses)
        }

        time_breakdown = {
            "total_hours": total_hours,
            "days_hours_minutes": days_hours_minutes,
            "by_course_type": {}  # 这里可以根据需要添加按课程类型的分类
        }

        return jsonify({
            "success": True,
            "data": {
                "learning_statistics": learning_statistics,
                "recent_activity": recent_activity,
                "progress_distribution": progress_distribution,
                "time_breakdown": time_breakdown
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/user/dashboard", methods=["GET"])
@login_required
def user_dashboard(user_id):
    """
    用户综合数据面板接口
    返回用户的全部关键数据
    """
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 1. 用户基本信息
        cursor.execute(
            "SELECT id, username, email, phone, role, balance, created_at FROM users WHERE id = %s",
            (user_id,)
        )
        user_result = cursor.fetchone()

        if not user_result:
            return jsonify({"success": False, "message": "用户不存在"}), 404

        # 角色转换
        role_map = {0: '学生', 1: '老师'}
        role = role_map.get(user_result[4], '未知')

        user_info = {
            "user_id": user_result[0],
            "username": user_result[1],
            "email": user_result[2],
            "phone": user_result[3],
            "role": role,
            "balance": float(user_result[5]) if user_result[5] is not None else 0.0,
            "created_at": user_result[6].strftime("%Y-%m-%d %H:%M:%S") if user_result[6] else None
        }

        # 2. 学习统计摘要
        # 总学习时长
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM learning_history WHERE user_id = %s",
            (user_id,)
        )
        total_seconds = cursor.fetchone()[0] or 0
        total_learning_hours = round(total_seconds / 3600, 2)

        # 已购课程数
        cursor.execute(
            "SELECT COUNT(*) FROM course_student WHERE user_id = %s",
            (user_id,)
        )
        total_courses = cursor.fetchone()[0] or 0

        # 已完成课程数
        cursor.execute(
            "SELECT COUNT(*) FROM course_progress WHERE user_id = %s AND progress = 100",
            (user_id,)
        )
        completed_courses = cursor.fetchone()[0] or 0

        # 连续学习天数
        cursor.execute(
            """
            SELECT DISTINCT DATE(start_at)
            FROM learning_history
            WHERE user_id = %s
            ORDER BY DATE(start_at) DESC
            """,
            (user_id,)
        )
        rows = cursor.fetchall()
        dates = [row[0] for row in rows]

        streak = 0
        today_date = datetime.date.today()
        today_learned = any(date == today_date for date in dates) if dates else False

        if dates:
            expected = today_date if today_learned else today_date - datetime.timedelta(days=1)
            for d in dates:
                if d == expected:
                    streak += 1
                    expected -= datetime.timedelta(days=1)
                else:
                    break

        # 今日学习时长
        today_start = datetime.datetime.combine(today_date, datetime.time.min)
        tomorrow_start = today_start + datetime.timedelta(days=1)
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0) 
            FROM learning_history 
            WHERE user_id = %s AND start_at >= %s AND start_at < %s
            """,
            (user_id, today_start, tomorrow_start)
        )
        today_seconds = cursor.fetchone()[0] or 0
        today_learning_minutes = today_seconds // 60

        # 完成率
        completion_rate = round((completed_courses / total_courses * 100), 2) if total_courses > 0 else 0.0

        learning_summary = {
            "total_learning_hours": total_learning_hours,
            "total_courses": total_courses,
            "completed_courses": completed_courses,
            "current_streak": streak,
            "today_learning_minutes": today_learning_minutes,
            "completion_rate": completion_rate
        }

        # 3. 最近活动
        # 最近学习的课程（最近3门）
        cursor.execute(
            """
            SELECT 
                lh.course_id,
                c.title,
                cp.progress,
                MAX(lh.start_at) as last_studied
            FROM learning_history lh
            JOIN courses c ON lh.course_id = c.id
            LEFT JOIN course_progress cp ON lh.course_id = cp.course_id AND cp.user_id = %s
            WHERE lh.user_id = %s
            GROUP BY lh.course_id, c.title, cp.progress
            ORDER BY last_studied DESC
            LIMIT 3
            """,
            (user_id, user_id)
        )
        recent_courses_data = cursor.fetchall()

        recent_courses = []
        for row in recent_courses_data:
            recent_courses.append({
                "course_id": row[0],
                "title": row[1],
                "progress": row[2] or 0,
                "last_studied": row[3].strftime("%Y-%m-%d %H:%M:%S") if row[3] else None
            })

        # 最近考试（最近3次）
        cursor.execute(
            """
            SELECT 
                er.exam_id,
                e.title,
                er.score,
                (SELECT SUM(score) FROM questions WHERE exam_id = er.exam_id) as total_score,
                er.created_at
            FROM exam_results er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.user_id = %s
            ORDER BY er.created_at DESC
            LIMIT 3
            """,
            (user_id,)
        )
        recent_exams_data = cursor.fetchall()

        recent_exams = []
        for row in recent_exams_data:
            exam_id, title, score, total_score, created_at = row
            total_score = total_score or 100  # 如果没有题目总分，默认100
            percentage = round((score / total_score * 100), 2) if total_score > 0 else 0

            recent_exams.append({
                "exam_id": exam_id,
                "title": title,
                "score": score,
                "total_score": total_score,
                "percentage": percentage,
                "date": created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else None
            })

        # 最近评论（最近3条）
        cursor.execute(
            """
            SELECT 
                c.id,
                c.course_id,
                cs.title,
                c.content,
                c.rating,
                c.created_at
            FROM comments c
            JOIN courses cs ON c.course_id = cs.id
            WHERE c.user_id = %s
            ORDER BY c.created_at DESC
            LIMIT 3
            """,
            (user_id,)
        )
        recent_comments_data = cursor.fetchall()

        recent_comments = []
        for row in recent_comments_data:
            recent_comments.append({
                "comment_id": row[0],
                "course_id": row[1],
                "course_title": row[2],
                "content": row[3][:50] + "..." if len(row[3]) > 50 else row[3],  # 截断长评论
                "rating": row[4],
                "created_at": row[5].strftime("%Y-%m-%d %H:%M:%S") if row[5] else None
            })

        recent_activity = {
            "recent_courses": recent_courses,
            "recent_exams": recent_exams,
            "recent_comments": recent_comments
        }

        # 4. 进度概览
        # 按状态统计
        cursor.execute(
            """
            SELECT 
                COUNT(CASE WHEN progress = 100 THEN 1 END) as completed,
                COUNT(CASE WHEN progress > 0 AND progress < 100 THEN 1 END) as in_progress,
                COUNT(CASE WHEN progress = 0 OR progress IS NULL THEN 1 END) as not_started
            FROM course_progress 
            WHERE user_id = %s
            """,
            (user_id,)
        )
        status_stats = cursor.fetchone()

        by_status = {
            "completed": status_stats[0] or 0,
            "in_progress": status_stats[1] or 0,
            "not_started": status_stats[2] or 0
        }

        # 按百分比区间统计
        cursor.execute(
            """
            SELECT 
                COUNT(CASE WHEN progress >= 0 AND progress < 25 THEN 1 END) as range_0_25,
                COUNT(CASE WHEN progress >= 25 AND progress < 50 THEN 1 END) as range_25_50,
                COUNT(CASE WHEN progress >= 50 AND progress < 75 THEN 1 END) as range_50_75,
                COUNT(CASE WHEN progress >= 75 AND progress < 100 THEN 1 END) as range_75_100,
                COUNT(CASE WHEN progress = 100 THEN 1 END) as range_100
            FROM course_progress 
            WHERE user_id = %s
            """,
            (user_id,)
        )
        range_stats = cursor.fetchone()

        by_percentage = [
            {"range": "0-25%", "count": range_stats[0] or 0},
            {"range": "25-50%", "count": range_stats[1] or 0},
            {"range": "50-75%", "count": range_stats[2] or 0},
            {"range": "75-100%", "count": range_stats[3] or 0},
            {"range": "100%", "count": range_stats[4] or 0}
        ]

        progress_overview = {
            "by_status": by_status,
            "by_percentage": by_percentage
        }

        # 5. 互动统计
        # 评论总数
        cursor.execute(
            "SELECT COUNT(*) FROM comments WHERE user_id = %s",
            (user_id,)
        )
        total_comments = cursor.fetchone()[0] or 0

        # 课程点赞数
        cursor.execute(
            "SELECT COUNT(*) FROM course_likes WHERE user_id = %s",
            (user_id,)
        )
        total_course_likes = cursor.fetchone()[0] or 0

        # 评论点赞数
        cursor.execute(
            "SELECT COUNT(*) FROM comment_likes WHERE user_id = %s",
            (user_id,)
        )
        total_comment_likes = cursor.fetchone()[0] or 0

        # 总点赞数
        total_likes_given = total_course_likes + total_comment_likes

        # 收藏数
        cursor.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = %s",
            (user_id,)
        )
        total_favorites = cursor.fetchone()[0] or 0

        interaction_stats = {
            "total_comments": total_comments,
            "total_likes_given": total_likes_given,
            "total_course_likes": total_course_likes,
            "total_comment_likes": total_comment_likes,
            "total_favorites": total_favorites
        }

        # 6. 成就系统
        # 连续学习成就
        streak_achievements = [
            {"days": 7, "achieved": streak >= 7, "date": None},  # 实际项目中应该有具体达成日期
            {"days": 30, "achieved": streak >= 30, "date": None},
            {"days": 100, "achieved": streak >= 100, "date": None}
        ]

        # 课程完成成就
        completion_achievements = [
            {"courses": 5, "achieved": completed_courses >= 5, "date": None},
            {"courses": 10, "achieved": completed_courses >= 10, "date": None},
            {"courses": 20, "achieved": completed_courses >= 20, "date": None}
        ]

        achievements = {
            "streak_achievements": streak_achievements,
            "completion_achievements": completion_achievements
        }

        # 7. 快速链接
        # 继续学习（进度最高但未完成的课程）
        cursor.execute(
            """
            SELECT 
                cp.course_id,
                c.title,
                cp.progress,
                l.id as lesson_id,
                l.title as lesson_title
            FROM course_progress cp
            JOIN courses c ON cp.course_id = c.id
            LEFT JOIN lessons l ON c.id = l.course_id
            WHERE cp.user_id = %s AND cp.progress < 100
            ORDER BY cp.progress DESC, cp.updated_at DESC
            LIMIT 1
            """,
            (user_id,)
        )
        continue_learning_data = cursor.fetchone()

        continue_learning = None
        if continue_learning_data:
            continue_learning = {
                "course_id": continue_learning_data[0],
                "course_title": continue_learning_data[1],
                "progress": continue_learning_data[2],
                "lesson_id": continue_learning_data[3],
                "lesson_title": continue_learning_data[4]
            }

        # 推荐课程（按学生数排名，排除已购买课程）
        cursor.execute(
            """
            SELECT 
                c.id,
                c.title,
                c.price,
                c.student_count,
                u.username as teacher_name
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.id NOT IN (SELECT course_id FROM course_student WHERE user_id = %s)
            ORDER BY c.student_count DESC
            LIMIT 3
            """,
            (user_id,)
        )
        recommended_courses_data = cursor.fetchall()

        recommended_courses = []
        for row in recommended_courses_data:
            recommended_courses.append({
                "course_id": row[0],
                "title": row[1],
                "price": float(row[2]) if row[2] is not None else 0.0,
                "student_count": row[3],
                "teacher_name": row[4]
            })

        quick_links = {
            "continue_learning": continue_learning,
            "recommended_courses": recommended_courses
        }

        return jsonify({
            "success": True,
            "data": {
                "user_info": user_info,
                "learning_summary": learning_summary,
                "recent_activity": recent_activity,
                "progress_overview": progress_overview,
                "interaction_stats": interaction_stats,
                "achievements": achievements,
                "quick_links": quick_links
            }
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    app.run(debug=True)
