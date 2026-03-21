from passlib.context import CryptContext

# Soporta ambos: bcrypt (recomendado) y pbkdf2_sha256 (fallback)
pwd_context = CryptContext(
    schemes=["bcrypt", "pbkdf2_sha256"],
    deprecated="auto",
)

def hash_password(password: str) -> str:
    # Por defecto generará bcrypt si bcrypt está disponible
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)