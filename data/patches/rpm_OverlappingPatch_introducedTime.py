import os
import json
import logging
import subprocess
import tempfile

# 设置日志
logging.basicConfig(filename='fo_patch_tracking.log',
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# 加载 JSON 数据
with open("rpm_patch_comparison_report.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

# 提取补丁对任务
# 假设原始数据结构为：{pkg: {group: [{fedora: ..., openeuler: ...}, ...]}}
def extract_patch_pairs(data):
    tasks = []
    for pkg_name, patch_info in data.items():
        for group in ["common_patches", "same_function_different_content"]:
            group_data = patch_info.get(group, [])
            for item in group_data:
                fedora_patch = ""
                openeuler_patch = ""
                if isinstance(item, dict):
                    fedora_patch = item.get("fedora", "")
                    openeuler_patch = item.get("openeuler", "")
                elif isinstance(item, str):
                    fedora_patch = item
                    openeuler_patch = item
                tasks.append({
                    "pkg_name": pkg_name,
                    "group": group,
                    "fedora": fedora_patch,
                    "openeuler": openeuler_patch
                })
    return tasks

def get_correct_repo_name(repo_url, pkg_name):
    # 使用git ls-remote命令获取仓库的所有分支和标签
    try:
        output = subprocess.check_output(['git', 'ls-remote', repo_url], text=True, encoding='utf-8', errors='ignore')
        lines = output.splitlines()
        for line in lines:
            if line.endswith(f'refs/heads/{pkg_name}'):
                return pkg_name
            elif line.endswith(f'refs/heads/{pkg_name.lower()}'):
                return pkg_name.lower()
            elif line.endswith(f'refs/heads/{pkg_name.upper()}'):
                return pkg_name.upper()
    except subprocess.CalledProcessError as e:
        logging.error(f"[ERROR] git ls-remote command failed for {pkg_name}: {e}")
    return pkg_name

def check_branch_exists(repo_path, branch_name):
    """检查指定分支是否存在"""
    try:
        result = subprocess.run(
            ["git", "branch", "-a"], 
            cwd=repo_path, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="ignore"
        )
        branches = result.stdout.splitlines()
        for branch in branches:
            if branch_name in branch.strip():
                return True
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"[ERROR] Failed to check branch {branch_name}: {e}")
        return False

# Git 克隆并获取 patch 提交时间（适用于 Fedora 和 openEuler）
def get_patch_commit_date(repo_url, pkg_name, patch_filename, distro):
    patch_basename = os.path.basename(patch_filename)
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp()
        if distro == "openeuler":
            repo_url = f"https://gitee.com/src-openeuler/{pkg_name}.git"
            pkg_name = get_correct_repo_name(repo_url, pkg_name)
            # 克隆仓库（不使用--depth限制，获取完整历史）
            clone_cmd = ["git", "clone", repo_url, pkg_name]
            logging.info(f"[INFO] Cloning {repo_url}")
        else:
            # Fedora仓库，不限制深度
            clone_cmd = ["git", "clone", repo_url, pkg_name]
            logging.info(f"[INFO] Cloning {repo_url}")
            
        try:
            subprocess.run(clone_cmd, cwd=tmpdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8", errors="ignore")
            repo_path = os.path.join(tmpdir, pkg_name)
            
            # 切换到指定分支
            if distro == "fedora":
                branch_name = "f41"
                if check_branch_exists(repo_path, branch_name):
                    checkout_cmd = ["git", "checkout", branch_name]
                    subprocess.run(checkout_cmd, cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logging.info(f"[INFO] Switched to branch {branch_name}")
                else:
                    logging.warning(f"[WARNING] Branch {branch_name} not found for {pkg_name}, using default branch")
            elif distro == "openeuler":
                branch_name = "openEuler-24.03-LTS"
                if check_branch_exists(repo_path, branch_name):
                    checkout_cmd = ["git", "checkout", branch_name]
                    subprocess.run(checkout_cmd, cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logging.info(f"[INFO] Switched to branch {branch_name}")
                else:
                    logging.warning(f"[WARNING] Branch {branch_name} not found for {pkg_name}, using default branch")
            
            # 使用git log --follow查找补丁首次引入的时间
            # 格式化输出，获取全部历史并按时间顺序排列
            log_cmd = ["git", "log", "--follow", "--format=%H %aI", "--", patch_basename]
            output = subprocess.check_output(log_cmd, cwd=repo_path, text=True, encoding="utf-8", errors="ignore")
            lines = output.splitlines()
            
            if lines:
                # 获取最后一行，即最早的提交（首次引入）
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
    finally:
        # 尝试清理临时目录
        if tmpdir and os.path.exists(tmpdir):
            try:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception as e:
                logging.warning(f"[WARNING] Failed to clean up temp dir {tmpdir}: {e}")
                # 不因为清理问题而失败

# 新的主流程，生成理想结构

def track_patch_introduced_times_new(data):
    tasks = extract_patch_pairs(data)
    logging.info(f"[INFO] Total patch pairs to process: {len(tasks)}")

    result = {}
    for task in tasks:
        pkg = task["pkg_name"]
        group = task["group"]
        fedora_patch = task["fedora"]
        openeuler_patch = task["openeuler"]

        if not fedora_patch and not openeuler_patch:
            continue

        fedora_time = ""
        openeuler_time = ""
        if fedora_patch:
            repo_url = f"https://src.fedoraproject.org/rpms/{pkg}.git"
            fedora_time = get_patch_commit_date(repo_url, pkg, fedora_patch, "fedora") or "未找到"
        if openeuler_patch:
            repo_url = f"https://gitee.com/src-openeuler/{pkg}.git"
            openeuler_time = get_patch_commit_date(repo_url, pkg, openeuler_patch, "openeuler") or "未找到"

        result.setdefault(pkg, {}).setdefault(group, []).append({
            "fedora": fedora_patch,
            "openeuler": openeuler_patch,
            "fedora_time": fedora_time,
            "openeuler_time": openeuler_time
        })
        logging.info(f"[INFO] {pkg} {group}: {fedora_patch} / {openeuler_patch} => {fedora_time} / {openeuler_time}")

    with open("fo_introduced_times.json", "w", encoding="utf-8") as out_f:
        json.dump(result, out_f, indent=2, ensure_ascii=False)
    logging.info("[DONE] Results saved to fo_introduced_times.json")

# 执行新主流程
track_patch_introduced_times_new(raw_data)