# Tenant Middleware Architecture Diagrams

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SLACK WORKSPACE                             │
│                                                                     │
│  User types: /followup                                              │
│  User clicks: [Create Gmail Draft]                                 │
│  User receives: event notification                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTPS Webhook
                           │ team_id=T0123456789
                           │ X-Slack-Signature: v0=abc123...
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FLASK APPLICATION                              │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │          TENANT MIDDLEWARE (before_request)               │    │
│  │                                                           │    │
│  │  1. Extract team_id from request                         │    │
│  │     └─ slack_parser.extract_tenant_id_from_request()     │    │
│  │                                                           │    │
│  │  2. Verify Slack signature (HMAC-SHA256)                 │    │
│  │     └─ slack_parser.verify_slack_signature()             │    │
│  │                                                           │    │
│  │  3. Load tenant from cache/database                      │    │
│  │     ├─ Check Redis cache (tenant:slack_id:T0123...)      │    │
│  │     └─ If miss, query PostgreSQL tenants table           │    │
│  │                                                           │    │
│  │  4. Set tenant in thread-local context                   │    │
│  │     └─ tenant_context.set_current_tenant(tenant)         │    │
│  │                                                           │    │
│  │  5. Attach to Flask g object                             │    │
│  │     └─ g.tenant = tenant                                 │    │
│  └───────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           ▼                                         │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │              REQUEST HANDLER EXECUTES                     │    │
│  │                                                           │    │
│  │  @app.route('/slack/interactions')                        │    │
│  │  def handle_interaction():                                │    │
│  │      tenant = get_current_tenant()                        │    │
│  │                                                           │    │
│  │      # All queries automatically scoped                   │    │
│  │      meetings = scoped_query(MeetingSession, db).all()   │    │
│  │                                                           │    │
│  │      # CRM from tenant's connection                       │    │
│  │      crm = get_tenant_crm_connection()                    │    │
│  │                                                           │    │
│  │      return jsonify(response)                             │    │
│  └───────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           ▼                                         │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │          TENANT MIDDLEWARE (after_request)                │    │
│  │                                                           │    │
│  │  1. Clear tenant context                                  │    │
│  │     └─ tenant_context.clear_tenant_context()             │    │
│  │                                                           │    │
│  │  2. Close database session                                │    │
│  │     └─ db.close()                                         │    │
│  │                                                           │    │
│  │  3. Return response to Slack                              │    │
│  └───────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SLACK WORKSPACE                             │
│                                                                     │
│  User sees: ✓ Gmail draft created successfully!                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Thread Isolation

```
┌─────────────────────────────────────────────────────────────────┐
│                      HTTP REQUEST THREADS                        │
│                                                                  │
│  Thread 1                Thread 2                Thread 3       │
│  ┌──────────┐          ┌──────────┐           ┌──────────┐     │
│  │ Request  │          │ Request  │           │ Request  │     │
│  │ from     │          │ from     │           │ from     │     │
│  │ Tenant A │          │ Tenant B │           │ Tenant A │     │
│  └────┬─────┘          └────┬─────┘           └────┬─────┘     │
│       │                     │                      │            │
│       ▼                     ▼                      ▼            │
│  ┌──────────┐          ┌──────────┐           ┌──────────┐     │
│  │threading │          │threading │           │threading │     │
│  │ .local() │          │ .local() │           │ .local() │     │
│  │          │          │          │           │          │     │
│  │ tenant = │          │ tenant = │           │ tenant = │     │
│  │ Tenant A │          │ Tenant B │           │ Tenant A │     │
│  └────┬─────┘          └────┬─────┘           └────┬─────┘     │
│       │                     │                      │            │
│       ▼                     ▼                      ▼            │
│  ┌──────────┐          ┌──────────┐           ┌──────────┐     │
│  │ Query:   │          │ Query:   │           │ Query:   │     │
│  │ tenant_id│          │ tenant_id│           │ tenant_id│     │
│  │ = A      │          │ = B      │           │ = A      │     │
│  └──────────┘          └──────────┘           └──────────┘     │
│                                                                  │
│  COMPLETELY ISOLATED - NO CROSS-CONTAMINATION                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Tenant Loading

```
┌─────────────────────────────────────────────────────────────────┐
│                    TENANT LOADING FLOW                          │
└─────────────────────────────────────────────────────────────────┘

Request arrives with team_id: T0123456789
              │
              ▼
┌─────────────────────────────┐
│ Check Redis Cache           │
│ Key: tenant:slack_id:T012...│
└──────────┬──────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌────────┐   ┌────────────────────────────┐
│ CACHE  │   │ CACHE MISS                 │
│  HIT   │   │                            │
│ ~1-2ms │   │ Query PostgreSQL:          │
│        │   │ SELECT * FROM tenants      │
└────┬───┘   │ WHERE slack_team_id =      │
     │       │   'T0123456789'            │
     │       │ AND deleted_at IS NULL     │
     │       │                            │
     │       │ ~50-100ms                  │
     │       └──────────┬─────────────────┘
     │                  │
     │                  ▼
     │       ┌────────────────────────────┐
     │       │ Cache in Redis (TTL=5min)  │
     │       └──────────┬─────────────────┘
     │                  │
     └──────────────────┘
                        │
                        ▼
             ┌────────────────────────┐
             │ Return Tenant Object   │
             │                        │
             │ - id: uuid             │
             │ - slack_team_id        │
             │ - slack_team_name      │
             │ - subscription_status  │
             │ - plan_tier            │
             └────────────────────────┘
```

---

## Security: Request Verification

```
┌─────────────────────────────────────────────────────────────────┐
│              SLACK SIGNATURE VERIFICATION                       │
└─────────────────────────────────────────────────────────────────┘

Slack Request Headers:
  X-Slack-Request-Timestamp: 1531420618
  X-Slack-Signature: v0=a2114d57b48eac39b9ad189dd8316235a7b4a8d21a10bd27519666489c69b503

Request Body:
  team_id=T0123456789&command=/followup&user_id=U9876543210...

              │
              ▼
┌─────────────────────────────┐
│ 1. Check Timestamp          │
│    Current - Timestamp < 5m │
│    (Prevent replay attacks) │
└──────────┬──────────────────┘
           │ ✓ Valid
           ▼
┌─────────────────────────────┐
│ 2. Compute Expected Sig     │
│                             │
│    basestring = "v0:" +     │
│      timestamp + ":" +      │
│      body                   │
│                             │
│    expected = HMAC-SHA256(  │
│      signing_secret,        │
│      basestring             │
│    )                        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 3. Compare Signatures       │
│    (constant-time)          │
│                             │
│    hmac.compare_digest(     │
│      expected,              │
│      received               │
│    )                        │
└──────────┬──────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌────────┐   ┌─────────┐
│ Valid  │   │ Invalid │
│   ✓    │   │    ✗    │
│        │   │         │
│Process │   │ Return  │
│Request │   │ 403     │
└────────┘   └─────────┘
```

---

## Database Query Scoping

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUERY SCOPING FLOW                           │
└─────────────────────────────────────────────────────────────────┘

Handler Code:
  meetings = scoped_query(MeetingSession, db).all()

              │
              ▼
┌─────────────────────────────┐
│ 1. Get Current Tenant ID    │
│    from thread-local        │
│                             │
│    tenant_id =              │
│      get_current_tenant_id()│
│                             │
│    → uuid-1234-5678...      │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 2. Create Base Query        │
│                             │
│    query = db.query(        │
│      MeetingSession         │
│    )                        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 3. Add Tenant Filter        │
│                             │
│    query = query.filter(    │
│      MeetingSession         │
│        .tenant_id ==        │
│        tenant_id            │
│    )                        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 4. Add Soft Delete Filter   │
│                             │
│    query = query.filter(    │
│      MeetingSession         │
│        .deleted_at          │
│        .is_(None)           │
│    )                        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 5. Execute Query            │
│                             │
│    SQL:                     │
│    SELECT * FROM            │
│      meeting_sessions       │
│    WHERE                    │
│      tenant_id = $1 AND     │
│      deleted_at IS NULL     │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Return Results              │
│ (ONLY current tenant's data)│
└─────────────────────────────┘
```

---

## Multi-Tenant Data Isolation

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATABASE STRUCTURE                         │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                        TENANTS TABLE                             │
├────────────────┬──────────────────┬──────────────┬───────────────┤
│ id (UUID)      │ slack_team_id    │ team_name    │ subscription  │
├────────────────┼──────────────────┼──────────────┼───────────────┤
│ uuid-aaaa-...  │ T0123456789      │ Acme Corp    │ active        │
│ uuid-bbbb-...  │ T9876543210      │ Beta Inc     │ active        │
│ uuid-cccc-...  │ T1111111111      │ Gamma LLC    │ trial         │
└────────────────┴──────────────────┴──────────────┴───────────────┘
         │                  │                 │
         │                  │                 │
         ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MEETING_SESSIONS TABLE                       │
├────────┬────────────┬──────────────┬──────────────┬─────────────┤
│ id     │ tenant_id  │ meeting      │ fathom_id    │ user_id     │
├────────┼────────────┼──────────────┼──────────────┼─────────────┤
│ uuid-1 │ uuid-aaaa  │ Client Call  │ 12345        │ uuid-u1     │ ← Acme
│ uuid-2 │ uuid-aaaa  │ Sales Demo   │ 12346        │ uuid-u2     │ ← Acme
│ uuid-3 │ uuid-bbbb  │ Product Rev  │ 45678        │ uuid-u3     │ ← Beta
│ uuid-4 │ uuid-cccc  │ Team Sync    │ 78901        │ uuid-u4     │ ← Gamma
└────────┴────────────┴──────────────┴──────────────┴─────────────┘

When Acme Corp makes request:
  Context: tenant_id = uuid-aaaa
  Query: WHERE tenant_id = uuid-aaaa
  Result: [uuid-1, uuid-2]  ← Only Acme's meetings

ISOLATION ENFORCED BY:
  1. Thread-local context (tenant per request)
  2. Automatic WHERE tenant_id = ... filter
  3. No manual tenant_id manipulation allowed
  4. verify_tenant_access() for cross-checks
```

---

## CRM Integration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              TENANT-SCOPED CRM INTEGRATION                      │
└─────────────────────────────────────────────────────────────────┘

User clicks: [Create Crono Note]
              │
              ▼
┌─────────────────────────────┐
│ 1. Get Current Tenant       │
│    tenant =                 │
│      get_current_tenant()   │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 2. Load Tenant's CRM        │
│    Connection               │
│                             │
│    crm_conn =               │
│      scoped_query(          │
│        CRMConnection, db    │
│      ).filter_by(           │
│        is_default=True      │
│      ).first()              │
│                             │
│    Result: Crono config     │
│      for this tenant        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 3. Create CRM Provider      │
│                             │
│    crm = Factory.create(    │
│      crm_conn.provider_type,│
│      crm_conn.credentials   │
│    )                        │
│                             │
│    → Uses tenant's API keys │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 4. Create Note in CRM       │
│                             │
│    note_id = crm            │
│      .create_meeting_note() │
│                             │
│    → Tenant A's note in     │
│      Tenant A's CRM account │
└─────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                       CRM CONNECTIONS                         │
├────────────┬─────────────┬───────────┬──────────────────────┤
│ tenant_id  │ provider    │ default   │ credentials_secret   │
├────────────┼─────────────┼───────────┼──────────────────────┤
│ uuid-aaaa  │ crono       │ true      │ aws-secret-aaaa-crono│ ← Acme
│ uuid-bbbb  │ hubspot     │ true      │ aws-secret-bbbb-hub  │ ← Beta
│ uuid-cccc  │ salesforce  │ true      │ aws-secret-cccc-sf   │ ← Gamma
└────────────┴─────────────┴───────────┴──────────────────────┘

Each tenant has their own:
  - CRM provider choice (Crono, HubSpot, Salesforce, etc.)
  - API credentials (stored in AWS Secrets Manager)
  - CRM configuration
  - Account mappings
```

---

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ERROR HANDLING FLOW                          │
└─────────────────────────────────────────────────────────────────┘

Request arrives
      │
      ▼
┌─────────────────────┐
│ Verify Signature    │
└──────┬──────────────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
┌──────┐ ┌──────────────────────────────┐
│ Valid│ │ Invalid                      │
└──┬───┘ │                              │
   │     │ → Return 403                 │
   │     │    {"error": "Invalid sig"} │
   │     └──────────────────────────────┘
   ▼
┌─────────────────────┐
│ Extract team_id     │
└──────┬──────────────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
┌──────┐ ┌──────────────────────────────┐
│Found │ │ Missing                      │
└──┬───┘ │                              │
   │     │ → Return 400                 │
   │     │    {"error": "Missing ID"}  │
   │     └──────────────────────────────┘
   ▼
┌─────────────────────┐
│ Load Tenant         │
└──────┬──────────────┘
       │
   ┌───┴────────┐
   │            │
   ▼            ▼
┌──────┐    ┌────────────┐
│Found │    │ Not Found  │
│      │    │            │
└──┬───┘    │ → Return   │
   │        │    403     │
   │        │ "Not       │
   │        │ installed" │
   │        └────────────┘
   ▼
┌─────────────────────┐
│ Check Subscription  │
└──────┬──────────────┘
       │
   ┌───┴────────┐
   │            │
   ▼            ▼
┌──────┐    ┌────────────┐
│Active│    │ Suspended  │
│      │    │            │
└──┬───┘    │ → Return   │
   │        │    403     │
   │        │ "Suspended"│
   │        └────────────┘
   ▼
┌─────────────────────┐
│ Set Context         │
│ Process Request     │
│ Return Success      │
└─────────────────────┘
```

---

## Cache Performance

```
┌─────────────────────────────────────────────────────────────────┐
│                  CACHE PERFORMANCE COMPARISON                   │
└─────────────────────────────────────────────────────────────────┘

WITHOUT REDIS:
─────────────
  Request 1: ████████████████████████████████████████████ 100ms (DB)
  Request 2: ████████████████████████████████████████████ 100ms (DB)
  Request 3: ████████████████████████████████████████████ 100ms (DB)
  Request 4: ████████████████████████████████████████████ 100ms (DB)

  Average: 100ms per request


WITH REDIS:
───────────
  Request 1: ████████████████████████████████████████████ 100ms (MISS → DB)
  Request 2: █ 2ms (HIT)
  Request 3: █ 2ms (HIT)
  Request 4: █ 2ms (HIT)
  Request 5: █ 2ms (HIT)
  ... (for 5 minutes TTL)

  Average: 2ms per request (after cache warm)


PERFORMANCE IMPROVEMENT:
────────────────────────
  50x faster response time
  98% reduction in database load
  99.9% uptime even if Redis down (degrades to DB)
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION DEPLOYMENT                        │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                          INTERNET                              │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                      LOAD BALANCER                             │
│                    (nginx / AWS ALB)                           │
└───────────┬────────────────────────────┬───────────────────────┘
            │                            │
    ┌───────┴────────┐          ┌───────┴────────┐
    │                │          │                │
    ▼                ▼          ▼                ▼
┌─────────┐    ┌─────────┐  ┌─────────┐    ┌─────────┐
│ Flask   │    │ Flask   │  │ Flask   │    │ Flask   │
│ App 1   │    │ App 2   │  │ App 3   │    │ App 4   │
│         │    │         │  │         │    │         │
│ Thread  │    │ Thread  │  │ Thread  │    │ Thread  │
│ Pool    │    │ Pool    │  │ Pool    │    │ Pool    │
└────┬────┘    └────┬────┘  └────┬────┘    └────┬────┘
     │              │            │              │
     └──────┬───────┴────────┬───┴──────────────┘
            │                │
            ▼                ▼
     ┌──────────┐     ┌──────────┐
     │  Redis   │     │PostgreSQL│
     │  Cluster │     │ Primary  │
     │          │     │          │
     │  Cache   │     │ Replica  │
     └──────────┘     └──────────┘

Each Flask instance:
  - Independent thread pool
  - Thread-local tenant context
  - Shared Redis cache
  - Shared PostgreSQL database

Scaling:
  - Horizontal: Add more Flask instances
  - Cache: Redis cluster for high availability
  - Database: Read replicas for queries
```

This comprehensive implementation provides enterprise-grade multi-tenant isolation for your Slack application!
