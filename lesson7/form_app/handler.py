from datetime import datetime, timedelta
from email.utils import formatdate, parsedate_to_datetime
from http import HTTPStatus, cookies
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
import re
import traceback
from urllib.parse import parse_qs, quote, unquote
import mimetypes
import os
import secrets
import hashlib

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError

from form_app.database import (
    delete_user_form, 
    get_admin_by_login, 
    get_all_user_forms, 
    get_prog_lang_stats, 
    get_user_form_by_id, 
    get_user_programming_languages, 
    save_user_form, 
    find_user_by_login, 
    update_user_data, 
    check_password, 
    update_user_form_by_id
)
from form_app.exceptions import InvalidRequestError
from form_app.models import Request, Response
from form_app.validators import UserFormModel

APPLICATION_URLENCODED = "application/x-www-form-urlencoded"
EPOCH = formatdate(0, usegmt=True)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape()  # Автоматическое экранирование в шаблонах Jinja2
)

sessions = {} 

def generate_csrf_token():
    return secrets.token_hex(16)

def set_csrf_token(cookies):
    csrf_token = generate_csrf_token()
    cookies["csrf_token"] = csrf_token
    cookies["csrf_token"]["httponly"] = True
    cookies["csrf_token"]["samesite"] = "Strict"
    return csrf_token

def check_csrf_token(request, formdata):
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie:
        raise Exception("CSRF token cookie missing")
    
    form_token = formdata.get("csrf_token")
    if not form_token:
        raise Exception("CSRF token missing in form")
    
    if form_token != csrf_cookie.value:
        raise Exception("Invalid CSRF token")

def get_urlencoded_data(request: Request, rfile) -> dict:
    if request.headers.get("Content-Type", "") != APPLICATION_URLENCODED:
        raise InvalidRequestError("invalid Content-Type")

    content_length = int(request.headers.get("Content-Length", 0))
    if content_length == 0:
        raise InvalidRequestError("invalid Content-Length")

    content = rfile.read(content_length).decode()
    query = {}
    for name, value in parse_qs(content).items():
        if name.endswith("[]"):
            query[name[:-2]] = value
        else:
            query[name] = value[0]
    return query

class HTTPHandler(BaseHTTPRequestHandler):
    routes = {"GET": [], "POST": []}

    @property
    def req(self) -> Request:
        headers = dict(self.headers)
        cookies = SimpleCookie(headers.get("Cookie", ""))
        return Request(headers=headers, cookies=cookies)

    def resp(self, response: Response):
        self.send_response(response.status)
        for k, v in response.headers.items():
            self.send_header(k, v)
        for morsel in response.cookies.values():
            self.send_header("Set-Cookie", morsel.OutputString())
        self.end_headers()
        if response.content:
            body = (
                response.content.encode()
                if isinstance(response.content, str)
                else response.content
            )
            self.wfile.write(body)

    @classmethod
    def get(cls, path_pattern: str):
        pattern = re.compile(rf"^{path_pattern}$")
        def decorator(func):
            def handler(self, **kwargs):
                resp = func(self.req, **kwargs)
                self.resp(resp)
            cls.routes["GET"].append((pattern, handler))
            return func
        return decorator

    @classmethod
    def post(cls, path_pattern: str, *, urlencoded: bool = False):
        pattern = re.compile(rf"^{path_pattern}$")
        def decorator(func):
            def handler(self, **kwargs):
                request = self.req
                data = None
                if urlencoded:
                    data = get_urlencoded_data(request, self.rfile)
                    resp = func(request, data, **kwargs)
                else:
                    resp = func(request, **kwargs)
                self.resp(resp)
            cls.routes["POST"].append((pattern, handler))
            return func
        return decorator

    def serve_static(self):

        static_dir = os.path.join(os.path.dirname(__file__), "static") 
        
        relative_path = os.path.relpath(self.path, '/static/')
        
        file_path = os.path.join(static_dir, relative_path)
        
        if not os.path.isfile(file_path):
            self.send_error(404, explain=f"File not found: {file_path}")
            return

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            content_type, _ = mimetypes.guess_type(file_path)
            
            self.send_response(200)
            self.send_header('Content-Type', content_type or 'application/octet-stream')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except PermissionError:
            self.send_error(403, explain="Access denied")
        except IOError:
            self.send_error(500, explain="Error reading file")

    def do_GET(self):
        try:
            if self.path.startswith("/static/"):
                return self.serve_static()  

            for pattern, handler in self.routes["GET"]:
                m = pattern.match(self.path)
                if not m:
                    continue
                kwargs = m.groupdict()
                for k, v in kwargs.items():
                    if v.isdigit():
                        kwargs[k] = int(v)
                return handler(self, **kwargs)

            self.send_error(404, explain=f"Page {self.path} not found")

        except Exception as e:
            # Логирование без раскрытия конфиденциальных данных
            print(f"Server error: {e}")
            self.send_error(500, explain="Server error")

    def do_POST(self):
        try:
            for pattern, handler in self.routes["POST"]:
                m = pattern.match(self.path)
                if not m:
                    continue
                kwargs = m.groupdict()
                for k, v in kwargs.items():
                    if v.isdigit():
                        kwargs[k] = int(v)
                return handler(self, **kwargs)

            self.send_error(404, explain=f"Page {self.path} not found")

        except InvalidRequestError as e:
            self.send_error(400, explain=str(e))
        except Exception as e:
            # Логирование без раскрытия конфиденциальных данных
            print(f"Server error: {e}")
            self.send_error(500, explain="Server error")

@HTTPHandler.get("/")
def root(request: Request) -> Response:
    """Главная страница"""
    headers = {"Content-Type": "text/html"}
    cookies = SimpleCookie()

    for name in request.cookies:
        if name.endswith("_err") or name == "success":
            cookies[name] = request.cookies[name]
            cookies[name]["expires"] = EPOCH

    data = {}
    for name in request.cookies:
        data[name] = unquote(request.cookies[name].value)
    data["prog_languages"] = data.get("prog_languages", "").split("|")

    content = env.get_template("index.html").render(**data)
    return Response(
        status=200, headers=headers, cookies=cookies, content=content
    )

@HTTPHandler.post("/submit", urlencoded=True)
def form(request: Request, content: dict) -> Response:
    cookies = SimpleCookie()

    try:
        form_data = UserFormModel(**content)
    except ValidationError as e:
        for err in e.errors():
            location, msg = err["loc"][0], err["msg"]
            
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            elif "at most 500 characters" in msg:
                msg = "Биография не должна превышать 500 символов"
            elif "not a valid email address" in msg:
                msg = "Электронная почта имеет неверный формат"
            elif "invalid datetime format" in msg or "Invalid date format" in msg:
                msg = "Некорректная дата рождения"
            
            cookies[f"{location}_err"] = quote(msg.capitalize())

        # Сохраняем введённые данные
        for field in UserFormModel.model_fields:
            value = content.get(field, "")
            if isinstance(value, list):
                value = "|".join(value)
            cookies[field] = quote(value)

        return Response(
            status=303, headers={"Location": "/"}, cookies=cookies, content=""
        )

    login, password = save_user_form(form_data)

    cookies["login"] = login
    cookies["password"] = password

    for field in UserFormModel.model_fields:
        cookies[field] = ""
        cookies[field]["expires"] = EPOCH
        cookies[f"{field}_err"] = ""
        cookies[f"{field}_err"]["expires"] = EPOCH

    cookies["success"] = "1"

    return Response(
        status=303, headers={"Location": "/success"}, cookies=cookies, content=""
    )

@HTTPHandler.get("/success")
def success(request: Request) -> Response:
    headers = {"Content-Type": "text/html"}
    cookies = SimpleCookie()

    login = request.cookies.get("login")
    password = request.cookies.get("password")

    data = {}
    if login and password:
        data["login"] = unquote(login.value)
        data["password"] = unquote(password.value)

    # Удаляем пароль из кук после показа
    cookies["password"] = ""
    cookies["password"]["expires"] = EPOCH

    content = env.get_template("success.html").render(**data)

    return Response(
        status=200, headers=headers, cookies=cookies, content=content
    )

@HTTPHandler.get("/login")
def login_form(request: Request) -> Response:
    cookies = SimpleCookie()
    error = request.cookies.get("login_err")
    error_msg = unquote(error.value) if error else ""
    cookies["login_err"] = ""
    cookies["login_err"]["expires"] = EPOCH

    content = env.get_template("login.html").render(error=error_msg)
    return Response(
        status=200, headers={"Content-Type": "text/html"}, cookies=cookies, content=content
    )


@HTTPHandler.post("/login", urlencoded=True)
def login_post(request: Request, content: dict) -> Response:
    login = content.get("login", "")
    password = content.get("password", "")
    cookies = SimpleCookie()

    user = find_user_by_login(login)
    if not user:
        cookies["login_err"] = quote("Пользователь не найден.")
        return Response(
            status=303, headers={"Location": "/login"}, cookies=cookies, content=""
        )

    salt = user["salt"]
    if isinstance(salt, bytes):
        salt = salt.hex()

    if not check_password(password, user["password_hash"], salt):
        cookies["login_err"] = quote("Неверный пароль.")
        return Response(
            status=303, headers={"Location": "/login"}, cookies=cookies, content=""
        )

    # Успешный логин
    session_id = secrets.token_hex(16)
    sessions[session_id] = login
    expires = (datetime.now() + timedelta(hours=1)).timestamp()

    cookies["session_id"] = session_id
    cookies["session_id"]["expires"] = formatdate(expires, usegmt=True)

    return Response(
        status=303, headers={"Location": "/edit"}, cookies=cookies, content=""
    )

@HTTPHandler.get("/edit")
def edit_form(request: Request) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("session_id")

    if not session_cookie or session_cookie.value not in sessions:
        return Response(
            status=303, headers={"Location": "/login"}, cookies=cookies, content=""
        )

    login = sessions[session_cookie.value]

    user = find_user_by_login(login)
    if not user:
        del sessions[session_cookie.value]
        return Response(
            status=303, headers={"Location": "/login"}, cookies=cookies, content=""
        )

    # Проверяем, есть ли ошибки валидации
    has_validation_errors = any(name.endswith("_err") for name in request.cookies)

    # Формируем данные для отображения
    data = {}

    # Если есть ошибки валидации, используем данные из кук
    if has_validation_errors:
        for field in UserFormModel.model_fields:
            cookie_val = request.cookies.get(field)
            if cookie_val:
                if field == "prog_languages":
                    val = unquote(cookie_val.value)
                    data[field] = val.split("|") if val else []
                else:
                    data[field] = unquote(cookie_val.value)
            else:
                data[field] = ""

        # Проверяем, есть ли поле phone, если нет, берем из phone_number
        if 'phone' not in data or not data['phone']:
            data['phone'] = user.get('phone_number', '')
    else:
        # Если ошибок нет, берем данные из БД
        data = {
            'full_name': user.get('full_name', ''),
            'phone': user.get('phone_number', ''),
            'email': user.get('email', ''),
            'birth_date': user.get('birth_date', ''),
            'gender': user.get('gender', ''),
            'bio': user.get('bio', ''),
            'prog_languages': user.get('prog_languages', [])
        }

    # Обрабатываем ошибки из кук
    errors = {}
    for name in request.cookies:
        if name.endswith("_err"):
            errors[name] = unquote(request.cookies[name].value)
            cookies[name] = ""
            cookies[name]["expires"] = EPOCH

    success_edit = request.cookies.get("success_edit")
    if success_edit:
        cookies["success_edit"] = ""
        cookies["success_edit"]["expires"] = EPOCH

        # При успешном редактировании очищаем все куки с данными формы
        if not has_validation_errors:
            for field in UserFormModel.model_fields:
                if field in request.cookies:
                    cookies[field] = ""
                    cookies[field]["expires"] = EPOCH

    context = data.copy()
    context.update(errors)
    context["success_edit"] = bool(success_edit)

    content = env.get_template("edit.html").render(**context)

    return Response(
        status=200,
        headers={"Content-Type": "text/html"},
        cookies=cookies,
        content=content,
    )

@HTTPHandler.post("/edit", urlencoded=True)
def edit_post(request: Request, content: dict) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("session_id")

    if not session_cookie or session_cookie.value not in sessions:
        return Response(
            status=303, headers={"Location": "/login"}, cookies=cookies, content=""
        )

    login = sessions[session_cookie.value]

    try:
        form_data = UserFormModel(**content)
    except ValidationError as e:
        for err in e.errors():
            location, msg = err["loc"][0], err["msg"]

            # Обработка различных форматов ошибок от Pydantic
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            elif "at most 500 characters" in msg:
                msg = "Биография не должна превышать 500 символов"
            elif "not a valid email address" in msg:
                msg = "Электронная почта имеет неверный формат"
            elif "invalid datetime format" in msg or "Invalid date format" in msg:
                msg = "Некорректная дата рождения"

            cookies[f"{location}_err"] = quote(msg.capitalize())

        # Сохраняем введённые данные
        for field in UserFormModel.model_fields:
            value = content.get(field, "")
            if isinstance(value, list):
                value = "|".join(value)
            cookies[field] = quote(value)

        return Response(
            status=303, headers={"Location": "/edit"}, cookies=cookies, content=""
        )

    # Обновляем данные пользователя в БД
    update_user_data(login, form_data)

    # Очищаем все куки с данными формы при успешном обновлении
    for field in UserFormModel.model_fields:
        cookies[field] = ""
        cookies[field]["expires"] = EPOCH
        cookies[f"{field}_err"] = ""
        cookies[f"{field}_err"]["expires"] = EPOCH

    # Устанавливаем флаг успешного обновления
    cookies["success_edit"] = "1"
    cookies["success_edit"]["expires"] = formatdate(
        (datetime.now() + timedelta(days=1)).timestamp(), usegmt=True
    )

    return Response(
        status=303, headers={"Location": "/edit"}, cookies=cookies, content=""
    )

admin_sessions = {}

@HTTPHandler.get("/admin")
def admin_login(request: Request) -> Response:
    cookies = SimpleCookie()
    error = request.cookies.get("admin_login_err")
    error_msg = unquote(error.value) if error else ""
    cookies["admin_login_err"] = ""
    cookies["admin_login_err"]["expires"] = EPOCH

    content = env.get_template("admin_login.html").render(error=error_msg)
    return Response(
        status=200, headers={"Content-Type": "text/html"}, cookies=cookies, content=content
    )

@HTTPHandler.post("/admin", urlencoded=True)
def admin_login_post(request: Request, content: dict) -> Response:
    login = content.get("login", "")
    password = content.get("password", "")
    cookies = SimpleCookie()

    admin = get_admin_by_login(login)
    if not admin:
        cookies["admin_login_err"] = quote("Администратор не найден.")
        return Response(
            status=303, headers={"Location": "/admin"}, cookies=cookies, content=""
        )

    salt = admin["salt"]
    if isinstance(salt, bytes):
        salt = salt.hex()

    if not check_password(password, admin["password_hash"], salt):
        cookies["admin_login_err"] = quote("Неверный пароль.")
        return Response(
            status=303, headers={"Location": "/admin"}, cookies=cookies, content=""
        )

    # Генерация токена сессии администратора
    session_id = secrets.token_hex(16)
    admin_sessions[session_id] = login
    expires = (datetime.now() + timedelta(hours=1)).timestamp()

    cookies["admin_session_id"] = session_id
    cookies["admin_session_id"]["expires"] = formatdate(expires, usegmt=True)

    return Response(
        status=303, headers={"Location": "/admin/dashboard"}, cookies=cookies, content=""
    )

@HTTPHandler.get("/admin/dashboard")
def admin_dashboard(request: Request) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("admin_session_id")

    if not session_cookie or session_cookie.value not in admin_sessions:
        return Response(
            status=303, headers={"Location": "/admin"}, cookies=cookies, content=""
        )

    user_forms = get_all_user_forms()
    stats = get_prog_lang_stats()

    content = env.get_template("admin_dashboard.html").render(user_forms=user_forms, stats=stats)
    return Response(
        status=200, headers={"Content-Type": "text/html"}, cookies=cookies, content=content
    )

@HTTPHandler.get(r"/admin/edit/(?P<form_id>\d+)")
def admin_edit_form(request: Request, form_id: int) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("admin_session_id")

    # Проверка сессии
    if not session_cookie or session_cookie.value not in admin_sessions:
        return Response(303, {"Location": "/admin"}, cookies, "")

    # Получаем форму из БД
    user_form = get_user_form_by_id(form_id)
    if not user_form:
        return Response(404, {"Content-Type": "text/html"}, cookies, "Форма не найдена")

    # Генерируем CSRF токен
    csrf_token = secrets.token_hex(16)
    cookies["admin_csrf_token"] = csrf_token
    cookies["admin_csrf_token"]["path"] = "/"
    cookies["admin_csrf_token"]["httponly"] = True
    cookies["admin_csrf_token"]["samesite"] = "Strict"

    # Собираем данные и ошибки
    data = {}
    for field in UserFormModel.model_fields:
        if field == "prog_languages":
            data[field] = user_form.get(field, "").split(", ") if user_form.get(field) else []
        else:
            data[field] = user_form.get(field, "")
    if not data.get("phone"):
        data["phone"] = user_form.get("phone_number", "")

    # Обрабатываем ошибки из кук
    errors = {}
    for name, morsel in request.cookies.items():
        if name.endswith("_err"):
            errors[name] = unquote(morsel.value)
            cookies[name] = ""
            cookies[name]["expires"] = EPOCH

    # Если нет ошибок валидации, очищаем куки с данными формы
    if not errors:
        for field in UserFormModel.model_fields:
            if field in request.cookies:
                cookies[field] = ""
                cookies[field]["expires"] = EPOCH

    # Объединяем
    context = data.copy()
    context.update(errors)
    context["csrf_token"] = csrf_token
    context["form_id"] = form_id

    content = env.get_template("admin_edit_form.html").render(**context)
    return Response(200, {"Content-Type": "text/html"}, cookies, content)

@HTTPHandler.post(r"/admin/edit/(?P<form_id>\d+)", urlencoded=True)
def admin_edit_form_post(request: Request, content: dict, form_id: int) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("admin_session_id")

    # Проверка сессии
    if not session_cookie or session_cookie.value not in admin_sessions:
        return Response(303, {"Location": "/admin"}, cookies, "")

    # Проверка CSRF токена
    csrf_cookie = request.cookies.get("admin_csrf_token")
    form_token = content.get("csrf_token")
    if not csrf_cookie or not form_token or form_token != csrf_cookie.value:
        return Response(403, {"Location": f"/admin/edit/{form_id}"}, cookies, "CSRF Validation Failed")

    # Валидация данных
    form_fields_in_content = ["full_name", "phone", "email", "birth_date", "gender", "prog_languages", "bio"]
    try:
        update_data = {
            "full_name": content.get("full_name", ""),
            "phone": content.get("phone", ""),
            "email": content.get("email", ""),
            "birth_date": content.get("birth_date", None),
            "gender": content.get("gender", ""),
            "prog_languages": content.get("prog_languages", []),
            "bio": content.get("bio", ""),
        }
        validated_data = UserFormModel(**update_data)

    except ValidationError as e:
        # Сохраняем ошибки и введенные данные в куки
        for err in e.errors():
            field_name_in_model = err['loc'][0]
            # Убираем фразу "Value error," из сообщения об ошибке
            msg = err['msg'].replace("Value error, ", "")
            cookies[f"{field_name_in_model}_err"] = quote(msg.capitalize())

        for field in form_fields_in_content:
            value = content.get(field, "")
            if isinstance(value, list): value = "|".join(value)
            cookies[field] = quote(str(value))

        # Редирект обратно на форму
        return Response(303, {"Location": f"/admin/edit/{form_id}"}, cookies, "")

    except Exception as e:
        print(f"ERROR: Form data processing error for form_id={form_id}: {e}")
        cookies["edit_err"] = quote("Error processing form data.")
        return Response(400, {"Location": f"/admin/edit/{form_id}"}, cookies, "Bad Request")

    # Обновление данных в БД
    try:
        update_user_form_by_id(form_id, validated_data)
        cookies["success_edit"] = "1"  # Сообщение об успешном сохранении
        return Response(303, {"Location": f"/admin/edit/{form_id}"}, cookies, "")

    except Exception as e:
        print(f"ERROR: Database update failed for form_id={form_id}: {e}")
        cookies["edit_err"] = quote("Error saving data to the database. Please try again.")
        return Response(400, {"Location": f"/admin/edit/{form_id}"}, cookies, "Database Error")
    
@HTTPHandler.get(r"/admin/delete/(?P<form_id>\d+)")
def admin_delete_form(request: Request, form_id: int) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("admin_session_id")

    if not session_cookie or session_cookie.value not in admin_sessions:
        return Response(
            status=303, headers={"Location": "/admin"}, cookies=cookies, content=""
        )

    delete_user_form(form_id)

    return Response(
        status=303, headers={"Location": "/admin/dashboard"}, cookies=cookies, content=""
    )

@HTTPHandler.get("/admin/logout")
def admin_logout(request: Request) -> Response:
    cookies = SimpleCookie()
    session_cookie = request.cookies.get("admin_session_id")
    if session_cookie and session_cookie.value in admin_sessions:
        del admin_sessions[session_cookie.value]

    cookies["admin_session_id"] = ""
    cookies["admin_session_id"]["expires"] = EPOCH

    return Response(
        status=303, headers={"Location": "/admin"}, cookies=cookies, content=""
    )