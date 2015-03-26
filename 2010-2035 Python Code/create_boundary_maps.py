import logging
import mapnik
import xml.etree.ElementTree as ET
import os
import subprocess
import tempfile

# Set up logging
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

# Parameters
countryListXml = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/Python Code/country_list.xml"
dbPath = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/adminBoundaries/adminBoundaries.sqlite"
epsDir = "C:/BirthsAndPregnanciesMapping/results/eps"
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

# Loop through countries in xml
countryList = ET.parse(countryListXml).getroot()
for country in countryList.findall("country"):
    name = country.find("name").text
    iso3 = country.find("iso3").text

    logging.info("Processing %s" % name)

    # Create Datasource
    query = '(SELECT * FROM adminboundaries WHERE iso3 = "%s")' % iso3
    datasource = mapnik.SQLite(file=dbPath, table=query, geometry_field="Geometry", key_field="PK_UID", use_spatial_index=False)

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
    outPsPath = os.path.join(tempfile.gettempdir(), "%sadminBoundaries.ps" % iso3)
    mapnik.render_to_file(map, outPsPath)

    # Convert postscript to EPS file using ghostscript
    outEpsPath = os.path.join(epsDir, "/%sadminBoundaries.eps" % iso3)
    subprocess.call(["C:/Program Files/gs/gs9.15/bin/gswin64c",
                     "-dDEVICEWIDTHPOINTS=%s" % width,
                     "-dDEVICEHEIGHTPOINTS=%s" % height,
                     "-sDEVICE=eps2write",
                     "-o",
                     outEpsPath,
                     outPsPath])

    # Delete temporary file
    os.remove(outPsPath)
