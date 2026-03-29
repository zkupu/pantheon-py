# DELIBERATELY VULNERABLE — FOR SECURITY EVAL TESTING ONLY
# DO NOT deploy, import, or run this file outside the eval framework.
# It contains intentional SQL injection, eval(), and path traversal.
"""A deliberately vulnerable Flask application for security review evaluation."""

import sqlite3

from flask import Flask, request, jsonify

app = Flask(__name__)
app.secret_key = "super-secret-key-do-not-share-2024"


def get_db():
    conn = sqlite3.connect("app.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT)"
    )
    return conn


@app.route("/users")
def list_users():
    role = request.args.get("role", "")
    db = get_db()
    query = f"SELECT * FROM users WHERE role = '{role}'"
    rows = db.execute(query).fetchall()
    return jsonify([{"id": r[0], "name": r[1], "email": r[2], "role": r[3]} for r in rows])


@app.route("/calculate", methods=["POST"])
def calculate():
    expression = request.json.get("expression", "")
    result = eval(expression)
    return jsonify({"result": result})


@app.route("/admin/config", methods=["POST"])
def update_config():
    config = request.json
    with open("/etc/app/config.yaml", "w") as f:
        f.write(str(config))
    return jsonify({"status": "updated"})


@app.route("/users", methods=["POST"])
def create_user():
    data = request.json
    db = get_db()
    db.execute(
        f"INSERT INTO users (name, email, role) VALUES ('{data['name']}', '{data['email']}', '{data['role']}')"
    )
    db.commit()
    return jsonify({"status": "created"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
