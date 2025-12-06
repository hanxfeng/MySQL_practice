import pymysql

db_config = {
    "host": "101.200.161.243",
    "user": "root",
    "password": "050316",
    "database": "online_learning",
    "charset": "utf8mb4"
}


def course_list(page=1, keyword=None):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        if keyword == None:
            cursor.execute(
                'select id,title,price,student_count,cover_url from courses limit %s,10',
                ((page - 1) * 10)
            )
            re = cursor.fetchall()

            return re
    except:
        print("运行失败")
    finally:
        cursor.close()
        conn.close()


print(course_list())
