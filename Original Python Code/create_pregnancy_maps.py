import mapnik
import os
import fnmatch
import logging

# Set up logging
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

# Parameters
rastDir = "C:/BirthsAndPregnanciesMapping/results/raster"
outPngDir = "C:/BirthsAndPregnanciesMapping/results/png"
max_img_size = 5000 # Max width or height of output image

# Define raster color scheme
c = mapnik.RasterColorizer(mapnik.COLORIZER_DISCRETE, mapnik.Color(54,97,255))
c.add_stop(0, mapnik.COLORIZER_EXACT, mapnik.Color(87,36,255))
c.add_stop(0) # Uses default colour value
c.add_stop(0.1, mapnik.Color(79,159,227))
c.add_stop(0.2, mapnik.Color(0,255,255))
c.add_stop(0.5, mapnik.Color(102,255,77))
c.add_stop(1, mapnik.Color(209,255,105))
c.add_stop(1.5, mapnik.Color(230,230,0))
c.add_stop(2, mapnik.Color(230,153,0))
c.add_stop(2.5, mapnik.Color(255,64,0))
c.add_stop(10, mapnik.Color(168,0,0))

# Create style
style = mapnik.Style()
rule = mapnik.Rule()
symbolizer = mapnik.RasterSymbolizer()
symbolizer.colorizer = c
rule.symbols.append(symbolizer)
style.rules.append(rule)

# Get list of raster paths
rasterPaths = []
for root, dirnames, filenames in os.walk(rastDir):
    for filename in fnmatch.filter(filenames, '*2012pregnancies.tif'):
        rasterPaths.append(os.path.join(root,filename))
        
# Loop through rasters, generate PNG outputs
for rasterPath in rasterPaths:

    outPngPath = os.path.join(outPngDir, os.path.splitext(os.path.basename(rasterPath))[0] + ".png")

    # Create layer
    datasource = mapnik.Gdal(file=rasterPath, band=1)
    layer = mapnik.Layer("pregnancies")
    layer.datasource = datasource
    layer.styles.append("pregnanciesStyle")

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

    # Create map object
    map = mapnik.Map(width, height)
    map.append_style("pregnanciesStyle", style)
    map.layers.append(layer)
    map.zoom_all()

    # Output to file
    logging.info("Creating %s" % outPngPath)
    mapnik.render_to_file(map, outPngPath)
