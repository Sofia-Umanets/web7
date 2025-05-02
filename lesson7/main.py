from http.server import HTTPServer

from form_app.handler import HTTPHandler
from form_app.database import hash_password


def main():
    host = "0.0.0.0"
    port = 8080

    httpd = HTTPServer((host, port), HTTPHandler)
    print(f"Сервер запущен на https://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
