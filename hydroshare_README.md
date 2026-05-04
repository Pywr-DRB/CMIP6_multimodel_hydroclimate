This DATSETNAMEreadme.txt file was generated on 2024-02-24 by Shih-Chieh Kao


GENERAL INFORMATION

1. Title of Dataset: 

        CMIP6-based Multi-model Hydroclimate Projection over the Conterminous US, Version 1.1

2. Author Information
	A. Principal Investigator Contact Information
		Name: Shih-Chieh Kao
		Institution: Oak Ridge National Laboratory
		Address: PO Box 2008 MS 6038, Oak Ridge, TN 37831-6038
		Email: kaos@ornl.gov

	B. Associate or Co-investigator Contact Information
		Name: Deeksha Rastogi
		Institution: Oak Ridge National Laboratory
		Address: PO Box 2008 MS 6085, Oak Ridge, TN 37831-6085
		Email: rastogid@ornl.gov

	C. Alternate Contact Information
		Name: Sudershan Gangrade
		Institution: Oak Ridge National Laboratory
		Address: PO Box 2008 MS 6038, Oak Ridge, TN 37831-6038
		Email: gangrades@ornl.gov

3. Date of data collection (single date, range, approximate date) <suggested format YYYY-MM-DD>: 

        2022-09-30

4. Geographic location of data collection <latitude, longiute, or city/region, State, Country, as appropriate>: 

        Conterminous United States (125W–66.5W, 24N–53N)

5. Information about funding sources that supported the collection of the data: 

        This dataset is derived to support the SECURE Water Act Section 9505 Assessment for the US Department of Energy (DOE) Water Power Technologies Office (WPTO).


SHARING/ACCESS INFORMATION

1. Licenses/restrictions placed on the data: 

        Open to share. No restriction.

2. Links to publications that cite or use the data: 

        Kao, S.-C., M. Ashfaq, D. Rastogi, S. Gangrade, R. Uría Martínez, A. Fernandez, G. Konapala, N. Voisin, T. Zhou, W. Xu, H. Gao, B. Zhao, and G. Zhao (2022), The Third Assessment of the Effects of Climate Change on Federal Hydropower, ORNL/TM-2021/2278, Oak Ridge National Laboratory, Oak Ridge, TN, https://doi.org/10.2172/1887712.

        Rastogi, D., S.-C. Kao, and M. Ashfaq (2022), How May the Choice of Downscaling Techniques and Meteorological Reference Observations Affect Future Hydroclimate Projections?, Earth's Future, 10(8), e2022EF002734, https://doi.org/10.1029/2022EF002734.

3. Links to other publicly accessible locations of the data: 

	(Only a subset) Kao, S.-C., M. Ashfaq, D. Rastogi, and S. Gangrade (2022), CMIP6-Based Multi-Model Hydroclimate Projection over the Conterminous US, HydroSource, Oak Ridge National Laboratory, Oak Ridge, TN, https://doi.org/10.21951/SWA9505V3/1887469.

4. Links/relationships to ancillary data sets: 

	This project uses a variety of ancillary data sets. The details are referred to Kao et al. (2022), https://doi.org/10.2172/1887712

5. Was data derived from another source? yes/no
	A. If yes, list source(s): 

	Yes, this project uses a variety of external data (climate, land surface, hydrology). The details are referred to Kao et al. (2022), https://doi.org/10.2172/1887712

6. Recommended citation for this dataset: 

	Kao, S.-C., M. Ashfaq, D. Rastogi, S. Gangrade, R. Uría Martínez, A. Fernandez, G. Konapala, N. Voisin, T. Zhou, W. Xu, H. Gao, B. Zhao, and G. Zhao (2022), The Third Assessment of the Effects of Climate Change on Federal Hydropower, ORNL/TM-2021/2278, Oak Ridge National Laboratory, Oak Ridge, TN, https://doi.org/10.2172/1887712.


DATA & FILE OVERVIEW

1. File List:

        The majority of data are in daily temporal resolution, provided in a general format.:

                [Simulation Name]/[Variable Name]/[File Name]

        [Simulation Name]

                Simulations [DaymetV4] and [Livneh] are driven by historical Daymet and Livneh observations.

                Other simulation names are a combination of [GCM Name][SSP Scenarios][Ensemble ID][Downscaling Method][Reference Meteorological Observations].

        [GCM Name] This includes the following CMIP6 GCMs:

                ACCESS-CM2
                BCC-CSM2-MR
                CNRM-ESM2-1
                EC-Earth3
                MPI-ESM1-2-HR
                MRI-ESM2-0
                NorESM2-MM

        [SSP Scenarios] This includes the following emission scenarios:

                ssp585
                ssp370
                ssp245
                ssp126

        [Ensemble ID] This is the unique CMIP6 ensemble ID of each GCM simualtion

        [Downscaling Method] This includes the following downscaling methods:

                DBCCA
                RegCM

        [Reference Meteorological Observations] This includes the following reference meteorological observations:

                Daymet
                Livneh

        [Variable Name]  This includes the following variables:

                Field Name      Units   Description
                prcp            mm/day  precipitation
                tmax            deg C   daily maximum temperature
                tmin            deg C   daily minimum temperature
                wind            m/s     wind speed
                srad            W/m2    shortwave radiation (estimated by VIC-MetClim)
                lrad            W/m2    longwave radiation (estimated by VIC-MetClim)
                qair            kg/kg   specific humidity (estimated by VIC-MetClim)
                rhum            %       relative humidity (estimated by VIC-MetClim)
                vp              Pa      near surface vapor pressure (estimated by VIC-MetClim)
                vpd             Pa      near surface vapor pressure deficit (estimated by VIC-MetClim)
                pres            Pa      near surface atmospheric pressure (estimated by VIC-MetClim)
                runoff          mm/day  total runoff (baseflow + surface runoff) (estimated by VIC)
                runoffs         mm/day  surface runoff (estimated by VIC)
                runoffb         mm/day  baseflow (estimated by VIC)
                swe             mm      snow water equivalent (estimated by VIC)
                evap            mm/day  evapotranspiration (estimated by VIC)
                pet             mm/day  potential evaporation (estimated by VIC)
                soilm           mm      soil moisture (estimated by VIC)
                PRMS_runoff     mm/day  total runoff (baseflow + surface runoff) (estimated by PRMS)
                PRMS_runoffs    mm/day  surface runoff (estimated by PRMS)
                PRMS_runoffb    mm/day  baseflow (estimated by PRMS)
                PRMS_swe        mm      snow water equivalent (estimated by PRMS)
                PRMS_evap       mm/day  evapotranspiration (estimated by PRMS)
                PRMS_pet        mm/day  potential evaporation (estimated by PRMS)
                PRMS_soilm      mm      soil moisture (estimated by PRMS)

        [File Name]  This includes [Simulation Name], [Variable Name], and [Year] from 1950-2099. Files with a single year number contain data at daily resolution. Files with a range of years (e.g., 1980_2019) are temporally averaged/aggregated data, either at monthly or annual time scales.

        In addition to gridded data, spatially aggregated data are provided in the HUC_Summary and County_Summary folders. HUC_Summary provides summaries at 2-, 4-, 6-, and 8-digit US Hydrologic Unit Code watersheds (HUC02, HUC04, HUC06, HUC08). County_Summary provides summaries at both county and state levels, labeled by the FIPS code. Shapefiles used as the basis of this analysis are also included.

2. Relationship between files, if important: 

        NA

3. Additional related data collected that was not included in the current data package: 

        NA

4. Are there multiple versions of the dataset? yes/no
	A. If yes, name of file(s) that was updated: 
		i. Why was the file updated? 
		ii. When was the file updated? 

        NA


METHODOLOGICAL INFORMATION

1. Description of methods used for collection/generation of data:

        See Kao et al. (2022), https://doi.org/10.2172/1887712

2. Methods for processing the data: 

        See Kao et al. (2022), https://doi.org/10.2172/1887712

3. Instrument- or software-specific information needed to interpret the data: 

        All files are in NetCDF formats. Need to use any form of NetCDF readers to access the data.

4. Standards and calibration information, if appropriate: 

        See Kao et al. (2022), https://doi.org/10.2172/1887712

5. Environmental/experimental conditions: 

        NA

6. Describe any quality-assurance procedures performed on the data: 

        See Kao et al. (2022), https://doi.org/10.2172/1887712

7. People involved with sample collection, processing, analysis and/or submission: 

        NA


DATA-SPECIFIC INFORMATION FOR: ACCESS-CM2_ssp585_r1i1p1f1_DBCCA_Daymet_VIC4_prcp_1980 (example)

1. Number of variables: 

        4

2. Number of cases/rows: 

        dimensions:
                time = UNLIMITED ; // (365 currently)
                lon = 1405 ;
                lat = 697 ;

3. Variable List:

        double time(time) ;
                time:units = "days since 1980-01-01" ;
                time:calendar = "standard" ;
                time:long_name = "day" ;
                time:standard_name = "time" ;
        double lon(lon) ;
                lon:units = "degrees_east" ;
                lon:long_name = "longitude coordinate" ;
                lon:standard_name = "longitude" ;
        double lat(lat) ;
                lat:units = "degrees_north" ;
                lat:long_name = "latitude coordinate" ;
                lat:standard_name = "latitude" ;
        float prcp(time, lat, lon) ;
                prcp:long_name = "daily total precipitation" ;
                prcp:units = "mm/day" ;

4. Missing data codes:

        NA

5. Specialized formats or other abbreviations used: 

        NetCDF