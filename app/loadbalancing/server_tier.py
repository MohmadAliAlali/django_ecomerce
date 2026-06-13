from dataclasses import dataclass


@dataclass(frozen=True)
class ServerTier:
    name: str
    max_active_requests: int
    target_response_time_ms: int

    @classmethod
    def from_env(cls, raw: str | None) -> 'ServerTier':
        key = (raw or 'MEDIUM').strip().upper()
        tiers = {
            'SMALL': cls('SMALL', 64, 200),
            'MEDIUM': cls('MEDIUM', 128, 150),
            'MONSTER': cls('MONSTER', 256, 100),
        }
        return tiers.get(key, tiers['MEDIUM'])
