from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber
from datetime import date
import re
from enum import Enum

class GenderEnum(str, Enum):
    male = "male"
    female = "female"

class ProgrammingLanguageEnum(str, Enum):
    pascal = "Pascal"
    c = "C"
    cpp = "C++"
    javascript = "JavaScript"
    php = "PHP"
    python = "Python"
    java = "Java"
    haskell = "Haskell"
    clojure = "Clojure"
    prolog = "Prolog"
    scala = "Scala"
    go = "Go"

class UserFormModel(BaseModel):
    full_name: str = Field(..., max_length=150, description="ФИО")
    phone: str = Field(..., description="Телефон")
    email: EmailStr = Field(..., max_length=100, description="Электронная почта")
    birth_date: date = Field(..., description="Дата рождения")
    gender: str = Field(..., description="Пол")
    bio: str = Field(..., max_length=500, description="Биография")

    prog_languages: list[str] = Field(..., description="Языки программирования")
    contract_agreed: bool = True

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"^[А-Яа-яA-Za-z\s]+$", value):
            raise ValueError("ФИО должно содержать только буквы и пробелы")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not re.match(r"^\+?\d{1,4}[-\s]?\d{3,14}$", value):
            raise ValueError("Телефон должен содержать только цифры, пробелы, дефисы и символ '+'")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> EmailStr:
        if len(value) > 100:
            raise ValueError("Электронная почта не должна превышать 100 символов")
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", str(value)):
            raise ValueError("Электронная почта имеет неверный формат")
        return value

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, value: str) -> str:
        if len(value) > 500:
            raise ValueError("Биография не должна превышать 500 символов")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if 0 <= age <= 110:
            return value
        raise ValueError("Некорректная дата рождения")

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: GenderEnum) -> GenderEnum:
        if value not in (GenderEnum.male, GenderEnum.female):
            raise ValueError("Неверное значение пола")
        return value
    
    @field_validator("prog_languages")
    @classmethod
    def validate_prog_languages(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Выберите хотя бы один язык программирования")
        return value