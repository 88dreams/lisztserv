import secrets
import base64

def generate_jwt_key():
    """Generate a secure random key for JWT signing."""
    # Generate 32 random bytes and encode them in base64
    random_bytes = secrets.token_bytes(32)
    jwt_key = base64.b64encode(random_bytes).decode('utf-8')
    return jwt_key

if __name__ == "__main__":
    key = generate_jwt_key()
    print("\nGenerated JWT Secret Key:")
    print("------------------------")
    print(key)
    print("\nAdd this to your .env file as:")
    print(f'JWT_SECRET_KEY="{key}"') 