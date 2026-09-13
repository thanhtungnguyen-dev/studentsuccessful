"""Compose credential assembly; preserve an explicit managed-PostgreSQL URL."""

import os
import sys

from sqlalchemy import URL


def main():
    # Production supplies DATABASE_URL through its secret store. Local Compose
    # intentionally derives a URL from the PostgreSQL service credentials.
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = URL.create(
            "postgresql+psycopg2",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host="postgres",
            port=5432,
            database=os.environ["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
