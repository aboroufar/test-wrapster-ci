import os
from logging import Logger
from typing import Optional
import json
import whetherstack_client
from omegaconf import DictConfig

from wrapster.core.rest_adapters.api_client import ApiClient
from wrapster.core.rest_adapters.configuration import ExtendedClientConfiguration
from wrapster.core.rest_adapters.rest import ApiException
from wrapster.core.utils.prometheus_client_utils import PrometheusClientMetrics


class DataRetrieveHandler:
    """DataRetrieveHandler for the vpws tracker."""

    def __init__(
        self,
        logger: Logger,
        client_settings: DictConfig,
    ):
        """Handler for the vpws tracker."""
        self.client_settings = client_settings
        self.logger = logger

    def data_retrieve_pipeline(self) -> str:
        """Run the data retrieve pipeline."""
        prometheus_metrics = PrometheusClientMetrics(
            logger=self.logger,
        )
        configuration = ExtendedClientConfiguration(
            whetherstack_client.Configuration(),
            client_settings=self.client_settings.whether_client_settings,
        )
        api_client = ApiClient(
            configuration=configuration,
            prometheus_metrics=prometheus_metrics,
            logger=self.logger,
        )
        api_instance = whetherstack_client.DefaultApi(api_client)

        api_client.stale_redis_cache_on()

        output = {
            "location": None,
            "temperature": None,
        }
        try:
            # Current Weather
            api_result = api_instance.get_current_weather(
                access_key=os.environ.get("PROD_WHETHER_ACCESS_TOKEN"),
                query="New York",
            )
            output["temperature"] = api_result.current.temperature
            output["location"] = api_result.location.name
        except ApiException as e:
            self.logger.error(
                "Exception when calling DefaultApi->get_current_weather: %s\n" % e
            )

        return json.dumps(output)


class WhetherWrapperManager:
    """WhetherWrapperManager for the vpws tracker."""

    def __init__(self) -> None:
        self._handler: Optional[DataRetrieveHandler] = None

    @property
    def handler(self) -> Optional[DataRetrieveHandler]:
        """Get the current DataRetrieveHandler instance."""
        return self._handler

    @handler.setter
    def handler(self, handler: Optional[DataRetrieveHandler]) -> None:
        """Set the DataRetrieveHandler instance."""
        self._handler = handler

    def run_data_retrieve_pipeline(self) -> Optional[str]:
        """Run the data retrieve pipeline using the handler if set."""
        if self.handler is not None:
            return self.handler.data_retrieve_pipeline()
        return None
