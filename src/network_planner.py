import math
import os
import re
import tempfile
import unicodedata
from collections import defaultdict, deque
from datetime import datetime

import networkx as nx
from processing import run
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType, QSize, Qt, QVariant
from qgis.PyQt.QtGui import QFont, QPainter, QPixmap, QTextDocument
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.utils import iface


class SpatialNetworkExpansionPlanner(QDialog):
    """
    SPATIAL NETWORK EXPANSION & FEASIBILITY PLANNER (PYQT6 / PYQGIS)
    ----------------------------------------------------------------
    - Strict street-centerline routing via weighted NetworkX graphs.
    - Density-aware pathfinding with trunk cost amortization.
    - Compatible with PyQt6 / Qt6.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Feasibility & Expansion Analysis - Utility Network")
        self.setMinimumWidth(700)
        self.setMinimumHeight(840)

        self.residential_layer = None
        self.commercial_layer = None
        self.developments_layer = None
        self.streets_layer = None
        self.existing_network_layer = None

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 30)

        self.setup_tabs()
        self.setup_footer()

        self.setLayout(self.layout)

    def setup_footer(self):
        footer_frame = QFrame()
        footer_frame.setFrameShape(QFrame.Shape.HLine)
        footer_frame.setStyleSheet("background-color: #f0f0f0; padding: 5px;")

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)

        author_label = QLabel("Spatial Network Expansion & Feasibility Tool | PyQGIS / NetworkX")
        author_label.setStyleSheet("color: #666666; font-size: 10px; font-style: italic;")
        author_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        footer_layout.addStretch()
        footer_layout.addWidget(author_label)
        footer_frame.setLayout(footer_layout)
        self.layout.addWidget(footer_frame)

    def setup_tabs(self):
        self.tabs = QTabWidget()

        self.tab_config = QWidget()
        self.setup_config_tab()
        self.tabs.addTab(self.tab_config, "⚙️ Layer Configuration")

        self.tab_costs = QWidget()
        self.setup_additional_costs_tab()
        self.tabs.addTab(self.tab_costs, "💰 Connection Costs")

        self.tab_feasibility = QWidget()
        self.setup_feasibility_tab()
        self.tabs.addTab(self.tab_feasibility, "📊 Multi-Demand Feasibility")

        self.layout.addWidget(self.tabs)

    def setup_config_tab(self):
        layout = QVBoxLayout()

        title_label = QLabel("NETWORK LAYER CONFIGURATION")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title_label)

        instructions = QLabel(
            "Select the demand and infrastructure vector layers:\n"
            "• RESIDENTIAL: Residential building points (Units count field).\n"
            "• COMMERCIAL: Commercial establishments / businesses.\n"
            "• ACTIVE DEVELOPMENTS: Ongoing construction projects (uses Residential average units).\n"
            "• STREETS: Road centerline network (routing graph).\n"
            "• EXISTING NETWORK: Starting infrastructure trunk lines."
        )
        instructions.setStyleSheet("color: #34495e; background-color: #ecf0f1; padding: 8px; border-radius: 5px;")
        layout.addWidget(instructions)

        grupo_config = QGroupBox("📁 Vector Layer Selection")
        grupo_config.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout_config = QVBoxLayout()

        layout_res = QHBoxLayout()
        layout_res.addWidget(QLabel("1. RESIDENTIAL:"))
        self.cbo_residential = QComboBox()
        self.load_layers_combo(self.cbo_residential)
        self.cbo_residential.currentIndexChanged.connect(self.update_residential_fields)
        layout_res.addWidget(self.cbo_residential)
        layout_config.addLayout(layout_res)

        layout_field_units = QHBoxLayout()
        layout_field_units.addWidget(QLabel("   ↳ Units Field (Residential):"))
        self.cbo_units_field = QComboBox()
        layout_field_units.addWidget(self.cbo_units_field)
        layout_config.addLayout(layout_field_units)

        layout_com = QHBoxLayout()
        layout_com.addWidget(QLabel("2. COMMERCIAL:"))
        self.cbo_commercial = QComboBox()
        self.load_layers_combo(self.cbo_commercial)
        layout_com.addWidget(self.cbo_commercial)
        layout_config.addLayout(layout_com)

        layout_dev = QHBoxLayout()
        layout_dev.addWidget(QLabel("3. ACTIVE DEVELOPMENTS:"))
        self.cbo_developments = QComboBox()
        self.load_layers_combo(self.cbo_developments)
        layout_dev.addWidget(self.cbo_developments)
        layout_config.addLayout(layout_dev)

        layout_streets = QHBoxLayout()
        layout_streets.addWidget(QLabel("4. STREETS (Road Graph):"))
        self.cbo_streets = QComboBox()
        self.load_layers_combo(self.cbo_streets)
        layout_streets.addWidget(self.cbo_streets)
        layout_config.addLayout(layout_streets)

        layout_net = QHBoxLayout()
        layout_net.addWidget(QLabel("5. EXISTING NETWORK:"))
        self.cbo_network = QComboBox()
        self.load_layers_combo(self.cbo_network)
        layout_net.addWidget(self.cbo_network)
        layout_config.addLayout(layout_net)

        grupo_config.setLayout(layout_config)
        layout.addWidget(grupo_config)

        self.btn_confirm = QPushButton("✅ Confirm Configuration")
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; font-weight: bold;
                padding: 10px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #219653; }
        """)
        self.btn_confirm.clicked.connect(self.confirm_selections)
        layout.addWidget(self.btn_confirm)

        layout.addStretch()
        self.tab_config.setLayout(layout)

    def setup_additional_costs_tab(self):
        layout = QVBoxLayout()

        title_label = QLabel("ADDITIONAL COSTS & SERVICE CONNECTIONS")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title_label)

        grupo_connection = QGroupBox("💰 Lateral / Service Connection Cost per Customer")
        grupo_connection.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_connection = QFormLayout()

        self.spin_connection_cost = QDoubleSpinBox()
        self.spin_connection_cost.setRange(0.0, 1000000.0)
        self.spin_connection_cost.setDecimals(2)
        self.spin_connection_cost.setSingleStep(1000.0)
        self.spin_connection_cost.setValue(25000.00)
        self.spin_connection_cost.setPrefix("$ ")

        form_connection.addRow(
            "Connection Cost per Building/Customer (Residential, Commercial, or Development):",
            self.spin_connection_cost,
        )
        grupo_connection.setLayout(form_connection)

        layout.addWidget(grupo_connection)
        layout.addStretch()
        self.tab_costs.setLayout(layout)

    def setup_feasibility_tab(self):
        layout = QVBoxLayout()

        title_label = QLabel("DEMAND, COST & FILTERING PARAMETERS")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title_label)

        grupo_params = QGroupBox("⚙️ Consumption Estimates & Local Density Thresholds")
        grupo_params.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout_params = QVBoxLayout()

        layout_res_cons = QHBoxLayout()
        layout_res_cons.addWidget(QLabel("Annual Demand per Residential Unit (units/yr):"))
        self.input_unit_demand = QLineEdit("140.00")
        layout_res_cons.addWidget(self.input_unit_demand)
        layout_params.addLayout(layout_res_cons)

        layout_com_cons = QHBoxLayout()
        layout_com_cons.addWidget(QLabel("Annual Demand per Commercial Point (units/yr):"))
        self.input_comm_demand = QLineEdit("7000.00")
        layout_com_cons.addWidget(self.input_comm_demand)
        layout_params.addLayout(layout_com_cons)

        layout_cost = QHBoxLayout()
        layout_cost.addWidget(QLabel("Main Line Installation Cost ($/m):"))
        self.input_cost_per_m = QLineEdit("500.00")
        layout_cost.addWidget(self.input_cost_per_m)
        layout_params.addLayout(layout_cost)

        layout_tariff = QHBoxLayout()
        layout_tariff.addWidget(QLabel("Average Utility Tariff ($/unit):"))
        self.input_tariff = QLineEdit("3.00")
        layout_tariff.addWidget(self.input_tariff)
        layout_params.addLayout(layout_tariff)

        layout_cluster = QHBoxLayout()
        layout_cluster.addWidget(QLabel("DBSCAN Cluster Radius (m):"))
        self.input_cluster_dist = QLineEdit("30.0")
        layout_cluster.addWidget(self.input_cluster_dist)
        layout_params.addLayout(layout_cluster)

        layout_dens_min = QHBoxLayout()
        layout_dens_min.addWidget(QLabel("Minimum Acceptable Linear Density (units/m/yr):"))
        self.input_min_density = QLineEdit("10.0")
        layout_dens_min.addWidget(self.input_min_density)
        layout_params.addLayout(layout_dens_min)

        hbox_complete = QHBoxLayout()

        self.chk_complete_streets = QCheckBox("Complete street segments (min. coverage):")
        self.chk_complete_streets.setChecked(False)

        self.spin_pct_complete = QSpinBox()
        self.spin_pct_complete.setRange(0, 100)
        self.spin_pct_complete.setValue(30)
        self.spin_pct_complete.setSuffix("%")
        self.spin_pct_complete.setEnabled(False)

        self.chk_limit_ext = QCheckBox("Cap max extension:")
        self.chk_limit_ext.setChecked(True)
        self.chk_limit_ext.setEnabled(False)

        self.spin_max_ext_complete = QDoubleSpinBox()
        self.spin_max_ext_complete.setRange(10.0, 10000.0)
        self.spin_max_ext_complete.setSingleStep(50.0)
        self.spin_max_ext_complete.setValue(300.0)
        self.spin_max_ext_complete.setSuffix(" m")
        self.spin_max_ext_complete.setEnabled(False)

        def update_complete_state():
            active = self.chk_complete_streets.isChecked()
            self.spin_pct_complete.setEnabled(active)
            self.chk_limit_ext.setEnabled(active)
            self.spin_max_ext_complete.setEnabled(active and self.chk_limit_ext.isChecked())

        self.chk_complete_streets.toggled.connect(update_complete_state)
        self.chk_limit_ext.toggled.connect(update_complete_state)

        hbox_complete.addWidget(self.chk_complete_streets)
        hbox_complete.addWidget(self.spin_pct_complete)
        hbox_complete.addWidget(self.chk_limit_ext)
        hbox_complete.addWidget(self.spin_max_ext_complete)
        hbox_complete.addStretch()

        layout_params.addLayout(hbox_complete)

        grupo_params.setLayout(layout_params)
        layout.addWidget(grupo_params)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(160)
        self.log_text.setStyleSheet("background-color: #2c3e50; color: #ecf0f1; font-family: Consolas, monospace;")
        layout.addWidget(self.log_text)

        self.btn_process = QPushButton("🚀 Run Integrated Feasibility & Route Network")
        self.btn_process.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white; font-weight: bold;
                padding: 12px; border-radius: 5px; font-size: 14px;
            }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.btn_process.clicked.connect(self.run_feasibility_analysis)
        layout.addWidget(self.btn_process)

        layout.addStretch()
        self.tab_feasibility.setLayout(layout)

    def load_layers_combo(self, combo_box):
        combo_box.clear()
        combo_box.addItem("-- Select Layer --", None)
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                combo_box.addItem(f"{layer.name()} ({layer.featureCount()} features)", layer)

    def update_residential_fields(self):
        self.cbo_units_field.clear()
        layer = self.cbo_residential.currentData()
        if layer:
            for field in layer.fields():
                self.cbo_units_field.addItem(field.name(), field.name())

    def log(self, message):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def confirm_selections(self):
        self.residential_layer = self.cbo_residential.currentData()
        self.commercial_layer = self.cbo_commercial.currentData()
        self.developments_layer = self.cbo_developments.currentData()
        self.streets_layer = self.cbo_streets.currentData()
        self.existing_network_layer = self.cbo_network.currentData()

        if not all([self.residential_layer, self.streets_layer, self.existing_network_layer]):
            QMessageBox.warning(
                self, "⚠️ Warning", "At least RESIDENTIAL, STREETS, and EXISTING NETWORK layers must be selected!"
            )
            return

        QMessageBox.information(self, "✅ Success", "Layers and field mappings confirmed!")

    def run_feasibility_analysis(self):
        try:
            cost_per_m = float(self.input_cost_per_m.text().replace(',', '.'))
            tariff_per_unit = float(self.input_tariff.text().replace(',', '.'))
            unit_demand = float(self.input_unit_demand.text().replace(',', '.'))
            comm_demand = float(self.input_comm_demand.text().replace(',', '.'))
            dbscan_radius = float(self.input_cluster_dist.text().replace(',', '.'))
            min_density_limit = float(self.input_min_density.text().replace(',', '.'))

            units_field = self.cbo_units_field.currentText()

            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(5)
            self.log("=== STARTING MULTI-DEMAND FEASIBILITY ANALYSIS ===")

            project_crs = QgsCoordinateReferenceSystem("EPSG:3857")

            avg_res_units = 0.0
            if self.residential_layer and units_field:
                units_list = []
                for feat in self.residential_layer.getFeatures():
                    try:
                        val = float(feat[units_field])
                        if val > 0:
                            units_list.append(val)
                    except (ValueError, TypeError):
                        pass
                if units_list:
                    avg_res_units = sum(units_list) / len(units_list)
                    self.log(f"ℹ️ Average residential units calculated: {avg_res_units:.2f} units/building")

            est_dev_demand = avg_res_units * unit_demand

            def prepare_point_layer(layer_in, value_field, mult_factor, fixed_value=None):
                if not layer_in:
                    return None

                layer_proj = run("native:reprojectlayer", {
                    'INPUT': layer_in, 'TARGET_CRS': project_crs, 'OUTPUT': 'memory:'
                })['OUTPUT']

                layer_2d = run("native:dropmzvalues", {
                    'INPUT': layer_proj, 'OUTPUT': 'memory:'
                })['OUTPUT']

                if layer_2d.geometryType() != QgsWkbTypes.PointGeometry:
                    pts_layer = run("native:centroids", {
                        'INPUT': layer_2d, 'ALL_PARTS': False, 'OUTPUT': 'memory:'
                    })['OUTPUT']
                else:
                    pts_layer = layer_2d

                vl_temp = QgsVectorLayer(f"Point?crs={project_crs.authid()}", "temp_demand", "memory")
                prov = vl_temp.dataProvider()
                prov.addAttributes([QgsField("EST_DEMAND", QMetaType.Type.Double, "double", 15, 2)])
                vl_temp.updateFields()

                fields_names = [f.name() for f in pts_layer.fields()]
                feats_out = []

                for feat in pts_layer.getFeatures():
                    f_out = QgsFeature(vl_temp.fields())
                    f_out.setGeometry(feat.geometry())

                    if fixed_value is not None:
                        demand_val = float(fixed_value)
                    else:
                        raw_val = feat[value_field] if value_field in fields_names else 0
                        try:
                            demand_val = float(raw_val) * mult_factor if raw_val is not None else 0.0
                        except (ValueError, TypeError):
                            demand_val = 0.0

                    f_out.setAttribute("EST_DEMAND", demand_val)
                    feats_out.append(f_out)

                prov.addFeatures(feats_out)
                vl_temp.updateExtents()
                return vl_temp

            self.log("1/5: Computing demand and reprojecting to metric CRS...")
            point_layers = []

            if self.residential_layer:
                p_res = prepare_point_layer(self.residential_layer, units_field, unit_demand)
                if p_res:
                    point_layers.append(p_res)

            if self.commercial_layer:
                p_com = prepare_point_layer(self.commercial_layer, None, 1.0, fixed_value=comm_demand)
                if p_com:
                    point_layers.append(p_com)

            if self.developments_layer:
                p_dev = prepare_point_layer(self.developments_layer, None, 1.0, fixed_value=est_dev_demand)
                if p_dev:
                    point_layers.append(p_dev)

            if not point_layers:
                raise Exception("No valid demand layer was processed.")

            self.progress_bar.setValue(20)
            self.log("2/5: Merging demand layers and street network...")

            merged_demand = run("native:mergevectorlayers", {
                'LAYERS': point_layers, 'CRS': project_crs, 'OUTPUT': 'memory:MERGED_DEMAND'
            })['OUTPUT']

            streets_proj_raw = run("native:reprojectlayer", {
                'INPUT': self.streets_layer, 'TARGET_CRS': project_crs, 'OUTPUT': 'memory:'
            })['OUTPUT']
            streets_layer_proj = run("native:dropmzvalues", {
                'INPUT': streets_proj_raw, 'OUTPUT': 'memory:'
            })['OUTPUT']

            network_proj_raw = run("native:reprojectlayer", {
                'INPUT': self.existing_network_layer, 'TARGET_CRS': project_crs, 'OUTPUT': 'memory:'
            })['OUTPUT']
            existing_network_proj = run("native:dropmzvalues", {
                'INPUT': network_proj_raw, 'OUTPUT': 'memory:'
            })['OUTPUT']

            self.log("3/5: Clustering concentrated demand (DBSCAN)...")
            dbscan_out = run("native:dbscanclustering", {
                'INPUT': merged_demand,
                'MIN_SIZE': 2,
                'EPS': dbscan_radius,
                'DBSCAN_FIELD_NAME': 'CLUSTER_ID',
                'OUTPUT': 'memory:CLUSTERS'
            })['OUTPUT']

            self.log("4/5: Computing demand-weighted cluster centroids...")
            centroids_layer = QgsVectorLayer(f"Point?crs={project_crs.authid()}", "LOAD_CENTROIDS", "memory")
            prov_cent = centroids_layer.dataProvider()
            prov_cent.addAttributes([
                QgsField("CLUSTER_ID", QMetaType.Type.Int),
                QgsField("EST_DEMAND", QMetaType.Type.Double, "double", 15, 2),
            ])
            centroids_layer.updateFields()

            clusters_data = {}
            isolated_feats = []

            for feat in dbscan_out.getFeatures():
                c_id = feat['CLUSTER_ID']
                demand = feat['EST_DEMAND'] if feat['EST_DEMAND'] is not None else 0.0
                geom = feat.geometry()

                if not geom or geom.isEmpty():
                    continue

                pt_raw = geom.asPoint() if not geom.isMultipart() else geom.asMultiPoint()[0]
                pt = QgsPointXY(pt_raw.x(), pt_raw.y())

                if c_id is None or c_id < 0 or str(c_id) == 'NULL':
                    f_out = QgsFeature(centroids_layer.fields())
                    f_out.setGeometry(QgsGeometry.fromPointXY(pt))
                    f_out.setAttribute("CLUSTER_ID", -1)
                    f_out.setAttribute("EST_DEMAND", demand)
                    isolated_feats.append(f_out)
                else:
                    if c_id not in clusters_data:
                        clusters_data[c_id] = [0.0, 0.0, 0.0]

                    weight = demand if demand > 0 else 1.0
                    clusters_data[c_id][0] += pt.x() * weight
                    clusters_data[c_id][1] += pt.y() * weight
                    clusters_data[c_id][2] += weight

            centroid_feats = []
            for c_id, values in clusters_data.items():
                sum_xw, sum_yw, total_w = values
                if total_w > 0:
                    cx = sum_xw / total_w
                    cy = sum_yw / total_w

                    f_cent = QgsFeature(centroids_layer.fields())
                    f_cent.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(cx, cy)))
                    f_cent.setAttribute("CLUSTER_ID", c_id)
                    f_cent.setAttribute("EST_DEMAND", total_w)
                    centroid_feats.append(f_cent)

            prov_cent.addFeatures(centroid_feats + isolated_feats)
            centroids_layer.updateExtents()

            self.progress_bar.setValue(40)
            self.log(f"Filtering demand poles (Min. linear density: {min_density_limit:.1f} units/m)...")

            network_geoms = [
                f.geometry() for f in existing_network_proj.getFeatures() if f.geometry() and not f.geometry().isEmpty()
            ]
            merged_network_geom = QgsGeometry.unaryUnion(network_geoms) if network_geoms else None

            viable_centroids = QgsVectorLayer(f"Point?crs={project_crs.authid()}", "VIABLE_CENTROIDS", "memory")
            prov_cf = viable_centroids.dataProvider()
            prov_cf.addAttributes([
                QgsField("CLUSTER_ID", QMetaType.Type.Int),
                QgsField("EST_DEMAND", QMetaType.Type.Double, "double", 15, 2),
                QgsField("POINT_DENS", QMetaType.Type.Double, "double", 15, 2),
            ])
            viable_centroids.updateFields()

            viable_feats = []
            for f_c in centroids_layer.getFeatures():
                point_demand = f_c['EST_DEMAND'] if f_c['EST_DEMAND'] else 0.0

                if merged_network_geom and point_demand > 0:
                    dist_m = max(f_c.geometry().distance(merged_network_geom), 1.0)
                    point_density = point_demand / dist_m

                    if point_density >= min_density_limit:
                        f_viable = QgsFeature(viable_centroids.fields())
                        f_viable.setGeometry(f_c.geometry())
                        f_viable.setAttribute("CLUSTER_ID", f_c['CLUSTER_ID'])
                        f_viable.setAttribute("EST_DEMAND", point_demand)
                        f_viable.setAttribute("POINT_DENS", point_density)
                        viable_feats.append(f_viable)
                else:
                    viable_feats.append(f_c)

            prov_cf.addFeatures(viable_feats)
            viable_centroids.updateExtents()

            total_demand_units = sum([
                f['EST_DEMAND'] for f in viable_centroids.getFeatures() if f['EST_DEMAND'] is not None
            ])

            self.progress_bar.setValue(50)

            # -----------------------------------------------------------------
            # 5. TOPOLOGICAL ROUTING WITH NETWORKX
            # -----------------------------------------------------------------
            self.log("5/5: Building weighted street graph in memory (NetworkX)...")

            street_fields = [f.name().lower() for f in streets_layer_proj.fields()]
            if 'access' in street_fields:
                streets_layer_proj = run("native:extractbyexpression", {
                    'INPUT': streets_layer_proj,
                    'EXPRESSION': '("access" IS NULL OR lower("access") NOT IN (\'customers\', \'private\')) AND ("highway" IS NULL OR lower("highway") NOT IN (\'service\',\'footway\'))',
                    'OUTPUT': 'memory:PUBLIC_STREETS'
                })['OUTPUT']

            streets_layer_proj = run("native:retainfields", {
                'INPUT': streets_layer_proj,
                'FIELDS': ['name', 'alt_name', 'highway', 'surface', 'lanes', 'access', 'bridge'],
                'OUTPUT': 'memory:CLEAN_STREETS'
            })['OUTPUT']

            G = nx.Graph()

            def pt_to_tuple(pt):
                return (round(pt.x(), 2), round(pt.y(), 2))

            centroid_index = QgsSpatialIndex(viable_centroids.getFeatures())

            for feat in streets_layer_proj.getFeatures():
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue

                lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
                for line in lines:
                    for i in range(len(line) - 1):
                        p1 = pt_to_tuple(line[i])
                        p2 = pt_to_tuple(line[i + 1])
                        dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])

                        # Urban gravity weighting: discount edge cost near high-demand clusters
                        mid_pt = QgsPointXY((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
                        nearby_ids = centroid_index.nearestNeighbor(mid_pt, 5)

                        surrounding_demand = 0.0
                        for c_id in nearby_ids:
                            feat_c = viable_centroids.getFeature(c_id)
                            if feat_c.geometry().distance(QgsGeometry.fromPointXY(mid_pt)) <= 150.0:
                                surrounding_demand += (feat_c['EST_DEMAND'] or 1.0)

                        attraction_factor = 1.0 + (surrounding_demand / 1000.0)
                        effective_weight = dist / attraction_factor

                        G.add_edge(p1, p2, weight=effective_weight, real_dist=dist, street_id=feat.id())

            existing_nodes = set()
            for geom in network_geoms:
                lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
                for line in lines:
                    for pt in line:
                        p_tup = pt_to_tuple(pt)
                        nearest_nodes = sorted(G.nodes(), key=lambda n: math.hypot(n[0] - p_tup[0], n[1] - p_tup[1]))
                        if nearest_nodes and math.hypot(nearest_nodes[0][0] - p_tup[0], nearest_nodes[0][1] - p_tup[1]) < 30.0:
                            existing_nodes.add(nearest_nodes[0])

            ROOT_NODE = (-999999.0, -999999.0)
            for n_ex in existing_nodes:
                G.add_edge(ROOT_NODE, n_ex, weight=0.0, real_dist=0.0)

            demand_nodes_info = []
            for f_c in viable_centroids.getFeatures():
                pt_c = f_c.geometry().asPoint()
                p_tup = pt_to_tuple(pt_c)

                neighbors = centroid_index.nearestNeighbor(pt_c, 15)
                nearby_count = sum(
                    1 for v_id in neighbors
                    if viable_centroids.getFeature(v_id).geometry().distance(f_c.geometry()) <= 500.0
                )

                nearest_nodes = sorted(
                    [n for n in G.nodes() if n != ROOT_NODE],
                    key=lambda n: math.hypot(n[0] - p_tup[0], n[1] - p_tup[1]),
                )
                if nearest_nodes:
                    demand_nodes_info.append((nearby_count, nearest_nodes[0]))

            demand_nodes_info.sort(key=lambda x: x[0], reverse=True)
            demand_nodes = [item[1] for item in demand_nodes_info]

            self.log("⚡ Routing dense urban core first with trunk cost amortization...")
            project_edges = set()

            for dest_node in demand_nodes:
                try:
                    path = nx.shortest_path(G, source=ROOT_NODE, target=dest_node, weight='weight')
                    for i in range(1, len(path) - 1):
                        u, v = path[i], path[i + 1]
                        edge = tuple(sorted([u, v]))
                        project_edges.add(edge)
                        G[u][v]['weight'] = 0.001
                except nx.NetworkXNoPath:
                    pass

            def normalize_street_name(text):
                if not text or str(text).upper() == 'NULL':
                    return ""
                s = str(text).split(',')[0]
                s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII').upper().strip()
                s = re.sub(
                    r'^(RUA|R\.|RODOVIA|ROD\.|AVENIDA|AV\.|TRAVESSA|TV\.|ESTRADA|EST\.|ALAMEDA|AL\.|ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|DR|DRIVE)\s+',
                    '',
                    s,
                )
                s = re.sub(r'[^\w\s]', ' ', s)
                return re.sub(r'\s+', ' ', s).strip()

            if hasattr(self, 'chk_complete_streets') and self.chk_complete_streets.isChecked():
                proj_len_by_name = defaultdict(float)
                for u, v in project_edges:
                    rid = G[u][v].get('street_id')
                    if rid is not None:
                        f_r = streets_layer_proj.getFeature(rid)
                        if 'name' in f_r.fields().names() and f_r['name']:
                            n_norm = normalize_street_name(f_r['name'])
                            if n_norm:
                                proj_len_by_name[n_norm] += math.hypot(u[0] - v[0], u[1] - v[1])

                base_len_by_name = defaultdict(float)
                edges_by_name = defaultdict(list)
                for u, v, data in G.edges(data=True):
                    rid = data.get('street_id')
                    if rid is not None:
                        f_r = streets_layer_proj.getFeature(rid)
                        if 'name' in f_r.fields().names() and f_r['name']:
                            n_norm = normalize_street_name(f_r['name'])
                            if n_norm:
                                base_len_by_name[n_norm] += math.hypot(u[0] - v[0], u[1] - v[1])
                                edges_by_name[n_norm].append((u, v))

                min_pct = self.spin_pct_complete.value() / 100.0
                cap_ext = self.chk_limit_ext.isChecked()
                max_added_m = self.spin_max_ext_complete.value()

                for n_norm, proj_len in proj_len_by_name.items():
                    base_len = base_len_by_name.get(n_norm, 0.0)
                    if not (base_len > 0 and (proj_len / base_len) >= min_pct):
                        continue

                    adj_street = defaultdict(list)
                    for u, v in edges_by_name[n_norm]:
                        dist_uv = math.hypot(u[0] - v[0], u[1] - v[1])
                        adj_street[u].append((v, dist_uv))
                        adj_street[v].append((u, dist_uv))

                    connected_nodes = set()
                    for u, v in project_edges:
                        if u in adj_street:
                            connected_nodes.add(u)
                        if v in adj_street:
                            connected_nodes.add(v)

                    queue = deque(connected_nodes)
                    visited = set(connected_nodes)
                    added_len = 0.0

                    while queue:
                        curr = queue.popleft()
                        for neighbor, dist_uv in adj_street[curr]:
                            exists = (curr, neighbor) in project_edges or (neighbor, curr) in project_edges
                            if not exists:
                                if cap_ext and (added_len + dist_uv) > max_added_m:
                                    continue
                                project_edges.add((curr, neighbor))
                                added_len += dist_uv

                            if neighbor not in visited:
                                visited.add(neighbor)
                                queue.append(neighbor)

            edges_by_street = defaultdict(list)
            ref_feat_by_group = {}

            for u, v in project_edges:
                street_id = G[u][v].get('street_id')
                seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(u[0], u[1]), QgsPointXY(v[0], v[1])])

                group_key = f"ID_{street_id}"
                if street_id is not None:
                    f_temp = streets_layer_proj.getFeature(street_id)
                    if 'name' in f_temp.fields().names() and f_temp['name']:
                        norm_name = normalize_street_name(f_temp['name'])
                        if norm_name:
                            group_key = f"NAME_{norm_name}"
                            if group_key not in ref_feat_by_group:
                                ref_feat_by_group[group_key] = f_temp

                    if group_key not in ref_feat_by_group:
                        ref_feat_by_group[group_key] = f_temp

                edges_by_street[group_key].append(seg_geom)

            planned_network_layer = QgsVectorLayer(
                f"MultiLineString?crs={project_crs.authid()}", "PLANNED_NETWORK_BY_STREET", "memory"
            )
            prov_rf = planned_network_layer.dataProvider()

            col_order = ['name', 'alt_name', 'highway', 'surface', 'lanes', 'access', 'bridge']
            orig_fields = {f.name(): f for f in streets_layer_proj.fields()}

            ordered_fields = [orig_fields[col] for col in col_order if col in orig_fields]
            present_cols = [f.name() for f in ordered_fields]

            final_fields = list(ordered_fields)
            final_fields.append(QgsField("PLANNED_LEN_M", QVariant.Double, "double", 12, 2))
            final_fields.append(QgsField("ACTIVE_DEVS", QVariant.Int, "integer", 10))
            final_fields.append(QgsField("DENSITY_U_M", QVariant.Double, "double", 12, 2))
            final_fields.append(QgsField("RANK_SCORE", QVariant.Double, "double", 12, 2))

            prov_rf.addAttributes(final_fields)
            planned_network_layer.updateFields()

            def index_demand_layer(orig_layer):
                if not orig_layer or not isinstance(orig_layer, QgsVectorLayer):
                    return None, None, None

                lyr_proj = run("native:reprojectlayer", {
                    'INPUT': orig_layer,
                    'TARGET_CRS': project_crs,
                    'OUTPUT': 'memory:'
                })['OUTPUT']

                addr_candidates = ['street', 'address', 'logradouro', 'endereco', 'rua', 'nome_rua', 'via', 'name']
                addr_col = next((f.name() for f in lyr_proj.fields() if f.name().lower() in addr_candidates), None)

                idx = QgsSpatialIndex(lyr_proj.getFeatures())
                return lyr_proj, idx, addr_col

            lyr_res = self.cbo_residential.currentData()
            units_field = self.cbo_units_field.currentData() or self.cbo_units_field.currentText()
            lyr_com = self.cbo_commercial.currentData()
            lyr_dev = self.cbo_developments.currentData()

            res_proj, idx_res, col_addr_res = index_demand_layer(lyr_res)
            com_proj, idx_com, col_addr_com = index_demand_layer(lyr_com)
            dev_proj, idx_dev, col_addr_dev = index_demand_layer(lyr_dev)

            demand_per_unit = float(self.input_unit_demand.text().replace(',', '.'))
            demand_commercial = float(self.input_comm_demand.text().replace(',', '.'))

            avg_dev_units = 10.0
            if res_proj and units_field and units_field in res_proj.fields().names():
                unit_vals = [
                    float(f[units_field])
                    for f in res_proj.getFeatures()
                    if f[units_field] is not None and float(f[units_field]) > 0
                ]
                if unit_vals:
                    avg_dev_units = sum(unit_vals) / len(unit_vals)

            street_feats = []
            total_length_m = 0.0
            unique_connected_customers = set()

            for group_key, geom_list in edges_by_street.items():
                street_geom = QgsGeometry.unaryUnion(geom_list)
                if not street_geom or street_geom.isEmpty():
                    continue

                len_m = street_geom.length()
                total_length_m += len_m

                f_orig = ref_feat_by_group.get(group_key)
                curr_street_name = ""
                if f_orig and 'name' in f_orig.fields().names():
                    curr_street_name = normalize_street_name(f_orig['name'])

                search_buffer = street_geom.buffer(
                    50.0, 5, QgsGeometry.EndCapStyle.Flat, QgsGeometry.JoinStyle.Round, 2.0
                )
                search_bbox = search_buffer.boundingBox()

                def filter_street_points(lyr_proj, spatial_idx, addr_col):
                    valid_pts = []
                    if not lyr_proj or not spatial_idx:
                        return valid_pts
                    for fid in spatial_idx.intersects(search_bbox):
                        feat = lyr_proj.getFeature(fid)
                        if search_buffer.contains(feat.geometry()):
                            if addr_col and feat[addr_col] and curr_street_name:
                                pt_addr = normalize_street_name(feat[addr_col])
                                if pt_addr and (pt_addr in curr_street_name or curr_street_name in pt_addr):
                                    valid_pts.append(feat)
                            elif not curr_street_name or not addr_col:
                                valid_pts.append(feat)
                    return valid_pts

                pts_res = filter_street_points(res_proj, idx_res, col_addr_res)
                res_demand = 0.0
                for f_res in pts_res:
                    units = float(f_res[units_field]) if (units_field and f_res[units_field]) else 1.0
                    res_demand += units * demand_per_unit
                    unique_connected_customers.add(('RES', f_res.id()))

                pts_com = filter_street_points(com_proj, idx_com, col_addr_com)
                com_demand = len(pts_com) * demand_commercial
                for f_com in pts_com:
                    unique_connected_customers.add(('COM', f_com.id()))

                pts_dev = filter_street_points(dev_proj, idx_dev, col_addr_dev)
                dev_count = len(pts_dev)
                dev_demand = dev_count * avg_dev_units * demand_per_unit
                for f_dev in pts_dev:
                    unique_connected_customers.add(('DEV', f_dev.id()))

                street_demand = res_demand + com_demand + dev_demand
                density_u_m = (street_demand / len_m) if len_m > 0 else 0.0

                weighted_potential = street_demand / math.sqrt(max(len_m, 50.0))
                rank_score = weighted_potential * (1.0 + (dev_count * 0.25))

                if len_m < 25.0:
                    rank_score = 0.0

                feat_rf = QgsFeature(planned_network_layer.fields())
                feat_rf.setGeometry(street_geom)

                if f_orig is not None:
                    attrs = [f_orig[col] for col in present_cols]
                    attrs.append(round(len_m, 2))
                    attrs.append(dev_count)
                    attrs.append(round(density_u_m, 2))
                    attrs.append(rank_score)
                    feat_rf.setAttributes(attrs)

                street_feats.append(feat_rf)

            idx_score = planned_network_layer.fields().indexOf("RANK_SCORE")
            score_vals = [f.attribute(idx_score) for f in street_feats if f.attribute(idx_score) is not None]
            max_score = max(score_vals) if score_vals else 0.0

            if max_score > 0:
                for f in street_feats:
                    raw_val = f.attribute(idx_score) or 0.0
                    norm_100 = round((raw_val / max_score) * 100.0, 1)
                    f.setAttribute(idx_score, norm_100)

            prov_rf.addFeatures(street_feats)
            planned_network_layer.updateExtents()

            # FINANCIAL METRICS
            total_connected_customers = len(unique_connected_customers)
            unit_conn_cost = self.spin_connection_cost.value()
            network_capex = total_length_m * cost_per_m
            connections_capex = total_connected_customers * unit_conn_cost
            estimated_capex = network_capex + connections_capex

            global_density = total_demand_units / total_length_m if total_length_m > 0 else 0
            unit_capex_cost = estimated_capex / total_demand_units if total_demand_units > 0 else 0
            gross_annual_revenue = total_demand_units * tariff_per_unit
            revenue_per_m = gross_annual_revenue / total_length_m if total_length_m > 0 else 0
            simple_payback_yrs = estimated_capex / gross_annual_revenue if gross_annual_revenue > 0 else 0

            # FEASIBILITY SUMMARY LAYER
            report_layer = QgsVectorLayer("Point", "📊 FEASIBILITY_REPORT", "memory")
            prov_rel = report_layer.dataProvider()

            prov_rel.addAttributes([
                QgsField("CALC_DATE", QMetaType.Type.QString),
                QgsField("AVG_RES_UNITS", QMetaType.Type.Double, "double", 10, 2),
                QgsField("TOTAL_ANNUAL_DEMAND", QMetaType.Type.Double, "double", 15, 2),
                QgsField("NETWORK_LENGTH_M", QMetaType.Type.Double, "double", 15, 2),
                QgsField("ESTIMATED_CAPEX", QMetaType.Type.Double, "double", 15, 2),
                QgsField("LINEAR_DENSITY", QMetaType.Type.Double, "double", 10, 2),
                QgsField("UNIT_CAPEX_COST", QMetaType.Type.Double, "double", 10, 2),
                QgsField("GROSS_ANNUAL_REV", QMetaType.Type.Double, "double", 15, 2),
                QgsField("REV_PER_METER", QMetaType.Type.Double, "double", 10, 2),
                QgsField("PAYBACK_YEARS", QMetaType.Type.Double, "double", 10, 2),
            ])
            report_layer.updateFields()

            f_rel = QgsFeature(report_layer.fields())
            f_rel.setAttribute("CALC_DATE", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            f_rel.setAttribute("AVG_RES_UNITS", round(avg_res_units, 2))
            f_rel.setAttribute("TOTAL_ANNUAL_DEMAND", round(total_demand_units, 2))
            f_rel.setAttribute("NETWORK_LENGTH_M", round(total_length_m, 2))
            f_rel.setAttribute("ESTIMATED_CAPEX", round(estimated_capex, 2))
            f_rel.setAttribute("LINEAR_DENSITY", round(global_density, 2))
            f_rel.setAttribute("UNIT_CAPEX_COST", round(unit_capex_cost, 2))
            f_rel.setAttribute("GROSS_ANNUAL_REV", round(gross_annual_revenue, 2))
            f_rel.setAttribute("REV_PER_METER", round(revenue_per_m, 2))
            f_rel.setAttribute("PAYBACK_YEARS", round(simple_payback_yrs, 2))

            prov_rel.addFeatures([f_rel])
            report_layer.updateExtents()

            res_html = f"""
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background-color: #1e293b;
                    color: #f8fafc;
                    margin: 0;
                    padding: 12px;
                }}
                .header {{
                    background: linear-gradient(135deg, #1e3a8a, #3b82f6);
                    color: white;
                    padding: 14px;
                    border-radius: 8px;
                    text-align: center;
                    font-size: 16px;
                    font-weight: bold;
                    margin-bottom: 16px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
                }}
                .section-title {{
                    font-size: 13px;
                    font-weight: bold;
                    color: #38bdf8;
                    border-bottom: 2px solid #0284c7;
                    padding-bottom: 4px;
                    margin: 18px 0 10px 0;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 6px;
                    background-color: #ffffff;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                }}
                th {{
                    background-color: #0f172a;
                    color: #f1f5f9;
                    font-size: 11px;
                    text-align: left;
                    padding: 10px;
                    font-weight: bold;
                    text-transform: uppercase;
                }}
                td {{
                    padding: 10px;
                    font-size: 12px;
                    border-top: 1px solid #e2e8f0;
                    color: #0f172a;
                    background-color: #ffffff;
                }}
                tr:nth-child(even) td {{
                    background-color: #f8fafc;
                }}
                .val-highlight {{
                    color: #15803d;
                    font-weight: bold;
                }}
                .val-alert {{
                    color: #b91c1c;
                    font-weight: bold;
                }}
                .footer-note {{
                    font-size: 11px;
                    color: #94a3b8;
                    font-style: italic;
                    margin-top: 14px;
                }}
            </style>
            <body>
                <div class='header'>📊 NETWORK EXPANSION & FEASIBILITY REPORT</div>

                <div class='section-title'>📌 Executive Project Summary</div>
                <table>
                    <tr><th>Project Metric</th><th>Calculated Value</th></tr>
                    <tr><td><b>Avg. Units / Residential Building:</b></td><td><b>{avg_res_units:.1f} units</b></td></tr>
                    <tr><td><b>Viable Annual Demand:</b></td><td><b>{total_demand_units:,.2f} units/yr</b></td></tr>
                    <tr><td><b>Planned Network Length:</b></td><td><b>{total_length_m:,.2f} m</b> ({total_length_m/1000:.2f} km)</td></tr>
                    <tr><td><b>Estimated Total CAPEX:</b></td><td><span class='val-alert'>$ {estimated_capex:,.2f}</span></td></tr>
                </table>

                <div class='section-title'>💰 Financial Analysis (Tariff: $ {tariff_per_unit:.4f}/unit)</div>
                <table>
                    <tr><th>Financial Indicator</th><th>Calculated Value</th></tr>
                    <tr><td><b>Estimated Gross Annual Revenue:</b></td><td><span class='val-highlight'>$ {gross_annual_revenue:,.2f} / yr</span></td></tr>
                    <tr><td><b>Annual Revenue per Meter:</b></td><td><b>$ {revenue_per_m:,.2f} / m / yr</b></td></tr>
                    <tr><td><b>Simple Gross Payback:</b></td><td><b>{simple_payback_yrs:.2f} years</b> ({simple_payback_yrs*12:.1f} months)</td></tr>
                </table>

                <div class='section-title'>🏆 Efficiency Indicators</div>
                <table>
                    <tr><th>Performance Metric</th><th>Index</th></tr>
                    <tr><td><b>Global Demand Density:</b></td><td><b>{global_density:,.2f} units/m</b></td></tr>
                    <tr><td><b>Unit CAPEX per Demand Unit:</b></td><td><b>$ {unit_capex_cost:,.2f} / unit</b></td></tr>
                </table>
                <p class='footer-note'>* Summary saved to layer <b>'📊 FEASIBILITY_REPORT'</b>.</p>
            </body>
            """

            doc = QTextDocument()
            doc.setHtml(res_html)
            doc.setTextWidth(480)

            img_size = QSize(int(doc.idealWidth()), int(doc.size().height()))
            pixmap = QPixmap(img_size)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            doc.drawContents(painter)
            painter.end()

            img_path = os.path.join(tempfile.gettempdir(), "feasibility_report.png").replace("\\", "/")
            pixmap.save(img_path, "PNG")

            QgsProject.instance().addMapLayer(planned_network_layer)
            QgsProject.instance().addMapLayer(viable_centroids)
            QgsProject.instance().addMapLayer(report_layer)

            dock = QDockWidget("📊 Feasibility Report", iface.mainWindow())
            lbl_img = QLabel()
            lbl_img.setPixmap(pixmap)
            scroll = QScrollArea()
            scroll.setWidget(lbl_img)
            dock.setWidget(scroll)

            iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

            self.progress_bar.setValue(100)
            self.log("=== PROCESSING COMPLETED SUCCESSFULLY ===")

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("📊 Feasibility Results")
            msg_box.setText(res_html)
            msg_box.exec()

        except Exception as e:
            self.log(f"❌ ERROR: {str(e)}")
            QMessageBox.critical(self, "❌ Error", f"An error occurred during processing:\n{str(e)}")
        finally:
            self.progress_bar.setVisible(False)


if __name__ == "__main__":
    tool = SpatialNetworkExpansionPlanner()
    tool.exec()