import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.crud import crud_user
from app.db.session import SessionLocal
from app.schemas.user import UserCreate


def add_users(csv_file_path: str):
    print(f"--- Starting user import from '{csv_file_path}' ---")
    db = SessionLocal()

    created_count = 0
    skipped_count = 0
    error_count = 0

    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            if 'email' not in reader.fieldnames or 'password' not in reader.fieldnames:
                print("ERROR: CSV file must contain 'email' and 'password' headers.")
                return

            for row in reader:
                email = row.get('email', '').strip()
                password = row.get('password', '').strip()

                if not email or not password:
                    print(f"WARNING: Skipping row with empty email or password: {row}")
                    error_count += 1
                    continue

                existing_user = crud_user.user.get_by_email(db, email=email)
                if existing_user:
                    print(f"Skipping: User with email '{email}' already exists.")
                    skipped_count += 1
                    continue

                user_in = UserCreate(email=email, password=password)
                try:
                    crud_user.user.create(db, obj_in=user_in)
                    print(f"SUCCESS: Created user for '{email}'.")
                    created_count += 1
                except Exception as e:
                    print(f"ERROR: Could not create user for '{email}'. Reason: {e}")
                    db.rollback()
                    error_count += 1

    except FileNotFoundError:
        print(f"ERROR: The file '{csv_file_path}' was not found.")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return
    finally:
        db.close()

    print("\n--- Import Summary ---")
    print(f"Users Created:  {created_count}")
    print(f"Users Skipped:  {skipped_count}")
    print(f"Rows with Errors: {error_count}")
    print("----------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bulk create user accounts from a CSV file. The CSV must have 'email' and 'password' headers."
    )
    parser.add_argument(
        "csv_file",
        help="Path to the CSV file containing user credentials."
    )

    args = parser.parse_args()
    add_users(args.csv_file)
