import os
import fnmatch
import arcpy

inDir = "C:/BirthsandPregnancies/WorldPop/"
outDir = "C:/BirthsandPregnancies/WorldPop/POP_compressed/"

matches = []
for root, dirnames, filenames in os.walk(inDir):
  for filename in fnmatch.filter(filenames, '*.tif'):
      matches.append(os.path.join(root[len(inDir):], filename))

for match in matches:
    inRast = os.path.normpath(os.path.join(inDir, match))
    outRast = os.path.normpath(os.path.join(outDir, match))
    newDir = os.path.dirname(outRast)
    if not os.path.exists(newDir):
        os.makedirs(newDir)
    print "Compressing " + inRast
    arcpy.CopyRaster_management(inRast, outRast)