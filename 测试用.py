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
    select l.id AS lesson_id,COALESCE(lp.progress, 0) AS progress
    from lessons l
    LEFT JOIN learning_progress lp 
        ON lp.lesson_id = l.id AND lp.user_id = %s
    WHERE l.course_id = %s
    ORDER BY l.id ASC
    """,
    (1, 1)
)

course_price = cursor.fetchall()
print(course_price)