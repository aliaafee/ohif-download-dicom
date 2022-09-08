import json
import urllib.request
import os
from threading import Thread
from time import perf_counter
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def get_dicom_urllist(urllist_string):
    urllist = []
    
    data = json.loads(urllist_string)

    studies = data['studies']

    for si, study in enumerate(studies):
        #print(f"Study {si}\t{study['StudyInstanceUID']}")
        print(study.keys())

        serieses = study['series']
        for sei, series in enumerate(serieses):
            #print(f"\tSeries {sei}")

            instances = series['instances']

            for ii, instance in enumerate(instances):
                #print(f"\t\tInstances {ii}")
                #print(f"\t\t\turl {instance['url']}")

                url = instance['url'].replace("dicomweb:", "")
                #print(f"\t\t\turl {url}")
                urllist.append((study['PatientID'], study['PatientName'], url))
    return urllist


def get_dicom_urllist_string(url):
    filename, headers = urllib.request.urlretrieve(url)
    with open(filename) as f:
        return f.read()


def get_download_url(src_url):
    src_parsed = urlparse(src_url)
    qs = parse_qs(src_parsed.query)
    if not 'url' in qs:
        raise ValueError
    if not qs['url']:
        raise ValueError
    return qs['url'][0]    


def get_outfilename(list_item, output_dir):
    patient_id, patient_name, url = list_item 
    base, _, ident = url.partition("file=/")
    ident = ident.replace("/", "-")
    return os.path.join(
        output_dir,
        f"{patient_id}-{ident}.dcm"
    )


def download_dicoms(urls, output_dir):
    for i, list_item in enumerate(urls):
        patient_id, patient_name, url = list_item 
        urllib.request.urlretrieve(
            url,
            get_outfilename(list_item, output_dir)
        )
        print(".", end="")


def split_array(array, parts=2):
    if parts > len(array):
        parts = len(array)
    result = []
    chunk_size = len(array) / parts
    for i in range(parts):
        chunk_start = int(chunk_size + (i - 1) * chunk_size)
        chunk_end = int(chunk_size + i * chunk_size)
        result.append(array[chunk_start:chunk_end])
    return result


def download_dicoms_threaded(urls, output_dir, thread_count=5):
    urls_parts = split_array(urls, thread_count)
    threads = []
    for urls_part in urls_parts:
        t = Thread(target=download_dicoms, args=(urls_part, output_dir))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


def main():
    output_root = os.path.join(Path.home(), "Downloads")

    src = input("DICOM url: ")

    try:
        download_url = get_download_url(src)
    except ValueError as e:
        print("DICOM url does not look right")
        return()
    
    output_subdir = input(f"Output : {output_root}{os.sep}")
    output_dir = os.path.join(output_root, output_subdir)

    try:
        urllist_string = get_dicom_urllist_string(download_url)
    except Exception as e:
        print(f"Could not get DICOM list ({e})")
        return

    urls = get_dicom_urllist(urllist_string)

    print(f"Found {len(urls)} DICOM files")

    if not urls:
        print(f"Nothing to Download")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("Downloading", end="")

    start_time = perf_counter()
    download_dicoms_threaded(urls, output_dir, 10)
    end_time = perf_counter()
    
    print("Done")
    print(f"Took {end_time-start_time: 0.2f} second(s).")


if __name__ == "__main__":
    main()
    
