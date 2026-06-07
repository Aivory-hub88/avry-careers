"""Configuration module for AVRY Careers Service"""
import os
import sys
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ValidationError, ConfigDict
from dotenv import load_dotenv

# Load unified .env from project root (covers all services)
load_dotenv(".env.local")  # legacy — takes precedence if present
load_dotenv(".env")        # unified config


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Allow extra fields to be ignored (for shared .env across services)
    model_config = ConfigDict(extra='ignore')

    # Server configuration
    app_name: str = "AVRY Careers Service"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8090

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/aivery"

    # JWT Authentication
    supabase_jwt_secret: str = ""
    jwt_secret: str = ""  # Legacy fallback

    # Encryption key for PII and CV files (AES-256)
    encryption_key: str = ""

    # SMTP settings for applicant communication
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: str = "careers@aivory.id"

    # CORS configuration
    cors_origins: list[str] = ["*"]


# Global settings instance
try:
    settings = Settings()
    print(f"✓ Configuration loaded successfully")
    print(f"  - App: {settings.app_name} v{settings.app_version}")
    print(f"  - Port: {settings.port}")
    print(f"  - Encryption: {'Configured' if settings.encryption_key else 'Not configured'}")
    print(f"  - SMTP: {'Configured' if settings.smtp_user else 'Not configured'}")
except ValidationError as e:
    print(f"✗ Configuration validation failed:")
    for error in e.errors():
        field = '.'.join(str(loc) for loc in error['loc'])
        print(f"  - {field}: {error['msg']}")
    print("\nPlease check your .env file and ensure all required variables are set correctly.")
    sys.exit(1)
except Exception as e:
    print(f"✗ Failed to load configuration: {str(e)}")
    sys.exit(1)
