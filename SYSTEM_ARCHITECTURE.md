# LisztServ System Architecture

## Core System [MUSIC_SCANNING]
COMPONENTS:
- WebContentExtractor: URL → text_content
- SpotifyManager: spotify_links → album_data
- ContentProcessor: text → music_references
- PlaylistManager: tracks → spotify_playlist

FLOWS:
1. URL_SCAN:
   ```
   input: URL
   WebContentExtractor.extract(URL) → content
   SpotifyManager.scan_links(content) → album_ids
   foreach album_id:
     SpotifyManager.get_album_info(id) → album_data
   output: album_list
   ```

2. GPT_SCAN:
   ```
   input: URL
   WebContentExtractor.extract(URL) → content
   ContentProcessor.analyze(content) → music_references
   SpotifyManager.search(music_references) → albums
   output: album_list
   ```

3. PLAYLIST_CREATE:
   ```
   input: album_ids, playlist_name
   PlaylistManager.create(name) → playlist_id
   foreach album_id:
     SpotifyManager.get_tracks(id) → tracks
   PlaylistManager.add_tracks(playlist_id, tracks)
   output: playlist_url
   ```

## Payment System [PAYMENT]
COMPONENTS:
- AuthService: user_management
- PaymentService: transaction_processing
- CreditService: balance_management
- UsageService: token_tracking

DATABASE_SCHEMA:
```sql
users:
  id: UUID
  email: STRING
  stripe_customer_id: STRING
  
payments:
  id: UUID
  user_id: FK(users)
  amount: FLOAT
  status: ENUM('pending','complete','failed')
  
user_credits:
  user_id: FK(users)
  balance: FLOAT
  
usage_records:
  id: UUID
  user_id: FK(users)
  tokens: INTEGER
  cost: FLOAT
```

FLOWS:
1. USER_REGISTRATION:
   ```
   input: email, password
   AuthService.validate(email, password)
   AuthService.create_user() → user
   StripeAPI.create_customer() → stripe_id
   CreditService.initialize(user.id)
   output: user_token
   ```

2. CREDIT_PURCHASE:
   ```
   input: user_id, amount
   StripeAPI.create_payment_intent(amount) → intent
   Frontend.show_payment_form(intent)
   on_success:
     PaymentService.record_payment(user_id, amount)
     CreditService.add_credits(user_id, amount)
   output: new_balance
   ```

3. GPT_USAGE:
   ```
   input: user_id, request
   CreditService.check_balance(user_id) → sufficient
   if sufficient:
     UsageService.estimate_cost(request) → estimated_cost
     CreditService.reserve(user_id, estimated_cost)
     GPT.process(request) → result, actual_cost
     UsageService.record(user_id, actual_cost)
     CreditService.finalize(user_id, actual_cost)
   output: gpt_result
   ```

## System Integration [CORE+PAYMENT]
INTERACTION_POINTS:
1. GPT_REQUEST_FLOW:
   ```
   URL_input → check_credits → process_GPT → record_usage → return_results
   ```

2. USER_ACTIONS:
   ```
   URL_scan: free
   GPT_scan: requires_credits OR user_openai_key
   Playlist_create: requires_spotify_auth
   ```

3. CREDIT_SYSTEM:
   ```
   pricing:
     token_rate: USD/1000_tokens
     minimum_balance: 1.0 USD
     auto_reload: configurable
   ```

## Technical Implementation [STACK]
```
Frontend: Flask + JavaScript
Database: PostgreSQL + SQLAlchemy
Auth: JWT + bcrypt
Payments: Stripe
APIs: Spotify, OpenAI
Migration: Alembic
```

## Environment [CONFIG]
REQUIRED_ENV_VARS:
```
SPOTIFY_*: API credentials
OPENAI_*: API key
DB_*: Database connection
STRIPE_*: Payment processing
JWT_*: Authentication
```

## Error Handling [RESILIENCE]
STRATEGIES:
1. Database: transaction_rollback
2. Payments: idempotency_keys
3. API: retry_with_backoff
4. Credits: reserve_then_adjust

## Security [PROTECTION]
MEASURES:
1. Auth: JWT_with_refresh
2. Payments: Stripe_only
3. Database: parameterized_queries
4. API_keys: env_vars_only

## Scaling [GROWTH]
CONSIDERATIONS:
1. Database: connection_pooling
2. Cache: redis_ready
3. Tasks: async_capable
4. State: session_managed 