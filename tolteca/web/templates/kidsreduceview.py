#! /usr/bin/env python


from dasha.web.templates import ComponentTemplate
import dash_html_components as html
from dasha.web.templates.utils import fa
import dash_core_components as dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Output, Input, State
# from dasha.web.extensions.celery import get_celery_app
from tollan.utils.fmt import pformat_yaml
from ..tasks.shareddata import SharedToltecDataset
from .. import tolteca_toltec_datastore
from dasha.web.extensions.cache import cache


class KidsReduceView(ComponentTemplate):

    """This is a view that shows the current KIDs reduce status."""

    _component_cls = html.Div

    _dataset_label = 'kidsreduce'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataset = SharedToltecDataset(self._dataset_label)
        self.datafiles = tolteca_toltec_datastore

    @property
    def title_text(self):
        return (fa("far fa-chart-bar"), "KIDs Reduce")

    def setup_layout(self, app):

        self.interval = self.child(dcc.Interval, update_interval=1)

        _debug_datastore = self.child(html.Pre)

        n_rows = 50
        content = self.child(dbc.Row)
        content_rows = [
                content.child(dbc.Col).child(
                    dbc.Card, color='light', className='mx-2 mb-2',
                    style={"width": "18rem"}
                    )
                for _ in range(n_rows)]
        # content_row_ids = [
        #         content.child(dcc.Store, data=i)
        #         for i in range(n_rows)]
        # content_row_timers = [
        #         content.child(dcc.Interval, update_interval=1)
        #         for i in range(n_rows)]

        for i, row in enumerate(content_rows):
            # set up the span and action buttons
            c_header = row.child(dbc.CardHeader)
            c_body = row.child(dbc.CardBody)
            # c_header = row.child(dbc.CardHeader)
            c_footer = row.child(dbc.CardFooter)
            row.c_info = c_body.child(html.Pre, className='mb-2')
            row.c_state = c_header.child(html.Div, "N/A", className='mb-2')
            actions_container = c_footer.child(html.Div, className='mb-2')
            row.c_actions = {
                    k: actions_container.child(
                        dbc.Button, t,
                        className='my-0 mr-2 badge badge-info')
                    for k, t in [('reduce', 'Run reduce'), ]
                    }
        super().setup_layout(app)

        @cache.memoize(timeout=30)
        def get_files(pattern):
            # return "abc"
            return list(self.datafiles.rootpath.glob(pattern))

        @cache.memoize(timeout=1)
        def get_table():
            return self.dataset.index_table

        @app.callback(
                Output(_debug_datastore.id, 'children'),
                [Input(self.interval.id, 'n_intervals')],
                []
                )
        def update(n_intervals):
            ds = self.dataset._index_table_store
            debug = ds.connection.jsonget(ds._key, ds._revkey, ds._keykey)
            debug = pformat_yaml(debug)
            return debug

        @app.callback(
                Output(content.id, 'children'),
                [Input(self.interval.id, 'n_intervals')],
                []
                )
        def update_info(n_intervals):
            tbl = get_table().to_dict('records')
            result = []
            for i in range(n_rows):
                if i >= len(tbl):
                    break
                entry = tbl[i]
                row = content_rows[i]
                row.c_info.children = pformat_yaml(entry)
                # pattern = \
                #     f'**/toltec*_' \
                #     f'{entry["Obsnum"]:06d}' \
                #     f'_{entry["SubObsNum"]:02d}_{entry["ScanNum"]:04d}*'
                # print(self.datafiles.rootpath)
                # print(pattern)
                # filepath = get_files(pattern)
                # print(filepath)
                badges = []
                if len(entry['reduced_files']) > 0:
                    badges.append(dbc.Badge(
                        'Reduced',
                        color="success", className="mr-1"))
                    row.c_actions['reduce'].disabled = True
                else:
                    row.c_actions['reduce'].disabled = False
                if len(entry['files']) > 0:
                    badges.append(dbc.Badge(
                        'Raw',
                        color="secondary", className="mr-1"
                        ))

                row.c_state.children = badges
                result.append(row.layout)
            return result
        # for i in range(n_rows):
        #     @app.callback(
        #             Output(content_rows[i].id, 'children'),
        #             [Input(content_row_timers[i].id, 'n_intervals')],
        #             [State(content_row_ids[i].id, 'data')]
        #             )
        #     def update_row(n_intervals, i):
        #         if i is None:
        #             return
        #         print(i)
        #         tbl = get_table()
        #         if i >= len(tbl):
        #             return
        #         entry = tbl.iloc[i:i + 1].to_dict(
        #                 "records")[0]
        #         row = content_rows[i]
        #         row.c_info.children = pformat_yaml(entry)
        #         pattern = \
        #             f'**/toltec*_' \
        #             f'{entry["Obsnum"]:06d}' \
        #             f'_{entry["SubObsNum"]:02d}_{entry["ScanNum"]:04d}*'
        #         print(self.datafiles.rootpath)
        #         print(pattern)
        #         filepath = get_files(pattern)
        #         print(filepath)
        #         row.c_state.children = str(filepath)
        #         return row.layout.children

    @property
    def layout(self):
        return super().layout
