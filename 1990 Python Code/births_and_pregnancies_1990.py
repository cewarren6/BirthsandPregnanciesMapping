import arcpy
import xlrd
import tempfile
import os
import csv
import logging
import fnmatch
import xlsxwriter
import math
import itertools
import xml.etree.ElementTree as ET


def dhsAsfrJoin(urbanAsfrFc, ruralAsfrFc, iso2, dhsRegionsFc, urbanAreasShp, iso3, outGDB):

    global asfrPresent

    try:
        # Extract ASFR data for selected country
        arcpy.TableToTable_conversion(urbanAsfrFc,
                                      "in_memory",
                                      "urbanAsfrExtract",
                                      """ iso = '%s' """ % iso2)
        arcpy.TableToTable_conversion(ruralAsfrFc,
                                      "in_memory",
                                      "ruralAsfrExtract",
                                      """ iso = '%s' """ % iso2)

        # Check ASFR data exists for selected country
        if int(arcpy.GetCount_management("in_memory/urbanAsfrExtract").getOutput(0)) == 0 and int(arcpy.GetCount_management("in_memory/ruralAsfrExtract").getOutput(0)) == 0:
            asfrPresent = False
            logging.warning("No Age Specific Fertity Rate data available")

        else:
            asfrPresent = True

            # Extract DHS regions and urban polygons for selected country
            arcpy.FeatureClassToFeatureClass_conversion(dhsRegionsFc,
                                                        "in_memory",
                                                        "dhs_extract",
                                                        """ ISO = '%s' """ % iso2)
            arcpy.FeatureClassToFeatureClass_conversion(urbanAreasShp,
                                                        "in_memory",
                                                        "urban_extract",
                                                        """ ISO3 = '%s' """ % iso3)
            # Union of urban and dhs polygons
            arcpy.Union_analysis(["in_memory/dhs_extract", "in_memory/urban_extract"],
                                 "in_memory/dhsUrbanRural")
            # Separate urban and rural polygons
            arcpy.FeatureClassToFeatureClass_conversion("in_memory/dhsUrbanRural",
                                                        "in_memory",
                                                        "dhsUrban",
                                                        """ ONES = 1 """)
            arcpy.FeatureClassToFeatureClass_conversion("in_memory/dhsUrbanRural",
                                                        "in_memory",
                                                        "dhsRural",
                                                        """ ONES = 0 """)

            # Join DHS polygons to ASFR tables
            arcpy.JoinField_management("in_memory/dhsUrban", "REG_ID", "in_memory/urbanAsfrExtract", "REG_ID", ["a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550"])
            arcpy.JoinField_management("in_memory/dhsRural", "REG_ID", "in_memory/ruralAsfrExtract", "REG_ID", ["a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550"])
            
            # Merge rural and urban polygons
            arcpy.Merge_management(["in_memory/dhsUrban", "in_memory/dhsRural"], 
                                   r"C:\Google Drive\BirthsandPregnanciesMapping\results\test\result.gdb\dhsAsfr%s" % iso3) 
                                   #outGDB + "/dhsAsfr%s" % iso3)

    finally:
        arcpy.Delete_management("in_memory")


def findPopRast(popRastDir, iso3, grumpPopRast, countryBoundaries, outDir):
    # Look for tif files
    matches = []
    for root, dirnames, filenames in os.walk(popRastDir + "\\" + iso3):
      for filename in fnmatch.filter(filenames, '*.tif'):
          matches.append(os.path.join(root, filename))
    # If match found return path
    if len(matches) == 1:
        return matches[0]
    # If no matches, clip grump population raster and resample to 100m resolution
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

            arcpy.CopyRaster_management(grumpPop100m, os.path.join(outDir, "pop1990%s.tif" % iso3))
            return os.path.join(outDir, "pop1990%s.tif" % iso3)
        finally:
            arcpy.env.cellSize = defaultCellSize
            arcpy.Delete_management("in_memory")
            arcpy.Delete_management(tmpdir)
            arcpy.env.workspace = old_workspace
            arcpy.env.scratchWorkspace = old_scratchWorkspace
            arcpy.CheckInExtension("Spatial")
    else:
        logging.error("Multiple population rasters found")



def unajustedBirthsEstimates(ageFc, iso3, ageXls, isoNum, popRastPath, asfrPresent, unBirthsXls, outputGdb, outputDir):

    arcpy.CheckOutExtension("Spatial")

    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace

    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir


    try:
        # Get raster cell size
        popRast = arcpy.Raster(popRastPath)
        cellSize = (popRast.meanCellHeight + popRast.meanCellWidth) / float(2)


        # Extract subnational age breakdowns for selected country
        arcpy.FeatureClassToFeatureClass_conversion(ageFc,
                                                    "in_memory",
                                                    "age_extract",
                                                    """ ISO = '%s' """ % (iso3,))

        # If no features found, use national data from spreadsheet
        if int(arcpy.GetCount_management("in_memory/age_extract").getOutput(0)) == 0:
            logging.warning("No sub-national age bands, using national data")
            subNationalData = False

            # Calculate total population from raster
            popRastMask = popRast * 0
            arcpy.CopyRaster_management(popRastMask, "popRastMask.tif", pixel_type="1_BIT")
            arcpy.BuildRasterAttributeTable_management("popRastMask.tif", "Overwrite")
            arcpy.sa.ZonalStatisticsAsTable("popRastMask.tif", "VALUE", popRast, "in_memory/popRastZonalStats", "DATA", "SUM")
            with arcpy.da.SearchCursor("in_memory/popRastZonalStats", "SUM") as c:
                for row in c:
                    totalPop = row[0]

            # Get female populations by age from spreadsheet, calculate ratios
            wb = xlrd.open_workbook(ageXls)
            ws = wb.sheet_by_name("1990")
            for row in range(1, ws.nrows):
                if int(ws.cell_value(row, 4)) == int(isoNum):
                    ageRatioFemale = { k : ((v * 1000) / totalPop)  for k, v in zip(("a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550"), ws.row_values(row, 6, 13)) }

        else:
            subNationalData = True

        # Calculate number of women of child bearing age
        wocbaRasters = {}
        for ageField in ("a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550"):
            if subNationalData == True:

                ageRast = "age_%s.tif" % ageField
                arcpy.PolygonToRaster_conversion("in_memory/age_extract",
                                                 ageField,
                                                 ageRast,
                                                 cell_assignment="MAXIMUM_AREA",
                                                 cellsize=cellSize)

                wocbaRasters[ageField] =  (ageRast * popRast * 0.5)

            else:
                wocbaRasters[ageField] = (ageRatioFemale[ageField] * popRast)

        if asfrPresent == False:
            # Calculate total women of child bearing age
            wocbaSum = arcpy.sa.CellStatistics(wocbaRasters.values(), "SUM", "DATA")
            wocbaSumRastMask = wocbaSum * 0
            arcpy.CopyRaster_management(wocbaSumRastMask, "wocbaSumRastMask.tif", pixel_type="1_BIT")
            arcpy.BuildRasterAttributeTable_management("wocbaSumRastMask.tif", "Overwrite")
            arcpy.sa.ZonalStatisticsAsTable("wocbaSumRastMask.tif", "VALUE", wocbaSum, "in_memory/wocbaSumZonalStats", "DATA", "SUM")
            with arcpy.da.SearchCursor("in_memory/wocbaSumZonalStats", "SUM") as c:
                for row in c:
                    totalWocba = row[0]
            # Retrieve UN total births from spreadsheet
            wb = xlrd.open_workbook(unBirthsXls)
            ws = wb.sheet_by_name("ESTIMATES")
            for row in range(1, ws.nrows):
                if ws.cell_value(row, 4) == iso3 and int(ws.cell_value(row, 2)) == 1990:
                    unTotal = ws.cell_value(row, 3) * 1000
            # Calculate fertility rate
            fertilityRate = float(unTotal) / float(totalWocba)

        # Multiply wocba and asfr rasters and sum outputs
        birthsRasters = []
        for ageField in ("a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550"):

            if asfrPresent == True:
                asfrRast = "asfr_%s.tif" % ageField
                arcpy.PolygonToRaster_conversion(outputGdb + "/dhsAsfr%s" % iso3,
                                                 ageField,
                                                 asfrRast,
                                                 cell_assignment="MAXIMUM_AREA",
                                                 cellsize=cellSize)

                birthsRasters.append(wocbaRasters[ageField] * asfrRast)

            else:
                birthsRasters.append(wocbaRasters[ageField] * fertilityRate)

        births = arcpy.sa.CellStatistics(birthsRasters, "SUM", "DATA")
        arcpy.CopyRaster_management(births, os.path.join(outputDir, "%s1990unadjustedBirths.tif" % iso3), pixel_type="32_BIT_FLOAT")

    finally:
        # Tidy up
        arcpy.CheckInExtension("Spatial")
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace

def adjustedBirthsEstimates(unBirthsXls, iso3, year, outputDir):

    arcpy.CheckOutExtension("Spatial")

    old_workspace = arcpy.env.workspace
    old_scratchWorkspace = arcpy.env.scratchWorkspace
    
    tmpdir = tempfile.mkdtemp()
    arcpy.env.workspace = tmpdir
    arcpy.env.scratchWorkspace = tmpdir

    try:
        unadjustedBirthsRast = os.path.join(outputDir, "%s%sunadjustedBirths.tif" % (iso3, year))
        # Calculate total births
        rasterMask = arcpy.Raster(unadjustedBirthsRast) * 0
        arcpy.CopyRaster_management(rasterMask, "rasterMask.tif", pixel_type="1_BIT")
        arcpy.BuildRasterAttributeTable_management("rasterMask.tif", "Overwrite")
        arcpy.sa.ZonalStatisticsAsTable("rasterMask.tif", "VALUE", unadjustedBirthsRast, "in_memory/zonalStats", "DATA", "SUM")
        with arcpy.da.SearchCursor("in_memory/zonalStats", "SUM") as c:
            for row in c:
                unadjustedTotal = row[0]

        # Retrieve UN total from spreadsheet
        wb = xlrd.open_workbook(unBirthsXls)
        ws = wb.sheet_by_name("ESTIMATES")
        for row in range(1, ws.nrows):
            if ws.cell_value(row, 4) == iso3 and int(ws.cell_value(row, 2)) == year:
                unTotal = ws.cell_value(row, 3) * 1000

        # Calculate adjusted births raster
        adjustmentFactor = unTotal / unadjustedTotal
        adjustedBirths = arcpy.sa.Times(unadjustedBirthsRast, adjustmentFactor)
        arcpy.CopyRaster_management(adjustedBirths, os.path.join(outputDir, "%s%sadjustedBirths.tif" % (iso3, year)), pixel_type="32_BIT_FLOAT")

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.Delete_management(tmpdir)
        arcpy.env.workspace = old_workspace
        arcpy.env.scratchWorkspace = old_scratchWorkspace

# def growthRatesJoin(urbanGrowthFc, ruralGrowthFc, countryBoundaries, urbanAreasShp, iso3, outputGdb):

#     try:
#         # Extract polygons by country iso
#         arcpy.FeatureClassToFeatureClass_conversion(countryBoundaries,
#                                                     "in_memory",
#                                                     "countryBoundary",
#                                                     """ iso_alpha3 = '%s' """ % (iso3,))
#         arcpy.FeatureClassToFeatureClass_conversion(urbanAreasShp,
#                                                     "in_memory",
#                                                     "urban_extract",
#                                                     """ ISO3 = '%s' """ % (iso3,))
#         # Union of urban and boundary polygons
#         arcpy.Union_analysis(["in_memory/countryBoundary", "in_memory/urban_extract"],
#                              "in_memory/countryUrbanRural")
#         # Separate urban and rural polygons
#         arcpy.FeatureClassToFeatureClass_conversion("in_memory/countryUrbanRural",
#                                                     "in_memory",
#                                                     "countryUrban",
#                                                     """ ONES = 1 """)
#         arcpy.FeatureClassToFeatureClass_conversion("in_memory/countryUrbanRural",
#                                                     "in_memory",
#                                                     "countryRural",
#                                                     """ ONES = 0 """)
#         # Join growth rates data
#         arcpy.JoinField_management("in_memory/countryUrban", "iso_alpha2", urbanGrowthFc, "ISO2", ["Growth20102015", "Growth20152020", "Growth20202025", "Growth20252030"])
#         arcpy.JoinField_management("in_memory/countryRural", "iso_alpha2", ruralGrowthFc, "ISO2", ["Growth20102015", "Growth20152020", "Growth20202025", "Growth20252030"])
#         # Merge urban and rural data back together
#         arcpy.Merge_management(["in_memory/countryUrban", "in_memory/countryRural"], outputGdb + "/growthRates%s" % iso3)

#     finally:
#         # Tidy up
#         arcpy.Delete_management("in_memory")


# def futureBirthsEstimates(growthRatesXls, iso3, isoNum, outputGDB, outputDir):

#     arcpy.CheckOutExtension("Spatial")

#     old_workspace = arcpy.env.workspace
#     old_scratchWorkspace = arcpy.env.scratchWorkspace
    
#     tmpdir = tempfile.mkdtemp()
#     arcpy.env.workspace = tmpdir
#     arcpy.env.scratchWorkspace = tmpdir

#     try:
#         # Estimate births for 2015, 2020, 2025, and 2030
#         for growthField in ("Growth20102015", "Growth20152020", "Growth20202025", "Growth20252030"):

#             fromYear = growthField[-8:-4] # Year growth is calculated from
#             toYear = growthField[-4:] # Year growth is calculated to

#             # Retrieve adjusted births raster and raster cell size
#             adjustedBirthsRast = arcpy.Raster(os.path.join(outputDir, "%s%sadjustedBirths.tif" % (iso3, fromYear)))
#             cellSize = (adjustedBirthsRast.meanCellHeight + adjustedBirthsRast.meanCellWidth) / float(2)

#             # Create raster of growth rates from feature class
#             growthRast = "%s.tif" % growthField
#             arcpy.PolygonToRaster_conversion(outputGDB + "/growthRates%s" % iso3,
#                                              growthField,
#                                              growthRast,
#                                              cell_assignment="MAXIMUM_AREA",
#                                              cellsize=cellSize)

#             # Calculate unadjusted births and create output raster
#             unadjustedBirths = adjustedBirthsRast * arcpy.sa.Exp(arcpy.Raster(growthRast) / 100 * 5)
#             arcpy.CopyRaster_management(unadjustedBirths, os.path.join(outputDir, "%s%sunadjustedBirths.tif" % (iso3, toYear)), pixel_type="32_BIT_FLOAT")

#             # Calculate adjusted births
#             adjustedBirthsEstimates(unBirthsXls, iso3, int(toYear), outputDir)


#         # Estimate births for 2012

#         # Retrieve 2010 adjusted births raster
#         adjustedBirthsRast = arcpy.Raster(os.path.join(outputDir, "%s2010adjustedBirths.tif" % iso3))

#         # Calculate unadjusted births and create output raster
#         growthRast = "Growth20102015.tif"
#         unadjustedBirths = adjustedBirthsRast * arcpy.sa.Exp(arcpy.Raster(growthRast) / 100 * 2)
#         arcpy.CopyRaster_management(unadjustedBirths, os.path.join(outputDir, "%s2012unadjustedBirths.tif" % iso3), pixel_type="32_BIT_FLOAT")

#         # Calculate adjusted births
#         adjustedBirthsEstimates(unBirthsXls, iso3, 2012, outputDir)


#         # 2035 estimates are calculated separately, as only national growth rates are available

#         # Retrieve adjusted births raster
#         adjustedBirthsRast = arcpy.Raster(os.path.join(outputDir, "%s2030adjustedBirths.tif" % iso3))

#         # Retrieve growth rate from spreadsheet
#         wb = xlrd.open_workbook(growthRatesXls)
#         ws = wb.sheet_by_name("MEDIUM FERTILITY")
#         for row in range(17, ws.nrows):
#             if int(ws.cell_value(row, 4)) == int(isoNum):
#                 growthRate = ws.cell_value(row, 9)

#         # Calculate unadjusted births and create output raster
#         unadjustedBirths = adjustedBirthsRast * math.exp(growthRate / 100 * 5)
#         arcpy.CopyRaster_management(unadjustedBirths, os.path.join(outputDir, "%s2035unadjustedBirths.tif" % iso3), pixel_type="32_BIT_FLOAT")

#         # Calculate adjusted births
#         adjustedBirthsEstimates(unBirthsXls, iso3, 2035, outputDir)


#     finally:
#         # Tidy up
#         arcpy.CheckInExtension("Spatial")
#         arcpy.Delete_management(tmpdir)
#         arcpy.env.workspace = old_workspace
#         arcpy.env.scratchWorkspace = old_scratchWorkspace

def pregnanciesEstimates(birthPregMultiXlsx, iso3, outputDir):

    arcpy.CheckOutExtension("Spatial")

    try:
        # Retrieve multiplier from spreadsheet
        wb = xlrd.open_workbook(birthPregMultiXlsx)
        ws = wb.sheet_by_name("2012")
        for row in range(1, ws.nrows):
            if ws.cell_value(row, 2) == iso3:
                birthPregMulti = ws.cell_value(row, 1)

        # Multiply births estimates for each year by multiplier
        year = 1990
        #for year in ("1990"):
        rastPath = os.path.join(outputDir, "%s%sadjustedBirths.tif" % (iso3, year))
        birthsRast = arcpy.Raster(rastPath)

        pregnancies = birthsRast * birthPregMulti

        outRast = os.path.join(outputDir, "%s%spregnancies.tif" % (iso3, year))
        arcpy.CopyRaster_management(pregnancies, outRast, pixel_type="32_BIT_FLOAT")

    finally:
        arcpy.CheckInExtension("Spatial")

def adminLevel2Estimates(adminBoundaryFc, iso3, urbanAreasShp, rastDir, outGdb):

    arcpy.CheckOutExtension("Spatial")    

    try:
        # Extract polygons for selected country
        arcpy.FeatureClassToFeatureClass_conversion(adminBoundaryFc,
                                                    "in_memory",
                                                    "adminBoundsExtract",
                                                    """ ISO3 = '%s' """ % (iso3,))

        arcpy.FeatureClassToFeatureClass_conversion(urbanAreasShp,
                                                    "in_memory",
                                                    "urban_extract",
                                                    """ ISO3 = '%s' """ % (iso3,))
        # Identity of urban and admin boundary polygons
        arcpy.Identity_analysis("in_memory/adminBoundsExtract", "in_memory/urban_extract", "in_memory/adminUrbanRural", "NO_FID")

        # Define output feature class
        outputFc = os.path.join(outGdb, "birthsAndPregnancies%s" % iso3)

        # Aggregate polygons
        arcpy.Dissolve_management("in_memory/adminUrbanRural", outputFc, ["ADM2_CODE", "ADM2_NAME", "ONES"])
        # Create new fields for zonal statistics
        arcpy.AddField_management(outputFc, "urbanOrRural", "TEXT")
        arcpy.AddField_management(outputFc, "ZONES", "TEXT")

        with arcpy.da.UpdateCursor(outputFc, ["ADM2_CODE", "ONES", "urbanOrRural", "ZONES"]) as upCur:
            for row in upCur:
                if row[1] == 1:
                    row[2] = "URBAN"
                else:
                    row[2] = "RURAL"                    
                row[3] = str(row[0]) + str(row[2])
                upCur.updateRow(row)

        # Remove "ONES" field as no longer needed
        arcpy.DeleteField_management(outputFc, "ONES")
        
        year = "1990"
        # Calculate zonal statistics SUM for each raster
        #for year, desc in itertools.product(("1990"), ("adjustedBirths", "pregnancies")):
        for desc in ("adjustedBirths", "pregnancies"):

            raster = os.path.join(rastDir, "%s%s%s.tif" % (iso3, year, desc))
            arcpy.sa.ZonalStatisticsAsTable(outputFc, "ZONES", raster, "in_memory/%s%sSUM"  % (desc, year), "DATA", "SUM")

            # ArcGIS does not allow field renaming, so create new field and copy data across
            arcpy.AddField_management("in_memory/%s%sSUM"  % (desc, year), "%s%s" % (desc, year), "DOUBLE")
            arcpy.CalculateField_management("in_memory/%s%sSUM"  % (desc, year), "%s%s" % (desc, year), "!SUM!", "PYTHON_9.3")

            # Join stats table to output feature class
            arcpy.JoinField_management(outputFc, "ZONES", "in_memory/%s%sSUM"  % (desc, year), "ZONES", ["%s%s" % (desc, year)])

        # Remove "ONES" field as no longer needed
        arcpy.DeleteField_management(outputFc, "ZONES")

    finally:
        arcpy.Delete_management("in_memory")
        arcpy.CheckInExtension("Spatial")

def outputToExcel(outGdb, iso3, outXlsxDir):

    year = "1990"
    # Input feature class
    outputFc = os.path.join(outGdb, "birthsAndPregnancies%s" % iso3)
    # Fieldnames
    fields = ("ADM2_CODE", "ADM2_NAME", "urbanOrRural", "adjustedBirths1990", "pregnancies1990")
              # "pregnancies2010", "adjustedBirths2012", "pregnancies2012",
              # "adjustedBirths2015", "pregnancies2015", "adjustedBirths2020",
              # "pregnancies2020", "adjustedBirths2025", "pregnancies2025",
              # "adjustedBirths2030", "pregnancies2030", "adjustedBirths2035",
              # "pregnancies2035")

    # Create output spreadsheet
    outXlsx = os.path.join(outXlsxDir, "birthsAndPregnancies%s%s.xlsx" % (iso3, year))

    wb = xlsxwriter.Workbook(outXlsx)
    ws = wb.add_worksheet()

    # Row counter
    outRow = 0

    # Add headers to first row
    fmt = wb.add_format( {'bold': True} )

    for i in xrange(len(fields)):
        ws.write(outRow, i, fields[i], fmt)
        ws.set_column(i, i, len(fields[i]))

    # Move down to second row
    outRow = 1

    # Use search cursor to loop through feature class rows
    with arcpy.da.SearchCursor(outputFc, fields) as cur:
        for inRow in cur:
            # Write data to spreadsheet
            for i in xrange(len(fields)):
                ws.write(outRow, i, inRow[i])
            # Move down one row
            outRow += 1

    # Save and close output spreadsheet
    wb.close()


if __name__ == "__main__":

    # Input paths
    countryListXml = "C:\\Google Drive\\BirthsandPregnanciesMapping\\country_list.xml" # List of countries to process

    urbanAsfrFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\asfr_1990.gdb\\asfrURBAN" # Urban ASFR data
    ruralAsfrFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\asfr_1990.gdb\\asfrRURAL" # Rural ASFR data
    dhsRegionsFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\dhsBoundaries\\1990\\dhsBoundaries.gdb\\subnational_boundaries" # DHS boundaries   
    urbanAreasShp = "C:\\BirthsandPregnancies\\GRUMP\\af_as_lac_urban_EA.shp" # Urban area extents
    ageFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Africa_SubNational_ageStructures\\iPums\\EA.shp" # Asia\Africa Sub-national breakdown of population by age
    ageXls = "C:\\Google Drive\\BirthsandPregnanciesMapping\\POPULATION_BY_AGE_FEMALE_EA.xls" # UN national breakdown of female population by age
    popRastDir = "C:\\BirthsandPregnancies\\WorldPop1990" # Population raster directory
    grumpPopRast = "C:\\BirthsandPregnancies\\GRUMP\\grump_pop_1990.tif" # GRUMP 1990 population raster
    unBirthsXls = "C:\\Google Drive\\BirthsandPregnanciesMapping\\births-by-year_1990_ea.xls" # UN estimates of births
    birthPregMultiXlsx = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Births-to-pregnancies-multipliers.xlsx" # Births to pregnancy multipliers
    countryBoundaries = "C:\\Google Drive\\BirthsandPregnanciesMapping\\LSIB-WSV\\lsib-wsv.gdb\\detailed_world_polygons" # Country boundary polygons
    #urbanGrowthFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Growth Rates\\GrowthRates.gdb\\Urban" # Urban growth rates
    #ruralGrowthFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Growth Rates\\GrowthRates.gdb\\Rural" # Rural growth rates
    adminBoundaryFc = "C:\\Google Drive\\BirthsandPregnanciesMapping\\adminBoundaries\\adminBoundaries.gdb\\g2014_2010_2_EA" # Admin level 2 boundaries
    #growthRatesXls = "C:\\Google Drive\\BirthsandPregnanciesMapping\\WPP2012_POP_F02_POPULATION_GROWTH_RATE.XLS" # UN National Growth Rates
    
# Output paths
    outDir = "C:\\BirthsandPregnancies\\results\\raster" # Raster output directory
    outGDB = "C:\\Google Drive\\BirthsandPregnanciesMapping\\results\\test\\result.gdb" # Vector output geodatabase
    outXlsxDir = "C:\\BirthsandPregnancies\\results\\excel" # Excel output directory

    # Set up logging
    logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

    # Allow files to be overwritten
    arcpy.env.overwriteOutput = True

    # Loop through countries listed within xml file
    countryList = ET.parse(countryListXml).getroot()

    for country in countryList.findall("country"):
        countryName = country.find("name").text
        iso2 = country.find("iso2").text
        iso3 = country.find("iso3").text
        isoNum = country.find("isoNum").text

        logging.info("Processing %s" % countryName)        
     
        # Join ASFRs (if they exist) to DHS polygons
        logging.info("Joining ASRFs to DHS polygons")
        dhsAsfrJoin(urbanAsfrFc, ruralAsfrFc, iso2, dhsRegionsFc, urbanAreasShp, iso3, outGDB)

        # Find population raster
        logging.info("Retrieving population raster")
        popRastPath = findPopRast(popRastDir, iso3, grumpPopRast, countryBoundaries, outDir)
            
        # Calculate estimated number of births
        logging.info("Calculating estimated number of births")
        unajustedBirthsEstimates(ageFc, iso3, ageXls, isoNum, popRastPath, asfrPresent, unBirthsXls, outGDB, outDir)
        
        # Adjust births raster to match UN estimates
        logging.info("Adjusting births raster to match UN estimates")        
        adjustedBirthsEstimates(unBirthsXls, iso3, 1990, outDir)

        # Join growth rates to country boundaries
        # logging.info("Joining growth rates to country boundaries")
        # growthRatesJoin(urbanGrowthFc, ruralGrowthFc, countryBoundaries, urbanAreasShp, iso3, outGDB)
        
        # Estimate future births
        # logging.info("Estimating future births")
        # futureBirthsEstimates(growthRatesXls, iso3, isoNum, outGDB, outDir)

        # Estimate pregnancies
        logging.info("Estimating pregnancies")
        pregnanciesEstimates(birthPregMultiXlsx, iso3, outDir)

        # Zonal statistics by admin region
        logging.info("Calculating zonal statistics by admin regions")
        adminLevel2Estimates(adminBoundaryFc, iso3, urbanAreasShp, outDir, outGDB)

        # Create excel spreadsheet output
        logging.info("Creating Excel spreadsheet output")
        outputToExcel(outGDB, iso3, outXlsxDir)