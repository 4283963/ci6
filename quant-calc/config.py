import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    
    lookback_window: int = 200
    calc_interval: float = 0.1
    risk_free_rate: float = 0.02
    confidence_level: float = 0.95
    
    symbols: list = None

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = [
                "BTC", "ETH", "SOL", "BNB", "XRP",
                "ADA", "DOGE", "DOT", "AVAX", "LINK"
            ]


def load_config() -> Config:
    return Config(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        redis_db=int(os.getenv("REDIS_DB", 0)),
        redis_password=os.getenv("REDIS_PASSWORD", ""),
        lookback_window=int(os.getenv("LOOKBACK_WINDOW", 200)),
        calc_interval=float(os.getenv("CALC_INTERVAL", 0.1)),
        risk_free_rate=float(os.getenv("RISK_FREE_RATE", 0.02)),
        confidence_level=float(os.getenv("CONFIDENCE_LEVEL", 0.95)),
    )
