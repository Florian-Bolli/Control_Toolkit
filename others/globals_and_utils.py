import logging
import os
from datetime import datetime
from importlib import import_module
from importlib.util import find_spec

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "0"  # all TF messages

import tensorflow as tf
from numpy.random import SFC64, Generator
from SI_Toolkit.TF.TF_Functions.Compile import Compile

LOGGING_LEVEL = logging.INFO


class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(name):
    # logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logger = logging.getLogger(name)
    logger.setLevel(LOGGING_LEVEL)
    # create console handler
    ch = logging.StreamHandler()
    ch.setFormatter(CustomFormatter())
    logger.addHandler(ch)
    return logger


log = get_logger(__name__)


def create_rng(id: str, seed: str, use_tf: bool = False):
    if seed == "None":
        log.info(f"{id}: No random seed specified. Seeding with datetime.")
        seed = int(
            (datetime.now() - datetime(1970, 1, 1)).total_seconds() * 1000.0
        )  # Fully random

    if use_tf:
        return tf.random.Generator.from_seed(seed=seed)
    else:
        return Generator(SFC64(seed=seed))


def import_controller_by_name(controller_full_name: str) -> type:
    """Search for the specified controller name in the following order:
    1) Control_Toolkit_ASF/Controllers/
    2) Control_Toolkit/Controllers/

    :param controller_full_name: The controller to import by full name
    :type controller_full_name: str
    :return: The controller class
    :rtype: type[template_controller]
    """
    asf_name = f"Control_Toolkit_ASF.Controllers.{controller_full_name}"
    toolkit_name = f"Control_Toolkit.Controllers.{controller_full_name}"
    if find_spec(asf_name) is not None:
        log.info(f"Importing controller {controller_full_name} from Control_Toolkit_ASF")
        return getattr(import_module(asf_name), controller_full_name)
    elif find_spec(toolkit_name) is not None:
        log.info(f"Importing controller {controller_full_name} from Control_Toolkit")
        return getattr(import_module(toolkit_name), controller_full_name)
    else:
        raise ValueError(f"Cannot find controller with full name {controller_full_name} in Control Toolkit or ASF files.")
    
