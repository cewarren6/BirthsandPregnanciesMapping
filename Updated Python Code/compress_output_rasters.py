import os
import tarfile
import logging
import xml.etree.ElementTree as ET

years = (2010, 2012, 2015, 2020, 2025, 2030, 2035)
datasets = ("adjustedBirths", "pregnancies")

rasterDir = "C:/BirthsandPregnancies/results/raster"
countryListXml = "C:/Users/cr2m14/Google Drive/BirthsandPregnanciesMapping/Python Code/country_list.xml"
outputDir = "C:/BirthsandPregnancies/results/compressed_rasters"

# Set up logging
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s", level=logging.INFO)

# Loop through countries listed within xml file
countryList = ET.parse(countryListXml).getroot()

for country in countryList.findall("country"):
    iso3 = country.find("iso3").text

    # Create tar.gz archive for each country and dataset
    for dataset in datasets:

        logging.info("Compressing %s - %s" % (iso3, dataset))

        tgz = tarfile.open(os.path.join(outputDir, "%s-%s.tar.gz" % (iso3, dataset)), "w:gz")

        for year in years:

            tiff = os.path.join(rasterDir, "%s%s%s.tif" % (iso3, year, dataset))
            tfw = os.path.join(rasterDir, "%s%s%s.tfw" % (iso3, year, dataset))

            tgz.add(tiff, os.path.basename(tiff))
            tgz.add(tfw, os.path.basename(tfw))

        tgz.close()