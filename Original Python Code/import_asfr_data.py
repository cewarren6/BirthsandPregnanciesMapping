import csv
import arcpy
import xlrd
import os

asfrLookup = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/asfr_lookup.csv"
asfrDir = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/ASFR"
asfrGdb = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/asfr.gdb"

# Loop through ASFR lookup asfr lookup table
with open(asfrLookup) as csvFile:
    reader = csv.reader(csvFile, delimiter=",")
    next(reader, None) # Skip header row
    for row in reader:
        iso2, fileName, levelRank = row

        # Open excel spreadsheet
        xlsxPath = os.path.join(asfrDir, fileName)
        wb = xlrd.open_workbook(xlsxPath)

        for i in ("URBAN", "RURAL"):
            # Add data to table with insert cursor
            c = arcpy.da.InsertCursor("%s/asfr%s" % (asfrGdb, i), ("iso", "region", "levelRank", "a1520", "a2025", "a2530", "a3035", "a3540", "a4045", "a4550", "sourceFile"))

            for col in range(1, wb.sheet_by_name(i).ncols):

                region, a1520, a2025, a2530, a3035, a3540, a4045, a4550 = wb.sheet_by_name(i).col_values(col, 0, 8)

                rowData = [iso2, region, levelRank, a1520, a2025, a2530, a3035, a3540, a4045, a4550, fileName]

                c.insertRow(rowData)

            del c