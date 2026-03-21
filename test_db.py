from sqlalchemy import create_engine, text

connection_string = (
    "mssql+pyodbc://app_user:PasswordFuerte123!"
    "@localhost\\SQLEXPRESS/IntranetApp"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Encrypt=yes&TrustServerCertificate=yes"
)

engine = create_engine(connection_string)

with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sys.databases"))
    for row in result:
        print(row)