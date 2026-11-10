"""Plotly figure creation for the active experiment."""

from __future__ import annotations

from typing import Final

import numpy as np
import plotly.graph_objects as go

from dahlia.services.experiment import PreparedExperiment, precision_digits

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
    """Return a padded [min, max] range for a Plotly axis.

    Adds 7 % of the data span as padding on each side so points near
    the edge of the scatter are not clipped.
    """
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    span = maximum - minimum
    padding = span * 0.07 if span else 1.0
    return [minimum - padding, maximum + padding]


def _tick_text(experiment: PreparedExperiment) -> list[str]:
    """Format display tick values to the dataset's decimal precision."""
    digits = precision_digits(experiment.config.precision)
    return [f"{value:.{digits}f}" for value in experiment.display_ticks]


def build_experiment_figure(
    experiment: PreparedExperiment,
    predicted_value: float,
) -> go.Figure:
    """Build the Plotly scatter figure for the active annotation step.

    Renders two traces: one for all currently observed points (coloured
    by their known target value) and one for the single active point
    whose target the annotator is estimating (coloured by the current
    slider/input value).  An arrow annotation marks the active point.

    Parameters
    ----------
    experiment:
        Prepared experiment state, including coordinates, config and
        the current annotation index.
    predicted_value:
        The annotator's current guess for the active point's target
        value, used to colour the active marker and populate its tooltip.

    Returns
    -------
    go.Figure
        A configured Plotly Figure ready to be serialised and passed to
        a NiceGUI ``ui.plotly`` element.
    """
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
        uirevision=f"step_{experiment.current_step}",
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


def build_predefined_preview_figure(
    dataset_name: str,
    removed_indices: tuple[int, ...] | list[int],
    annotation_indices: tuple[int, ...] | list[int],
    projection_name: str = "PCA",
) -> go.Figure | None:
    """Build a 2D overview figure for a predefined set definition.

    Shows:
    - Observed points (known data) in muted neutral gray.
    - Other removed points (NA) in light coral with 'x' marks.
    - 15 evaluation points in vivid DAHLIA purple with step numbers 1..15.
    """
    from dahlia.services.config import DATASETS
    from dahlia.services.data import load_dataset
    from dahlia.services.projection import compute_projection

    cfg = DATASETS.get(dataset_name)
    if cfg is None:
        return None

    try:
        df = load_dataset(cfg)
        coords = compute_projection(df, cfg, projection_name, seed=0)
    except Exception:
        return None

    removed_set = set(removed_indices)
    annotation_set = set(annotation_indices)
    observed_idx = [i for i in df.index if i not in removed_set]
    other_removed_idx = [i for i in removed_indices if i not in annotation_set]

    fig = go.Figure()

    # 1. Observed points
    if observed_idx:
        obs_coords = coords.loc[observed_idx]
        fig.add_trace(
            go.Scattergl(
                x=obs_coords["x"],
                y=obs_coords["y"],
                mode="markers",
                marker=dict(size=7, color="#b0b0ba", opacity=0.6, line=dict(width=0.5, color="white")),
                name="Observed data",
                hoverinfo="text",
                hovertext=[f"Observed (row {i})" for i in observed_idx],
            )
        )

    # 2. Other removed NA points
    if other_removed_idx:
        rem_coords = coords.loc[other_removed_idx]
        fig.add_trace(
            go.Scattergl(
                x=rem_coords["x"],
                y=rem_coords["y"],
                mode="markers",
                marker=dict(size=8, color="#e06c75", symbol="x", line=dict(width=1.2, color="#e06c75")),
                name="Other NA points",
                hoverinfo="text",
                hovertext=[f"Removed NA (row {i})" for i in other_removed_idx],
            )
        )

    # 3. 15 Human Evaluation points with step numbers
    if annotation_indices:
        ann_coords = coords.loc[list(annotation_indices)]
        step_numbers = [str(step) for step in range(1, len(annotation_indices) + 1)]
        fig.add_trace(
            go.Scattergl(
                x=ann_coords["x"],
                y=ann_coords["y"],
                mode="markers+text",
                marker=dict(
                    size=14,
                    color="#6B5DD3",
                    line=dict(width=2, color="#ffffff"),
                ),
                text=step_numbers,
                textposition="top center",
                textfont=dict(size=11, family="monospace", color="#4335A8"),
                name="Evaluation points (1-15)",
                hoverinfo="text",
                hovertext=[
                    f"Step {step}: Row {idx}"
                    for step, idx in enumerate(annotation_indices, start=1)
                ],
            )
        )

    fig.update_layout(
        margin=dict(l=40, r=40, t=30, b=40),
        paper_bgcolor="white",
        plot_bgcolor="#fafafc",
        hovermode="closest",
        dragmode="pan",
        xaxis=dict(
            range=_axis_range(coords["x"].to_numpy()),
            gridcolor="#ededf2",
            gridwidth=0.7,
            zeroline=False,
            tickfont=dict(size=9, family="monospace", color="#9999a1"),
        ),
        yaxis=dict(
            range=_axis_range(coords["y"].to_numpy()),
            gridcolor="#ededf2",
            gridwidth=0.7,
            zeroline=False,
            tickfont=dict(size=9, family="monospace", color="#9999a1"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, family="sans-serif"),
        ),
        height=380,
    )
    return fig
