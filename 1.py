from flask import Flask, request, render_template, jsonify, Response
from functools import wraps
import pymysql
import jwt
import bcrypt
import datetime

app = Flask(__name__)

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
    keyword = data.get("keyword", None)

    page = max(int(page), 1)
    page_size = 10
    offset = (page - 1) * page_size

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        if keyword != None:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses where title like ORDER BY created_at DESC '
                '%s limit %s 10',
                ("%" + keyword + "%", offset)
            )
        else:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses ORDER BY created_at DESC limit %s 10',
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
        return jsonify({"success": False, "message": "缺少 course_id"}), 400

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
        return jsonify({"success": False, "message": "course_id不能为空"}), 400

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


@app.route("/api/progress/get",methods=["POST"])
@login_required
def progress_get(user_id):
    data = request.json or {}
    course_id = data.get("course_id")

    if not course_id:
        return jsonify({"success": False, "message": "course_id不能为空"})

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    #




if __name__ == '__main__':
    app.run(debug=True)
