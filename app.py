"""
PRODUCTION-READY Flask Application
Railway-optimized with lazy loading and no blocking startup operations
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, send_from_directory
from config import Config
from models.database import db
from models.document import Document
from models.transaction import Transaction
from models.category import Category, DEFAULT_CATEGORIES
from models.budget import Budget
from utils.db_utils import DatabaseUtils
from utils.seed_data import SeedData
from utils.file_handler import FileHandler
from werkzeug.utils import secure_filename
from utils.performance_monitor import perf_monitor
from models.conversation import Conversation
from models.message import Message
from routes.chat_routes_semantic import chat_bp
from routes.reports import report_bp
import os
from routes.budget_routes import budget_bp
from routes.insights_routes import insights_bp
from datetime import datetime
from models.notification_system import Notification, NotificationManager, BudgetNotificationManager
from routes.notification_routes import notification_bp
from routes.hdfc_routes import hdfc_bp
from sqlalchemy import func, desc
from models.user import User
from flask_login import LoginManager, login_required, current_user
from routes.auth_routes import auth_bp
import psutil
import gc


def create_app():
    """Application factory with authentication - PRODUCTION OPTIMIZED"""

    from werkzeug.middleware.proxy_fix import ProxyFix

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    app = Flask(
        __name__,
        static_folder=os.path.join(BASE_DIR, "static"),
        static_url_path="/static"
    )

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1
    )

    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ========================================================================
    # ✅ DATABASE INITIALIZATION - NO BLOCKING OPERATIONS
    # ========================================================================
    # Initialize SQLAlchemy WITHOUT create_all() or test queries
    db.init_app(app)
    
    # ❌ REMOVED: init_db(app) - prevents startup hang
    # Database tables are created manually via shell or migrations
    # This ensures Railway deployment completes in <60 seconds

    # ========================================================================
    # FLASK-LOGIN SETUP
    # ========================================================================
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ========================================================================
    # ✅ FIXED: API AUTHENTICATION HANDLING
    # ========================================================================
    @app.before_request
    def handle_api_authentication():
        """
        Handle authentication differently for API routes vs web routes.
        API routes should return JSON 401, not redirect to login.
        """
        from flask import request, jsonify
        from flask_login import current_user
        
        # Skip for static files and health check
        if request.path.startswith('/static/') or request.path == '/health':
            return None
        
        # For API routes, return JSON error instead of redirect
        if request.path.startswith('/api/'):
            # Public API endpoints that don't need auth
            public_endpoints = [
                '/api/login',
                '/api/register',
                '/api/check-username',
                '/api/check-email'
            ]
            
            if request.path in public_endpoints:
                return None
            
            # Check if user is authenticated
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'error': 'Authentication required',
                    'redirect': '/login'
                }), 401
        
        return None

    # ========================================================================
    # BLUEPRINT REGISTRATION
    # ========================================================================
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(hdfc_bp)

    return app


app = create_app()


# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html')

@app.route('/reports')
@login_required
def reports_page():
    return render_template('reports.html')

@app.route('/budgets')
@login_required
def budgets_page():
    return render_template('budgets.html')

@app.route('/insights')
@login_required
def insights_page():
    return render_template('insights.html')

@app.route('/notifications')
@login_required
def notifications_page():
    return render_template('notification_center.html')

@app.route('/transactions')
@login_required
def transactions_page():
    return render_template('transactions.html')

@app.route('/hdfc-sync')
@login_required
def hdfc_sync_page():
    return render_template('hdfc_sync.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_page():
    if request.method == 'GET':
        return render_template('upload.html')

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    file_info, error = FileHandler.save_file(file, app.config['UPLOAD_FOLDER'])

    if error:
        return jsonify({'success': False, 'error': error}), 400

    try:
        file_type = FileHandler.get_file_type(file_info['original_filename'])

        document = Document(
            filename=file_info['saved_filename'],
            original_filename=file_info['original_filename'],
            file_type=file_type,
            file_path=file_info['file_path'],
            processed=False
        )
        db.session.add(document)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'File uploaded successfully',
            'document': document.to_dict()
        })
    except Exception as e:
        FileHandler.delete_file(file_info['file_path'])
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ✅ HEALTH CHECK (NO AUTH REQUIRED) - CRITICAL FOR RAILWAY
# ============================================================================

@app.route('/health')
def health_check():
    """Single health check endpoint for Railway - NO AUTH REQUIRED"""
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        return jsonify({
            'status': 'healthy',
            'service': 'finance-app',
            'memory_mb': round(memory_mb, 1),
            'memory_percent': round(process.memory_percent(), 1),
            'database': 'connected',
            'version': '1.0.0'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# DASHBOARD API
# ============================================================================

@app.route('/api/stats')
@login_required
def get_stats():
    return jsonify(DatabaseUtils.get_dashboard_stats())

@app.route('/api/category-breakdown')
@login_required
def get_category_breakdown():
    return jsonify(DatabaseUtils.get_category_breakdown())

@app.route('/api/recent-transactions')
@login_required
def get_recent_transactions():
    limit = request.args.get('limit', 10, type=int)
    return jsonify(DatabaseUtils.get_recent_transactions(limit))

@app.route('/api/monthly-trend')
@login_required
def get_monthly_trend():
    months = request.args.get('months', 6, type=int)
    return jsonify(DatabaseUtils.get_monthly_trend(months))

@app.route('/api/categories')
@login_required
def get_categories():
    categories = Category.query.all()
    return jsonify([cat.to_dict() for cat in categories])

@app.route('/api/vendors/top')
@login_required
def get_top_vendors():
    try:
        limit = request.args.get('limit', 6, type=int)

        vendors = db.session.query(
            Transaction.vendor_name.label('vendor_name'),
            func.count(Transaction.id).label('transaction_count'),
            func.sum(Transaction.amount).label('total_spending'),
            func.max(Transaction.transaction_date).label('last_transaction_date')
        ).filter(
            Transaction.vendor_name.isnot(None),
            Transaction.vendor_name != ''
        ).group_by(
            Transaction.vendor_name
        ).order_by(
            desc('total_spending')
        ).limit(limit).all()

        vendor_list = []
        for v in vendors:
            try:
                last_date = None
                if v.last_transaction_date:
                    if isinstance(v.last_transaction_date, str):
                        last_date = v.last_transaction_date
                    else:
                        last_date = v.last_transaction_date.isoformat()

                vendor_list.append({
                    'vendor_name': str(v.vendor_name) if v.vendor_name else 'Unknown',
                    'transaction_count': int(v.transaction_count) if v.transaction_count else 0,
                    'total_spending': float(v.total_spending) if v.total_spending else 0.0,
                    'last_transaction_date': last_date
                })
            except Exception as e:
                print(f"Error processing vendor {v}: {str(e)}")
                continue

        print(f"✅ Found {len(vendor_list)} vendors")
        return jsonify({'success': True, 'vendors': vendor_list})

    except Exception as e:
        print(f"❌ Error in get_top_vendors: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ADMIN / DEBUG ROUTES
# ============================================================================

@app.route('/admin/seed')
@login_required
def seed_database():
    try:
        SeedData.generate_documents(10)
        SeedData.generate_transactions(50)

        return jsonify({
            'success': True,
            'message': 'Database seeded successfully!',
            'documents': Document.query.count(),
            'transactions': Transaction.query.count()
        })
    except Exception as e:
        import traceback
        print("❌ SEEDING ERROR:")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/clear')
@login_required
def clear_database():
    try:
        SeedData.clear_all_data()
        return jsonify({'success': True, 'message': 'All data cleared successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DOCUMENT ROUTES
# ============================================================================

@app.route('/api/documents')
@login_required
def get_documents():
    documents = Document.query.order_by(Document.upload_date.desc()).all()
    return jsonify([doc.to_dict() for doc in documents])

@app.route('/api/documents/<int:doc_id>')
@login_required
def get_document(doc_id):
    document = db.session.get(Document, doc_id)
    if not document:
        return jsonify({'error': 'Document not found'}), 404
    return jsonify(document.to_dict())

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    try:
        document = db.session.get(Document, doc_id)
        if not document:
            return jsonify({'success': False, 'error': 'Document not found'}), 404

        FileHandler.delete_file(document.file_path)
        db.session.delete(document)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Document deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/uploads/<filename>')
@login_required
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/document-details/<int:doc_id>')
@login_required
def get_document_details(doc_id):
    try:
        document = db.session.get(Document, doc_id)
        if not document:
            return jsonify({'error': 'Document not found'}), 404

        transactions = Transaction.query.filter_by(document_id=doc_id).all()

        return jsonify({
            'document': document.to_dict(),
            'raw_text': document.raw_text[:500] if document.raw_text else None,
            'transactions': [t.to_dict() for t in transactions],
            'transaction_count': len(transactions)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# ✅ DOCUMENT PROCESSING - LAZY LOADED (NO STARTUP IMPORT)
# ============================================================================

processor = None

@app.route('/api/process-document/<int:doc_id>', methods=['POST'])
@login_required
def process_document(doc_id):
    global processor

    try:
        # ✅ Lazy initialization - imports ONLY when first API call is made
        if processor is None:
            print("🔄 Lazy-loading DocumentProcessingWorkflow...")
            from utils.processor import DocumentProcessingWorkflow
            processor = DocumentProcessingWorkflow()
            print("✅ DocumentProcessingWorkflow initialized")

        success, message = processor.process_document(doc_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/process-all-documents', methods=['POST'])
@login_required
def process_all_documents():
    global processor
    
    try:
        # ✅ Lazy load processor
        if processor is None:
            print("🔄 Lazy-loading DocumentProcessingWorkflow...")
            from utils.processor import DocumentProcessingWorkflow
            processor = DocumentProcessingWorkflow()
            print("✅ DocumentProcessingWorkflow initialized")
        
        documents = Document.query.filter_by(processed=False).all()

        if not documents:
            return jsonify({'success': True, 'message': 'No documents to process', 'processed_count': 0})

        success_count = 0
        failed_count = 0
        errors = []

        for doc in documents:
            success, message = processor.process_document(doc.id)
            if success:
                success_count += 1
            else:
                failed_count += 1
                errors.append(f"{doc.original_filename}: {message}")

        return jsonify({
            'success': True,
            'message': f'Processed {success_count} documents',
            'processed_count': success_count,
            'failed_count': failed_count,
            'errors': errors
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ✅ NLP / CHAT API - LAZY LOADED (NO STARTUP IMPORT)
# ============================================================================

nlp_processor = None

@app.route('/api/query', methods=['POST'])
@login_required
def process_query():
    try:
        global nlp_processor

        # ✅ Lazy initialization - imports ONLY when first API call is made
        if nlp_processor is None:
            print("🔄 Lazy-loading EnhancedSmartNLPProcessor...")
            from ai_modules.smart_nlp import EnhancedSmartNLPProcessor
            nlp_processor = EnhancedSmartNLPProcessor()
            print("✅ Smart NLP Processor initialized")

        data = request.get_json()
        query = data.get('query', '')

        if not query:
            return jsonify({'success': False, 'error': 'No query provided'}), 400

        print(f"\n{'='*60}")
        print(f"📝 Processing query: {query}")
        print(f"{'='*60}")

        result = nlp_processor.process_query_smart(query)

        print(f"✅ Query processed successfully")
        print(f"   Intent: {result.get('intent', 'unknown')}")
        print(f"   Confidence: {result.get('confidence', 0):.1f}%")
        print(f"   Time: {result.get('processing_time', 'N/A')}")
        print(f"{'='*60}\n")

        return jsonify({'success': True, 'result': result})

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ QUERY PROCESSING ERROR")
        print(f"{'='*60}")
        print(f"Query: {data.get('query', 'N/A') if 'data' in locals() else 'N/A'}")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")

        return jsonify({'success': False, 'error': f"{type(e).__name__}: {str(e)}"}), 500

@app.route('/api/clear-context', methods=['POST'])
@login_required
def clear_context():
    try:
        global nlp_processor
        if nlp_processor:
            nlp_processor.clear_context()
        return jsonify({'success': True, 'message': 'Context cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/performance-stats')
@login_required
def get_performance_stats():
    return jsonify(perf_monitor.get_stats())


# ============================================================================
# TRANSACTIONS API
# ============================================================================

@app.route('/api/transactions', methods=['GET', 'POST'])
@login_required
def handle_transactions():
    """GET: list with filters/pagination | POST: create with budget sync"""

    if request.method == 'GET':
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            category_id = request.args.get('category_id', type=int)
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            payment_method = request.args.get('payment_method')

            query = Transaction.query

            if category_id:
                query = query.filter_by(category_id=category_id)
            if start_date:
                query = query.filter(Transaction.transaction_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
            if end_date:
                query = query.filter(Transaction.transaction_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
            if payment_method:
                query = query.filter_by(payment_method=payment_method)

            query = query.order_by(Transaction.transaction_date.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)

            return jsonify({
                'success': True,
                'transactions': [t.to_dict() for t in paginated.items],
                'total': paginated.total,
                'page': page,
                'pages': paginated.pages,
                'per_page': per_page
            })
        except Exception as e:
            print(f"❌ Error fetching transactions: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    # POST
    try:
        data = request.get_json()

        for field in ['amount', 'vendor_name', 'category_id']:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        try:
            amount = float(data['amount'])
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError as e:
            return jsonify({'success': False, 'error': f'Invalid amount: {str(e)}'}), 400

        transaction_date = None
        if data.get('transaction_date'):
            try:
                transaction_date = datetime.strptime(data['transaction_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        category = Category.query.get(data['category_id'])
        if not category:
            return jsonify({'success': False, 'error': 'Invalid category ID'}), 400

        transaction = Transaction(
            document_id=None,
            transaction_date=transaction_date or datetime.now().date(),
            amount=amount,
            currency=data.get('currency', 'INR'),
            vendor_name=data['vendor_name'].strip(),
            description=data.get('description', 'Manual entry').strip(),
            category_id=data['category_id'],
            payment_method=data.get('payment_method', 'Other'),
            tax_amount=float(data.get('tax_amount', 0.0)),
            tax_percentage=float(data.get('tax_percentage', 0.0)) if data.get('tax_percentage') else None
        )

        db.session.add(transaction)
        db.session.commit()

        # Auto-sync budget
        from utils.budget_utils import BudgetUtils
        BudgetUtils.sync_transaction_budgets(transaction)

        print(f"✅ Transaction created: {transaction.vendor_name} - ₹{transaction.amount}")

        return jsonify({
            'success': True,
            'message': 'Transaction created successfully',
            'transaction': transaction.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating transaction: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/transactions/<int:trans_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def handle_single_transaction(trans_id):
    """GET: single transaction | PUT: update with budget sync | DELETE: delete with budget sync"""

    transaction = Transaction.query.get(trans_id)

    if not transaction:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    if request.method == 'GET':
        return jsonify({'success': True, 'transaction': transaction.to_dict()})

    if request.method == 'PUT':
        try:
            data = request.get_json()

            old_category_id = transaction.category_id
            old_date = transaction.transaction_date

            if 'amount' in data:
                amount = float(data['amount'])
                if amount <= 0:
                    return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
                transaction.amount = amount

            if 'vendor_name' in data:
                transaction.vendor_name = data['vendor_name'].strip()

            if 'transaction_date' in data:
                transaction.transaction_date = datetime.strptime(data['transaction_date'], '%Y-%m-%d').date()

            if 'category_id' in data:
                category = Category.query.get(data['category_id'])
                if not category:
                    return jsonify({'success': False, 'error': 'Invalid category ID'}), 400
                transaction.category_id = data['category_id']

            if 'description' in data:
                transaction.description = data['description'].strip()

            if 'payment_method' in data:
                transaction.payment_method = data['payment_method']

            if 'tax_amount' in data:
                transaction.tax_amount = float(data['tax_amount'])

            transaction.updated_at = datetime.utcnow()
            db.session.commit()

            from utils.budget_utils import BudgetUtils
            BudgetUtils.sync_transaction_budgets(
                transaction,
                old_category_id=old_category_id,
                old_date=old_date
            )

            print(f"✅ Transaction updated: {transaction.id}")
            return jsonify({
                'success': True,
                'message': 'Transaction updated successfully',
                'transaction': transaction.to_dict()
            })
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error updating transaction: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    if request.method == 'DELETE':
        try:
            category_id = transaction.category_id
            transaction_date = transaction.transaction_date

            db.session.delete(transaction)
            db.session.commit()

            from utils.budget_utils import BudgetUtils
            BudgetUtils.sync_deleted_transaction_budget(category_id, transaction_date)

            print(f"✅ Transaction deleted: {trans_id}")
            return jsonify({'success': True, 'message': 'Transaction deleted successfully'})
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error deleting transaction: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/transactions/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_transactions():
    try:
        data = request.get_json()
        transaction_ids = data.get('transaction_ids', [])

        if not transaction_ids:
            return jsonify({'success': False, 'error': 'No transaction IDs provided'}), 400

        deleted_count = Transaction.query.filter(
            Transaction.id.in_(transaction_ids)
        ).delete(synchronize_session=False)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'{deleted_count} transactions deleted',
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in bulk delete: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/transactions/import', methods=['POST'])
@login_required
def import_transactions():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        filename = file.filename.lower()

        if not filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'Unsupported file format. Use CSV'}), 400

        import csv
        from io import StringIO

        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        transactions_created = 0
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):
            try:
                transaction = Transaction(
                    transaction_date=datetime.strptime(row['date'], '%Y-%m-%d').date(),
                    amount=float(row['amount']),
                    vendor_name=row['vendor'],
                    description=row.get('description', 'Imported from CSV'),
                    category_id=int(row.get('category_id', 1)),
                    payment_method=row.get('payment_method', 'Other')
                )
                db.session.add(transaction)
                transactions_created += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        db.session.commit()

        from utils.budget_utils import BudgetUtils
        print("🔄 Syncing all budgets after bulk import...")
        updated_count = BudgetUtils.sync_all_budgets()
        print(f"✅ Synced {updated_count} budgets")

        return jsonify({
            'success': True,
            'message': f'Imported {transactions_created} transactions',
            'imported_count': transactions_created,
            'budgets_updated': updated_count,
            'errors': errors
        })
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error importing transactions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/transactions/validate-duplicate', methods=['POST'])
@login_required
def validate_duplicate():
    try:
        data = request.get_json()

        similar = Transaction.query.filter(
            Transaction.vendor_name == data['vendor_name'],
            Transaction.amount == float(data['amount'])
        ).all()

        if similar:
            return jsonify({
                'success': True,
                'is_duplicate': True,
                'similar_transactions': [t.to_dict() for t in similar[:5]]
            })
        else:
            return jsonify({'success': True, 'is_duplicate': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# MEMORY MANAGEMENT - PRODUCTION OPTIMIZATION
# ============================================================================

@app.before_request
def log_memory():
    """Log memory usage before each request"""
    if os.environ.get('FLASK_ENV') == 'production':
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        if memory_mb > 400:  # 400MB threshold on 512MB limit
            print(f"⚠️ High memory ({memory_mb:.1f} MB), forcing cleanup...")
            gc.collect()

@app.after_request
def cleanup_after_request(response):
    """Cleanup after each request"""
    gc.collect()
    return response


# ============================================================================
# ✅ PRODUCTION STARTUP - REMOVED if __name__ == "__main__" BLOCK
# ============================================================================
# Railway uses Gunicorn, not Flask's built-in server
# No app.run() call needed - this prevents port conflicts and double servers
