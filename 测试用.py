import pymysql

conn = pymysql.connect(**db_config)
cursor = conn.cursor()
cursor.execute(
    "select sum(duration_seconds) from learning_history where user_id = %s",
    (0,)
)

course_price = cursor.fetchone()[0]
print(course_price)