# LisztServ Master Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Technical Implementation](#technical-implementation)
4. [Testing Infrastructure](#testing-infrastructure)
5. [Development Guidelines](#development-guidelines)
6. [Deployment & Operations](#deployment-operations)

## Project Overview

LisztServ is a modern desktop application that helps users discover and create Spotify playlists from web content. It uses both direct URL scanning and AI-powered content analysis to find and organize music into playlists.

### Core Features
- 🎵 Web page scanning for Spotify album links
- 🤖 AI-powered music content extraction
- 📝 Automated Spotify playlist creation
- 🎨 Modern, user-friendly interface
- 🔄 Support for various music review sites and blogs

### Prerequisites
- Python 3.8 or higher
- Spotify Developer Account
- OpenAI API Key (for AI-powered scanning)
- Git (for development)

## System Architecture

### Core Components

#### Frontend Layer (`src/lisztserv/frontend/`)
- Flask-based web application
- Modern UI with responsive design
- Real-time progress updates
- Error handling and user feedback

#### Backend Services
1. **Web Content Extraction (`WebContentExtractor`)**
   - Playwright-based content extraction
   - Async operation support
   - Configurable content selectors
   - JavaScript rendering support

2. **Spotify Integration (`SpotifyManager`)**
   - OAuth authentication
   - Playlist management
   - Album and track search
   - Rate limiting and caching

3. **Content Processing (`ContentProcessor`)**
   - GPT-powered content analysis
   - Music reference extraction
   - Metadata normalization
   - Error handling and retry logic

4. **Payment System**
   - Stripe integration
   - Credit management
   - Usage tracking
   - Webhook handling

### Database Schema
```sql
users:
  id: UUID (PK)
  email: VARCHAR(255)
  password_hash: VARCHAR(255)
  stripe_customer_id: VARCHAR(255)
  created_at: TIMESTAMP
  is_active: BOOLEAN

user_credits:
  user_id: UUID (FK)
  balance: DECIMAL(10,2)
  last_updated: TIMESTAMP

usage_records:
  id: UUID (PK)
  user_id: UUID (FK)
  tokens: INTEGER
  cost: DECIMAL(10,4)
  timestamp: TIMESTAMP
  request_type: VARCHAR(50)
  metadata: JSONB
```

## Technical Implementation

### Technology Stack
- **Frontend**: Flask + JavaScript
- **Database**: PostgreSQL + SQLAlchemy
- **Authentication**: JWT + bcrypt
- **Payments**: Stripe
- **APIs**: Spotify, OpenAI
- **Migration**: Alembic

### Key Features Implementation

#### Web Page Analysis
- Content extraction with Playwright
- Configurable content selectors
- Error handling and retries
- Progress tracking

#### Spotify Integration
- OAuth flow implementation
- Playlist CRUD operations
- Track search and matching
- Rate limit handling

#### GPT Analysis
- Content understanding
- Music extraction
- Credit management
- Usage tracking

## Testing Infrastructure

### Directory Structure
```
lisztserv/tests/
├── __init__.py              # Test package initialization
├── conftest.py             # Test configuration and fixtures
├── test_api_integration.py # API integration tests
├── test_core.py           # Core functionality tests
├── test_payments.py       # Payment system tests
├── test_payment_integration.py # Payment integration tests
├── test_performance.py    # Performance tests
├── test_security.py       # Security tests
├── test_web_content_extractor.py # Web content extraction tests
```

### Test Configuration
- SQLite test database
- Mock services (Stripe, Spotify)
- Async test support
- Comprehensive fixtures

### Component Tests

#### Web Content Extractor Tests
- Content extraction verification
- Error handling
- Resource cleanup
- Mock browser interactions

#### Payment System Tests
- Stripe integration
- Credit management
- Webhook handling
- Error scenarios

#### Integration Tests
- API endpoints
- Authentication flows
- Payment processing
- Error handling

### Running Tests
```bash
# Basic test run
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=lisztserv --cov-report=html

# Specific components
pytest tests/test_payments.py
pytest -m "integration"
```

## Development Guidelines

### Code Style
- Black formatter (line length: 88)
- Google style docstrings
- Type hints
- Comprehensive error handling

### Git Workflow
- Feature branches: `feature/*`
- Bug fixes: `fix/*`
- Hotfixes: `hotfix/*`
- Commit format: `type(scope): description`

### Testing Requirements
- Minimum coverage: 80%
- Required test types:
  - Unit tests
  - Integration tests
  - API tests
  - Performance tests

## Deployment & Operations

### Requirements
- Memory: 512MB minimum
- CPU: 1vCPU minimum
- Disk: 10GB minimum

### Environment Variables
```
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
OPENAI_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
DATABASE_URL=
```

### Logging
- Application logs: `logs/spot-main-*.log`
- Spotify operations: `logs/spot-spotify-*.log`
- Debug information: `logs/spot-debug-*.log`
- GPT operations: `logs/spot-gpt-*.log`

### Monitoring
- Error tracking: Sentry
- Performance: Prometheus
- Log aggregation: Elasticsearch

### Security Measures
1. Authentication
   - JWT with refresh tokens
   - Secure password hashing
   - Rate limiting

2. Payment Security
   - Stripe for all transactions
   - Webhook signature verification
   - Idempotency keys

3. Data Protection
   - Parameterized queries
   - Input validation
   - Secure file operations

### Scaling Considerations
1. Database
   - Connection pooling
   - Query optimization
   - Index management

2. Caching
   - Redis-ready implementation
   - Configurable TTLs
   - Cache invalidation

3. Task Processing
   - Async capability
   - Queue management
   - Resource limits 