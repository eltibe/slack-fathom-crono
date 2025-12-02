#!/usr/bin/env python3
"""
Script per verificare/creare il tenant fisso nel database.
"""

from src.database import get_db
from src.models.tenant import Tenant
import sys

def setup_tenant():
    """Verifica o crea il tenant con slack_team_id = T02R43CJEMA"""

    with get_db() as db:
        # Cerca il tenant esistente
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == 'T02R43CJEMA').first()

        if tenant:
            print('✅ Tenant già esistente!')
            print(f'   ID: {tenant.id}')
            print(f'   Slack Team ID: {tenant.slack_team_id}')
            print(f'   Nome: {tenant.slack_team_name}')
            print(f'   Piano: {tenant.plan_tier}')
            print(f'   Attivo: {tenant.is_active}')
            return tenant
        else:
            print('❌ Tenant NON trovato. Creo il tenant ora...')

            # Crea nuovo tenant
            new_tenant = Tenant(
                slack_team_id='T02R43CJEMA',
                slack_team_name='Lorenzo Team',
                plan_tier='free',
                is_active=True
            )
            db.add(new_tenant)
            db.commit()
            db.refresh(new_tenant)

            print('✅ Tenant creato con successo!')
            print(f'   ID: {new_tenant.id}')
            print(f'   Slack Team ID: {new_tenant.slack_team_id}')
            print(f'   Nome: {new_tenant.slack_team_name}')
            return new_tenant

if __name__ == '__main__':
    try:
        setup_tenant()
        sys.exit(0)
    except Exception as e:
        print(f'❌ Errore: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
