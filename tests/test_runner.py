from dev_time_agent.runner import RuntimeConfig, load_runtime_config


def test_load_runtime_config_uses_environment_values() -> None:
    config = load_runtime_config(
        {
            "DEV_TIME_SERVER_INTERNAL_BASE_URL": "http://127.0.0.1:18080",
            "DEV_TIME_AGENT_POLL_INTERVAL_SECONDS": "0.25",
        }
    )

    assert config == RuntimeConfig(
        server_internal_base_url="http://127.0.0.1:18080",
        poll_interval_seconds=0.25,
    )


def test_load_runtime_config_uses_local_defaults() -> None:
    config = load_runtime_config({})

    assert config == RuntimeConfig(
        server_internal_base_url="http://localhost:8080",
        poll_interval_seconds=5.0,
    )
