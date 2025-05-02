import os
import mysql.connector
from mysql.connector import Error
from form_app.validators import UserFormModel
from dotenv import load_dotenv
import secrets
import hashlib
from datetime import date

# Загрузка переменных окружения
load_dotenv()

DB_CONFIG = {
    #'host': os.getenv('MYSQL_HOST', 'db'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'port': 3306,
}

def get_db_connection():
    try:
        print("Attempting to connect with config:", {k: v for k, v in DB_CONFIG.items() if k != 'password'})
        connection = mysql.connector.connect(**DB_CONFIG)
        print("Database connection successful")
        return connection
    except Error as e:
        print(f"Error connecting to MySQL Platform: {e}")
        raise

def database_connection(function):
    def wrapper(*args, **kwargs):
        connection = None
        try:
            connection = get_db_connection()
            return function(*args, connection=connection, **kwargs)
        except Exception as e:
            print(f"Database connection error in wrapper: {e}")
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()
    return wrapper

def hash_password(password: str, salt: bytes = None):
    if salt is None:
        salt = secrets.token_bytes(16)
    # Используем pbkdf2_hmac для хеширования пароля
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return hashed.hex(), salt.hex()

def check_password(plain_password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    hashed = hashlib.pbkdf2_hmac('sha256', plain_password.encode(), salt, 100000)
    return hashed.hex() == password_hash

@database_connection
def save_user_form(form_data: UserFormModel, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor()

    # Генерируем логин и пароль
    login = secrets.token_hex(4)  # 8 символов hex
    password = secrets.token_urlsafe(8)  # примерно 8 символов

    password_hash, salt = hash_password(password)

    # Вставляем данные формы с новыми полями
    INSERT_FORM_SQL = (
        "INSERT INTO user_forms "
        "(full_name, phone_number, email, birth_date, gender, bio, "
        "login, password_hash, salt) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )

    insert_form_data = (
        form_data.full_name,
        form_data.phone,
        form_data.email,
        form_data.birth_date,
        form_data.gender,
        form_data.bio,
        login,
        password_hash,
        salt,
    )

    cursor.execute(INSERT_FORM_SQL, insert_form_data)
    form_id = cursor.lastrowid

    # Обработка языков программирования (если есть)
    prog_languages_values = form_data.prog_languages
    if prog_languages_values:
        SELECT_PROG_LANGS_SQL = (
            "SELECT lang_id FROM programming_languages WHERE name IN ({})".format(
                ','.join(['%s'] * len(prog_languages_values))
            )
        )

        cursor.execute(SELECT_PROG_LANGS_SQL, prog_languages_values)
        lang_ids = [row[0] for row in cursor.fetchall()]

        INSERT_USER_LANGS_SQL = (
            "INSERT INTO user_prog_languages (lang_id, form_id) "
            "VALUES (%s, %s)"
        )
        for lang_id in lang_ids:
            cursor.execute(INSERT_USER_LANGS_SQL, (lang_id, form_id))

    conn.commit()
    print(f"Form saved successfully with login: {login}")

    return login, password

@database_connection
def find_user_by_login(login: str, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor(dictionary=True)

    QUERY = "SELECT * FROM user_forms WHERE login = %s LIMIT 1"
    cursor.execute(QUERY, (login,))
    user = cursor.fetchone()
    
    if user:
        # Получаем языки программирования для этого пользователя
        languages_query = """
        SELECT pl.name 
        FROM programming_languages pl
        JOIN user_prog_languages upl ON pl.lang_id = upl.lang_id
        WHERE upl.form_id = %s
        """
        
        cursor.execute(languages_query, (user['form_id'],))
        languages = [row['name'] for row in cursor.fetchall()]
        user['prog_languages'] = languages
    
    return user

@database_connection
def update_user_data(login: str, form_data: UserFormModel, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor()

    UPDATE_SQL = (
        "UPDATE user_forms SET "
        "full_name = %s, "
        "phone_number = %s, "
        "email = %s, "
        "birth_date = %s, "
        "gender = %s, "
        "bio = %s "
        "WHERE login = %s"
    )

    update_data = (
        form_data.full_name,
        form_data.phone,
        form_data.email,
        form_data.birth_date,
        form_data.gender,
        form_data.bio,
        login,
    )

    cursor.execute(UPDATE_SQL, update_data)

    # Обновляем языки программирования:

    # Сначала удаляем старые связи
    DELETE_LANGS_SQL = "DELETE FROM user_prog_languages WHERE form_id = (SELECT form_id FROM user_forms WHERE login = %s)"
    cursor.execute(DELETE_LANGS_SQL, (login,))

    # Вставляем новые
    prog_languages_values = form_data.prog_languages
    if prog_languages_values:
        SELECT_PROG_LANGS_SQL = (
            "SELECT lang_id FROM programming_languages WHERE name IN ({})".format(
                ','.join(['%s'] * len(prog_languages_values))
            )
        )
        cursor.execute(SELECT_PROG_LANGS_SQL, prog_languages_values)
        lang_ids = [row[0] for row in cursor.fetchall()]

        # Получаем form_id
        cursor.execute("SELECT form_id FROM user_forms WHERE login = %s", (login,))
        form_id = cursor.fetchone()[0]

        INSERT_USER_LANGS_SQL = (
            "INSERT INTO user_prog_languages (lang_id, form_id) "
            "VALUES (%s, %s)"
        )
        for lang_id in lang_ids:
            cursor.execute(INSERT_USER_LANGS_SQL, (lang_id, form_id))

    conn.commit()
    print(f"User data updated for login: {login}")


@database_connection
def get_all_user_forms(**kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor(dictionary=True)

    QUERY = """
        SELECT uf.form_id, uf.full_name, uf.phone_number, uf.email, uf.birth_date, uf.gender, uf.bio, 
               GROUP_CONCAT(pl.name SEPARATOR ', ') as prog_languages
        FROM user_forms uf
        LEFT JOIN user_prog_languages upl ON uf.form_id = upl.form_id
        LEFT JOIN programming_languages pl ON upl.lang_id = pl.lang_id
        GROUP BY uf.form_id
    """
    cursor.execute(QUERY)
    user_forms = cursor.fetchall()
    return user_forms

@database_connection
def delete_user_form(form_id: int, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor()

    DELETE_SQL = "DELETE FROM user_forms WHERE form_id = %s"
    cursor.execute(DELETE_SQL, (form_id,))
    conn.commit()

@database_connection
def get_user_form_by_id(form_id: int, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor(dictionary=True)

    QUERY = """
        SELECT uf.full_name, uf.phone_number, uf.email, uf.birth_date, uf.gender, uf.bio, 
               GROUP_CONCAT(pl.name SEPARATOR ', ') as prog_languages
        FROM user_forms uf
        LEFT JOIN user_prog_languages upl ON uf.form_id = upl.form_id
        LEFT JOIN programming_languages pl ON upl.lang_id = pl.lang_id
        WHERE uf.form_id = %s
        GROUP BY uf.form_id
    """
    cursor.execute(QUERY, (form_id,))
    user_form = cursor.fetchone()
    return user_form

@database_connection
def update_user_form_by_id(form_id: int, form_data: UserFormModel, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor()

    UPDATE_SQL = (
        "UPDATE user_forms SET "
        "full_name = %s, "
        "phone_number = %s, "
        "email = %s, "
        "birth_date = %s, "
        "gender = %s, "
        "bio = %s "
        "WHERE form_id = %s"
    )

    update_data = (
        form_data.full_name,
        form_data.phone,
        form_data.email,
        form_data.birth_date,
        form_data.gender,
        form_data.bio,
        form_id,
    )

    cursor.execute(UPDATE_SQL, update_data)

    # Обновляем языки программирования:

    # Сначала удаляем старые связи
    DELETE_LANGS_SQL = "DELETE FROM user_prog_languages WHERE form_id = %s"
    cursor.execute(DELETE_LANGS_SQL, (form_id,))

    # Вставляем новые
    prog_languages_values = form_data.prog_languages
    if prog_languages_values:
        SELECT_PROG_LANGS_SQL = (
            "SELECT lang_id FROM programming_languages WHERE name IN ({})".format(
                ','.join(['%s'] * len(prog_languages_values))
            )
        )
        cursor.execute(SELECT_PROG_LANGS_SQL, prog_languages_values)
        lang_ids = [row[0] for row in cursor.fetchall()]

        INSERT_USER_LANGS_SQL = (
            "INSERT INTO user_prog_languages (lang_id, form_id) "
            "VALUES (%s, %s)"
        )
        for lang_id in lang_ids:
            cursor.execute(INSERT_USER_LANGS_SQL, (lang_id, form_id))

    conn.commit()

@database_connection
def get_prog_lang_stats(**kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor(dictionary=True)

    QUERY = """
        SELECT pl.name, COUNT(upl.lang_id) as count
        FROM programming_languages pl
        LEFT JOIN user_prog_languages upl ON pl.lang_id = upl.lang_id
        GROUP BY pl.name
    """
    cursor.execute(QUERY)
    stats = cursor.fetchall()
    return stats

@database_connection
def get_user_programming_languages(login: str, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor()
    
    query = """
    SELECT pl.name 
    FROM programming_languages pl
    JOIN user_prog_languages upl ON pl.lang_id = upl.lang_id
    JOIN user_forms uf ON upl.form_id = uf.form_id
    WHERE uf.login = %s
    """
    
    cursor.execute(query, (login,))
    return [row[0] for row in cursor.fetchall()]

@database_connection
def get_admin_by_login(login: str, **kwargs):
    conn = kwargs["connection"]
    cursor = conn.cursor(dictionary=True)

    QUERY = "SELECT * FROM admins WHERE login = %s LIMIT 1"
    cursor.execute(QUERY, (login,))
    admin = cursor.fetchone()
    return admin