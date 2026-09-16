import odoo

tenant = env['tour.saas.tenant'].browse(2)
db_name = tenant.db_name
print('Tenant: %s, db: %s, state: %s' % (tenant.name, db_name, tenant.state))

# Reset tenant state
tenant.state = 'draft'
env.cr.commit()

# Create it
print('Starting database creation...')
try:
    tenant._do_create_database()
    tenant.state = 'active'
    env.cr.commit()
    print('SUCCESS! Database created.')
except Exception as e:
    print('FAILED: %s' % str(e))
    import traceback
    traceback.print_exc()
    env.cr.rollback()
