import os
from models.database import db
from models.category import Category, DEFAULT_CATEGORIES

def init_db_once(app):
    if os.environ.get("DB_INIT_DONE") == "true":
        print("⏭️ DB already initialized — skipping")
        return

    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables ensured")

            if Category.query.count() == 0:
                for cat in DEFAULT_CATEGORIES:
                    db.session.add(Category(name=cat))
                db.session.commit()
                print("✅ Default categories seeded")

            os.environ["DB_INIT_DONE"] = "true"

        except Exception as e:
            print("❌ Database init failed:", e)
