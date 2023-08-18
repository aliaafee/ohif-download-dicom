# ohif_download_dicom
Download DICOM files from OHIF Viewer. Tested to work on one particular setup, not tested on anything else.

## Setup

* Install python3
* No additional packages are required.

## Usage

* Run `download-dicoms.py` with python3.
* Proved url as a command line argument to start download.
* Use command line option `-v` or `--viewer=` to change the default viewer for DICOM files.
* When command line argument is not provided, there will be a prompt asking for the url.

## Using the Protocol Handler

### Windows

* To Use protocol handler, edit the .reg.template file with appropriate paths, and add to the registry.
* The protocol handler will open all links with `dldicom://` with the downloader.
* If the `--viewer==` option is not set the download folder will be opened in the file browser.

### MacOSX

* Instructions are forthcoming.

## Build standalone executable

* Note: These instructions are meant to be platform agnostic, but have not been tested on all platforms.
* Install the build requirements `pip install -r build-requirements.txt`
* Build the executable `pyinstaller download-dicoms.spec`
* The executable will located in `dist\`