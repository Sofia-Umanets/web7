from dataclasses import dataclass
from http.cookies import SimpleCookie

@dataclass
class Request:
    headers: dict[str, str]
    cookies: SimpleCookie

@dataclass
class Response:
    status: int
    headers: dict[str, str]
    cookies: SimpleCookie
    content: str


