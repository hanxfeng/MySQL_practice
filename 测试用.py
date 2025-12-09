import pymysql
db_config = {
    "host": "101.200.161.243",
    "user": "root",
    "password": "050316",
    "database": "online_learning",
    "charset": "utf8mb4"
}
conn = pymysql.connect(**db_config)
cursor = conn.cursor()
cursor.execute(
    "select created_at from course_student where user_id = %s and course_id = %s",
    (1, 1)
)
course_price = cursor.fetchone()
print(course_price)