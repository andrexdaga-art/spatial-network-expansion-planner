from datetime import datetime

from processing import run
from qgis.core import (
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class HeatmapGeneratorTool(QDialog):
    """
    SPATIAL DEMAND HEATMAP GENERATOR (KDE / KERNEL DENSITY ESTIMATION)
    ------------------------------------------------------------------
    Generates a continuous in-memory demand density raster with non-linear
    pseudo-color styling to highlight both regional and local demand hubs.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Demand Density Heatmap Generator (KDE)")
        self.setMinimumWidth(550)
        self.setMinimumHeight(480)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)

        self.setup_ui()
        self.setLayout(self.layout)

    def setup_ui(self):
        title_label = QLabel("🔥 SPATIAL DEMAND HEATMAP (KDE)")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        self.layout.addWidget(title_label)

        config_group = QGroupBox("⚙️ Kernel Density Parameters")
        config_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        config_layout = QVBoxLayout()

        # Point layer selection
        layer_layout = QHBoxLayout()
        layer_layout.addWidget(QLabel("Point Layer (Demand / Centroids):"))
        self.cbo_points = QComboBox()
        self.load_point_layers()
        self.cbo_points.currentIndexChanged.connect(self.update_weight_fields)
        layer_layout.addWidget(self.cbo_points)
        config_layout.addLayout(layer_layout)

        # Weight field selection
        field_layout = QHBoxLayout()
        field_layout.addWidget(QLabel("Weight Field (Load / Demand):"))
        self.cbo_weight_field = QComboBox()
        field_layout.addWidget(self.cbo_weight_field)
        config_layout.addLayout(field_layout)

        # Search radius (bandwidth)
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Smoothing Bandwidth / Radius (meters):"))
        self.input_radius = QLineEdit("600.0")
        radius_layout.addWidget(self.input_radius)
        config_layout.addLayout(radius_layout)

        # Output pixel size
        pixel_layout = QHBoxLayout()
        pixel_layout.addWidget(QLabel("Output Pixel Resolution (meters):"))
        self.input_pixel = QLineEdit("30.0")
        pixel_layout.addWidget(self.input_pixel)
        config_layout.addLayout(pixel_layout)

        config_group.setLayout(config_layout)
        self.layout.addWidget(config_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(110)
        self.log_text.setStyleSheet("background-color: #2c3e50; color: #ecf0f1; font-family: Consolas, monospace;")
        self.layout.addWidget(self.log_text)

        self.btn_generate = QPushButton("🔥 Generate Demand Heatmap")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #e67e22; color: white; font-weight: bold;
                padding: 12px; border-radius: 5px; font-size: 14px;
            }
            QPushButton:hover { background-color: #d35400; }
        """)
        self.btn_generate.clicked.connect(self.run_kde)
        self.layout.addWidget(self.btn_generate)

    def load_point_layers(self):
        self.cbo_points.clear()
        self.cbo_points.addItem("-- Select Point Layer --", None)
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.cbo_points.addItem(f"{layer.name()} ({layer.featureCount()} points)", layer)

    def update_weight_fields(self):
        self.cbo_weight_field.clear()
        self.cbo_weight_field.addItem("(Unweighted - Simple Point Density)", None)
        layer = self.cbo_points.currentData()
        if layer:
            for field in layer.fields():
                self.cbo_weight_field.addItem(field.name(), field.name())

            for candidate in ("EST_DEMAND", "CONSUMO_EST"):
                idx = self.cbo_weight_field.findText(candidate)
                if idx >= 0:
                    self.cbo_weight_field.setCurrentIndex(idx)
                    break

    def log(self, message):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def run_kde(self):
        try:
            point_layer = self.cbo_points.currentData()
            weight_field = self.cbo_weight_field.currentData()
            radius_m = float(self.input_radius.text().replace(',', '.'))
            pixel_m = float(self.input_pixel.text().replace(',', '.'))

            if not point_layer:
                QMessageBox.warning(self, "⚠️ Warning", "Please select a valid point layer!")
                return

            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(10)
            self.log("=== STARTING DEMAND HEATMAP GENERATION ===")

            metric_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            self.log("1/2: Reprojecting points to metric CRS (EPSG:3857)...")

            projected_points = run("native:reprojectlayer", {
                'INPUT': point_layer,
                'TARGET_CRS': metric_crs,
                'OUTPUT': 'memory:'
            })['OUTPUT']

            self.progress_bar.setValue(50)
            self.log(f"2/2: Computing Kernel Density Estimation in memory (Radius: {radius_m}m)...")

            kde_params = {
                'INPUT': projected_points,
                'RADIUS': radius_m,
                'PIXEL_SIZE': pixel_m,
                'KERNEL': 0,  # Quartic kernel
                'DECAY': 0,
                'OUTPUT_VALUE': 0,
                'WEIGHT_FIELD': weight_field if weight_field else '',
                'OUTPUT': 'TEMPORARY_OUTPUT',
            }

            temp_raster_path = run("qgis:heatmapkerneldensityestimation", kde_params)['OUTPUT']
            raster_layer = QgsRasterLayer(temp_raster_path, "🔥 DEMAND_HEATMAP_KDE")

            if raster_layer and raster_layer.isValid():
                # Non-linear color ramp to highlight secondary regional demand clusters
                stats = raster_layer.dataProvider().bandStatistics(1)
                max_val = stats.maximumValue if stats.maximumValue > 0 else 1.0

                shader = QgsRasterShader()
                ramp_shader = QgsColorRampShader()
                ramp_shader.setColorRampType(QgsColorRampShader.Type.Interpolated)

                ramp_items = [
                    QgsColorRampShader.ColorRampItem(0, QColor(0, 0, 0, 0), "No Demand"),
                    QgsColorRampShader.ColorRampItem(max_val * 0.01, QColor(255, 255, 178, 160), "Very Low"),
                    QgsColorRampShader.ColorRampItem(max_val * 0.05, QColor(254, 204, 92, 190), "Low Regional"),
                    QgsColorRampShader.ColorRampItem(max_val * 0.15, QColor(253, 141, 60, 210), "Medium Regional"),
                    QgsColorRampShader.ColorRampItem(max_val * 0.40, QColor(227, 26, 28, 230), "High"),
                    QgsColorRampShader.ColorRampItem(max_val, QColor(128, 0, 38, 250), "Critical Core"),
                ]

                ramp_shader.setColorRampItemList(ramp_items)
                shader.setRasterShaderFunction(ramp_shader)

                renderer = QgsSingleBandPseudoColorRenderer(raster_layer.dataProvider(), 1, shader)
                raster_layer.setRenderer(renderer)
                raster_layer.triggerRepaint()

                QgsProject.instance().addMapLayer(raster_layer)

                self.progress_bar.setValue(100)
                self.log("=== HEATMAP GENERATED SUCCESSFULLY ===")
                QMessageBox.information(self, "✅ Success", "Demand heatmap generated with regional cluster styling!")
            else:
                raise Exception("The generated temporary raster layer is invalid.")

        except Exception as e:
            self.log(f"❌ ERROR: {str(e)}")
            QMessageBox.critical(self, "❌ Error", f"An error occurred during heatmap generation:\n{str(e)}")
        finally:
            self.progress_bar.setVisible(False)


if __name__ == "__main__":
    tool_heatmap = HeatmapGeneratorTool()
    tool_heatmap.exec()