"""
Flask Routes for HDFC Email Integration
WITH PERSISTENT CREDENTIAL STORAGE

Add to routes/hdfc_routes.py
"""

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from models.database import db
from integrations.hdfc_email_parser import HDFCEmailParser, HDFCTransactionSync
from models.bank_credentials import CredentialManager
from datetime import datetime

# Create blueprint
hdfc_bp = Blueprint('hdfc', __name__, url_prefix='/hdfc')

# ============================================================================
# HDFC EMAIL SYNC ROUTES WITH PERSISTENT STORAGE
# ============================================================================

@hdfc_bp.route('/setup', methods=['GET'])
@login_required
def setup_page():
    """HDFC email setup page"""
    return render_template('hdfc_setup.html')


@hdfc_bp.route('/connect', methods=['POST'])
@login_required
def connect_email():
    """Connect email account for HDFC sync (saves to database)"""
    try:
        data = request.get_json()
        
        email_address = data.get('email_address')
        app_password = data.get('app_password')
        
        if not email_address or not app_password:
            return jsonify({
                'success': False,
                'error': 'Email and app password required'
            }), 400
        
        # Test connection
        parser = HDFCEmailParser(email_address, app_password)
        
        if parser.connect():
            parser.disconnect()
            
            # ✅ SAVE TO DATABASE (encrypted) - NOW WITH user_id
            CredentialManager.save_credentials(
                email_address=email_address,
                app_password=app_password,
                bank_name='HDFC',
                user_id=current_user.id
            )
            
            return jsonify({
                'success': True,
                'message': 'Email connected and saved successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to connect. Check credentials.'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hdfc_bp.route('/sync', methods=['POST'])
@login_required
def sync_transactions():
    """Sync HDFC transactions from email (uses stored credentials)"""
    try:
        data = request.get_json()
        days_back = data.get('days_back', 30)
        
        # ✅ GET CREDENTIALS FROM DATABASE - NOW WITH user_id
        credentials = CredentialManager.get_credentials(user_id=current_user.id)
        
        if not credentials:
            return jsonify({
                'success': False,
                'error': 'No saved credentials. Please connect your email first.',
                'needs_connection': True
            }), 400
        
        # Initialize parser with stored credentials
        parser = HDFCEmailParser(
            credentials['email'],
            credentials['password']
        )
        
        # Fetch and parse emails
        print(f"🔄 Fetching HDFC emails (last {days_back} days)...")
        transactions = parser.fetch_hdfc_emails(days_back=days_back)
        
        parser.disconnect()
        
        if not transactions:
            return jsonify({
                'success': True,
                'message': 'No new transactions found',
                'stats': {
                    'total': 0,
                    'added': 0,
                    'duplicates': 0,
                    'errors': 0
                }
            })
        
        # Sync to database with user_id
        sync_engine = HDFCTransactionSync(db.session, current_user.id)
        stats = sync_engine.sync_transactions(transactions)
        
        # Update last sync time
        CredentialManager.update_last_sync(user_id=current_user.id)
        
        return jsonify({
            'success': True,
            'message': f'Synced {stats["added"]} transactions',
            'stats': stats
        })
        
    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hdfc_bp.route('/auto-sync', methods=['POST'])
@login_required
def enable_auto_sync():
    """Enable automatic daily sync"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        # TODO: Implement background scheduler (APScheduler)
        # For now, just acknowledge the request
        
        return jsonify({
            'success': True,
            'message': f'Auto-sync {"enabled" if enabled else "disabled"}',
            'note': 'Manual sync for now - auto-sync coming soon!'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hdfc_bp.route('/status', methods=['GET'])
@login_required
def get_status():
    """Get HDFC sync status (from database)"""
    try:
        # ✅ GET STATUS FROM DATABASE - NOW WITH user_id
        credential = CredentialManager.get_active_credential(user_id=current_user.id)
        
        is_connected = credential is not None
        
        # Get last sync info
        from models.transaction import Transaction
        last_sync_trans = Transaction.query.filter_by(
            source='hdfc_email',
            user_id=current_user.id
        ).order_by(
            Transaction.created_at.desc()
        ).first()
        
        return jsonify({
            'success': True,
            'is_connected': is_connected,
            'email': credential.email_address if credential else None,
            'last_sync': credential.last_sync.isoformat() if (credential and credential.last_sync) else None,
            'last_transaction': last_sync_trans.created_at.isoformat() if last_sync_trans else None,
            'total_synced': Transaction.query.filter_by(
                source='hdfc_email',
                user_id=current_user.id
            ).count()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hdfc_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect_email():
    """Disconnect email account (deactivates in database)"""
    try:
        # ✅ DEACTIVATE IN DATABASE - NOW WITH user_id
        CredentialManager.delete_credentials(user_id=current_user.id)
        
        return jsonify({
            'success': True,
            'message': 'Email disconnected'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@hdfc_bp.route('/test-connection', methods=['POST'])
@login_required
def test_connection():
    """Test if stored credentials still work"""
    try:
        credentials = CredentialManager.get_credentials(user_id=current_user.id)
        
        if not credentials:
            return jsonify({
                'success': False,
                'error': 'No saved credentials'
            }), 400
        
        # Test connection
        parser = HDFCEmailParser(
            credentials['email'],
            credentials['password']
        )
        
        if parser.connect():
            parser.disconnect()
            return jsonify({
                'success': True,
                'message': 'Connection test successful!'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Connection test failed. Credentials may have expired.'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
