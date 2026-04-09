import sqlalchemy

from .base import Base


class Customer(Base):
    """Customer profile collected from conversations."""

    __tablename__ = 'customers'

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    customer_key = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, unique=True, index=True)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    platform = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    user_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    user_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    phone = sqlalchemy.Column(sqlalchemy.String(64), nullable=True, index=True)
    email = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    company = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    requirements = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    notes = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    tags = sqlalchemy.Column(sqlalchemy.JSON, nullable=True)
    profile_data = sqlalchemy.Column(sqlalchemy.JSON, nullable=True)
    latest_summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    conversation_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, default=0)
    first_contact_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    last_contact_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    last_extracted_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    )


class CustomerConversation(Base):
    """Conversation records associated with customers."""

    __tablename__ = 'customer_conversations'

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    customer_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    platform = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    user_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    user_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    role = sqlalchemy.Column(sqlalchemy.String(50), nullable=False, index=True)
    content_text = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    raw_message_content = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    extracted_payload = sqlalchemy.Column(sqlalchemy.JSON, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
