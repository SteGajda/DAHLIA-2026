"""Preview by default; --apply writes only to the explicitly named server/database."""

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-server", required=True)
    parser.add_argument("--expect-database", required=True)
    parser.add_argument("--author-id", type=int)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[3] / "frontend" / "data")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        from sqlalchemy import text
        from app.db.session import engine, SessionLocal
        from app.services.dataset_import import import_datasets
        if engine.dialect.name != "mssql":
            print("This import command requires SQL Server.")
            return 1
        with SessionLocal() as db:
            server, database = db.execute(text("SELECT CONVERT(nvarchar(128), SERVERPROPERTY('ServerName')), DB_NAME()")).one()
            print(f"Server: {server}\nDatabase: {database}")
            if server.casefold() != args.expect_server.casefold() or database.casefold() != args.expect_database.casefold():
                print("The connected server/database differs from the expected target. Nothing was imported.")
                return 1
            try:
                plan = import_datasets(db, args.data_dir, author_id=args.author_id, apply=args.apply)
            except (ValueError, FileNotFoundError) as exc:
                print(str(exc))
                return 1
            print("APPLIED" if args.apply else "PREVIEW ONLY: add --apply to write this plan.")
            for item in plan:
                print(f"{item['name']}: {item['row_count']} rows, ID={item['dataset_id']}, {item['status']}, author={item['created_by']}")
        return 0
    except Exception:
        print("Import failed; transaction rolled back. Connection details omitted.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
