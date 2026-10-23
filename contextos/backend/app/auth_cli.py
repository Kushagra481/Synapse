"""Generate a scrypt password verifier for AUTH_PASSWORD_HASH."""
from getpass import getpass

from app.core.auth import hash_password


def main() -> None:
    password = getpass("New ContextOS password (12+ characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    try:
        print(hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
