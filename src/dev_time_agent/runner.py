import os
import time
from dataclasses import dataclass
from collections.abc import Mapping

from dev_time_agent.client import HTTPServerClient
from dev_time_agent.worker import process_next_agent_job


@dataclass(frozen=True)
class RuntimeConfig:
    server_internal_base_url: str
    poll_interval_seconds: float


def load_runtime_config(environment: Mapping[str, str] | None = None) -> RuntimeConfig:
    loaded_environment = environment or os.environ
    return RuntimeConfig(
        server_internal_base_url=loaded_environment.get(
            "DEV_TIME_SERVER_INTERNAL_BASE_URL",
            "http://localhost:8080",
        ),
        poll_interval_seconds=float(
            loaded_environment.get("DEV_TIME_AGENT_POLL_INTERVAL_SECONDS", "5"),
        ),
    )


def run_forever(config: RuntimeConfig | None = None) -> None:
    loaded_config = config or load_runtime_config()
    server_client = HTTPServerClient(loaded_config.server_internal_base_url)

    while True:
        processed = process_next_agent_job(server_client)
        if not processed:
            time.sleep(loaded_config.poll_interval_seconds)
