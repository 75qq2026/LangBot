from .. import migration

from ...entity.persistence import customer as persistence_customer


@migration.migration_class(25)
class DBMigrateCustomerManagement(migration.DBMigration):
    """Create customer management tables."""

    async def upgrade(self):
        """Upgrade"""
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await conn.run_sync(persistence_customer.Customer.__table__.create, checkfirst=True)
            await conn.run_sync(persistence_customer.CustomerConversation.__table__.create, checkfirst=True)

    async def downgrade(self):
        """Downgrade"""
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await conn.run_sync(persistence_customer.CustomerConversation.__table__.drop, checkfirst=True)
            await conn.run_sync(persistence_customer.Customer.__table__.drop, checkfirst=True)
