from flask import Flask, request, render_template, jsonify, Response
import pymysql

app = Flask(__name__)

db_config = {
    "host": "101.200.161.243",
    "user": "root",
    "password": "050316",
    "database": "online_learning",
    "charset": "utf8mb4"
}


@app.route('/api/buy_course', methods=['POST'])
def buy_course():
    data = request.get_json()

    user_id = data.get("user_id")
    course_id = data.get("course_id")

    if not user_id or not course_id:
        return jsonify({"success": False, "message": "缺少 user_id 或 course_id"}), 400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 检测是否已购买
        cursor.execute(
            "select id from course_student where user_id = %s and course_id = %s",
            (user_id, course_id)
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "已拥有该课程，无需重复购买"}), 400

        # 查询课程价格
        cursor.execute(
            "select price from courses where id = %s",
            course_id
        )

        course = cursor.fetchone()  # 获取返回的数据
        if not course:
            return jsonify({"success": False, "message": "课程不存在"}), 404

        price = course[0]

        # 检查余额
        cursor.execute(
            "SELECT balance FROM users WHERE id=%s FOR UPDATE",
            user_id
        )
        user = cursor.fetchone()
        if not user or user[0] < price:
            return jsonify({"success": False, "message": "余额不足"}), 400

        # 创建订单
        cursor.execute(
            "INSERT INTO orders (user_id, course_id, price, status) VALUES (%s, %s, %s, 0)",
            (user_id, course_id, price)
        )
        order_id = cursor.lastrowid

        # 扣费
        cursor.execute(
            "UPDATE users SET balance = balance - %s WHERE id=%s",
            (price, user_id)
        )

        # 将订单状态更新为已支付
        cursor.execute(
            "UPDATE orders SET status=1 WHERE id=%s",
            (order_id,)
        )

        # 添加课程权限
        cursor.execute(
            "INSERT INTO course_student (user_id, course_id) VALUES (%s, %s)",
            (user_id, course_id)
        )

        # 初始化学习任务
        cursor.execute(
            """
            INSERT INTO lessons_progress (user_id, lesson_id, status)
            SELECT %s, id, 0
            FROM lessons WHERE course_id=%s
            """,
            (user_id, course_id)
        )

        # 提交事务
        conn.commit()

        return jsonify({
            "success": True,
            "message": "课程购买成功",
            "order_id": order_id
        })

    except Exception as e:
        # 出现异常回滚
        conn.rollback()
        return jsonify({"success": False, "message": "购买失败：{}".format(str(e))}), 500

    finally:
        cursor.close()
        conn.close()


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
                ("%"+keyword+"%", offset)
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
        teacher= cursor.fetchone()

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


if __name__ == '__main__':
    app.run(debug=True)
