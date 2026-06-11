from dev_time_agent import service_name


def test_service_name_identifies_agent_runtime() -> None:
    assert service_name() == "dev-time-agent"
