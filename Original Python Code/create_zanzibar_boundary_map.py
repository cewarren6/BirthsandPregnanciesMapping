import logging
import mapnik
import xml.etree.ElementTree as ET
import os
import subprocess
import tempfile

# Set up logging
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

# Parameters
shpPath = "C:/Projects/BirthsAndPregnanciesMapping/data/2014-04-24/Zanzibar/Zanzibar.shp"
epsDir = "C:/Projects/BirthsAndPregnanciesMapping/results/eps"
max_img_size = 1000 # Max width or height of output image

# Create style
stroke = mapnik.Stroke()
stroke.color = mapnik.Color(0,0,0)
stroke.width = 1.0
symbolizer = mapnik.LineSymbolizer(stroke)
rule = mapnik.Rule()
rule.symbols.append(symbolizer)
style = mapnik.Style()
style.rules.append(rule)

# Create Datasource
datasource = mapnik.Shapefile(file=shpPath)

# Create layer
layer = mapnik.Layer("boundaries")
layer.datasource = datasource
layer.styles.append("boundariesStyle")

# Calculate image output size
envelope = datasource.envelope()
dLong = envelope.maxx - envelope.minx
dLat = envelope.maxy - envelope.miny
aspectRatio = dLong / dLat

if dLong > dLat:
    width = max_img_size
    height = int(width / aspectRatio)
elif dLat > dLong:
    height = max_img_size
    width = int(aspectRatio * height)
else:
    width = max_img_size
    height = max_img_size

# Create map
map = mapnik.Map(width, height)
map.append_style("boundariesStyle", style)
map.layers.append(layer)
map.zoom_all()

# Output to temporary postscript file
outPsPath = os.path.join(tempfile.gettempdir(), "ZanzibarAdminBoundaries.ps")
mapnik.render_to_file(map, outPsPath)

# Convert postscript to EPS file using ghostscript
outEpsPath = os.path.join(epsDir, "ZanzibarAdminBoundaries.eps")
subprocess.call(["C:/Program Files/gs/gs9.14/bin/gswin64c",
                 "-dDEVICEWIDTHPOINTS=%s" % width,
                 "-dDEVICEHEIGHTPOINTS=%s" % height,
                 "-sDEVICE=eps2write",
                 "-o",
                 outEpsPath,
                 outPsPath])

# Delete temporary file
os.remove(outPsPath)
