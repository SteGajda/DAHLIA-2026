"""Plotly figure creation for the active experiment."""

from __future__ import annotations

from typing import Final

import numpy as np
import plotly.graph_objects as go

from dahlia.services.experiment import PreparedExperiment, precision_digits

# The exact plasma stops used by the approved Figma concept.
PLASMA_FIGMA: Final[list[list[float | str]]] = [
    [0.0, "rgb(13,8,135)"],
    [1 / 7, "rgb(84,2,163)"],
    [2 / 7, "rgb(139,10,165)"],
    [3 / 7, "rgb(185,50,137)"],
    [4 / 7, "rgb(219,92,104)"],
    [5 / 7, "rgb(244,136,73)"],
    [6 / 7, "rgb(254,188,43)"],
    [1.0, "rgb(240,249,33)"],
]


def _axis_range(values: np.ndarray) -> list[float]:
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    span = maximum - minimum
    padding = span * 0.07 if span else 1.0
    return [minimum - padding, maximum + padding]


def _tick_text(experiment: PreparedExperiment) -> list[str]:
    digits = precision_digits(experiment.config.precision)
    return [f"{value:.{digits}f}" for value in experiment.display_ticks]


def build_experiment_figure(
    experiment: PreparedExperiment,
    predicted_value: float,
) -> go.Figure:
    cfg = experiment.config
    target = cfg.incomplete_column
    current = experiment.current_index

    # Only fully observed points and the current active point are visible.
    observed_indices = experiment.incomplete.index[
        experiment.incomplete[target].notna()
    ]
    observed = experiment.original.loc[observed_indices]
    observed_xy = experiment.coordinates.loc[observed_indices]

    reference_values = observed.loc[:, cfg.reference_columns].to_numpy()
    target_values = observed[target].to_numpy()
    custom_observed = np.column_stack([reference_values, target_values])
    hover_observed = "<br>".join(
        [
            *(f"{column}: %{{customdata[{index}]}}" for index, column in enumerate(cfg.reference_columns)),
            f"{target}: %{{customdata[{len(cfg.reference_columns)}]}}",
            "<extra></extra>",
        ]
    )

    active_row = experiment.original.loc[current]
    active_xy = experiment.coordinates.loc[current]
    active_custom = [
        *[active_row[column] for column in cfg.reference_columns],
        predicted_value,
    ]
    hover_active = "<br>".join(
        [
            *(f"{column}: %{{customdata[{index}]}}" for index, column in enumerate(cfg.reference_columns)),
            f"Predicted value: %{{customdata[{len(cfg.reference_columns)}]}}",
            "<extra></extra>",
        ]
    )

    colorbar = dict(
        title=dict(text=target, side="top", font=dict(size=10, family="monospace")),
        tickmode="array",
        tickvals=list(experiment.display_ticks),
        ticktext=_tick_text(experiment),
        tickfont=dict(size=9, family="monospace", color="#777780"),
        thickness=14,
        len=0.83,
        x=1.015,
        xpad=8,
        outlinewidth=0,
    )

    figure = go.Figure()
    figure.add_trace(
        go.Scattergl(
            x=observed_xy["x"],
            y=observed_xy["y"],
            mode="markers",
            marker=dict(
                size=10,
                color=target_values,
                colorscale=PLASMA_FIGMA,
                cmin=experiment.value_min,
                cmax=experiment.value_max,
                showscale=True,
                colorbar=colorbar,
                line=dict(width=0.5, color="rgba(0,0,0,.18)"),
            ),
            customdata=custom_observed,
            hovertemplate=hover_observed,
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scattergl(
            x=[active_xy["x"]],
            y=[active_xy["y"]],
            mode="markers",
            marker=dict(
                size=10,
                color=[predicted_value],
                colorscale=PLASMA_FIGMA,
                cmin=experiment.value_min,
                cmax=experiment.value_max,
                showscale=False,
                line=dict(width=1.2, color="rgba(0,0,0,.48)"),
            ),
            customdata=[active_custom],
            hovertemplate=hover_active,
            showlegend=False,
        )
    )

    figure.add_annotation(
        x=float(active_xy["x"]),
        y=float(active_xy["y"]),
        text="×",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1.2,
        arrowcolor="#777780",
        ax=0,
        ay=-48,
        bgcolor="rgba(235,235,238,.94)",
        bordercolor="#bdbdc4",
        borderwidth=1,
        borderpad=3,
        font=dict(size=10, family="monospace", color="#55555d"),
    )

    figure.update_layout(
        margin=dict(l=54, r=92, t=24, b=52),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="closest",
        dragmode="pan",
        xaxis=dict(
            range=_axis_range(experiment.coordinates["x"].to_numpy()),
            fixedrange=False,
            gridcolor="#e5e5ea",
            gridwidth=0.7,
            zeroline=False,
            tickfont=dict(size=9, family="monospace", color="#9999a1"),
            title=None,
        ),
        yaxis=dict(
            range=_axis_range(experiment.coordinates["y"].to_numpy()),
            fixedrange=False,
            gridcolor="#e5e5ea",
            gridwidth=0.7,
            zeroline=False,
            tickfont=dict(size=9, family="monospace", color="#9999a1"),
            title=None,
        ),
        showlegend=False,
        uirevision=None,
    )
    figure.update_layout(
        modebar=dict(remove=["select2d", "lasso2d"]),
    )
    return figure


PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": True,
    "doubleClick": "reset+autosize",
    "responsive": True,
}
