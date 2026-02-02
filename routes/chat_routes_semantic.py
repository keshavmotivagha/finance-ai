"""
Updated Chat Routes with Semantic Chatbot (FIXED)
Save as: routes/chat_routes_semantic.py
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models.database import db
from models.conversation import Conversation
from models.message import Message
from datetime import datetime
from ai_modules.semantic_chatbot import SemanticChatbot

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

# Initialize chatbot lazily (only when needed, inside app context)
_semantic_bot = None

def get_semantic_bot():
    """Get or create semantic chatbot instance (lazy initialization)"""
    global _semantic_bot
    if _semantic_bot is None:
        print("🚀 Initializing Semantic Chatbot (first use)...", flush=True)
        try:
            _semantic_bot = SemanticChatbot()
            print("✅ Semantic Chatbot initialized successfully", flush=True)
        except Exception as e:
            import traceback
            print(f"❌ Failed to initialize SemanticChatbot: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            _semantic_bot = None  # Reset so next request retries
            raise RuntimeError(
                f"Chatbot initialization failed: {e}. "
                "Check that spaCy model (en_core_web_md) and "
                "sentence-transformers are installed correctly."
            )
    return _semantic_bot


@chat_bp.route('/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Get all conversations (list view)"""
    try:
        conversations = Conversation.query.filter_by(
            user_id=current_user.id
        ).order_by(
            Conversation.updated_at.desc()
        ).all()
        
        return jsonify({
            'success': True,
            'conversations': [conv.to_dict() for conv in conversations]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    """Get a specific conversation with all messages"""
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict_detailed()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations', methods=['POST'])
@login_required
def create_conversation():
    """Create a new conversation"""
    try:
        data = request.get_json()
        title = data.get('title', 'New Conversation')
        
        conversation = Conversation(
            title=title,
            user_id=current_user.id
        )
        db.session.add(conversation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/<int:conversation_id>', methods=['DELETE'])
@login_required
def delete_conversation(conversation_id):
    """Delete a conversation"""
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        db.session.delete(conversation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Conversation deleted'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
@login_required
def send_message(conversation_id):
    """
    Send a message and get AI response using semantic understanding
    ✅ FIXED: Better error handling for chatbot initialization failures
    """
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        data = request.get_json()
        user_message_content = data.get('content', '')
        
        if not user_message_content.strip():
            return jsonify({
                'success': False,
                'error': 'Message content cannot be empty'
            }), 400
        
        # 1. Save user message
        user_message = Message(
            conversation_id=conversation_id,
            role='user',
            content=user_message_content
        )
        db.session.add(user_message)
        db.session.flush()  # Get the ID without committing yet
        
        # 2. Process with semantic chatbot
        try:
            bot = get_semantic_bot()
            ai_response = bot.process_message(
                query=user_message_content,
                conversation_id=conversation_id
            )
            
            # 3. Save AI response message
            assistant_message = Message(
                conversation_id=conversation_id,
                role='assistant',
                content=ai_response['response'],
                intent=ai_response.get('intent'),
                confidence=ai_response.get('confidence')
            )
            
            # Store entities if available
            if ai_response.get('understanding', {}).get('entities'):
                assistant_message.set_entities(ai_response['understanding']['entities'])
            
            db.session.add(assistant_message)
            
        except RuntimeError as e:
            # Chatbot init failure - save friendly error message
            print(f"❌ RuntimeError in send_message: {str(e)}", flush=True)
            
            assistant_message = Message(
                conversation_id=conversation_id,
                role='assistant',
                content=(
                    "I'm having trouble initializing my AI models right now. "
                    "This usually happens when the server is starting up or under heavy load. "
                    "Please try again in a moment, or refresh the page."
                )
            )
            db.session.add(assistant_message)
            ai_response = {
                'response': assistant_message.content,
                'intent': 'error',
                'data': None,
                'chart_type': None,
                'understanding': {'error': str(e)}
            }
        
        # 4. Update conversation metadata
        conversation.updated_at = datetime.utcnow()
        
        # Auto-generate title from first user message
        if not conversation.title or conversation.title == 'New Conversation':
            conversation.title = Conversation.generate_title(user_message_content)
        
        # 5. Commit all changes
        db.session.commit()
        
        # 6. Return response
        return jsonify({
            'success': True,
            'user_message': user_message.to_dict(),
            'assistant_message': assistant_message.to_dict(),
            'data': ai_response.get('data'),
            'chart_type': ai_response.get('chart_type'),
            'understanding': ai_response.get('understanding')
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in send_message: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/<int:conversation_id>/title', methods=['PUT'])
@login_required
def update_title(conversation_id):
    """Update conversation title"""
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        data = request.get_json()
        conversation.title = data.get('title')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/search', methods=['GET'])
@login_required
def search_conversations():
    """Search conversations by content"""
    try:
        query = request.args.get('q', '')
        
        if not query:
            return jsonify({
                'success': True,
                'conversations': []
            })
        
        # Search in conversation titles and message content
        conversations = Conversation.query.filter_by(
            user_id=current_user.id
        ).join(Message).filter(
            db.or_(
                Conversation.title.ilike(f'%{query}%'),
                Message.content.ilike(f'%{query}%')
            )
        ).distinct().order_by(Conversation.updated_at.desc()).all()
        
        return jsonify({
            'success': True,
            'conversations': [conv.to_dict() for conv in conversations]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/conversations/<int:conversation_id>/context/reset', methods=['POST'])
@login_required
def reset_context(conversation_id):
    """
    Reset the chatbot context for this conversation.
    Only resets if the bot is already initialized — won't force init.
    """
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversation not found'
            }), 404
        
        global _semantic_bot
        if _semantic_bot is not None:
            _semantic_bot.reset_conversation()
        
        return jsonify({
            'success': True,
            'message': 'Context reset successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/chatbot/status', methods=['GET'])
@login_required
def chatbot_status():
    """
    Get current chatbot status and context.
    Reports whether the bot has been initialized yet without forcing init.
    """
    try:
        global _semantic_bot
        
        if _semantic_bot is None:
            return jsonify({
                'success': True,
                'status': {
                    'model': 'SemanticChatbot',
                    'initialized': False,
                    'note': 'Bot will initialize on first message'
                }
            })
        
        bot = _semantic_bot
        
        return jsonify({
            'success': True,
            'status': {
                'model': 'SemanticChatbot',
                'initialized': True,
                'context': {
                    k: str(v) if not isinstance(v, (dict, list, int, float, bool, type(None))) else v
                    for k, v in bot.context.items()
                },
                'memory_size': len(bot.conversation_memory),
                'cache_size': len(bot.embedding_cache)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
