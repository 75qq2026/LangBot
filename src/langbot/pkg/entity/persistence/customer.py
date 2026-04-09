import sqlalchemy

from .base import Base


class Customer(Base):
    """Customer profile extracted from conversations."""

    __tablename__ = 'customers'

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    launcher_type = sqlalchemy.Column(sqlalchemy.String(50), nullable=True, index=True)
    launcher_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    sender_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    sender_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    customer_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    phone = sqlalchemy.Column(sqlalchemy.String(64), nullable=True, index=True)
    requirement = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    company = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    address = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    intention = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    tags = sqlalchemy.Column(sqlalchemy.Text, nullable=True)  # JSON array string
    structured_profile = sqlalchemy.Column(sqlalchemy.Text, nullable=True)  # Full extracted profile JSON
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    last_conversation_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)


class CustomerConversation(Base):
    """Conversation timeline records associated with a customer."""

    __tablename__ = 'customer_conversations'

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    customer_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    message_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    role = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)  # user / assistant / system
    message_content = sqlalchemy.Column(sqlalchemy.Text, nullable=False)  # Original content payload
    message_text = sqlalchemy.Column(sqlalchemy.Text, nullable=True)  # Flattened plain text for search/readability
    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    launcher_type = sqlalchemy.Column(sqlalchemy.String(50), nullable=True, index=True)
    launcher_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    sender_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    sender_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    metadata_json = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
