from flask import Flask, request, render_template, jsonify, Response
import pymysql

app = Flask(__name__)

db_config = {
    "host":"101.200.161.243",
    "user":"root",
    "password":"050316",
    "database":"online_learning",
    "charset": "utf8mb4"
}

@app.route('/api/buy_course',methods=['POST'])
def buy_course():
    data = request.get_json()

    user_id = data.get("user_id")
    course_id = data.get("course_id")

    if not user_id or not course_id:
        return jsonify({"success":False,"message":"缺少 user_id 或 course_id"}),400

    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # 检测是否已购买
        cursor.execute(
            "select id from course_student where user_id = %s and course_id = %s",
            (user_id,course_id)
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "已拥有该课程，无需重复购买"}), 400

        # 查询课程价格
        cursor.execute(
            "select price from courses where id = %s",
            course_id
        )

        course = cursor.fetchone() # 获取返回的数据
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

@app.route('/api/course_list',methods=['POST'])
def course_list(page = 1,keyword = None):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        if keyword != None:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses where title = %s',
                (keyword)
            )
            all_list = cursor.fetchone()

            return jsonify({
                "id": all_list[0],
                "title": all_list[1],
                "price": all_list[2],
                "student_count": [3],
                "cover_url": all_list[4]
            })

        else:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses limit %s 10',
                ((page - 1) * 10)
            )
            all_list = cursor.fetchall()
            id = []
            title = []
            price = []
            student_count = []
            cover_url = []
            for i in all_list:
                id.append(i[0])
                title.append(i[1])
                price.append(i[2])
                student_count.append(i[3])
                cover_url.append(i[4])

            return jsonify({
                "id": id,
                "title": title,
                "price": price,
                "student_count": student_count,
                "cover_url": cover_url
            })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "购买失败：{}".format(str(e))}), 500
    finally:
        cursor.close()
        conn.close()



if __name__ == '__main__':
    app.run(debug=True)