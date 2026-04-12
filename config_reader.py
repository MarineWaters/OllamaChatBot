from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

env_file_path = '.env' if os.path.exists('.env') else None

class Settings(BaseSettings):
    bot_token: SecretStr
    openrouter_key: SecretStr
    api: SecretStr
    url: SecretStr
    
    model_config = SettingsConfigDict(
        env_file=env_file_path, 
        env_file_encoding='utf-8',
        case_sensitive=False
    )

config = Settings()
