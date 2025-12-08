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
    "select price from courses where id = %s",
    1
)
course_price = cursor.fetchone()
print(float(course_price[0]))