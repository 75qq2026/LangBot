from .. import migration

import sqlalchemy


@migration.migration_class(25)
class DBMigrateCustomerManagement(migration.DBMigration):
    """Create customer profile and conversation timeline tables."""

    async def upgrade(self):
        """Upgrade"""
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id VARCHAR(255) PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    last_contact_at DATETIME NOT NULL,
                    bot_id VARCHAR(255) NOT NULL,
                    bot_name VARCHAR(255) NOT NULL,
                    pipeline_id VARCHAR(255) NOT NULL,
                    pipeline_name VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    platform VARCHAR(255),
                    user_id VARCHAR(255) NOT NULL,
                    user_name VARCHAR(255),
                    customer_name VARCHAR(255),
                    phone VARCHAR(64),
                    company VARCHAR(255),
                    requirement_summary TEXT,
                    notes TEXT,
                    intent VARCHAR(255),
                    tags TEXT,
                    profile_status VARCHAR(64) NOT NULL DEFAULT 'new',
                    profile_data TEXT,
                    source_runner VARCHAR(255),
                    extraction_model VARCHAR(255),
                    conversation_count INTEGER NOT NULL DEFAULT 0,
                    CONSTRAINT uq_customers_bot_session_user UNIQUE (bot_id, session_id, user_id)
                )
                """
            )
        )
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS customer_conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    customer_id VARCHAR(255) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    bot_id VARCHAR(255) NOT NULL,
                    bot_name VARCHAR(255) NOT NULL,
                    pipeline_id VARCHAR(255) NOT NULL,
                    pipeline_name VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    platform VARCHAR(255),
                    user_id VARCHAR(255) NOT NULL,
                    user_name VARCHAR(255),
                    role VARCHAR(64) NOT NULL,
                    message_content TEXT NOT NULL,
                    message_text TEXT,
                    monitoring_message_id VARCHAR(255)
                )
                """
            )
        )

        indexes = [
            'CREATE INDEX IF NOT EXISTS ix_customers_created_at ON customers (created_at)',
            'CREATE INDEX IF NOT EXISTS ix_customers_updated_at ON customers (updated_at)',
            'CREATE INDEX IF NOT EXISTS ix_customers_last_contact_at ON customers (last_contact_at)',
            'CREATE INDEX IF NOT EXISTS ix_customers_bot_id ON customers (bot_id)',
            'CREATE INDEX IF NOT EXISTS ix_customers_pipeline_id ON customers (pipeline_id)',
            'CREATE INDEX IF NOT EXISTS ix_customers_session_id ON customers (session_id)',
            'CREATE INDEX IF NOT EXISTS ix_customers_user_id ON customers (user_id)',
            'CREATE INDEX IF NOT EXISTS ix_customers_customer_name ON customers (customer_name)',
            'CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers (phone)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_customer_id ON customer_conversations (customer_id)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_timestamp ON customer_conversations (timestamp)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_bot_id ON customer_conversations (bot_id)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_pipeline_id ON customer_conversations (pipeline_id)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_session_id ON customer_conversations (session_id)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_user_id ON customer_conversations (user_id)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_role ON customer_conversations (role)',
            'CREATE INDEX IF NOT EXISTS ix_customer_conversations_monitoring_message_id '
            'ON customer_conversations (monitoring_message_id)',
        ]

        for statement in indexes:
            await self.ap.persistence_mgr.execute_async(sqlalchemy.text(statement))

    async def downgrade(self):
        """Downgrade"""
        pass
