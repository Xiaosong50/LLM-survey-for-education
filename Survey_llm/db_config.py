import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host='localhost',
        user='admin',
        password='Lxs,123321',
        database='student_survey'
    )
