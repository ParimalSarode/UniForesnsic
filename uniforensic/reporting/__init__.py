"""Forensic reporting, visualization, and synthesis module."""

from uniforensic.reporting.plots import (
    plot_reliability_diagram,
    plot_scenario_breakdown,
    plot_system_comparison,
)
from uniforensic.reporting.report_generator import ResearchReportGenerator

__all__ = [
    "plot_reliability_diagram",
    "plot_scenario_breakdown",
    "plot_system_comparison",
    "ResearchReportGenerator",
]
