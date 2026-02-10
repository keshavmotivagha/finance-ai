from models.database import db
from models.category import Category, DEFAULT_CATEGORIES

def init_db_once(app):
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables ensured")

            # Seed default categories if empty
            if Category.query.count() == 0:
                for cat in DEFAULT_CATEGORIES:
                    db.session.add(Category(name=cat))
                db.session.commit()
                print("✅ Default categories seeded")

        except Exception as e:
            print("❌ Database init failed:", e)
