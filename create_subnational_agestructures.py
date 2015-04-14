from __future__ import division
import csv
import arcpy
import xlrd
import os
from collections import Counter


iPumsXls = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Africa_SubNational_ageStructures\\iPums\\EA\\TZA_ipums.csv" #Raw iPums data
outDir = "C:\\Google Drive\\BirthsandPregnanciesMapping\\Africa_SubNational_ageStructures\\iPums"
outIso = "TZA.csv"

age_dict = {} 						#Set age dictionary

with open(iPumsXls) as csvFile:

	for line in csvFile:			#Go through each observation in iPums data
		age_str = line.split(",")
		ISO = age_str[0]
		adm = age_str[4]
		age_class = age_str[7]
		if adm not in age_dict:		#If Python encounters new admin unit/age class, add to dictionary
			age_dict[adm] = {}
		if age_class not in age_dict[adm]:
			age_dict[adm][age_class] = 0
		age_dict[adm][age_class] = age_dict[adm][age_class] + 1 


#Output subnational age structures
orderedagecl=["1","2","3","4","8","9","10","11","12","13","14","15","16","17","18","19","20","98"]	#Order age class
out_file = open(os.path.join(outDir,outIso), 'w')
out_file.write("admin2, a0005, a0510, a1015, a1520, a2025, a2530, a3035, a3540, a4045, a4550, a5055, a5560, a6065, a6570, a7075, a7580, a80plus, aUnknown, ISO\n")
for adm in age_dict:						#Write admin unit
	out_file.write("{}".format(adm))   
 	for age_class in orderedagecl:			#Loop through age class for each admin unit
 		
 		if age_class in age_dict[adm]:		
 			age_prop = ((age_dict[adm][age_class])/(sum(Counter(age_dict[adm].values()))))	#Create proportions of total population in each age structure per admin unit
 			out_file.write(",{}".format(age_prop))

 		else:
 			out_file.write(",")	
 	out_file.write(",%s\n" % ISO)			#Write ISO for each line
out_file.close()

