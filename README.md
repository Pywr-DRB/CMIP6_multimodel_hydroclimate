# CMIP6_multimodel_hydroclimate

This repo is used to download and process meterological data from Kao et al. (2024) via globus API.

This dataset can be accessed through one of the following appraoches:

- [HydroSource Download] https://hydrosource2.ornl.gov/files/SWA9505V3/

- [Globus Download] https://doi.org/10.13139/OLCF/2311812


Dataset details can be found in the hydroshare [README](https://hydrosource2.ornl.gov/files/SWA9505V3/README_9505V3.txt).



Reference: 
Kao, S. C., Ashfaq, M., Rastogi, D., & Gangrade, S. (2024). CMIP6-based multi-model hydroclimate projection over the conterminous US, Version 1.1. HydroSource. Oak Ridge National Laboratory.


## Notes

Climate variables are only retrieved for Pywr-DRB relevant catchments. 

Variables are partitioned according to the [node catchment geometries](https://github.com/Pywr-DRB/Input-Data-Retrieval/tree/main/datasets/Spatial/DRB_shapefiles) located in Input-Data-Retrieval/datasets/Spatial/DRB_shapefiles/.

All workflows are performed using SLURM.