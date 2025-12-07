import pymysql

db_config = {
    "host": "101.200.161.243",
    "user": "root",
    "password": "050316",
    "database": "online_learning",
    "charset": "utf8mb4"
}


def course_list(course_id):
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "select title from lessons where id = %s"
            , course_id
        )
        re = cursor.fetchall()

        return re
    except:
        print("运行失败")
    finally:
        cursor.close()
        conn.close()


print(list(course_list(1)))
