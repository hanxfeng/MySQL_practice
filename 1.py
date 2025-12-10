from flask import Flask, request, render_template, jsonify, Response
from functools import wraps
import pymysql
import jwt
import bcrypt
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
    page = data.get("page", 1)
    keyword = data.get("keyword", "")

    page = max(int(page), 1)
    page_size = 10
    offset = (page - 1) * page_size

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        if keyword != None:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses where title like %s ORDER BY created_at DESC limit %s, 10',
                ("%" + keyword + "%", offset)
            )
        else:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses ORDER BY created_at DESC limit %s, 10',
                ((page - 1) * 10)
            )
        all_list = cursor.fetchall()
        result = []
        for row in all_list:
            result.append({
                "id": row[0],
                "title": row[1],
                "price": float(row[2]),
                "student_count": row[3],
                "cover_url": row[4]
            })

        return jsonify({"success": True, "data": result})
    except Exception as e:
        conn.rollback()
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
        return jsonify({"success": False, "message": "缺少参数 lesson_id 或 progress"}), 400

    progress = min(max(progress, 0), 100)  # 限制 0~100

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO learning_progress (user_id, lesson_id, progress)
            VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE progress=%s, updated_at=NOW()
            """,
            (user_id, lesson_id, progress)
        )

        conn.commit()
        return jsonify({"success": True, "message": "进度已更新"}), 200

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
    offset = (page-1) * limit

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


if __name__ == '__main__':
    app.run(debug=True)
