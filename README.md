# Spatial Network Expansion & Feasibility Planner

A geospatial decision-support toolkit built for **PyQGIS (Qt6 / PyQt6)** and **NetworkX** that automates utility distribution network routing, multi-demand spatial clustering, kernel density estimation (KDE), and financial feasibility modeling.

---

## Overview

Planning linear infrastructure expansion (such as gas, water, district heating, or fiber networks) requires balancing **street-level topological constraints** against **localized demand density** and **capital expenditure (CAPEX)**.

This repository provides two integrated geospatial tools:

1. **Multi-Demand Network Expansion & Feasibility Planner (`src/network_planner.py`)**
   - Unifies heterogeneous demand sources (residential buildings, commercial establishments, and active construction developments) into a common metric Coordinate Reference System (`EPSG:3857`).
   - Aggregates dense demand pockets using **DBSCAN spatial clustering** and computes demand-weighted load centroids.
   - Filters out economically unviable demand poles based on a minimum linear density threshold ($\text{units/m/yr}$).
   - Constructs a **density-weighted topological street graph** in `NetworkX`, routing from existing infrastructure trunks toward high-density urban cores first while amortizing shared main-line segments.
   - Aggregates planned segments by normalized street name, computes segment-level ranking scores (`0–100`), and generates an executive financial summary (CAPEX, annual gross revenue, and simple payback period).

2. **Spatial Demand Heatmap Generator (`src/kde_heatmap.py`)**
   - Computes weighted **Kernel Density Estimation (KDE)** rasters using a quartic kernel over demand points or weighted centroids.
   - Applies a non-linear pseudo-color ramp shader to highlight both primary urban cores and secondary regional demand hubs.

---

## Methodology & Routing Heuristics

### 1. Demand-Weighted DBSCAN Clustering
Point features are projected to a metric CRS and clustered via `native:dbscanclustering` ($\epsilon = \text{cluster radius}$). For each cluster $C$, a demand-weighted centroid $(\bar{x}, \bar{y})$ is calculated:

$$\bar{x} = \frac{\sum_{i \in C} x_i \cdot w_i}{\sum_{i \in C} w_i}, \quad \bar{y} = \frac{\sum_{i \in C} y_i \cdot w_i}{\sum_{i \in C} w_i}$$

where $w_i$ represents the estimated annual demand of point $i$.

### 2. Urban Gravity Graph Weighting & Trunk Amortization
Street centerlines are converted into an undirected graph $G = (V, E)$. Each edge $e = (u, v)$ with Euclidean length $d_e$ receives an effective routing weight discounted by surrounding demand $D_{150\text{m}}$ within a $150\text{ m}$ search radius:

$$w_e = \frac{d_e}{1 + \frac{D_{150\text{m}}}{1000}}$$

- **Core-First Ordering:** Viable centroids are sorted in descending order by neighborhood density ($500\text{ m}$ radius).
- **Trunk Reuse:** Once a shortest path is routed from the existing network super-source node to a target cluster, traversed edges have their weight reduced to $\approx 0$, encouraging subsequent branches to share existing main lines rather than creating redundant parallel paths.
- **Street Completion Heuristic:** Optional breadth-first graph traversal completes partially covered streets when coverage exceeds a user-defined percentage threshold, subject to a maximum extension cap.

### 3. Segment Ranking & Financial Metrics
Planned segments are dissolved by normalized street name and scored using a length-penalized potential index normalized to $[0, 100]$:

$$\text{Score}_s = \frac{D_s}{\sqrt{\max(L_s, 50)}} \cdot \left(1 + 0.25 \cdot N_{\text{dev}}\right)$$

---

## Repository Structure

```text
spatial-network-planner/
├── README.md
├── requirements.txt
└── src/
    ├── __init__.py
    ├── network_planner.py   # PyQt6 UI, DBSCAN clustering, NetworkX routing & financial report
    └── kde_heatmap.py       # Weighted KDE raster generator & non-linear styling
```

---

## Requirements & Installation

### QGIS Environment (Recommended)
This project runs directly inside **QGIS 3.34+ (Qt5 or Qt6)** using its bundled Python environment:

1. Open QGIS and launch the **Python Console** (`Ctrl+Alt+P`).
2. Ensure `networkx` is available in your QGIS Python environment (if not, install via OSGeo4W Shell / QGIS Python):
   ```bash
   pip install networkx
   ```
3. Load and execute either `src/network_planner.py` or `src/kde_heatmap.py` from the QGIS Script Editor.

---

## Development Roadmap

- [ ] **Decoupled Core Engine (`src/graph_engine.py`):** Extract pure `NetworkX` + `Shapely` graph construction and routing heuristics away from PyQGIS API bindings to enable headless CLI execution.
- [ ] **Automated Test Suite (`tests/`):** Add `pytest` unit tests covering weighted centroid math, trunk amortization paths, street-name normalization, and CAPEX/payback calculations.
- [ ] **Alternative Routing Solvers:** Benchmark sequential shortest-path amortization against Steiner Tree approximations and Minimum Spanning Tree (MST) heuristics.
- [ ] **Configurable CRS & Export Formats:** Allow custom projected CRS selection in the UI and direct export of feasibility reports to GeoPackage (`.gpkg`) and CSV.

---

## License

MIT License