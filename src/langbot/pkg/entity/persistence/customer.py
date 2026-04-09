import sqlalchemy

from .base import Base


class Customer(Base):
    """Structured customer profile collected from conversations."""

    __tablename__ = 'customers'
    __table_args__ = (
        sqlalchemy.UniqueConstraint('bot_id', 'session_id', 'user_id', name='uq_customers_bot_session_user'),
    )

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    last_contact_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    platform = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    user_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    user_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    customer_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
    phone = sqlalchemy.Column(sqlalchemy.String(64), nullable=True, index=True)
    company = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    requirement_summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    notes = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    intent = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    tags = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    profile_status = sqlalchemy.Column(sqlalchemy.String(64), nullable=False, default='new')
    profile_data = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    source_runner = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    extraction_model = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    conversation_count = sqlalchemy.Column(sqlalchemy.Integer, nullable=False, default=0)


class CustomerConversation(Base):
    """Conversation timeline entries associated with a customer."""

    __tablename__ = 'customer_conversations'

    id = sqlalchemy.Column(sqlalchemy.String(255), primary_key=True)
    customer_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False, index=True)
    bot_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    bot_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    pipeline_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    pipeline_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    session_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    platform = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    user_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    user_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    role = sqlalchemy.Column(sqlalchemy.String(64), nullable=False, index=True)
    message_content = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    message_text = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    monitoring_message_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=True, index=True)
