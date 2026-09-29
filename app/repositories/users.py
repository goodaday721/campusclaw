"""User repository: lookup users for authentication."""
import pymysql


class UserRepository:
    def __init__(self, conn: pymysql.connections.Connection) -> None:
        self.conn = conn

    def find_by_username(self, username: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role, class_id FROM users "
                "WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
            "class_id": row["class_id"],
        }
