#!/usr/bin/env python

import dash_bootstrap_components as dbc

import astropy.units as u
from dataclasses import dataclass, field
from pathlib import Path
from schema import Or
from typing import Union

from tollan.utils.dataclass_schema import add_schema

from .. import apps_registry, get_app_config
from ...utils.common_schema import PhysicalTypeSchema, RelPathSchema


@apps_registry.register('obs_planner')
@add_schema
@dataclass
class ObsPlannerConfig():
    """The config class for the obs planner app."""

    raster_model_length_max: u.Quantity = field(
        default=3 << u.deg,
        metadata={
            'description': 'The maximum length of raster scan model.',
            'schema': PhysicalTypeSchema('angle')
            }
        )
    lissajous_model_length_max: u.Quantity = field(
        default=20 << u.arcmin,
        metadata={
            'description': 'The maximum length of lissajous model.',
            'schema': PhysicalTypeSchema('angle')
            }
        )
    t_exp_max: u.Quantity = field(
        default=1. << u.hour,
        metadata={
            'description': 'The maximum length of observation time.',
            'schema': PhysicalTypeSchema('time')
            }
        )
    site_name: str = field(
        default='lmt',
        metadata={
            'description': 'The observing site name.',
            'schema': Or("lmt", )
            }
        )
    instru_name: str = field(
        default='toltec',
        metadata={
            'description': 'The observing instrument name.',
            'schema': Or("toltec", )
            }
        )
    pointing_catalog_path: Union[None, Path] = field(
        default=None,
        metadata={
            'description': 'The catalog path containing the pointing sources.',
            'schema': Or(RelPathSchema(), None)
            }
        )
    presets_config_path: Union[None, Path] = field(
        default=None,
        metadata={
            'description': 'The YAML config file path for the presets.',
            'schema': Or(RelPathSchema(), None)
            }
        )
    title_text: str = field(
        default='Obs Planner',
        metadata={
            'description': 'The title text of the page.'
            }
        )


def DASHA_SITE():
    """The dasha site entry point.
    """
    dasha_config = get_app_config(ObsPlannerConfig).to_dict()
    dasha_config.update({
        'template': 'tolteca.web.templates.obs_planner:ObsPlanner',
        'THEME': dbc.themes.LUMEN,
        # 'ASSETS_IGNORE': 'bootstrap.*',
        # 'DEBUG': True
        })
    return {
        'extensions': [
            {
                'module': 'dasha.web.extensions.dasha',
                'config': dasha_config
                },
            ]
        }