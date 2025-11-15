# Toward Efficient Package Maintenance: An Empirical Study of Patch Sharing across Four Linux Distributions

This repository contains the data, scripts, and analysis code for a comprehensive empirical study on patch sharing and maintenance practices across four major Linux distributions: Fedora, Debian, openEuler, and Ubuntu. The project aims to systematically extract, compare, and analyze software patches, revealing patterns of patch reuse, divergence, and collaboration in the open-source ecosystem.

Below is an overview of the repository’s structure and the purpose of each file or directory.

## Notice on RQ4-Related Data

The dataset related to Research Question 4 (RQ4) is **not included** in this repository, as it may potentially reveal author identities and compromise the anonymity required for the review process. 

If access is needed after the review period, please contact the authors directly.

## Directory Overview

```
relibrary/
  analysis/     # Scripts for statistical analysis and visualization of package and patch data
  core/
    package/    # Core package extraction, normalization, and comparison algorithms
    patch/      # Core patch extraction, normalization, and comparison algorithms
    distro/     # Distribution-specific source package and metadata extraction tools
  utils/
    db/         # Database utilities
    files/      # File utilities
data/
  packages/     # Package metadata and patch lists
  patches/      # Patch comparison results and logs
  db/           # SQLite databases for package/patch info
```

## Data Structure

- **data/packages/**  
  Contains package metadata and patch lists for each distribution.
- **data/patches/**  
  Stores patch comparison results, and analysis outputs.
- **data/db/**  
  Contains JSONFiles and SQLite databases for package and patch information from different distributions.

## Scripts

Below is a breakdown of the main Python scripts, their purposes, and their input/output locations:

### relibrary/analysis/package_compare.py
- **Purpose:**  
  Compares package lists across multiple distributions, finds common and unique packages, and generates HTML/JSON reports. Also supports searching for similar packages based on description similarity.

### relibrary/analysis/packageAnalysis.py
- **Purpose:**  
  Provides statistical analysis and visualization of package comparison results, including match types, homepage similarity, and distribution diagrams (e.g., pie charts, upset plots).

### relibrary/analysis/patchAnalysis.py
- **Purpose:**  
  Analyzes patch comparison results between distributions, generates summary statistics, and produces visualizations such as bar charts, histograms, boxplots, and upset plots for patch overlap and similarity.

### relibrary/analysis/patch_compare.py
- **Purpose:**  
  Compares patch sets for given packages across distributions, identifies common and unique patches, and generates detailed JSON reports and statistics.

### relibrary/analysis/patchNumAnalysis.py
- **Purpose:**  
  Calculates and summarizes the overlap and uniqueness of patches between distributions, reporting rates of overlap and completely different patch sets.

### relibrary/analysis/patchSumAnalysis.py
- **Purpose:**  
  Computes the total number of patches for each package in each distribution, and summarizes patch counts across all packages.

### relibrary/analysis/patchIntroducedTimeAnalysis.py
- **Purpose:**  
  Analyzes the introduction time of patches in different distributions, computes delay statistics, and generates visualizations (e.g., ECDF, boxplots, scatter plots) for patch synchronization and origin.

### relibrary/core/package/Repology.txt
- **Purpose:**  
  Contains SQL queries for extracting homologous (same-source) package data from the Repology database. The queries support identifying common packages across 2, 3, or 4 distributions (e.g., Fedora-Debian, Fedora-Debian-openEuler, Debian-Ubuntu-Fedora-openEuler) by matching packages through multiple methods: effective names (effname), source names (srcname), and upstream URLs (including project keys and normalized URLs). The Repology database dumps can be downloaded from [https://dumps.repology.org/](https://dumps.repology.org/).

### relibrary/core/package/package_analyzer.py
- **Purpose:**  
  Provides functions for extracting, normalizing, and comparing package lists and metadata from different distributions (Debian, Ubuntu, Fedora, openEuler), including similarity analysis and advanced comparison.

### relibrary/core/package/test_package_analyzer.py
- **Purpose:**  
  Command-line tool for testing and validating package analysis, comparison, and JSON output functions for multiple distributions.

### relibrary/core/package/SourcePackageAnalysis_withVersion.py
- **Purpose:**  
  Extracts and analyzes source package information (including version) from multiple distributions, supporting batch processing and output for downstream analysis.

### relibrary/core/distro/DebianPkgInfo/get_D_package_information.py
- **Purpose:**  
  Downloads, parses, and extracts metadata and patch information from Debian source packages, supporting batch operations and dependency analysis.

### relibrary/core/distro/FedoraPkgInfo/get_package_info.py
- **Purpose:**  
  Downloads, extracts, and parses Fedora source packages (SRPM), extracting spec metadata, dependencies, and patch information for further analysis.

### relibrary/core/distro/openEulerPkgInfo/get_package_info.py
- **Purpose:**  
  Downloads, extracts, and parses openEuler source packages (SRPM), extracting spec metadata, dependencies, and patch information for further analysis.

### relibrary/core/distro/UbuntuPkgInfo/get_U_package_information.py
- **Purpose:**  
  Downloads, parses, and extracts metadata and patch information from Ubuntu source packages, supporting batch operations and dependency analysis.

### relibrary/core/distro/DEB_source_download.py
- **Purpose:**  
  Automates the download and extraction of Debian source packages for a list of packages, supporting batch processing and directory management.

### relibrary/core/distro/RPM_source_download.py
- **Purpose:**  
  Automates the download and extraction of Fedora source packages (SRPM) for a list of packages, supporting batch processing and directory management.

### relibrary/core/patch/test_rpm_patch_analyzer.py
- **Purpose:**  
  Compares patches for common packages between Fedora and openEuler-24.03, supporting strip_level adaptation. Outputs comparison results and summary statistics.
- **Input:**  
  - data/packages/package_analysis_withVersion.json  
  - Local Fedora/openEuler source and patch directories
- **Output:**  
  - data/patches/rpm_patch_comparison_report.json  
  - patch_compare.log

### relibrary/core/patch/rpm_patch_analyzer.py
- **Purpose:**  
  Provides core algorithms for RPM patch normalization, feature extraction, similarity calculation, and comparison.

### relibrary/core/patch/deb_rpm_patch_analyzer.py
- **Purpose:**  
  Provides Debian patch extraction, feature analysis, and automated comparison with RPM patches.

### relibrary/core/patch/test_deb_rpm_patch_analyzer.py
- **Purpose:**  
  Compares and analyzes patches for common packages between Fedora and Debian. Automatically extracts, normalizes, and compares patch content, and outputs detailed reports and logs.
- **Input:**  
  - data/packages/package_analysis_withVersion.json  
  - Local Fedora/Debian source and patch directories
- **Output:**  
  - data/patches/deb_rpm_patch_comparison_report.json  
  - data/patches/deb_rpm_patches.log

### relibrary/core/patch/rpm_OverlappingPatch_introducedTime.py
- **Purpose:**  
  Tracks and analyzes the introduction time of overlapping (common or similar) patches between Fedora and openEuler by mining Git commit history for each patch file.

### relibrary/core/patch/deb_rpm_OverlappingPatch_introducedTime.py
- **Purpose:**  
  Tracks and analyzes the introduction time of overlapping (common or similar) patches between Fedora and Debian by mining Git/Salsa commit history for each patch file.

### relibrary/utils/db/db_operations.py
- **Purpose:**  
  Provides a lightweight SQLite database manager class for executing queries, fetching results, and managing transactions and schema introspection.

### relibrary/utils/db/sqlite_operations.py
- **Purpose:**  
  Encapsulates common SQLite operations, including batch import, merging, and querying of package and patch data.

### relibrary/utils/files/file_operations.py
- **Purpose:**  
  Provides general file reading/writing, directory management, and JSON utilities.

### relibrary/utils/files/json_compare.py
- **Purpose:**  
  Compares two JSON files or objects, highlights differences, and outputs a summary or diff file for further inspection.

### relibrary/utils/files/JsontoCsv.py
- **Purpose:**  
  Converts JSON files (list or dict) to CSV format for easier analysis or reporting.

### relibrary/utils/files/convert_timestamps.py
- **Purpose:**  
  Converts and normalizes various timestamp formats in JSON files to ISO8601 format for consistency in downstream analysis.

## Dependencies

- Python 3.7+
- sqlite3
- See `requirements.txt` for additional dependencies

