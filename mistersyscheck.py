import subprocess
import sys
import os

# Ensure tqdm and requests are installed
try:
    import tqdm
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])

import csv
import logging
from datetime import datetime
import time
from tqdm import tqdm
import threading
import itertools

# Spinner class
class Spinner:
    def __init__(self, message="Working..."):
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])  # Fixed escape issue
        self.running = False
        self.thread = None
        self.message = message

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def _spin(self):
        while self.running:
            sys.stdout.write(f"\r{self.message} {next(self.spinner)}")
            sys.stdout.flush()
            time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
        sys.stdout.flush()

# GitHub API setup
GITHUB_TOKEN = ""  # Optional: Use a token to avoid rate limits
ORG = "MiSTer-devel"
API_URL = "https://api.github.com"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# Config
EXCLUDE_ARCHIVED = True  # Set to False if you want to include archived repos

# Exceptions list
EXCLUDED_REPOS = {
    "u-boot_MiSTer", "Linux_Image_creator_MiSTer", "Main_MiSTer", "Hardware_MiSTer",
    "SD-InstallTool_Win_MiSTer", "SD-Installer-Win64_MiSTer", "Injector_MiSTer",
    "MiSTer-bootstrap", "Filters_MiSTer", "Updater_script_MiSTer", "Scripts_MiSTer",
    "MiSTer-devel.github.io", "MidiLink_MiSTer", "Fonts_MiSTer", "MiSTerConfigurator",
    "LXDE-Head_MiSTer", "Hardware_alternative", "MRA-Alternatives_MiSTer",
    "Retro-Controllers-USB-MiSTer", "mr-fusion", "xow_MiSTer", "T80", "T65",
    "Distribution_MiSTer", "Linux-Kernel_MiSTer", "Downloader_MiSTer",
    "ShadowMasks_MiSTer", "Presets_MiSTer", "PDFViewer_MiSTer", "MkDocs_MiSTer",
    "ArcadeDatabase_MiSTer", "Gamecontrollerdb_MiSTer", "Wiki_MiSTer",
    "Hiscores_MiSTer", "Cheats_MiSTer", "N64_ROM_Database", "Template_MiSTer"
}

# Special cases where sys folder is in a subdirectory
SPECIAL_SYS_PATHS = {
    "PDP1_MiSTer": "src/sys",
    "Apple-I_MiSTer": "boards/MiSTer/sys",
    "Arcade-Cave_MiSTer": "quartus/sys"
}

# Logging
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

# Format helper
def format_datetime(dt_str):
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S"), dt
    except Exception:
        return None, None, None

def get_rate_limit_status():
    url = f"{API_URL}/rate_limit"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        remaining = data['resources']['core']['remaining']
        reset_time = data['resources']['core']['reset']
        print(f"Remaining requests: {remaining}, Reset time: {datetime.fromtimestamp(reset_time)}")
        return remaining, reset_time
    except requests.exceptions.RequestException as e:
        logging.error(f"Rate limit check failed: {e}")
        return 0, None

def get_repos():
    repos = []
    page = 1
    while True:
        url = f"{API_URL}/orgs/{ORG}/repos?type=all&per_page=100&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Repo list failed: {e}")
            break

        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def get_latest_commit_date(repo_name, path):
    url = f"{API_URL}/repos/{ORG}/{repo_name}/commits?path={path}&per_page=1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0]['commit']['committer']['date']
    except requests.exceptions.RequestException as e:
        logging.error(f"Commit request failed for {repo_name}: {e}")
    return None

def check_sys_folder(repo_name):
    path = SPECIAL_SYS_PATHS.get(repo_name, "sys")
    date = get_latest_commit_date(repo_name, path)
    if not date:
        return None, None, None
    url = f"{API_URL}/repos/{ORG}/{repo_name}/commits?path={path}&per_page=1"
    try:
        commit_resp = requests.get(url, headers=HEADERS, timeout=10)
        commit_resp.raise_for_status()
        last_commit = commit_resp.json()[0]
        author_data = last_commit.get('author')
        if author_data and 'login' in author_data:
            author = author_data['login']
        else:
            author = last_commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
        return date, author, path
    except requests.exceptions.RequestException:
        return None, None, None

def get_latest_rbf_date(repo_name):
    url = f"{API_URL}/repos/{ORG}/{repo_name}/commits?path=releases&per_page=1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0]['commit']['committer']['date']
    except requests.exceptions.RequestException:
        return None
    return None

def main():
    start_time = time.time()

    spinner = Spinner("Checking rate limit")
    spinner.start()
    get_rate_limit_status()
    spinner.stop()

    spinner = Spinner("Fetching repositories")
    spinner.start()
    repos = get_repos()
    spinner.stop()

    results = []

    total_repos = 0
    checked_repos = 0
    repos_with_sys = 0
    errors_encountered = 0
    skipped_archived = []


    for repo in tqdm(repos, desc="Checking repositories"):
        repo_name = repo['name']
        total_repos += 1

        if repo_name in EXCLUDED_REPOS:
            continue

        is_archived = repo.get('archived', False)
        if EXCLUDE_ARCHIVED and is_archived:
            skipped_archived.append(repo_name)
            continue  # Skip archived repos completely

        checked_repos += 1
        status = "Deprecated" if is_archived else "Active"


        sys_date, user, path = check_sys_folder(repo_name)
        if sys_date:
            repos_with_sys += 1
            sys_date_fmt, sys_time_fmt, sys_dt = format_datetime(sys_date)
            rbf_date = get_latest_rbf_date(repo_name)
            if rbf_date:
                rbf_date_fmt, _, rbf_dt = format_datetime(rbf_date)
            else:
                rbf_date_fmt, rbf_dt = None, None

            release_newer = "Yes" if rbf_dt and rbf_dt >= sys_dt else "No"
            results.append((repo_name, sys_date_fmt, sys_time_fmt, user, rbf_date_fmt, release_newer, status))
        else:
            errors_encountered += 1

    # Sort results by sys date (oldest first)
    results.sort(key=lambda x: datetime.strptime(x[1], "%d/%m/%Y") if x[1] else datetime.min)

    # Output to terminal
    print("\nRepositories with 'sys' folder:")
    for name, sys_date_fmt, sys_time_fmt, user, rbf_date_fmt, release_newer, status in results:
        print(f"{name} — Sys: {sys_date_fmt} {sys_time_fmt} by {user} — RBF: {rbf_date_fmt} — Release newer? {release_newer} — Status: {status}")

    # List cores where release is not newer than sys
    no_new_release_cores = [row[0] for row in results if row[5] == "No"]

    print("\nCores where no new release since .sys was updated:")
    print(len(no_new_release_cores))
    if no_new_release_cores:
        print()
        for core in no_new_release_cores:
            print(core)

    if skipped_archived:
        print("\nArchived/Deprecated cores skipped:")
        print(len(skipped_archived))
        print()
        for core in skipped_archived:
            print(core)

    # Write CSV
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"mister_sys_folders_{timestamp}.csv"
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Core Name", "Sys Date", "Sys Time", "User", "Latest RBF Date", "Release Newer Than SYS?", "Status"])
        for row in results:
            writer.writerow(row)

    print(f"\nCSV saved as: {filename}")

    print("\nSummary:")
    print(f"Total repositories retrieved: {total_repos}")
    print(f"Repositories checked: {checked_repos}")
    print(f"Repositories with a 'sys' folder: {repos_with_sys}")
    print(f"Errors encountered: {errors_encountered}")

    elapsed_time = time.time() - start_time
    minutes, seconds = divmod(int(elapsed_time), 60)
    print(f"\nTotal runtime: {minutes} minutes, {seconds} seconds")

if __name__ == "__main__":
    main()
