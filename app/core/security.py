import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash.
    Also supports legacy passlib pbkdf2_sha256 hashes."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # If the stored hash is a legacy passlib format, try passlib as fallback
        try:
            from passlib.context import CryptContext
            ctx = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
            return ctx.verify(plain_password, hashed_password)
        except Exception:
            return False
