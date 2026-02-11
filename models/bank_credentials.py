"""
Persistent Credential Storage for HDFC Email Integration
Stores encrypted credentials in database

Create this file: models/bank_credentials.py
"""

from models.database import db
from datetime import datetime
from cryptography.fernet import Fernet
import os
import base64

class BankCredential(db.Model):
    """Store encrypted bank email credentials"""
    __tablename__ = 'bank_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    bank_name = db.Column(db.String(50), default='HDFC')
    email_address = db.Column(db.String(255), unique=True, nullable=False)
    encrypted_password = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<BankCredential {self.bank_name} - {self.email_address}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'email_address': self.email_address,
            'is_active': self.is_active,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CredentialManager:
    """Manage encrypted credentials"""
    
    # Generate a key for your app (do this once and store in environment variable)
    # In production, use: os.environ.get('ENCRYPTION_KEY')
    # For now, we'll use a fixed key (CHANGE THIS IN PRODUCTION!)
    
    @staticmethod
    def get_encryption_key():
        """Get or create encryption key"""
        key_file = 'encryption.key'
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            print("🔐 Generated new encryption key: encryption.key")
            print("⚠️  KEEP THIS FILE SECURE AND DON'T COMMIT TO GIT!")
            return key
    
    @staticmethod
    def encrypt_password(password: str) -> str:
        """Encrypt password"""
        key = CredentialManager.get_encryption_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()
    
    @staticmethod
    def decrypt_password(encrypted_password: str) -> str:
        """Decrypt password"""
        key = CredentialManager.get_encryption_key()
        cipher = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted_password.encode())
        decrypted = cipher.decrypt(encrypted_bytes)
        return decrypted.decode()
    
    @staticmethod
    def save_credentials(email_address: str, app_password: str, bank_name: str = 'HDFC', user_id: int = None) -> BankCredential:
        """Save or update credentials"""
        # Check if credentials already exist for this user
        query = BankCredential.query.filter_by(email_address=email_address)
        if user_id:
            query = query.filter_by(user_id=user_id)
        existing = query.first()
        
        if existing:
            # Update existing
            existing.encrypted_password = CredentialManager.encrypt_password(app_password)
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            db.session.commit()
            print(f"✅ Updated credentials for {email_address}")
            return existing
        else:
            # Create new
            credential = BankCredential(
                user_id=user_id,
                bank_name=bank_name,
                email_address=email_address,
                encrypted_password=CredentialManager.encrypt_password(app_password),
                is_active=True
            )
            db.session.add(credential)
            db.session.commit()
            print(f"✅ Saved credentials for {email_address}")
            return credential
    
    @staticmethod
    def get_credentials(user_id: int = None, email_address: str = None) -> dict:
        """Get decrypted credentials"""
        query = BankCredential.query.filter_by(is_active=True)
        
        if email_address:
            query = query.filter_by(email_address=email_address)
        elif user_id:
            query = query.filter_by(user_id=user_id, bank_name='HDFC')
        else:
            # Get any active HDFC credential
            query = query.filter_by(bank_name='HDFC')
        
        credential = query.first()
        
        if credential:
            return {
                'email': credential.email_address,
                'password': CredentialManager.decrypt_password(credential.encrypted_password),
                'bank_name': credential.bank_name
            }
        
        return None
    
    @staticmethod
    def get_active_credential(user_id: int = None) -> BankCredential:
        """Get active credential object"""
        query = BankCredential.query.filter_by(
            bank_name='HDFC',
            is_active=True
        )
        
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        return query.first()
    
    @staticmethod
    def delete_credentials(user_id: int = None, email_address: str = None):
        """Delete or deactivate credentials"""
        query = BankCredential.query
        
        if email_address:
            query = query.filter_by(email_address=email_address)
        elif user_id:
            query = query.filter_by(user_id=user_id, bank_name='HDFC')
        else:
            query = query.filter_by(bank_name='HDFC')
        
        credential = query.first()
        
        if credential:
            credential.is_active = False
            db.session.commit()
            print(f"✅ Deactivated credentials for {credential.email_address}")
    
    @staticmethod
    def update_last_sync(user_id: int = None):
        """Update last sync timestamp"""
        credential = CredentialManager.get_active_credential(user_id)
        if credential:
            credential.last_sync = datetime.utcnow()
            db.session.commit()


# ============================================================================
# Migration Helper - Run this once to create the table
# ============================================================================

def create_credentials_table():
    """Create bank_credentials table"""
    from app import app, db
    
    with app.app_context():
        try:
            db.create_all()
            print("✅ bank_credentials table created!")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == '__main__':
    create_credentials_table()
