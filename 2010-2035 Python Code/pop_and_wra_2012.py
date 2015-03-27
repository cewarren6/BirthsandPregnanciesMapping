import arcpy
import os
import fnmatch
import logging
import tempfile
import csv
import xml.etree.ElementTree as ET


def findPopRast(popRastDir, iso3, grumpPopRast, countryBoundaries, outDir):
    # Look for tif files
    matches = []
    for root, dirnames, filenames in os.walk(popRastDir + "\\" + iso3):
      for filename in fnmatch.filter(filenames, '*.tif'):
          matches.append(os.path.join(root, filename))
    # If match found return path
    if len(matches) == 1:
        return matches[0]
    # If no matches, clip grump population raster
    elif len(matches) == 0:
        logging.warning("No WorldPop raster available. Using GRUMP raster instead.")

        arcpy.CheckOutExtension("Spatial")
        old_workspace = arcpy.env.workspace
        old_scratchWorkspace = arcpy.env.scratchWorkspace        
        tmpdir = tempfile.mkdtemp()
        arcpy.env.workspace = tmpdir
        arcpy.env.scratchWorkspace = tmpdir
        defaultCellSize = arcpy.env.cellSize

        try:
            arcpy.FeatureClassToFeatureClass_conversion(countryBoundaries,
                                                        "in_memory",
                                                        "countryBoundary",
                                                        """ iso_alpha3 = '%s' """ % (iso3,))
            grumpPopClip = arcpy.sa.ExtractByMask(grumpPopRast, "in_memory/countryBoundary")

            currentCellSize = (grumpPopClip.meanCellHeight + grumpPopClip.meanCellWidth) / float(2)
            newCellSize = currentCellSize / float(10)            
            arcpy.env.cellSize = newCellSize
            grumpPop100m = grumpPopClip / float(100)

            arcpy.CopyRaster_management(grumpPop100m, os.path.join(outDir, "pop2010%s.tif" % iso3))
            return os.path.join(outDir, "pop2010%s.tif" % iso3)

        finally:
            arcpy.env.cellSize = defaultCellSize
            arcpy.Delete_management("in_memory")
            arcpy.Delete_management(tmpdir)
            arcpy.env.workspace = old_workspace
            arcpy.env.scratchWorkspace = old_scratchWorkspace
            arcpy.CheckInExtension("Spatial")
    else:
        logging.error("Multiple population rasters found")


def growthRatesJoin(urbanGrowthFc, ruralGrowthFc, countryBoundaries, urbanAreasShp, iso3, outGDB):

    try:
        # Extract polygons by country iso
        arcpy.FeatureClassToFeatureClass_conversion(countryBoundaries,
                                                    "in_memory",
                                                    "countryBoundary",
                                                    """ iso_alpha3 = '%s' """ % (iso3,))
        arcpy.FeatureClassToFeatureClass_conversion(urbanAreasShp,
                                                    "in_memory",
                                                    "urban_extract",
                                                    """ ISO3 = '%s' """ % (iso3,))
        # Union of urban and boundary polygons
        arcpy.Union_analysis(["in_memory/countryBoundary", "in_memory/urban_extract"],
                             "in_memory/countryUrbanRural")
        # Separate urban and rural polygons
        arcpy.FeatureClassToFeatureClass_conversion("in_memory/countryUrbanRural",
                                                    "in_memory",
                                                    "countryUrban",
                                                    """ ONES = 1 """)
        arcpy.FeatureClassToFeatureClass_conversion("in_memory/countryUrbanRural",
                                                    "in_memory",
                                                    "countryRural",
                                                    """ ONES = 0 """)
        # Join growth rates data
        arcpy.JoinField_management("in_memory/countryUrban", "iso_alpha2", urbanGrowthFc, "ISO2", ["Growth20102015"])
        arcpy.JoinField_management("in_memory/countryRural", "iso_alpha2", ruralGrowthFc, "ISO2", ["Growth20102015"])
        # Merge urban and rural data back together
        arcpy.Merge_management(["in_memory/countryUrban", "in_memory/countryRural"], outGDB + "/growthRates%s" % iso3)

    finally:
        # Tidy up
        arcpy.Delete_management("in_memory")

def estimate2012pop(popRast2010Path, outGDB, outDir, iso3):

    arcpy.CheckOutExtension("Spatial")
    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace        
    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir

    try:
        # Get raster cell size
        popRast2010 = arcpy.Raster(popRast2010Path)
        cellSize = (popRast2010.meanCellHeight + popRast2010.meanCellWidth) / float(2)

        # Create raster of growth rates from feature class
        arcpy.PolygonToRaster_conversion(outGDB + "/growthRates%s" % iso3,
                                         "Growth20102015",
                                         "growth20102015.tif",
                                         cell_assignment="MAXIMUM_AREA",
                                         cellsize=cellSize)

        pop2012 = popRast2010 * arcpy.sa.Exp(arcpy.Raster("growth20102015.tif") / 100 * 2)
        arcpy.CopyRaster_management(pop2012, os.path.join(outDir, "%s2012unadjustedPop.tif" % iso3), pixel_type="32_BIT_FLOAT")

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace
        arcpy.CheckInExtension("Spatial")

def getUnPopEst(unPopEstCsv, isoNum):
    # Retrieve UN estimate of population from csv
    with open(unPopEstCsv, 'rb') as csvFile:
        reader = csv.reader(csvFile)
        for row in reader:
            if row[0] == isoNum and row[3] == "Medium" and row[4] == "2012":
                unPop = float(row[8]) * 1000
    return unPop

def getUnWraEst(unPopBySexCsv, isoNum):
    # Retrieve UN estimate of women of reproductive age from csv
    with open(unPopBySexCsv, 'rb') as csvFile:
        reader = csv.reader(csvFile)
        wra = 0
        agebands = ("15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49")
        for row in reader:
            if row[0] == isoNum and row[3] == "Medium" and row[4] == "2012" and row[6] in agebands:
                wra += float(row[10]) * 1000
    return wra


def adjust2012pop(outDir, unPop2012, iso3):

    arcpy.CheckOutExtension("Spatial")
    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace        
    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir

    try:
        unadjustedPopRast = os.path.join(outDir, "%s2012unadjustedPop.tif" % iso3)
        # Calculate total pop
        rasterMask = arcpy.Raster(unadjustedPopRast) * 0
        arcpy.CopyRaster_management(rasterMask, "rasterMask.tif", pixel_type="1_BIT")
        arcpy.BuildRasterAttributeTable_management("rasterMask.tif", "Overwrite")
        arcpy.sa.ZonalStatisticsAsTable("rasterMask.tif", "VALUE", unadjustedPopRast, "in_memory/zonalStats", "DATA", "SUM")
        with arcpy.da.SearchCursor("in_memory/zonalStats", "SUM") as c:
            for row in c:
                unadjustedTotal = row[0]

        # Calculate adjusted population raster
        adjustmentFactor = unPop2012 / unadjustedTotal
        adjustedPop = arcpy.sa.Times(unadjustedPopRast, adjustmentFactor)
        arcpy.CopyRaster_management(adjustedPop, os.path.join(outDir, "%s2012adjustedPop.tif" % iso3), pixel_type="32_BIT_FLOAT")

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace
        arcpy.CheckInExtension("Spatial")

def estimateWra2012(outDir, ageFc, iso3, unWra2012, unPop2012):

    arcpy.CheckOutExtension("Spatial")
    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace        
    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir

    try:
        # Get raster cell size
        popRast = arcpy.Raster(os.path.join(outDir, "%s2012adjustedPop.tif" % iso3))
        cellSize = (popRast.meanCellHeight + popRast.meanCellWidth) / float(2)

        # Extract subnational age breakdowns for selected country
        arcpy.FeatureClassToFeatureClass_conversion(ageFc,
                                                    "in_memory",
                                                    "age_extract",
                                                    """ ISO = '%s' """ % (iso3,))

        # If no features found, use national data from spreadsheet
        if int(arcpy.GetCount_management("in_memory/age_extract").getOutput(0)) == 0:
            logging.warning("No sub-national age bands, using national data")
            wocba = float(unWra2012) / float(unPop2012)
            wra2012 = wocba * popRast
            

        else:
            arcpy.PolygonToRaster_conversion("in_memory/age_extract",
                                 "WOCBA",
                                 "wocba.tif",
                                 cell_assignment="MAXIMUM_AREA",
                                 cellsize=cellSize)

            wra2012 = arcpy.Raster("wocba.tif") * popRast

        arcpy.CopyRaster_management(wra2012, os.path.join(outDir, "%s2012unadjustedWRA.tif" % iso3), pixel_type="32_BIT_FLOAT")


    finally:
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace
        arcpy.CheckInExtension("Spatial")

def adjust2012wra(outDir, unWra2012, iso3):

    arcpy.CheckOutExtension("Spatial")
    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace        
    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir

    try:
        unadjustedWraRast = os.path.join(outDir, "%s2012unadjustedWRA.tif" % iso3)
        # Calculate total wra
        rasterMask = arcpy.Raster(unadjustedWraRast) * 0
        arcpy.CopyRaster_management(rasterMask, "rasterMask.tif", pixel_type="1_BIT")
        arcpy.BuildRasterAttributeTable_management("rasterMask.tif", "Overwrite")
        arcpy.sa.ZonalStatisticsAsTable("rasterMask.tif", "VALUE", unadjustedWraRast, "in_memory/zonalStats", "DATA", "SUM")
        with arcpy.da.SearchCursor("in_memory/zonalStats", "SUM") as c:
            for row in c:
                unadjustedTotal = row[0]

        # Calculate adjusted WRA raster
        adjustmentFactor = unWra2012 / unadjustedTotal
        adjustedWra = arcpy.sa.Times(unadjustedWraRast, adjustmentFactor)
        arcpy.CopyRaster_management(adjustedWra, os.path.join(outDir, "%s2012adjustedWRA.tif" % iso3), pixel_type="32_BIT_FLOAT")

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace
        arcpy.CheckInExtension("Spatial")

def urbanAndRuralPopAndWra(outDir, countryBoundaries, urbanAreasShp, iso3):

    arcpy.CheckOutExtension("Spatial")    

    try:
        # Extract polygons for selected country
        arcpy.FeatureClassToFeatureClass_conversion(countryBoundaries,
                                                    "in_memory",
                                                    "countryExtract",
                                                    """ iso_alpha3 = '%s' """ % iso3)

        arcpy.FeatureClassToFeatureClass_conversion(urbanAreasShp,
                                                    "in_memory",
                                                    "urban_extract",
                                                    """ ISO3 = '%s' """ % iso3)
        # Identity of urban and admin boundary polygons
        arcpy.Identity_analysis(countryBoundaries, "in_memory/urban_extract", "in_memory/countryUrbanRural", "NO_FID")

        # Aggregate polygons
        arcpy.Dissolve_management("in_memory/countryUrbanRural", "in_memory/zones", ["ONES"])

        # Create urbanOrRural field for zonal statistics
        arcpy.AddField_management("in_memory/zones", "urbanOrRural", "TEXT")
        with arcpy.da.UpdateCursor("in_memory/zones", ["ONES", "urbanOrRural"]) as upCur:
            for row in upCur:
                if row[0] == 1:
                    row[1] = "URBAN"
                else:
                    row[1] = "RURAL"                    
                upCur.updateRow(row)

        # Remove "ONES" field as no longer needed
        arcpy.DeleteField_management("in_memory/zones", "ONES")

        # Calculate total urban and rural populations
        arcpy.sa.ZonalStatisticsAsTable("in_memory/zones", "urbanOrRural", os.path.join(outDir, "%s2012adjustedPop.tif" % iso3), "in_memory/zonalStatsPop", "DATA", "SUM")
        urbanPop = 0
        ruralPop = 0
        with arcpy.da.SearchCursor("in_memory/zonalStatsPop", ["urbanOrRural", "SUM"]) as c:
            for row in c:
                if row[0] == "URBAN":
                    urbanPop += row[1]
                elif row[0] == "RURAL":
                    ruralPop += row[1]

        # Calculate total urban and rural women of reproducive age
        arcpy.sa.ZonalStatisticsAsTable("in_memory/zones", "urbanOrRural", os.path.join(outDir, "%s2012adjustedWRA.tif" % iso3), "in_memory/zonalStatsWra", "DATA", "SUM")
        urbanWra = 0
        ruralWra = 0
        with arcpy.da.SearchCursor("in_memory/zonalStatsWra", ["urbanOrRural", "SUM"]) as c:
            for row in c:
                if row[0] == "URBAN":
                    urbanWra += row[1]
                elif row[0] == "RURAL":
                    ruralWra += row[1]

        return (urbanPop, ruralPop, urbanWra, ruralWra)

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.CheckInExtension("Spatial")


if __name__ == "__main__":

    # Input paths
    countryListXml = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/country_list.xml" # List of countries to process

    popRastDir = "C:\\BirthsandPregnancies\\WorldPop" # Population raster directory
    grumpPopRast = "C:/BirthsandPregnancies/WorldPop/AfriPop_demo_2015_1km/ap15v4_TOTAL_adj.tif" # GRUMP population raster
    countryBoundaries = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/LSIB-WSV/lsib-wsv.gdb/detailed_world_polygons" # Country boundary polygons
    urbanGrowthFc = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/Growth Rates/GrowthRates.gdb/Urban" # Urban growth rates
    ruralGrowthFc = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/Growth Rates/GrowthRates.gdb/Rural" # Rural growth rates
    urbanAreasShp = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/GRUMP/af_as_lac_urban_Mano.shp" # Urban area extents
    unPopEstCsv = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/WPP2012_DB02_POPULATIONS_ANNUAL.CSV" # UN Population Estimates
    unPopBySexCsv = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/WPP2012_DB04_POPULATION_BY_SEX_ANNUAL.CSV" # UN Population estimates by age and sex
    ageFc = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/popByAgeGroup.gdb/asia_africa" # Asia/Africa Sub-national breakdown of population by age

    # Output paths
    outDir = "C:/BirthsandPregnancies/results/raster" # Raster output directory
    outGDB = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/results/test/result.gdb" # Vector output geodatabase
    outCsvFile = r"C:\BirthsandPregnancies\results\csv\popAndWra2012.csv" # Output CSV file

    # Set up logging
    logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

    # Allow files to be overwritten
    arcpy.env.overwriteOutput = True

    # Loop through countries listed within xml file
    countryList = ET.parse(countryListXml).getroot()

    # Create CSV writer for output data
    with open(outCsvFile, 'ab') as csvFile:
        csvWriter = csv.writer(csvFile)

        for country in countryList.findall("country"):
            countryName = country.find("name").text
            iso2 = country.find("iso2").text
            iso3 = country.find("iso3").text
            isoNum = country.find("isoNum").text

            logging.info("Processing %s" % countryName)

            # Find population raster
            logging.info("Retrieving population raster")
            popRast2010Path = findPopRast(popRastDir, iso3, grumpPopRast, countryBoundaries, outDir)


            # Join growth rates to country boundaries
            logging.info("Joining growth rates to country boundaries")
            growthRatesJoin(urbanGrowthFc, ruralGrowthFc, countryBoundaries, urbanAreasShp, iso3, outGDB)

            # Estimate population for 2012
            logging.info("Estimating population for 2012")
            estimate2012pop(popRast2010Path, outGDB, outDir, iso3)

            # Get UN estimate of population
            logging.info("Retrieving UN population estimate from csv file")
            unPop2012 = getUnPopEst(unPopEstCsv, isoNum)

            # Get UN estimate of women of reproductive age
            logging.info("Retrieving UN estimate of women of reproductive age from csv file")
            unWra2012 = getUnWraEst(unPopBySexCsv, isoNum)

            # Adjust population estimates to match UN figures
            logging.info("Adjusting population estimate to match UN figures")
            adjust2012pop(outDir, unPop2012, iso3)

            # Estimate women of reproductive age
            logging.info("Estimating number of women of reproductive age")
            estimateWra2012(outDir, ageFc, iso3, unWra2012, unPop2012)

            # Adjust women of reproductive age total to match UN figures
            logging.info("Adjusting estimate of women of reproductive age to match UN figures")
            adjust2012wra(outDir, unWra2012, iso3)

            # Calculate total urban and rural population and women of reproductive age
            logging.info("Calculating total urban and rural population and women of reproductive age")
            urbanPop, ruralPop, urbanWra, ruralWra = urbanAndRuralPopAndWra(outDir, countryBoundaries, urbanAreasShp, iso3)

            # Write outputs to csv
            logging.info("Writing output data to csv file")
            csvWriter.writerow([iso3, countryName, urbanPop, ruralPop, urbanWra, ruralWra])