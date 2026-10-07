from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "data/traverse.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
