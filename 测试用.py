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
    """
    select lh.id,lh.course_id,c.title,lh.lesson_id,l.title,lh.start_at,lh.finish_at,lh.duration_seconds
    from learning_history lh
    join courses c on lh.course_id = c.id
    join lessons l on lh.lesson_id = l.id
    where lh.user_id = %s
    limit 30
    """,
    (1,)
)

course_price = cursor.fetchall()
print(course_price)