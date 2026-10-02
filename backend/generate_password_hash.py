"""
Run this set or change the caregiver dashboard password.

It never writes the plain password anywhere, only a bcrypt hash, which
you paste into .env. If .env is ever leaked again, an attacker gets a
hash they'd have to crack, not the password itself.

Usage:
    python backend/generate_password_hash.py
"""
import bcrypt
import getpass


def main():
    password = getpass.getpass("New caregiver password: ")
    confirm = getpass.getpass("Confirm it: ")
    if not password:
        print("Password can't be empty.")
        return
    if password != confirm:
        print("Those didn't match — try again.")
        return

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print("\nAdd this line to your .env file (replacing any existing CAREGIVER_PASS_HASH):\n")
    print(f"CAREGIVER_PASS_HASH={hashed}")
    print("\nIf your .env still has a plain CAREGIVER_PASS line, delete it.")


if __name__ == "__main__":
    main()