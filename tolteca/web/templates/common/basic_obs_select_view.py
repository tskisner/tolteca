#! /usr/bin/env python


from dasha.web.templates import ComponentTemplate
from dasha.web.templates.collapsecontent import CollapseContent
import dash_html_components as html
from ...tasks.dbrt import dbrt
import dash_bootstrap_components as dbc
import dash_core_components as dcc
from dash.dependencies import Output, Input
from dasha.web.extensions.db import dataframe_from_db
from tollan.utils.log import get_logger
from dash_table import DataTable
import dash
from sqlalchemy import select
import networkx as nx
import json
import dash_cytoscape as cyto
import cachetools
import functools
from tolteca.datamodels.toltec import BasicObsData, BasicObsDataset


cyto.load_extra_layouts()


@functools.lru_cache(maxsize=None)
def get_bod(filepath):
    return BasicObsData(filepath)


@cachetools.func.ttl_cache(maxsize=1, ttl=1)
def query_raw_obs():

    logger = get_logger()
    t = dbrt['tolteca'].tables
    session = dbrt['tolteca'].session
    df_raw_obs = dataframe_from_db(
            select(
                [
                    t['dp_raw_obs'].c.pk,
                    t['data_prod_type'].c.label.label('dp_type'),
                    t['dp_raw_obs_type'].c.label.label('raw_obs_type'),
                    t['dp_raw_obs_master'].c.label.label('raw_obs_master')
                    ]
                + [
                    c for c in t['dp_raw_obs'].columns
                    if not c.name.endswith('pk')]
                + [
                    c for c in t['data_prod'].columns
                    if not c.name.endswith('pk')]
                + [
                    c for c in t['dpa_raw_obs_sweep_obs'].columns
                    if c.name not in ['pk', 'dp_raw_obs_pk']]
                + [
                    c for c in t['dpa_basic_reduced_obs_raw_obs'].columns
                    if c.name not in ['pk', 'dp_raw_obs_pk']]
                ).select_from(
                    t['dp_raw_obs']
                    .join(
                        t['dpa_raw_obs_sweep_obs'],
                        isouter=True,
                        onclause=(
                            t['dpa_raw_obs_sweep_obs'].c.dp_raw_obs_pk
                            == t['dp_raw_obs'].c.pk
                            )
                        )
                    .join(
                        t['dpa_basic_reduced_obs_raw_obs'],
                        isouter=True,
                        )
                    .join(t['data_prod'])
                    .join(t['data_prod_type'])
                    .join(t['dp_raw_obs_type'])
                    .join(t['dp_raw_obs_master'])
                ),
            session=session)
    # the pk columns needs to be in int, because when there is null
    # the automatic type is float
    for col in df_raw_obs.columns:
        if col.endswith('_pk') or col == 'pk':
            df_raw_obs[col] = df_raw_obs[col].fillna(-1.).astype(int)
    df_raw_obs['_roaches'] = df_raw_obs['source'].apply(
            lambda s: [int(i['key'][len('toltec'):]) for i in s['sources']])
    df_raw_obs['roaches'] = df_raw_obs['_roaches'].apply(
            lambda v: ','.join(map(str, v)))
    df_raw_obs.set_index('pk', drop=False, inplace=True)
    logger.debug(f"get {len(df_raw_obs)} entries from dp_raw_obs")
    logger.debug(f"dtypes: {df_raw_obs.dtypes}")
    return df_raw_obs


def get_calgroups(df_raw_obs):

    logger = get_logger()
    # create a list of connected components
    # each is a calgroup
    has_cal = df_raw_obs['dp_sweep_obs_pk'] > 0
    dg = nx.DiGraph()
    dg.add_edges_from(zip(
            df_raw_obs['dp_sweep_obs_pk'][has_cal], df_raw_obs['pk'][has_cal]))
    cc = list(nx.weakly_connected_components(dg))
    logger.debug(f'found {len(cc)} calgroups: {cc}')
    return cc


class BasicObsSelectView(ComponentTemplate):
    """This is a view that allow one to browse basic obs data.

    """
    _component_cls = html.Div

    logger = get_logger()

    def __init__(self, *args, file_search_paths=None, **kwargs):
        super().__init__(*args, **kwargs)
        # these paths are used to construct data file store objects
        # to locate the files.
        self._file_search_paths = file_search_paths

    def setup_layout(self, app):

        container = self
        # control_section, control_graph_section = container.grid(2, 1)
        # control_section.width = 3
        # control_graph_section.width = 9
        # ctx = {
        #         'control_graph_section': control_graph_section
        #         }

        control_section = container
        calgroup_selection_container, dataitem_selection_container = \
            control_section.grid(2, 1)

        ctx = self._setup_calgroup_selection(
                app, calgroup_selection_container, {})
        ctx = self._setup_dataitem_selection(
                app, dataitem_selection_container, ctx)

        super().setup_layout(app)
        self._ctx = ctx

    @property
    def ctx(self):
        """A dict that contains various related objects.
        """
        return getattr(self, '_ctx', None)

    @property
    def select_inputs(self):
        ctx = self.ctx
        if ctx is None:
            raise ValueError(
                    "setup_layout has to be called first")
        return [
                    Input(ctx['dataitem_select_drp'].id, 'value'),
                    Input(ctx['network_select_drp'].id, 'value'),
                    ]

    @staticmethod
    def bods_from_select_inputs(dataitem_value, network_value):
        """Return basic obs dataset from the selected items.

        This is to be used in user defined callbacks.
        """
        logger = get_logger()

        if dataitem_value is None or network_value is None:
            logger.debug("no update")
            raise dash.exceptions.PreventUpdate
        logger.debug(
                f"update bod with {dataitem_value} {network_value}")

        df_raw_obs = query_raw_obs()
        raw_obs_pks = dataitem_value
        df_raw_obs = df_raw_obs.loc[raw_obs_pks]

        nw = network_value
        bods = [get_bod(r.source['sources'][nw]['url']) for
                r in df_raw_obs.itertuples()]
        bods = BasicObsDataset(bod_list=bods)
        return bods

    def _setup_calgroup_selection(self, app, container, ctx):

        select_container, error_container = container.grid(2, 1)

        select_container_form = select_container.child(dbc.Form, inline=True)
        # calgroup_select_igrp = select_container_form.child(
        #             dbc.InputGroup, size='sm', className='w-auto mr-2')
        # calgroup_select_igrp.child(
        #         dbc.InputGroupAddon(
        #             "Select Cal Group", addon_type="prepend"))
        # calgroup_select_drp = calgroup_select_igrp.child(
        #         dbc.Select)
        calgroup_select_drp = select_container_form.child(
                dcc.Dropdown,
                placeholder="Select cal group",
                style={
                    'min-width': '240px'
                    },
                className='mr-2'
                )
        calgroup_refresh_btn = select_container_form.child(
                    dbc.Button, 'Refresh', color='primary', className='my-2',
                    size='sm'
                    )
        details_container = select_container_form.child(
                        CollapseContent(button_text='Details ...')).content
        details_container.parent = container
        df_raw_obs_dt = details_container.child(
                DataTable,
                # style_table={'overflowX': 'scroll'},
                page_action='native',
                page_current=0,
                page_size=10,
                style_table={
                    'overflowX': 'auto',
                    'width': '100%',
                    # 'overflowY': 'auto',
                    # 'height': '25vh',
                    },
                )

        @app.callback(
                [
                    Output(calgroup_select_drp.id, 'options'),
                    Output(df_raw_obs_dt.id, 'columns'),
                    Output(df_raw_obs_dt.id, 'data'),
                    Output(error_container.id, 'children'),
                    ],
                [
                    Input(calgroup_refresh_btn.id, 'n_clicks'),
                    ],
                )
        def update_calgroup(n_clicks):
            self.logger.debug("update calgroup")
            try:
                df_raw_obs = query_raw_obs()
            except Exception as e:
                self.logger.debug(f"error query db: {e}", exc_info=True)
                error_notify = dbc.Alert(
                        f'Query failed: {e.__class__.__name__}')
                return (dash.no_update, ) * 3 + (error_notify, )
            use_cols = [
                    c for c in df_raw_obs.columns
                    if c not in ['source', 'source_url']
                    ]
            df = df_raw_obs.reindex(columns=use_cols)
            cols = [{'label': c, 'id': c} for c in df.columns]
            data = df.to_dict('record')
            # make cal group options

            def make_option(g):
                g = list(g)
                n = len(g)
                c = df[df.index.isin(g)]
                c = c.sort_values(
                        by=['obsnum', 'subobsnum', 'scannum'])
                r = c.iloc[0]
                r1 = c.iloc[-1]
                label = f'{r["obsnum"]} - {r1["obsnum"]} ({n})'
                value = json.dumps(g)
                return {'label': label, 'value': value}

            calgroups = get_calgroups(df_raw_obs)
            options = list(map(make_option, calgroups))
            return options, cols, data, ""

        ctx['calgroup_select_drp'] = calgroup_select_drp
        return ctx

    def _setup_dataitem_selection(self, app, container, ctx):

        control_container, assoc_view_graph_container = container.grid(1, 2)
        control_container.width = 4
        assoc_view_graph_container.width = 8
        dataitem_select_container, network_select_container, error_container =\
            control_container.grid(3, 1)
        dataitem_select_container_form = dataitem_select_container.child(
                dbc.Form, inline=True)
        dataitem_select_drp = dataitem_select_container_form.child(
            dcc.Dropdown,
            placeholder="Select obs",
            multi=True,
            style={
                'min-width': '240px'
                },
            )
        dataitem_details_container = dataitem_select_container_form.child(
                        CollapseContent(button_text='Details ...')).content
        dataitem_details_container.parent = container
        dataitem_details_container.className = 'mb-4'  # fix the bottom margin
        df_raw_obs_dt = dataitem_details_container.child(
                DataTable,
                # style_table={'overflowX': 'scroll'},
                page_action='native',
                page_current=0,
                page_size=20,
                style_table={
                    'overflowX': 'auto',
                    'width': '100%',
                    # 'overflowY': 'auto',
                    # 'height': '25vh',
                    },
                )

        # assoc_view_graph_collapse = assoc_view_graph_container.child(
        #                 CollapseContent(button_text='Select on graph ...')
        #                 ).content
        assoc_view_graph_collapse = assoc_view_graph_container
        assoc_view_ctx = self._setup_assoc_view(
                app, assoc_view_graph_collapse)
        assoc_view_graph = assoc_view_ctx['assoc_view_graph']
        assoc_view_graph_legend = assoc_view_ctx['assoc_view_graph_legend']

        # network_options_store = container.child(dcc.Store, data=None)
        # network_select_ctx = self._setup_network_selection(
        #         app, container.child(dbc.Row).child(dbc.Col),
        #         {
        #             'network_options_store': network_options_store
        #             }
        #         )
        network_select_container_form = network_select_container.child(
                dbc.Form, inline=True)
        network_select_container.className = 'mt-1'  # text-monospace'
        network_select_ctx = self._setup_network_selection_simple(
                app, network_select_container_form, {})
        network_select_drp = network_select_ctx['network_select_drp']
        network_details_container = network_select_container_form.child(
                        CollapseContent(button_text='Details ...')).content
        network_details_container.parent = container
        network_details_container.className = 'mb-4'  # fix the bottom margin
        df_bod_dt = network_details_container.child(
                DataTable,
                # style_table={'overflowX': 'scroll'},
                page_action='native',
                page_current=0,
                page_size=20,
                style_table={
                    'overflowX': 'auto',
                    'width': '100%',
                    # 'overflowY': 'auto',
                    # 'height': '25vh',
                    },
                )

        @app.callback(
                Output(dataitem_select_drp.id, 'value'),
                [
                    Input(assoc_view_graph.id, 'selectedNodeData'),
                    ]
                )
        def update_from_assoc_graph_view(data):
            if not data:
                return dash.no_update
            return [int(d['id']) for d in data]

        assoc_view_graph.stylesheet = [
            {
                'selector': 'node',
                'style': {
                    'content': 'data(label)'
                    },
                },
            {
                'selector': ':selected',
                "style": {
                    "border-width": 2,
                    "border-color": "#222222",
                    "border-opacity": 1,
                    }
                }
            ]
        dispatch_type_color = {
                'TUNE': '#ccaaff',
                'Targ': '#aaaaff',
                'Timestream': '#99ccff'
                }
        type_stylesheet = [
            {
                'selector': f'[type = "{t}"]',
                'style': {
                    'background-color': c,
                    },
                }
            for t, c in dispatch_type_color.items()
            ]
        assoc_view_graph.stylesheet.extend(type_stylesheet)
        assoc_view_graph_legend.stylesheet = [
                {
                    'selector': 'node',
                    'style': {
                        'content': 'data(label)'
                        },
                    },
                ] + type_stylesheet

        @app.callback(
                Output(df_raw_obs_dt.id, 'style_data_conditional'),
                [
                    Input(dataitem_select_drp.id, 'value'),
                    ]
                )
        def update_selected_data_items(dataitem_value):
            if dataitem_value is None:
                return None
            dt_style = [
                    {
                        'if': {
                            'filter_query': '{{{}}} = {}'.format(
                                'pk', pk),
                        },
                        'backgroundColor': '#eeeeee',
                        }
                    for pk in dataitem_value
                    ]
            return dt_style

        _outputs = [
                    Output(dataitem_select_drp.id, 'options'),
                    Output(network_select_drp.id, 'options'),
                    Output(df_raw_obs_dt.id, 'columns'),
                    Output(df_raw_obs_dt.id, 'data'),
                    Output(assoc_view_graph.id, 'elements'),
                    Output(assoc_view_graph_legend.id, 'elements'),
                    Output(error_container.id, 'children'),
                    ]

        @app.callback(
                _outputs,
                [
                    Input(ctx['calgroup_select_drp'].id, 'value'),
                    ],
                )
        def update_calgroup(calgroup_value):
            if calgroup_value is None:
                raise dash.exceptions.PreventUpdate

            self.logger.debug("update dataitem")
            try:
                df_raw_obs = query_raw_obs()
                raw_obs_pks = json.loads(calgroup_value)
                df_raw_obs = df_raw_obs.loc[raw_obs_pks]
            except Exception as e:
                self.logger.debug(f"error query db: {e}", exc_info=True)
                error_notify = dbc.Alert(
                        f'Query failed: {e.__class__.__name__}')
                return (dash.no_update, ) * (
                        len(_outputs) - 1) + (error_notify, )
            use_cols = [
                    c for c in df_raw_obs.columns
                    if c not in ['source', 'source_url']
                    ]
            df = df_raw_obs.reindex(columns=use_cols)
            cols = [{'label': c, 'id': c} for c in df.columns]
            data = df.to_dict('record')

            # build the DAG to show the assocs
            nodes = [
                {
                    'data': {
                        'id': str(r.pk),
                        'label': f"{r.obsnum}",
                        'type': r.raw_obs_type,
                        'reduced': r.dp_basic_reduced_obs_pk > 0
                        },
                    }
                for r in df.itertuples()
                ]
            edges = []
            for r in df.itertuples():
                if r.dp_sweep_obs_pk < 0:
                    continue
                edges.append(
                    {
                        'data': {
                            'source': str(r.dp_sweep_obs_pk),
                            'target': str(r.pk),
                            'lable': ''
                            },
                        'selectable': False
                    })
            self.logger.debug(
                    f"collected {len(nodes)} nodes and {len(edges)} edges")
            elems = nodes + edges
            # legend
            elems_legend = [
                    {
                        'data': {
                            'id': t,
                            'label': t,
                            'type': t,
                            },
                        }
                    for t in set(df['raw_obs_type'])
                    ]
            # make cal group options

            def make_dataitem_option(r):
                label = f'{r.obsnum}-{r.raw_obs_type}'
                value = r.pk
                return {'label': label, 'value': value}

            options = list(map(make_dataitem_option, df_raw_obs.itertuples()))
            # get a set of all nws
            nws = set()
            for nw in df['_roaches']:  # this is a list
                for v in nw:
                    nws.add(v)

            # load the first source file and get the number of kids
            bods = {
                    i: get_bod(
                        df_raw_obs['source'].iloc[0]['sources'][i]['url'])
                    for i in nws
                    }

            def make_network_option_label(i):
                if i in nws:
                    bod = bods[i]
                    nkids = bod.meta["n_tones"]
                    nkids_tot = bod.meta["n_tones_design"]
                    return f'toltec{i} ({nkids}/{nkids_tot})'
                return f'toltec{i}'

            network_options = [
                    {
                        'label': make_network_option_label(i),
                        'value': i,
                        }
                    for i in nws
                    ]
            return (
                    options, network_options, cols, data,
                    elems, elems_legend,
                    "")

        _outputs = [
                    Output(df_bod_dt.id, 'columns'),
                    Output(df_bod_dt.id, 'data'),
                    ]

        @app.callback(
                _outputs,
                [
                    Input(dataitem_select_drp.id, 'value'),
                    Input(network_select_drp.id, 'value'),
                    ],
                )
        def update_bod_dt(dataitem_value, network_value):
            bods = self.bods_from_select_inputs(dataitem_value, network_value)
            tbl = bods.index_table
            # get all displayable columns
            use_cols = [
                    c for c in tbl.colnames
                    if not (
                        tbl.dtype[c].hasobject
                        or c in ['source', 'filename_orig']
                        or tbl.dtype[c].ndim > 0
                        )]
            df = tbl[use_cols].to_pandas()
            cols = [{'label': c, 'id': c} for c in df.columns]
            data = df.to_dict('record')
            return cols, data
        ctx.update({
                'dataitem_select_drp': dataitem_select_drp,
                'network_select_drp': network_select_drp,
                })
        return ctx

    def _setup_assoc_view(self, app, container):

        graph_container = container.child(dbc.Row).child(dbc.Col)
        # graph_controls_container = container.child(
        #         dbc.Form, inline=True)
        # graph_layout_select_group = graph_controls_container.child(
        #         dbc.FormGroup)
        # graph_layout_select_group.child(
        #         dbc.Label,
        #         'Layout:',
        #         className='mr-3'
        #         )
        # cyto_layouts = [
        #         'random', 'grid', 'circle', 'concentric',
        #         'breadthfirst', 'cose', 'cose-bilkent',
        #         'cola', 'euler', 'spread', 'dagre',
        #         'klay',
        #         ]

        # graph_layout_select = graph_layout_select_group.child(
        #         dbc.Select,
        #         options=[
        #             {'label': l, 'value': l}
        #             for l in cyto_layouts
        #             ],
        #         value='dagre',
        #         )

        def _get_layout(value):
            return {
                    'name': value,
                    'animate': True,
                    'nodeDimensionsIncludeLabels': True,
                    'rankDir': 'LR',
                    }

        height = '250px'
        graph_container_row = graph_container.child(dbc.Row)
        graph = graph_container_row.child(dbc.Col, width=8).child(
                cyto.Cytoscape,
                # layout_=_get_layout(graph_layout_select.value),
                layout_=_get_layout('dagre'),
                elements=[],
                style={
                    'min-height': height,
                    },
                # minZoom=0.8,
                userZoomingEnabled=True,
                userPanningEnabled=False,
                boxSelectionEnabled=True,
                autoungrabify=True,
                )
        graph_legend = graph_container_row.child(dbc.Col, width=2).child(
                cyto.Cytoscape,
                layout_=_get_layout('grid'),
                elements=[],
                style={
                    'min-height': height,
                    },
                # minZoom=0.8,
                userZoomingEnabled=True,
                userPanningEnabled=False,
                boxSelectionEnabled=False,
                autoungrabify=True,
                )

        # @app.callback(
        #         Output(graph.id, 'layout'),
        #         [
        #             Input(graph_layout_select.id, 'value')
        #             ]
        #         )
        # def update_graph_layout(value):
        #     if value is None:
        #         return dash.no_update
        #     return _get_layout(value)

        return {
                'assoc_view_graph': graph,
                'assoc_view_graph_legend': graph_legend,
                }

    def _setup_network_selection(self, app, container, ctx):
        # set up a network selection section
        network_select_section = container.child(dbc.Row).child(dbc.Col)
        network_select_section.child(dbc.Label, 'Select network(s):')
        network_select_row = network_select_section.child(
                dbc.Row, className='mx-0')
        preset_container = network_select_row.child(dbc.Col)
        preset = preset_container.child(
                dbc.Checklist, persistence=False,
                labelClassName='pr-1', inline=True)
        preset.options = [
                {'label': 'All', 'value': 'all'},
                {'label': '1.1mm', 'value': '1.1 mm Array'},
                {'label': '1.4mm', 'value': '1.4 mm Array'},
                {'label': '2.0mm', 'value': '2.0 mm Array'},
                ]
        preset.value = []
        network_container = network_select_row.child(dbc.Col)
        # make three button groups
        network_select = network_container.child(
                dbc.Checklist, persistence=False,
                labelClassName='pr-1', inline=True)

        network_options = [
                {'label': f'N{i}', 'value': i}
                for i in range(13)
                ]
        array_names = ['1.1 mm Array', '1.4 mm Array', '2.0 mm Array']
        preset_networks_map = dict()
        preset_networks_map['1.1 mm Array'] = set(
                o['value'] for o in network_options[0:7])
        preset_networks_map['1.4 mm Array'] = set(
                o['value'] for o in network_options[7:10])
        preset_networks_map['2.0 mm Array'] = set(
                o['value'] for o in network_options[10:13])
        preset_networks_map['all'] = functools.reduce(
                set.union, (preset_networks_map[k] for k in array_names))

        # this shall be a dcc.store that provide mapping of
        # value to enabled state
        network_options_store = ctx['network_options_store']

        # a callback to update the check state
        @app.callback(
                [
                    Output(network_select.id, "options"),
                    Output(network_select.id, "value"),
                    ],
                [
                    Input(preset.id, "value"),
                    Input(network_options_store.id, 'data')
                ]
            )
        def on_preset_change(preset_values, network_options_store_data):
            # this is all the nws
            nw_values = set()
            for pv in preset_values:
                nw_values = nw_values.union(preset_networks_map[pv])
            options = [
                    dict(**o) for o in network_options
                    if o['value'] in nw_values]
            values = list(nw_values)

            for option in options:
                v = option['value']
                # this is to update the option with the store data
                # json makes all the dict keys str
                option.update(
                        network_options_store_data.get(str(v), dict()))
                if option['disabled']:
                    values.remove(v)
            return options, values

        return {'network_select_chklst': network_select}

    def _setup_network_selection_simple(self, app, container, ctx):
        # set up a network selection section
        network_select_section = container
        # make three button groups
        network_select_drp = network_select_section.child(
                dcc.Dropdown,
                placeholder="Select network",
                style={
                    'min-width': '240px'
                    },
                )
        return {'network_select_drp': network_select_drp}