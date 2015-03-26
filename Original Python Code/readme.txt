births_and_pregnancies.py
- This is the main script
- Generates the estimates of future births and pregnancies for each country
- Outputs in raster, vector and excel format

compress_output_rasters.py
- for each country, collects the raster outputs into tarballs for births and pregnancies
- tarballs are then compressed with gzip

compress_tiffs.py
- applies LZW compression the the WorldPop rasters

country_list.xml
- list of all countries to be processed
- includes name and iso codes
- entries can be commented out, so you can select which countries to process

create_boundary_maps.py
- creates eps files of country and admin area boundaries
- reads data from sqlite database
- uses mapnik to apply style and generate postscript file
- ghostscript then converts postscript to eps file

create_pregnancy_maps.py
- uses mapnik to create png maps from 2012 pregnancy rasters

create_zanzibar_boundary_map.py
- creates boundary map of Zanzibar from shapefile

import_asfr_data.py
- imports ASFR data from Excel spreadsheets into file geodatabase table

pop_and_wra_2012.py
- calculates urban and rural population and women of reproductive age for each country
- outputs to csv