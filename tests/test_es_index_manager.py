"""Testing for Elasticsearch Index Manager."""

import pytest
from elasticsearch.utils import get_merged_config
from elasticsearch7 import ElasticsearchException
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.elasticsearch.config_flow import build_full_config
from custom_components.elasticsearch.const import (
    CONF_INDEX_MODE,
    DATASTREAM_METRICS_ILM_POLICY_NAME,
    DATASTREAM_METRICS_INDEX_TEMPLATE_NAME,
    DOMAIN,
    INDEX_MODE_DATASTREAM,
    INDEX_MODE_LEGACY,
    LEGACY_TEMPLATE_NAME,
)
from custom_components.elasticsearch.errors import ElasticException
from custom_components.elasticsearch.es_gateway import ElasticsearchGateway
from custom_components.elasticsearch.es_index_manager import IndexManager
from tests.test_util.aioclient_mock_utils import (
    extract_es_ilm_template_requests,
    extract_es_legacy_index_template_requests,
    extract_es_modern_index_template_requests,
)
from tests.test_util.es_startup_mocks import mock_es_initialization


async def get_index_manager(
    hass: HomeAssistant,
    es_url: str,
    index_mode: str,
):
    """Return a configured IndexManager."""
    config = build_full_config({"url": es_url, CONF_INDEX_MODE: index_mode})

    mock_entry = MockConfigEntry(
        unique_id="test_index_manager",
        domain=DOMAIN,
        version=4,
        data=config,
        title="ES Config",
    )

    gateway = ElasticsearchGateway(config_entry=mock_entry)

    await gateway.async_init()

    index_manager = IndexManager(hass, get_merged_config(mock_entry), gateway)

    yield index_manager

    await gateway.async_stop_gateway()


@pytest.mark.asyncio
async def test_esserverless_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_serverless_version=True,
        mock_modern_template_setup=True,
    )

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 0


@pytest.mark.asyncio
async def test_es811_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v811_cluster=True,
        mock_ilm_setup=True,
        mock_modern_template_setup=True,
    )

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    request = modern_template_requests[0].data[0]
    template = request["template"]
    template_settings = template["settings"]

    # Using DLM
    assert "lifecycle" in template
    assert template["lifecycle"]["data_retention"] == "365d"

    # Using ignore_missing_component_templates
    assert "ignore_missing_component_templates" in request
    assert "composed_of" in request

    # Using TSDS
    assert "index.mode" in template_settings
    assert template_settings["index.mode"] == "time_series"

    # Not Using ILM
    assert "index.lifecycle.name" not in template_settings

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    ilm_requests = extract_es_ilm_template_requests(es_aioclient_mock)

    assert len(ilm_requests) == 0


@pytest.mark.asyncio
async def test_es88_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v88_cluster=True,
        mock_ilm_setup=True,
        ilm_policy_name=DATASTREAM_METRICS_ILM_POLICY_NAME,
        mock_modern_template_setup=True,
    )

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    request = modern_template_requests[0].data[0]
    template = request["template"]
    template_settings = template["settings"]

    # Not using DLM
    assert "lifecycle" not in template

    # Using ignore_missing_component_templates
    assert "ignore_missing_component_templates" in request
    assert "composed_of" in request

    # Using TSDS
    assert "index.mode" in template_settings
    assert template_settings["index.mode"] == "time_series"

    # Using ILM
    assert "index.lifecycle.name" in template_settings
    assert (
        template_settings["index.lifecycle.name"] == DATASTREAM_METRICS_ILM_POLICY_NAME
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    ilm_requests = extract_es_ilm_template_requests(es_aioclient_mock)

    ilm_policy = ilm_requests[0].data[0]

    assert (
        "max_primary_shard_size"
        in ilm_policy["policy"]["phases"]["hot"]["actions"]["rollover"]
    )

    assert len(ilm_requests) == 1


@pytest.mark.asyncio
async def test_es80_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v80_cluster=True,
        mock_ilm_setup=True,
        ilm_policy_name=DATASTREAM_METRICS_ILM_POLICY_NAME,
        mock_modern_template_setup=True,
    )

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    request = modern_template_requests[0].data[0]
    template = request["template"]
    template_settings = template["settings"]

    # Not using DLM
    assert "lifecycle" not in template

    # Not using ignore_missing_component_templates
    assert "ignore_missing_component_templates" not in request
    assert "composed_of" not in request

    # Not using TSDS
    assert "index.mode" not in template_settings

    # Using ILM
    assert "index.lifecycle.name" in template_settings
    assert (
        template_settings["index.lifecycle.name"] == DATASTREAM_METRICS_ILM_POLICY_NAME
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    ilm_requests = extract_es_ilm_template_requests(es_aioclient_mock)

    ilm_policy = ilm_requests[0].data[0]

    assert (
        "max_primary_shard_size"
        in ilm_policy["policy"]["phases"]["hot"]["actions"]["rollover"]
    )

    assert len(ilm_requests) == 1


@pytest.mark.asyncio
async def test_es717_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v717_cluster=True,
        mock_ilm_setup=True,
        ilm_policy_name=DATASTREAM_METRICS_ILM_POLICY_NAME,
        mock_modern_template_setup=True,
    )

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    request = modern_template_requests[0].data[0]
    template = request["template"]
    template_settings = template["settings"]

    # Not using DLM
    assert "lifecycle" not in template

    # Not using ignore_missing_component_templates
    assert "ignore_missing_component_templates" not in request
    assert "composed_of" not in request

    # Not using TSDS
    assert "index.mode" not in template_settings

    # Using ILM
    assert "index.lifecycle.name" in template_settings
    assert (
        template_settings["index.lifecycle.name"] == DATASTREAM_METRICS_ILM_POLICY_NAME
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    ilm_requests = extract_es_ilm_template_requests(es_aioclient_mock)

    ilm_policy = ilm_requests[0].data[0]

    assert (
        "max_primary_shard_size"
        in ilm_policy["policy"]["phases"]["hot"]["actions"]["rollover"]
    )

    assert len(ilm_requests) == 1


@pytest.mark.asyncio
async def test_es711_datastream_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v711_cluster=True,
        mock_ilm_setup=True,
        ilm_policy_name=DATASTREAM_METRICS_ILM_POLICY_NAME,
        mock_modern_template_setup=True,
    )

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    request = modern_template_requests[0].data[0]
    template = request["template"]
    template_settings = template["settings"]

    # Not using DLM
    assert "lifecycle" not in template

    # Not using ignore_missing_component_templates
    assert "ignore_missing_component_templates" not in request
    assert "composed_of" not in request

    # Not using TSDS
    assert "index.mode" not in template_settings

    # Using ILM
    assert "index.lifecycle.name" in template_settings
    assert (
        template_settings["index.lifecycle.name"] == DATASTREAM_METRICS_ILM_POLICY_NAME
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    ilm_requests = extract_es_ilm_template_requests(es_aioclient_mock)

    ilm_policy = ilm_requests[0].data[0]

    assert (
        "max_primary_shard_size"
        not in ilm_policy["policy"]["phases"]["hot"]["actions"]["rollover"]
    )

    assert len(ilm_requests) == 1


@pytest.mark.asyncio
async def test_fail_esserverless_legacy_index_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for failure of legacy index mode setup on serverless."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_serverless_version=True,
        mock_template_setup=True,
    )

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    legacy_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_LEGACY
    ).__anext__()

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    with pytest.raises(ElasticException):
        await legacy_index_manager.async_setup()


@pytest.mark.asyncio
async def test_es88_legacy_index_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v88_cluster=True,
        mock_template_setup=True,
    )

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    legacy_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_LEGACY
    ).__anext__()

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    await legacy_index_manager.async_setup()

    legacy_template_requests = extract_es_legacy_index_template_requests(
        es_aioclient_mock
    )

    assert len(legacy_template_requests) == 1

    assert legacy_template_requests[0].url.path == "/_template/" + LEGACY_TEMPLATE_NAME

    assert legacy_template_requests[0].method == "PUT"

    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 1


async def test_es711_legacy_index_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_template_setup=True,
    )

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    legacy_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_LEGACY
    ).__anext__()

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    await legacy_index_manager.async_setup()

    legacy_template_requests = extract_es_legacy_index_template_requests(
        es_aioclient_mock
    )

    assert len(legacy_template_requests) == 1

    assert legacy_template_requests[0].url.path == "/_template/" + LEGACY_TEMPLATE_NAME

    assert legacy_template_requests[0].method == "PUT"

    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 1


async def test_es711_invalid_index_setup(
    hass: HomeAssistant,
    es_aioclient_mock: AiohttpClientMocker,
):
    """Test for modern index mode setup."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_template_setup=True,
    )

    with pytest.raises(ElasticException):
        await get_index_manager(
            hass=hass, es_url=es_url, index_mode="invalid"
        ).__anext__()


@pytest.mark.asyncio
async def test_modern_index_mode_update(
    hass: HomeAssistant, es_aioclient_mock: AiohttpClientMocker
):
    """Test for modern index mode update."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v811_cluster=True,
        mock_modern_template_setup=False,
        mock_modern_template_update=True,
    )

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    await modern_index_manager.async_setup()

    # In Datastream mode the template is updated each time the manager is initialized
    modern_template_requests = extract_es_modern_index_template_requests(
        es_aioclient_mock
    )

    assert len(modern_template_requests) == 1

    assert (
        modern_template_requests[0].url.path
        == "/_index_template/" + DATASTREAM_METRICS_INDEX_TEMPLATE_NAME
    )

    assert modern_template_requests[0].method == "PUT"

    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 0


@pytest.mark.asyncio
async def test_modern_index_mode_error(
    hass: HomeAssistant, es_aioclient_mock: AiohttpClientMocker
):
    """Test for modern index mode update."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v811_cluster=True,
        mock_modern_template_setup=False,
        mock_modern_template_error=True,
    )

    modern_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_DATASTREAM
    ).__anext__()

    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 0

    with pytest.raises(ElasticsearchException):
        await modern_index_manager.async_setup()

    # ILM setup occurs before our index template creation error
    assert len(extract_es_modern_index_template_requests(es_aioclient_mock)) == 1


async def test_legacy_index_mode_update(
    hass: HomeAssistant, es_aioclient_mock: AiohttpClientMocker
):
    """Test for modern index mode update."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v88_cluster=True,
        mock_template_setup=False,
        mock_template_update=True,
    )

    legacy_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_LEGACY
    ).__anext__()

    # Index Templates do not get updated in Legacy mode but ILM templates do

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    await legacy_index_manager.async_setup()

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 1


async def test_legacy_index_mode_error(
    hass: HomeAssistant, es_aioclient_mock: AiohttpClientMocker
):
    """Test for modern index mode update."""

    es_url = "http://localhost:9200"

    mock_es_initialization(
        es_aioclient_mock,
        es_url,
        mock_v88_cluster=True,
        mock_template_setup=False,
        mock_template_error=True,
    )

    legacy_index_manager = await get_index_manager(
        hass=hass, es_url=es_url, index_mode=INDEX_MODE_LEGACY
    ).__anext__()

    # Index Templates do not get updated in Legacy mode but ILM templates do

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 0

    with pytest.raises(ElasticException):
        await legacy_index_manager.async_setup()

    assert len(extract_es_legacy_index_template_requests(es_aioclient_mock)) == 1

    # ILM Setup occurs before the index creation fails
    assert len(extract_es_ilm_template_requests(es_aioclient_mock)) == 1
