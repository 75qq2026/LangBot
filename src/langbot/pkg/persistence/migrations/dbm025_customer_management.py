from .. import migration

import sqlalchemy


@migration.migration_class(25)
class DBMigrateCustomerManagement(migration.DBMigration):
    """Create customer profile and conversation tables."""

    async def upgrade(self):
        """Upgrade"""
        # customers table
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id VARCHAR(255) PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL UNIQUE,
                    bot_id VARCHAR(255) NOT NULL,
                    bot_name VARCHAR(255) NOT NULL,
                    pipeline_id VARCHAR(255) NOT NULL,
                    pipeline_name VARCHAR(255) NOT NULL,
                    launcher_type VARCHAR(50),
                    launcher_id VARCHAR(255),
                    sender_id VARCHAR(255),
                    sender_name VARCHAR(255),
                    customer_name VARCHAR(255),
                    phone VARCHAR(64),
                    requirement TEXT,
                    company VARCHAR(255),
                    address VARCHAR(255),
                    intention VARCHAR(255),
                    tags TEXT,
                    structured_profile TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    last_conversation_at TIMESTAMP NOT NULL
                )
                """
            )
        )

        # customer_conversations table
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.text(
                """
                CREATE TABLE IF NOT EXISTS customer_conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    customer_id VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    message_id VARCHAR(255),
                    role VARCHAR(50) NOT NULL,
                    message_content TEXT NOT NULL,
                    message_text TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    bot_id VARCHAR(255) NOT NULL,
                    bot_name VARCHAR(255) NOT NULL,
                    pipeline_id VARCHAR(255) NOT NULL,
                    pipeline_name VARCHAR(255) NOT NULL,
                    launcher_type VARCHAR(50),
                    launcher_id VARCHAR(255),
                    sender_id VARCHAR(255),
                    sender_name VARCHAR(255),
                    metadata_json TEXT
                )
                """
            )
        )

        # indexes: use IF NOT EXISTS for sqlite compatibility
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_customers_session_id ON customers(session_id)',
            'CREATE INDEX IF NOT EXISTS idx_customers_bot_id ON customers(bot_id)',
            'CREATE INDEX IF NOT EXISTS idx_customers_pipeline_id ON customers(pipeline_id)',
            'CREATE INDEX IF NOT EXISTS idx_customers_customer_name ON customers(customer_name)',
            'CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)',
            'CREATE INDEX IF NOT EXISTS idx_customers_last_conversation_at ON customers(last_conversation_at)',
            'CREATE INDEX IF NOT EXISTS idx_customer_conversations_customer_id ON customer_conversations(customer_id)',
            'CREATE INDEX IF NOT EXISTS idx_customer_conversations_session_id ON customer_conversations(session_id)',
            'CREATE INDEX IF NOT EXISTS idx_customer_conversations_timestamp ON customer_conversations(timestamp)',
            'CREATE INDEX IF NOT EXISTS idx_customer_conversations_role ON customer_conversations(role)',
            'CREATE INDEX IF NOT EXISTS idx_customer_conversations_message_id ON customer_conversations(message_id)',
        ]
        for sql in indexes:
            await self.ap.persistence_mgr.execute_async(sqlalchemy.text(sql))

    async def downgrade(self):
        """Downgrade"""
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.text('DROP TABLE IF EXISTS customer_conversations')
        )
        await self.ap.persistence_mgr.execute_async(sqlalchemy.text('DROP TABLE IF EXISTS customers'))
