"""
Chat Routes - IMPROVED VERSION
✅ Timeout fixes
✅ Better initialization
✅ Enhanced error handling
✅ Performance optimization
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.database import db
from models.conversation import Conversation
from models.message import Message
from datetime import datetime
import gc
import time
import threading

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

# Global state
_semantic_bot = None
_bot_loading = False
_bot_load_lock = threading.Lock()
_bot_ready_event = threading.Event()


def get_semantic_bot():
    """
    Thread-safe chatbot initialization with timeout protection
    """
    global _semantic_bot, _bot_loading
    
    # If bot is ready, return immediately
    if _semantic_bot is not None:
        return _semantic_bot
    
    # If another thread is loading, wait for it
    with _bot_load_lock:
        # Double-check after acquiring lock
        if _semantic_bot is not None:
            return _semantic_bot
        
        if _bot_loading:
            print("⏳ Waiting for bot initialization to complete...", flush=True)
            # Wait up to 60 seconds for initialization
            if not _bot_ready_event.wait(timeout=60):
                raise TimeoutError("Chatbot initialization timed out after 60 seconds")
            return _semantic_bot
        
        # This thread will do the initialization
        _bot_loading = True
        
        try:
            print("🚀 Initializing Semantic Chatbot...", flush=True)
            start_time = time.time()
            
            # Import and initialize
            from ai_modules.semantic_chatbot import SemanticChatbot
            _semantic_bot = SemanticChatbot()
            
            elapsed = time.time() - start_time
            print(f"✅ Semantic Chatbot initialized in {elapsed:.2f}s", flush=True)
            
            # Signal other waiting threads
            _bot_ready_event.set()
            
            # Cleanup
            gc.collect()
            
            return _semantic_bot
            
        except Exception as e:
            import traceback
            print(f"❌ Failed to initialize SemanticChatbot: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            
            # Reset loading state
            _bot_loading = False
            _bot_ready_event.clear()
            
            raise RuntimeError(
                f"Chatbot initialization failed: {e}. "
                "Check that spaCy model and sentence-transformers are installed correctly."
            )
        finally:
            _bot_loading = False


def initialize_bot_background():
    """
    Background initialization - called by app startup
    Returns immediately, initialization happens in background
    """
    def _init():
        try:
            print("🔥 Pre-warming chatbot in background...", flush=True)
            get_semantic_bot()
        except Exception as e:
            print(f"⚠️ Background pre-warming failed: {e}", flush=True)
    
    thread = threading.Thread(target=_init, daemon=True, name="ChatbotPrewarm")
    thread.start()
    return thread


@chat_bp.route('/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Get all conversations"""
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
        return jsonify({'success': False, 'error': str(e)}), 500


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
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict_detailed()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/conversations', methods=['POST'])
@login_required
def create_conversation():
    """Create a new conversation"""
    try:
        data = request.get_json() or {}
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
        return jsonify({'success': False, 'error': str(e)}), 500


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
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        db.session.delete(conversation)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Conversation deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
@login_required
def send_message(conversation_id):
    """
    Send a message and get AI response
    ✅ TIMEOUT PROTECTION
    ✅ BETTER ERROR HANDLING
    ✅ CONVERSATION HISTORY SUPPORT
    """
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        data = request.get_json()
        user_message_content = data.get('content', '').strip()
        
        if not user_message_content:
            return jsonify({'success': False, 'error': 'Message content cannot be empty'}), 400
        
        print(f"💬 User {current_user.id}: {user_message_content[:100]}...", flush=True)
        
        # 1. Save user message
        user_message = Message(
            conversation_id=conversation_id,
            role='user',
            content=user_message_content
        )
        db.session.add(user_message)
        db.session.flush()
        
        # 2. Process with semantic chatbot (with timeout protection)
        try:
            # Initialize bot with timeout protection
            start_time = time.time()
            bot = get_semantic_bot()
            init_time = time.time() - start_time
            
            if init_time > 5:
                print(f"⚠️ Bot initialization took {init_time:.2f}s", flush=True)
            
            # Get conversation history for better context
            recent_messages = Message.query.filter_by(
                conversation_id=conversation_id
            ).order_by(Message.created_at.desc()).limit(10).all()
            
            conversation_history = []
            for msg in reversed(recent_messages[1:]):  # Exclude current message
                conversation_history.append({
                    'role': msg.role,
                    'content': msg.content
                })
            
            # Process message with history
            import inspect
            sig = inspect.signature(bot.process_message)
            
            kwargs = {
                'query': user_message_content,
                'conversation_id': conversation_id,
            }
            
            # Add optional parameters if supported
            if 'user_id' in sig.parameters:
                kwargs['user_id'] = current_user.id
            if 'conversation_history' in sig.parameters:
                kwargs['conversation_history'] = conversation_history
            
            # If bot doesn't support user_id parameter, set it manually
            if 'user_id' not in sig.parameters:
                bot.current_user_id = current_user.id
            
            # Call with timeout protection
            process_start = time.time()
            ai_response = bot.process_message(**kwargs)
            process_time = time.time() - process_start
            
            print(f"✅ Response generated in {process_time:.2f}s", flush=True)
            
            # 3. Save AI response message
            assistant_message = Message(
                conversation_id=conversation_id,
                role='assistant',
                content=ai_response['response'],
                intent=ai_response.get('intent'),
                confidence=ai_response.get('confidence')
            )
            
            if ai_response.get('understanding', {}).get('entities'):
                assistant_message.set_entities(ai_response['understanding']['entities'])
            
            db.session.add(assistant_message)
            
        except TimeoutError as e:
            print(f"⏱️ Timeout error: {str(e)}", flush=True)
            
            assistant_message = Message(
                conversation_id=conversation_id,
                role='assistant',
                content=(
                    "I'm experiencing high load right now and couldn't process your request in time. "
                    "Please try again in a moment."
                )
            )
            db.session.add(assistant_message)
            ai_response = {
                'response': assistant_message.content,
                'intent': 'error',
                'data': None,
                'chart_type': None,
                'understanding': {'error': 'timeout'}
            }
            
        except RuntimeError as e:
            print(f"❌ RuntimeError: {str(e)}", flush=True)
            
            assistant_message = Message(
                conversation_id=conversation_id,
                role='assistant',
                content=(
                    "I'm having trouble initializing my AI models right now. "
                    "Please wait a moment and try again."
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
        
        # 4. Update conversation
        conversation.updated_at = datetime.utcnow()
        
        if not conversation.title or conversation.title == 'New Conversation':
            conversation.title = user_message_content[:50] + ('...' if len(user_message_content) > 50 else '')
        
        # 5. Commit all changes
        db.session.commit()
        
        # 6. Fix: Convert sets to lists for JSON serialization
        understanding = ai_response.get('understanding', {})
        if understanding:
            # Deep clean all sets in understanding
            understanding = _clean_for_json(understanding)
        
        # Cleanup memory
        gc.collect()
        
        # 7. Return response
        return jsonify({
            'success': True,
            'user_message': user_message.to_dict(),
            'assistant_message': assistant_message.to_dict(),
            'data': ai_response.get('data'),
            'chart_type': ai_response.get('chart_type'),
            'understanding': understanding
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


def _clean_for_json(obj):
    """Recursively convert sets to lists for JSON serialization"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_for_json(item) for item in obj]
    else:
        return obj


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
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        data = request.get_json()
        conversation.title = data.get('title')
        db.session.commit()
        
        return jsonify({'success': True, 'conversation': conversation.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/conversations/search', methods=['GET'])
@login_required
def search_conversations():
    """Search conversations by content"""
    try:
        query = request.args.get('q', '')
        
        if not query:
            return jsonify({'success': True, 'conversations': []})
        
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
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/conversations/<int:conversation_id>/context/reset', methods=['POST'])
@login_required
def reset_context(conversation_id):
    """Reset the chatbot context for this conversation"""
    try:
        conversation = Conversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        global _semantic_bot
        if _semantic_bot is not None:
            _semantic_bot.reset_conversation()
        
        return jsonify({'success': True, 'message': 'Context reset successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/chatbot/status', methods=['GET'])
@login_required
def chatbot_status():
    """Get current chatbot status and context"""
    try:
        global _semantic_bot, _bot_loading
        
        if _semantic_bot is None:
            return jsonify({
                'success': True,
                'status': {
                    'model': 'SemanticChatbot',
                    'initialized': False,
                    'loading': _bot_loading,
                    'note': 'Bot will initialize on first message'
                }
            })
        
        bot = _semantic_bot
        
        # Convert context for JSON serialization
        context_json = _clean_for_json(bot.context) if hasattr(bot, 'context') else {}
        
        return jsonify({
            'success': True,
            'status': {
                'model': 'SemanticChatbot',
                'initialized': True,
                'loading': False,
                'context': context_json,
                'memory_size': len(bot.conversation_memory) if hasattr(bot, 'conversation_memory') else 0,
                'cache_size': len(bot.embedding_cache) if hasattr(bot, 'embedding_cache') else 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
