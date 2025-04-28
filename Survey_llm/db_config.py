import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host='localhost',
        user='admin',
        password='password',
        database='student_survey'
    )
