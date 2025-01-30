# LISZTSERV_SYSTEM_SPECIFICATION

## SYSTEM_METADATA
{
    "version": "0.1.0",
    "architecture": "microservices",
    "language": "python3.8+",
    "async": true,
    "database": "postgresql",
    "web_framework": "flask"
}

## CORE_COMPONENTS
{
    "WebContentExtractor": {
        "type": "service",
        "dependencies": ["playwright"],
        "input_type": "URL:str",
        "output_type": "str",
        "async": true,
        "methods": {
            "extract_content": {
                "params": {"url": "str"},
                "returns": "str",
                "errors": ["PlaywrightError", "TimeoutError"]
            }
        },
        "configuration": {
            "timeout_seconds": 30,
            "js_rendering": true,
            "content_selectors": ["article", "main", ".content"]
        }
    },
    
    "SpotifyManager": {
        "type": "service",
        "dependencies": ["spotipy"],
        "state": "singleton",
        "methods": {
            "scan_spotify_links": {
                "params": {"content": "str"},
                "returns": "List[str]",
                "regex_patterns": [
                    "spotify.com/album/([a-zA-Z0-9]{22})",
                    "spotify:album:([a-zA-Z0-9]{22})"
                ]
            },
            "get_album_info": {
                "params": {"album_id": "str"},
                "returns": "Dict[str, Any]",
                "rate_limit": "1/second"
            }
        },
        "auth_required": true,
        "auth_type": "OAuth2"
    },

    "ContentProcessor": {
        "type": "service",
        "dependencies": ["openai"],
        "methods": {
            "analyze": {
                "params": {"content": "str"},
                "returns": "List[Dict[str, str]]",
                "gpt_prompt": "Identify music albums in the following text: {content}",
                "output_schema": {
                    "artist": "str",
                    "album": "str",
                    "year": "Optional[int]"
                }
            }
        },
        "rate_limit": "3/minute",
        "cost_tracking": true
    }
}

## DATABASE_SCHEMA
{
    "tables": {
        "users": {
            "columns": {
                "id": {"type": "UUID", "primary_key": true, "default": "uuid_generate_v4()"},
                "email": {"type": "VARCHAR(255)", "unique": true, "index": true},
                "password_hash": {"type": "VARCHAR(255)", "nullable": false},
                "stripe_customer_id": {"type": "VARCHAR(255)", "unique": true},
                "created_at": {"type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
                "is_active": {"type": "BOOLEAN", "default": true}
            },
            "indexes": ["email", "stripe_customer_id"]
        },
        "user_credits": {
            "columns": {
                "user_id": {"type": "UUID", "references": "users(id)"},
                "balance": {"type": "DECIMAL(10,2)", "default": 0},
                "last_updated": {"type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"}
            },
            "constraints": ["CHECK (balance >= 0)"]
        },
        "usage_records": {
            "columns": {
                "id": {"type": "UUID", "primary_key": true},
                "user_id": {"type": "UUID", "references": "users(id)"},
                "tokens": {"type": "INTEGER", "nullable": false},
                "cost": {"type": "DECIMAL(10,4)", "nullable": false},
                "timestamp": {"type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
                "request_type": {"type": "VARCHAR(50)"},
                "metadata": {"type": "JSONB"}
            }
        }
    }
}

## API_ENDPOINTS
{
    "/api/scan-url": {
        "method": "POST",
        "auth_required": false,
        "rate_limit": "10/minute",
        "request_schema": {
            "url": "str:required"
        },
        "response_schema": {
            "status": "str:enum[processing,complete,error]",
            "albums": "List[Album]"
        }
    },
    "/api/scan-gpt": {
        "method": "POST",
        "auth_required": true,
        "credit_check": true,
        "request_schema": {
            "url": "str:required",
            "scan_type": "str:enum[deep,quick]"
        },
        "response_schema": {
            "status": "str",
            "albums": "List[Album]",
            "credits_used": "float",
            "credits_remaining": "float"
        }
    }
}

## PAYMENT_FLOWS
{
    "credit_purchase": {
        "steps": [
            {
                "service": "PaymentService",
                "method": "create_payment_intent",
                "input": {"amount": "float", "currency": "str"},
                "output": "stripe.PaymentIntent"
            },
            {
                "service": "StripeWebhook",
                "event": "payment_intent.succeeded",
                "handler": "CreditService.add_credits",
                "idempotency": true
            }
        ],
        "error_handling": {
            "payment_failed": "revert_credit_reservation",
            "network_error": "retry_with_exponential_backoff"
        }
    }
}

## ERROR_HANDLING
{
    "global_handlers": {
        "DatabaseError": {
            "action": "rollback_transaction",
            "log_level": "ERROR",
            "retry_count": 3
        },
        "APIError": {
            "action": "exponential_backoff",
            "max_retries": 5,
            "initial_delay": 1
        }
    },
    "monitoring": {
        "error_tracking": "sentry",
        "performance_tracking": "prometheus",
        "log_aggregation": "elasticsearch"
    }
}

## ASYNC_PATTERNS
{
    "task_queues": {
        "gpt_processing": {
            "type": "high_priority",
            "max_concurrent": 5
        },
        "url_scanning": {
            "type": "medium_priority",
            "max_concurrent": 10
        }
    },
    "websocket_events": {
        "scan_progress": {
            "schema": {
                "status": "str",
                "progress": "int",
                "message": "str"
            }
        }
    }
}

## DEVELOPMENT_GUIDELINES
{
    "code_style": {
        "formatter": "black",
        "line_length": 88,
        "docstring_style": "google"
    },
    "testing": {
        "framework": "pytest",
        "coverage_minimum": 80,
        "required_test_types": [
            "unit",
            "integration",
            "api"
        ]
    },
    "git": {
        "branch_prefix": {
            "feature": "feature/",
            "bugfix": "fix/",
            "hotfix": "hotfix/"
        },
        "commit_format": "type(scope): description"
    }
}

## DEPLOYMENT
{
    "requirements": {
        "memory_minimum": "512MB",
        "cpu_minimum": "1vCPU",
        "disk_space": "10GB"
    },
    "environment_vars": {
        "required": [
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "OPENAI_API_KEY",
            "DATABASE_URL",
            "STRIPE_SECRET_KEY",
            "JWT_SECRET_KEY"
        ],
        "optional": [
            "LOG_LEVEL",
            "SENTRY_DSN",
            "REDIS_URL"
        ]
    },
    "health_checks": {
        "endpoints": ["/health", "/ready"],
        "metrics": ["/metrics"],
        "interval": "30s"
    }
}

## SECURITY_SPECIFICATIONS
{
    "authentication": {
        "jwt": {
            "algorithm": "HS256",
            "token_lifetime": "30m",
            "refresh_token_lifetime": "7d"
        },
        "password_requirements": {
            "min_length": 8,
            "require_special": true,
            "require_numbers": true
        }
    },
    "rate_limiting": {
        "default": "100/hour",
        "api": {
            "auth": "30/minute",
            "scan": "10/minute",
            "gpt": "3/minute"
        }
    }
} 