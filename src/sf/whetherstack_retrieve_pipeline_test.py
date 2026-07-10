import logging.config
import json
import os
import sys
import hydra
from typing import Dict, Any
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

from sf.use_cases.whether_test_handler import (
    DataRetrieveHandler,
    WhetherWrapperManager,
)


def get_temperature(cfg: DictConfig, logger: logging.Logger) -> Dict[str, Any]:
    """This function runs the tg list extraction from plannet."""
    data_retrieve_manager = WhetherWrapperManager()
    handler = DataRetrieveHandler(client_settings=cfg, logger=logger)
    data_retrieve_manager.handler = handler

    # The pipeline returns a JSON string, which we parse for the MCP response
    result_json = data_retrieve_manager.run_data_retrieve_pipeline()
    result = json.loads(result_json) if result_json else {}

    return {
        "status": "success",
        "data": {"result": result},
    }


def _run(cfg: DictConfig) -> Dict[str, Any]:
    """Entrypoint for the weather logic.

    Note: ne_id is not required as the location is currently hardcoded in the handler.
    """
    logger = logging.getLogger(__name__)

    return get_temperature(
        cfg=cfg,
        logger=logger,
    )


def mcp_entrypoint() -> Dict[str, Any]:
    """Retrieves current weather and temperature data from the Weatherstack API.

    This tool currently retrieves data for New York. It requires the
    PROD_WHETHER_ACCESS_TOKEN environment variable to be set.

    Returns:
        - A dictionary containing the location name and current temperature.
    """
    config_path = os.environ.get("CONFPATH")
    if not config_path:
        return {
            "status": "error",
            "data": {"report": "CONFPATH is not set"},
        }
    with initialize_config_dir(config_dir=config_path, version_base=None):
        cfg = compose(config_name="whether_wrapper_config", overrides=sys.argv[1:])
    return _run(cfg)


@hydra.main(
    version_base=None,
    config_path=os.environ.get("CONFPATH"),
    config_name="whether_wrapper_config",
)  # type: ignore
def main(cfg: DictConfig) -> Dict[str, Any]:
    """Main function to run the kit based tg list report."""
    return _run(cfg)


if __name__ == "__main__":
    main()
