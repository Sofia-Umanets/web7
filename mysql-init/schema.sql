CREATE DATABASE IF NOT EXISTS formdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE formdb;

CREATE TABLE programming_languages (
lang_id INT AUTO_INCREMENT PRIMARY KEY,
name VARCHAR(30) NOT NULL
);

INSERT INTO programming_languages (name) VALUES
('Pascal'), ('C'), ('C++'), ('JavaScript'), ('PHP'), ('Python'),
('Java'), ('Haskell'), ('Clojure'), ('Prolog'), ('Scala'), ('Go');

CREATE TABLE user_forms (
    form_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    email VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    gender ENUM('male', 'female') NOT NULL,
    bio TEXT NOT NULL,
    login VARCHAR(32) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_prog_languages (
lang_id INT,
form_id INT,
PRIMARY KEY (lang_id, form_id),
FOREIGN KEY (lang_id) REFERENCES programming_languages(lang_id),
FOREIGN KEY (form_id) REFERENCES user_forms(form_id) ON DELETE CASCADE
); 

CREATE TABLE admins (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    login VARCHAR(32) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL
);