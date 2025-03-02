import queue
import threading
import time
import os
import platform
import json
import urllib.request
import subprocess
import sys
import getopt
from urllib.parse import urlparse, parse_qs


if getattr(sys, 'frozen', False):
    application_path = os.path.realpath(os.path.dirname(sys.executable))
else:
    application_path = os.path.realpath(os.path.dirname(__file__))

CACHE_DIR = os.path.join(
    application_path,
    "downloaded"
)


def parse_urllist_string(urllist_string):
    data = json.loads(urllist_string)

    return data


def get_dicom_urllist(urllist_parsed):
    urllist = []

    studies = urllist_parsed['studies']

    for si, study in enumerate(studies):
        #print(f"Study {si}\t{study['StudyInstanceUID']}")
        #print(study.keys())

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


def get_dicom_study_instance_id(urllist_parsed):
    try:
        return urllist_parsed['studies'][0]['StudyInstanceUID']
    except:
        return ""


def get_dicom_patient_name(urllist_parsed):
    try:
        return urllist_parsed['studies'][0]['PatientName']
    except:
        return "X"


def get_dicom_urllist_string(url):
    filename, headers = urllib.request.urlretrieve(url)
    with open(filename) as f:
        return f.read()


def get_outfilename(list_item, output_dir):
    patient_id, patient_name, url = list_item 
    base, _, ident = url.partition("file=/")
    filename = os.path.join(
        output_dir,
        ident.replace("/", os.sep).upper()
    )
    return filename


def download_dicom(url_list_item, output_dir):
    output_filename = get_outfilename(url_list_item, output_dir)

    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    
    if os.path.exists(output_filename):
        return
    
    patient_id, patient_name, url = url_list_item
    urllib.request.urlretrieve(
        url,
        output_filename
    )




class BatchWorker:
    def __init__(self) -> None:
        self.work_queue = queue.Queue()
        self.threads = []
        self.total_tasks = 0
        self.cancelled = False


    def add_task(self, worker, args) -> None:
        self.work_queue.put([worker, args])
        self.total_tasks += 1


    def batch_worker(self) -> None:
        while not self.work_queue.empty():
            task_worker, args = self.work_queue.get()
            task_worker(*args)
            self.work_queue.task_done()


    def start(self, thread_count: int) -> None:
        for i in range(thread_count):
            t = threading.Thread(target=self.batch_worker, daemon=True)
            self.threads.append(t)
            t.start()


    def done(self) -> bool:
        if self.work_queue.empty():
            return True
        return False


    def remaining(self) -> int:
        return self.work_queue.unfinished_tasks


    def join(self) -> None:
        self.work_queue.join()


    def cancel(self) -> None:
        while not self.work_queue.empty():
            task_worker, args = self.work_queue.get()
            self.work_queue.task_done()
        self.cancelled = True

    def has_completed(self):
        if not self.cancelled:
            return True
        return False



class Downloader:
    def __init__(self, threads=10) -> None:
        self.thread_count = threads
        self.reset()


    def reset(self):
        self.src_url = ""
        self.dicom_dcmmkdir = ""
        self.batch_worker = BatchWorker()
        self.thread = threading.Thread(target=self.download_worker, daemon=True)
        self.message_queue = queue.Queue()
        self.completed = False
        self.failed = False
        self.output_dir = None


    def set_status(self, message: str) -> None:
        self.message_queue.put(message)


    def get_status(self) -> str:
        messages = []
        while True:
            try:
                messages.append(self.message_queue.get(block=False))
            except queue.Empty:
                break
        if not messages:
            return None
        return messages


    def download_worker(self) -> None:
        if not self.src_url:
            self.set_status("Source URL is not valid")
            self.failed = True
            return

        self.set_status("Getting DICOM file list...")

        try:
            urllist_string = get_dicom_urllist_string(self.src_url)
        except Exception as e:
            self.set_status(f"Could not get file list ({type(e).__name__}: {e})")
            self.failed = True
            return

        try:
            urllist_parsed = parse_urllist_string(urllist_string)
        except Exception as e:
            self.set_status(f"Failed to parse the file list ({type(e).__name__}: {e})")
            self.failed = True
            return

        try:
            url_list = get_dicom_urllist(urllist_parsed)
        except Exception as e:
            self.set_status(f"Failed to extract urls from the file list ({type(e).__name__}: {e})")
            self.failed = True
            return

        self.set_status(f"Found {len(url_list)} DICOM files")

        if not url_list:
            self.set_status(f"No DICOM files found")
            self.failed = True
            return

        study_id = get_dicom_study_instance_id(urllist_parsed)
        patient_name = get_dicom_patient_name(urllist_parsed)

        if not study_id:
            self.set_status("No Study Id Found")
            self.failed = True
            return

        output_dir = os.path.join(CACHE_DIR, f"{patient_name}.{study_id}")
        temp_dir = f"{output_dir}.partial"
        self.output_dir = output_dir

        if os.path.exists(output_dir):
            self.set_status(f"Study already downloaded")
            self.completed = True
            return

        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        for url_list_item in url_list:
            self.batch_worker.add_task(download_dicom, [url_list_item, temp_dir])

        self.set_status(f"Downloading {len(url_list)} DICOM files of {patient_name}")
        self.batch_worker.start(self.thread_count)

        self.batch_worker.join()

        if self.batch_worker.has_completed():
            self.set_status("Moving from temporary location")
            os.rename(temp_dir, output_dir)

        if self.dicom_dcmmkdir:
            self.set_status("Creating DICOMDIR")
            self.create_dicomdir(output_dir)

        self.set_status("Download Complete")
        
        self.completed = True


    def create_dicomdir(self, output_dir):
        if self.dicom_dcmmkdir == "":
            return
        try:
            result = subprocess.check_output([self.dicom_dcmmkdir, "+r", "*"], cwd=output_dir)
        except subprocess.CalledProcessError:
            print("Error Creating DICOMDIR")


    def start(self, src_url, dicom_dcmmkdir="") -> None:
        self.src_url = src_url
        self.dicom_dcmmkdir = dicom_dcmmkdir
        self.set_status("Starting Download...")
        self.thread.start()


    def has_completed(self) -> bool:
        if self.completed:
            return True
        if self.batch_worker.total_tasks == 0:
            return False
        if self.batch_worker.remaining() > 0:
            return False
        return True


    def has_failed(self) -> bool:
        if self.failed:
            return True
        return False


    def completed_percentage(self) -> int:
        if self.batch_worker.total_tasks == 0:
            return 0
        return int(float(self.batch_worker.total_tasks - self.batch_worker.remaining()) / float(self.batch_worker.total_tasks) * 100.0)


    def cancel(self) -> None:
        self.batch_worker.cancel()


    def join(self) -> None:
        self.thread.join()


    def get_download_path(self) -> str:
        return self.output_dir



def get_src_url(url):
    protocol, sep, download_url = url.partition(":")

    if protocol == 'dldicom':
        return download_url

    if protocol in ['http', 'https']:
        src_parsed = urlparse(url)
        qs = parse_qs(src_parsed.query)
        if 'url' in qs:
            if qs['url']:
                return qs['url'][0]     
        
    return url


def is_url(url):
    protocol, sep, download_url = url.partition(":")

    if not protocol in ['dldicom', 'http', 'https']:
        return False

    return True


def get_default_viewer():
    if platform.system() == "Darwin":
        return "open"
    return "explorer.exe"


def main_gui():
    from tkinter import ttk
    import tkinter as tk

    root = tk.Tk()
    root.geometry('400x130')
    root.title('Download DICOMs')
    root.resizable(False, False)
    root.grid()
    root.grid_columnconfigure(tuple(range(2)), weight=1)
    root.grid_rowconfigure(tuple(range(2)), weight=1)
    root.eval('tk::PlaceWindow . center')

    progress_bar = ttk.Progressbar(
        root,
        orient='horizontal',
        mode='indeterminate'
    )
    progress_bar.start()

    url_entry = tk.Entry(
        root,
        width = 48
    )


    url_label = ttk.Label(
        root,
        text='DICOM URL',
    )

    status_label = ttk.Label(
        root,
        text=''
    )

    start_button = ttk.Button(
        root,
        text='Start'
    )

    cancel_button = ttk.Button(
        root,
        text='Cancel',
    )

    open_button = ttk.Button(
        root,
        text='Open',
        state= tk.DISABLED
    )

    url_label.grid(column=0, row=0, padx=10, pady=20, columnspan=2, sticky=tk.W)
    url_entry.grid(column=0, row=0, padx=10, pady=20, columnspan=2, sticky=tk.E)
    status_label.grid(column=0, row=1, padx=10, pady=0, columnspan=2, sticky=tk.NSEW)
    cancel_button.grid(column=1, row=2, padx=10, pady=10, sticky=tk.W)
    
    download_url = ""
    dicom_viewer = get_default_viewer()
    dicom_dcmmkdir = ""
    

    try:
        opts, args = getopt.getopt(sys.argv[1:], "v:d:", ["viewer=", "dcmmkdir="])

        for opt, arg in opts:
            if opt in ("-v", "--viewer"):
                dicom_viewer = arg
            if opt in ("-d", "--dcmmkdir"):
                dicom_dcmmkdir = arg

        try:
            download_url = args[0]
        except IndexError:
            download_url = ""
            
    except getopt.GetoptError:
        print("Options Error")

    url_entry.insert(0, download_url)

    downloader = Downloader()

    def show_open_button():
        start_button.grid_forget()
        open_button.grid(column=0, row=2, padx=10, pady=10, sticky=tk.E)

    def show_start_button():
        open_button.grid_forget()
        start_button.grid(column=0, row=2, padx=10, pady=10, sticky=tk.E)

    def show_progress_bar():
        url_entry.grid_forget()
        url_label.grid_forget()
        progress_bar.grid(column=0, row=0, padx=10, pady=20, columnspan=2, sticky=tk.NSEW)

    def show_url_entry():
        progress_bar.grid_forget()
        url_label.grid(column=0, row=0, padx=10, pady=20, columnspan=2, sticky=tk.W)
        url_entry.grid(column=0, row=0, padx=10, pady=20, columnspan=2, sticky=tk.E)

    def cancel_handler():
        if downloader:
            downloader.cancel()
        root.destroy()

    def open_handler():
        if not downloader:
            return
        
        print(f"Opening File {downloader.get_download_path()}")
        DETACHED_PROCESS = 0x00000008
        cmd = [
            dicom_viewer,
            downloader.get_download_path(),
        ]
        p = subprocess.Popen(
            cmd, shell=False, stdin=None, stdout=None, stderr=None,
            close_fds=True, creationflags=DETACHED_PROCESS,
        )
        root.destroy()

    def update_status():
        status = downloader.get_status()
        if status:
            status_label['text'] = status[-1]

        percent_completed = downloader.completed_percentage()
        if percent_completed > 0:
            progress_bar['mode'] = 'determinate'
            progress_bar.stop()
            progress_bar['value'] = percent_completed

        if downloader.has_completed():
            progress_bar['mode'] = 'determinate'
            progress_bar.stop()
            progress_bar['value'] = 100
            status_label['text'] = 'Download Complete'
            open_button['state'] = tk.NORMAL
            cancel_button['text'] = 'Close'

        if downloader.has_failed():
            progress_bar['mode'] = 'determinate'
            progress_bar.stop()
            progress_bar['value'] = 0
            cancel_button['text'] = 'Close'
            downloader.reset()
            show_start_button()
            show_url_entry()

        root.after(10, update_status)


    def start_handler():
        show_open_button()
        show_progress_bar()
        downloader.start(get_src_url(url_entry.get()), dicom_dcmmkdir)

        
    start_button['command'] = start_handler
    cancel_button['command'] = cancel_handler
    open_button['command'] = open_handler
    
    show_start_button()

    update_status()

    if (download_url):
        start_handler()

    try:
        clipboard_text = root.clipboard_get()
    except:
        clipboard_text = ""

    if is_url(clipboard_text):
        url_entry.insert(0, clipboard_text)

    root.mainloop()

    downloader.cancel()
    try:
        downloader.join()
    except RuntimeError:
        pass


def main_cli():
    try:
        download_url = sys.argv[1]
    except IndexError:
        download_url = input("Download Url: ")

    downloader = Downloader(get_src_url(download_url))

    print("Starting Download...")
    downloader.start()

    prev_percent = 0
    while not downloader.has_failed() and not downloader.has_completed():
        status = downloader.get_status()

        percent_completed = downloader.completed_percentage()
        if percent_completed != prev_percent:
            prev_percent = percent_completed
            if status:
                for s in status:
                    print(f"{percent_completed}% : {s}")
            else:
                print(f"{percent_completed}%")

        time.sleep(1)

    status = downloader.get_status()
    if status:
        for s in status:
            print(s)
        
    downloader.join()


def main():
    try:
        main_gui()
    except ModuleNotFoundError:
        main_cli()


if __name__ == '__main__':
    main()
