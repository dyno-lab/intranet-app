# Secret Rotation Report

## Objective
Remove `.env` from Git tracking without deleting the local file, and document which secrets must be rotated manually.

## What was changed in this phase
- `.env` removed from Git tracking with `git rm --cached .env`
- `.gitignore` reinforced to ignore env files, backups, database files, Python cache files, virtualenvs, and logs
- `.env.example` rewritten with safe placeholder values only

## Local file safety
- Your local `./.env` file was **not deleted**
- Credentials were **not changed** in this phase

## Secrets / sensitive values to rotate manually

### 1. Application session / signing secret
- Variable: `SECRET_KEY`
- Why rotate: it was stored in tracked `.env`
- Recommended action: generate a new long random value and update production/local secrets storage

### 2. SQL Server credentials
- Variables:
  - `DB_USER`
  - `DB_PASSWORD`
- Why rotate: database credentials were stored in tracked `.env`
- Recommended action:
  - change the SQL login password
  - update all consumers that use the credential
  - verify application login after rotation

### 3. Automation token
- Variable: `AUTOMATION_API_KEY`
- Why rotate: if this variable was ever set in tracked `.env` or copied elsewhere, treat it as exposed
- Recommended action: issue a new token and replace the old one everywhere

## Other sensitive config to review
These are not always secrets, but should still be reviewed after rotation:
- `DB_SERVER`
- `DB_NAME`
- `DB_DRIVER`
- `DB_ENCRYPT`
- `DB_TRUST_CERT`
- `WKHTMLTOPDF_PATH`

## Suggested manual rotation checklist
1. Generate a new `SECRET_KEY`
2. Change the SQL password for `DB_USER`
3. Issue a new `AUTOMATION_API_KEY` if used
4. Update secret values in your real `.env` or secret store
5. Restart the app/services that load these variables
6. Test login and DB connectivity
7. Review Git history for previous secret exposure and decide whether deeper history cleanup is needed

## Important note
This phase only removes future tracking. It does **not** erase secrets from existing Git history.
