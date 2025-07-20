import os
import json
import logging
import subprocess
import shutil
import tempfile
import requests
from urllib.parse import quote

logging.basicConfig(filename='patch_tracking.log',
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

with open("deb_rpm_patch_comparison_report.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

def extract_patch_pairs(data):
    tasks = []
    for pkg_name, patch_info in data.items():
        for group in ["common_patches", "same_function_different_content"]:
            group_data = patch_info.get(group, [])
            for item in group_data:
                fedora_patch = item.get("fedora", "") if isinstance(item, dict) else ""
                debian_patch = item.get("debian", "") if isinstance(item, dict) else ""
                tasks.append({
                    "pkg_name": pkg_name,
                    "group": group,
                    "fedora": fedora_patch,
                    "debian": debian_patch
                })
    return tasks

def get_fedora_patch_commit_date(pkg_name, patch_filename):
    repo_url = f"https://src.fedoraproject.org/rpms/{pkg_name}.git"
    patch_basename = os.path.basename(patch_filename)
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_cmd = ["git", "clone", repo_url, pkg_name]
        try:
            subprocess.run(clone_cmd, cwd=tmpdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            repo_path = os.path.join(tmpdir, pkg_name)
            log_cmd = ["git", "log", "--follow", "--format=%H %aI", "--", patch_basename]
            output = subprocess.check_output(log_cmd, cwd=repo_path, text=True, encoding="utf-8", errors="ignore")
            lines = output.splitlines()
            
            if lines:
                last_line = lines[-1] if lines else ""
                if last_line:
                    commit_hash, commit_date = last_line.split(" ", 1)
                    logging.info(f"[FOUND] First commit for {patch_basename}: {commit_hash} at {commit_date}")
                    return commit_date
            
            return None
        except subprocess.CalledProcessError as e:
            logging.error(f"[ERROR] git command failed for {pkg_name}: {e}")
        except Exception as e:
            logging.error(f"[ERROR] Unexpected error for {pkg_name}: {e}")
    return None
CACHE_FILE = "salsa_project_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def find_debian_patch_commit_date(pkg_name, patch_name):
    cache = load_cache()

    if pkg_name in cache:
        paths = cache[pkg_name]
    else:
        search_url = f"https://salsa.debian.org/api/v4/projects?search={pkg_name}"
        try:
            response = requests.get(search_url)
            response.raise_for_status()
            projects = response.json()
            paths = [p["path_with_namespace"] for p in projects if pkg_name.lower() in p["name"].lower()]
            cache[pkg_name] = paths
            save_cache(cache)
        except Exception as e:
            logging.error(f"[ERROR] Failed to search project for {pkg_name}: {e}")
            return None

    for project_path in paths:
        encoded_project = quote(project_path, safe="")

        try:
            project_info_url = f"https://salsa.debian.org/api/v4/projects/{encoded_project}"
            project_resp = requests.get(project_info_url)
            project_resp.raise_for_status()
            default_branch = project_resp.json().get("default_branch", "master")
        except Exception as e:
            logging.warning(f"[WARN] Failed to get default branch for {project_path}, using 'master': {e}")
            default_branch = "master"

        encoded_patch_path = quote(f"debian/patches/{patch_name}", safe="")
        api_url = f"https://salsa.debian.org/api/v4/projects/{encoded_project}/repository/commits?path={encoded_patch_path}&ref_name={default_branch}&per_page=100"

        try:
            commit_resp = requests.get(api_url)
            if commit_resp.status_code == 200:
                commits = commit_resp.json()
                if commits:
                    last_commit = commits[-1]
                    commit_date = last_commit.get("committed_date")
                    commit_hash = last_commit.get("id")
                    if commit_date:
                        logging.info(f"[FOUND] First commit for {patch_name}: {commit_hash} at {commit_date}")
                        return commit_date
            elif commit_resp.status_code == 404:
                continue
            else:
                logging.warning(f"[WARN] Unexpected status {commit_resp.status_code} from {api_url}")
        except Exception as e:
            logging.warning(f"[WARN] Failed to query {api_url}: {e}")
            continue

    logging.error(f"[MISS] No commit found for {pkg_name}/{patch_name}")
    return None

def track_patch_introduced_times_new(data):
    tasks = extract_patch_pairs(data)
    logging.info(f"[INFO] Total patch pairs to process: {len(tasks)}")

    result = {}
    for task in tasks:
        pkg = task["pkg_name"]
        group = task["group"]
        fedora_patch = task["fedora"]
        debian_patch = task["debian"]

        if not fedora_patch and not debian_patch:
            continue

        fedora_time = get_fedora_patch_commit_date(pkg, fedora_patch) if fedora_patch else ""
        debian_time = find_debian_patch_commit_date(pkg, debian_patch) if debian_patch else ""

        result.setdefault(pkg, {}).setdefault(group, []).append({
            "fedora": fedora_patch,
            "debian": debian_patch,
            "fedora_time": fedora_time or "NOT FOUND",
            "debian_time": debian_time or "NOT FOUND"
        })

        logging.info(f"[INFO] {pkg} {group}: {fedora_patch} / {debian_patch} => {fedora_time} / {debian_time}")

    with open("patch_introduced_times.json", "w", encoding="utf-8") as out_f:
        json.dump(result, out_f, indent=2, ensure_ascii=False)
    logging.info("[DONE] Results saved to patch_introduced_times.json")

track_patch_introduced_times_new(raw_data)

