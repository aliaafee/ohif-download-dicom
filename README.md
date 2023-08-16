# ohif_download_dicom
Download DICOM files from OHIF Viewer

To run the downloader, just run using python3.

To Use protocol handler, edit the .reg.template file with appropriate paths, and add to the registry.
The protocol handler will open all links with dldicom:// with the downloader.
If the --viewer option is not set the download folder will be opened with the file browser.
