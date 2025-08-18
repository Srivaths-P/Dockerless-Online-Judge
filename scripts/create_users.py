import argparse
import csv
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.crud import crud_user
from app.db.session import SessionLocal
from app.schemas.user import UserCreate


def generate_secure_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            break
    return password


def create_users(email_file_path: str, output_csv_path: str):
    db = SessionLocal()
    created_credentials = []

    try:
        with open(email_file_path, 'r') as f:
            emails = [line.strip() for line in f if line.strip() and '@' in line]

        print(f"Found {len(emails)} emails to process.")

        for email in emails:
            existing_user = crud_user.user.get_by_email(db, email=email)
            if existing_user:
                print(f"Skipping: User with email '{email}' already exists.")
                continue

            password = generate_secure_password()
            user_in = UserCreate(email=email, password=password)

            try:
                user = crud_user.user.create(db, obj_in=user_in)
                created_credentials.append({'email': user.email, 'password': password})
                print(f"SUCCESS: Created user for '{user.email}'.")
            except Exception as e:
                print(f"ERROR: Could not create user for '{email}'. Reason: {e}")
                db.rollback()

        if created_credentials:
            with open(output_csv_path, 'w', newline='') as csvfile:
                fieldnames = ['email', 'password']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(created_credentials)
            print(f"\nSUCCESS: Wrote {len(created_credentials)} new user credentials to '{output_csv_path}'.")
        else:
            print("\nNo new users were created.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk create user accounts from a list of emails.")
    parser.add_argument("email_file", help="Path to a text file containing one email per line.")
    parser.add_argument("--output", default="new_user_credentials.csv",
                        help="Path to the output CSV file for credentials (default: new_user_credentials.csv).")

    args = parser.parse_args()
    create_users(args.email_file, args.output)
