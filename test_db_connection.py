#!/usr/bin/env python3
"""
Test script per verificare connessione database e lettura chiavi Crono.

Usage:
    python test_db_connection.py
"""

import os
import sys
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()

print("=" * 60)
print("TEST CONNESSIONE DATABASE")
print("=" * 60)

# 1. Verifica DATABASE_URL
db_url = os.getenv("DATABASE_URL")
print(f"\n1. DATABASE_URL presente: {'✅ SI' if db_url else '❌ NO'}")
if db_url:
    # Nascondi password per sicurezza
    safe_url = db_url
    if '@' in safe_url and ':' in safe_url:
        parts = safe_url.split('@')
        creds = parts[0].split(':')
        if len(creds) >= 3:
            safe_url = f"{creds[0]}:{creds[1]}:***@{parts[1]}"
    print(f"   URL: {safe_url}")
else:
    print("   ❌ DATABASE_URL non trovata nel .env")
    print("   → Aggiungi DATABASE_URL al file .env")
    sys.exit(1)

# 2. Test connessione database
print("\n2. Test connessione database...")
try:
    from src.database import db_manager, get_db

    # Forza riconnessione
    db_manager.connect()

    # Test query
    connection_ok = db_manager.check_connection()

    if connection_ok:
        print("   ✅ Connessione al database OK")

        # Mostra info database
        db_info = db_manager.get_database_info()
        print(f"   Pool size: {db_info.get('pool_size')}")
        print(f"   Max overflow: {db_info.get('max_overflow')}")

except Exception as e:
    print(f"   ❌ Errore connessione: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. Test lettura tenant e user
print("\n3. Test lettura dati tenant/user...")
try:
    from src.models import Tenant, User, UserSettings

    with get_db() as db:
        # Conta tenants
        tenant_count = db.query(Tenant).count()
        print(f"   Tenants nel database: {tenant_count}")

        if tenant_count > 0:
            # Mostra primo tenant
            tenant = db.query(Tenant).first()
            print(f"   → Tenant: {tenant.slack_team_name} ({tenant.slack_team_id})")

            # Conta users
            user_count = db.query(User).filter(User.tenant_id == tenant.id).count()
            print(f"   Users nel tenant: {user_count}")

            if user_count > 0:
                user = db.query(User).filter(User.tenant_id == tenant.id).first()
                print(f"   → User: {user.slack_user_id}")

                # Verifica settings
                settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
                if settings:
                    print(f"   ✅ UserSettings trovate")
                    has_public = bool(settings.crono_public_key)
                    has_private = bool(settings.crono_private_key)
                    print(f"      - crono_public_key: {'✅ SET' if has_public else '❌ NULL'}")
                    print(f"      - crono_private_key: {'✅ SET' if has_private else '❌ NULL'}")

                    if has_public and has_private:
                        print(f"      - public_key: {settings.crono_public_key[:20]}...")
                        print(f"      - private_key: {settings.crono_private_key[:20]}...")
                else:
                    print(f"   ⚠️  UserSettings non trovate per questo user")
        else:
            print("   ⚠️  Nessun tenant nel database")
            print("   → Esegui le migrazioni: alembic upgrade head")

except Exception as e:
    print(f"   ❌ Errore lettura dati: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. Test API endpoint (simulato)
print("\n4. Test simulazione lettura chiavi via helper...")
try:
    from src.slack_webhook_handler import get_user_crm_credentials

    with get_db() as db:
        # Usa il primo user trovato
        user = db.query(User).first()
        if user:
            tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()

            credentials = get_user_crm_credentials(
                db=db,
                slack_user_id=user.slack_user_id,
                team_id=tenant.slack_team_id if tenant else None
            )

            if credentials:
                print(f"   ✅ Credenziali Crono lette correttamente")
                print(f"      - public_key: {credentials['public_key'][:20]}...")
                print(f"      - private_key: {credentials['private_key'][:20]}...")
            else:
                print(f"   ❌ Credenziali Crono non trovate")
                print(f"      → Configura le chiavi via UI: http://localhost:3000/settings")
        else:
            print(f"   ⚠️  Nessun user nel database per testare")

except Exception as e:
    print(f"   ❌ Errore test credenziali: {e}")
    import traceback
    traceback.print_exc()

# 5. Test CronoProvider (se credenziali disponibili)
print("\n5. Test CronoProvider.search_accounts...")
try:
    from src.providers.crono_provider import CronoProvider

    with get_db() as db:
        user = db.query(User).first()
        if user and user.settings and user.settings.crono_public_key and user.settings.crono_private_key:
            credentials = {
                'public_key': user.settings.crono_public_key,
                'private_key': user.settings.crono_private_key
            }

            provider = CronoProvider(credentials=credentials)
            print(f"   Testing search for 'test'...")

            results = provider.search_accounts(query="test", limit=5)
            print(f"   ✅ Ricerca completata: {len(results)} risultati")

            if results:
                for i, acc in enumerate(results[:3], 1):
                    print(f"      {i}. {acc.get('name', 'N/A')} (ID: {acc.get('id', 'N/A')})")
            else:
                print(f"   ⚠️  Nessun account trovato (potrebbero non esserci match per 'test')")
        else:
            print(f"   ⏭️  SKIP - Nessuna credenziale Crono configurata")

except Exception as e:
    print(f"   ❌ Errore test CronoProvider: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST COMPLETATO")
print("=" * 60)
