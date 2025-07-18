import os
import json
import pandas as pd
from datetime import datetime
import glob
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import matplotlib.dates as mdates
COMPARISON_FILES = [
    ("data/patches/fo_introduced_times.json", "Fedora-openEuler"),
    ("data/patches/patch_introduced_times.json", "Fedora-Debian"),
]
OUTPUT_DIR = "data/patches/analysis_output"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def parse_time(t):
    if not t or t == "未找到": return pd.NaT
    try:
        return pd.to_datetime(t)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(t[:len(fmt)], fmt)
        except Exception:
            continue
    return pd.NaT

def safe_parse_time(col):
    # 替换无效内容
    col = col.replace(['未找到', 'NaT', 'None', ''], pd.NA)
    # 先全转utc，再去掉tz
    col = pd.to_datetime(col, errors='coerce', utc=True)
    # 去掉时区信息变本地时间
    return col.dt.tz_localize(None)


def load_introduced_times(json_path):
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)

def collect_patch_pairs(intro_json, key1, key2):
    pairs = []
    for pkg, info in intro_json.items():
        for p in info.get("common_patches", []):
            pairs.append((p.get(key1), p.get(key2), "common", pkg, p))
        for p in info.get("same_function_different_content", []):
            pairs.append((p.get(key1), p.get(key2), "similar", pkg, p))
    return pairs

def main():
    for intro_file, label in COMPARISON_FILES:
        intro_data = load_introduced_times(intro_file)
        if "openEuler" in label:
            key1, key2 = "fedora", "openeuler"
            time1, time2 = "fedora_time", "openeuler_time"
        else:
            key1, key2 = "fedora", "debian"
            time1, time2 = "fedora_time", "debian_time"
        rows = []
        miss_count = 0
        for fedora_patch, other_patch, ctype, pkg, entry in collect_patch_pairs(intro_data, key1, key2):
            fedora_time = entry.get(time1)
            other_time = entry.get(time2)
            if not fedora_time and not other_time:
                miss_count += 1
                print(f"[WARN] {pkg}: {fedora_patch}/{other_patch} 没查到时间")
            fedora_time = parse_time(fedora_time)
            other_time = parse_time(other_time)
            rows.append({
                "package": pkg,
                "fedora_patch": fedora_patch,
                f"{key2}_patch": other_patch,
                "type": ctype,
                "fedora_time": fedora_time,
                f"{key2}_time": other_time
            })
        df = pd.DataFrame(rows)
        outcsv = os.path.join(OUTPUT_DIR, f"{label}_patch_pair_intro_times.csv")
        df.to_csv(outcsv, index=False)
        print(f"Saved patch-pair time csv: {outcsv}, missed time count: {miss_count}")

def plot_patch_intro_analysis(csvfile, outdir, label, key_other):
    df = pd.read_csv(csvfile)
    df["fedora_time"] = safe_parse_time(df["fedora_time"])
    df[f"{key_other}_time"] = safe_parse_time(df[f"{key_other}_time"])

# 特殊：去除 openEuler 的引入时间为默认批量迁入时间的行
    if key_other == "openeuler":
        # 这里用原始字符串值做判断，避免时区影响
        raw_df = pd.read_csv(csvfile)
        special_time_substr = "2019-09-30"
        mask = ~raw_df["openeuler_time"].astype(str).str.contains(special_time_substr)
        print("去除 openeuler 批量引入补丁数：", (~mask).sum())
        df = df[mask].copy()
        df.reset_index(drop=True, inplace=True)
    print("数据类型检查：", df["fedora_time"].dtype, df[f"{key_other}_time"].dtype)
    print(f"原始补丁对总数：{len(df)}")
    print("fedora_time可用行数：", df["fedora_time"].notna().sum())
    print(f"{key_other}_time可用行数：", df[f"{key_other}_time"].notna().sum())
    print("都可用行数：", df[["fedora_time", f"{key_other}_time"]].dropna().shape[0])

    df = df.dropna(subset=["fedora_time", f"{key_other}_time"])

    # 可以保存drop前后的内容，人工核查
    df.to_csv(os.path.join(outdir, f"{label}_patch_intro_points_full.csv"), index=False)
    df2 = df.dropna(subset=["fedora_time", f"{key_other}_time"])
    df2.to_csv(os.path.join(outdir, f"{label}_patch_intro_points_used.csv"), index=False)

    if df2.empty:
        print(f"Skip {label}: no data")
        return

    # 1. ECDF (CDF of abs delay)
    if key_other == "openeuler":
        # 只保留2022-2024年数据
        start_2022 = pd.Timestamp('2022-01-01')
        end_2024_11 = pd.Timestamp('2024-12-01')
        df_ecdf = df[(df["fedora_time"] >= start_2022) & (df["fedora_time"] < end_2024_11) &
                     (df[f"{key_other}_time"] >= start_2022) & (df[f"{key_other}_time"] < end_2024_11)].copy()
    else:
        df_ecdf = df.copy()
    df_ecdf["delay"] = (df_ecdf["fedora_time"] - df_ecdf[f"{key_other}_time"]).dt.days
    df_ecdf["abs_delay"] = df_ecdf["delay"].abs()
    df_ecdf["first"] = np.where(df_ecdf["delay"] < 0, f'{key_other.capitalize()} First',
                                 np.where(df_ecdf["delay"] > 0, 'Fedora First', 'Simultaneous'))
    # ECDF
    fig, ax = plt.subplots()
    for who in ['Fedora First', f'{key_other.capitalize()} First']:
        x = df_ecdf.loc[df_ecdf['first'] == who, "abs_delay"]
        if len(x) == 0: continue
        sns.ecdfplot(x, ax=ax, label=who)
    ax.set_xscale("log")
    ax.set_xlabel("Absolute Introduction Delay (days, log scale)")
    ax.set_ylabel("ECDF")
    ax.set_title(f"Cumulative Distribution of Patch Introduction Delay\n({label})")
    ax.legend()
    fig.tight_layout()
    if key_other == "openeuler":
        fig.savefig(os.path.join(outdir, f"{label}_ecdf_delay_2022_2024.png"), dpi=300)
    else:
        fig.savefig(os.path.join(outdir, f"{label}_ecdf_delay.png"), dpi=300)
    plt.close(fig)

    # 确保df有delay、abs_delay、first三列，供后续箱线图等使用
    df["delay"] = (df["fedora_time"] - df[f"{key_other}_time"]).dt.days
    df["abs_delay"] = df["delay"].abs()
    df["first"] = np.where(df["delay"] < 0, f'{key_other.capitalize()} First',
                           np.where(df["delay"] > 0, 'Fedora First', 'Simultaneous'))

    # 2. Yearly boxplot
    min_dates = df[["fedora_time", f"{key_other}_time"]].min(axis=1)
    min_dates = pd.to_datetime(min_dates, errors="coerce")
    df["year"] = min_dates.dt.year
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(x="year", y="abs_delay", data=df[df["abs_delay"] < 3650], color="#4C72B0")
    ax.set_yscale("log")
    ax.set_ylabel("Absolute Delay (days, log scale)")

    ax.set_xlabel("Year (First Introduction)")
    ax.set_title(f"Yearly Distribution of Patch Introduction Delay ({label})")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"{label}_yearly_boxplot.png"), dpi=300)
    plt.close(fig)

    # 3. Scatter plot
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(df["fedora_time"], df[f"{key_other}_time"], s=8, alpha=0.5, color="#4C72B0")
    lims = [
        min(df["fedora_time"].min(), df[f"{key_other}_time"].min()),
        max(df["fedora_time"].max(), df[f"{key_other}_time"].max())
    ]
    ax.plot(lims, lims, '--', color='grey')
    ax.set_xlabel("Fedora Patch Introduction Date")
    ax.set_ylabel(f"{key_other.capitalize()} Patch Introduction Date")
    ax.set_title(f"Patch Introduction Synchronization ({label})")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"{label}_scatter_introduced.png"), dpi=300)
    plt.close(fig)

    # 设置阈值为2021年9月30日
    time_threshold = pd.Timestamp('2022-01-01')
    # 只保留两侧都是2021年及以后的补丁
    recent_df = df[(df["fedora_time"] >= time_threshold) & (df[f"{key_other}_time"] >= time_threshold)]
    if not recent_df.empty:
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(recent_df["fedora_time"], recent_df[f"{key_other}_time"], s=10, alpha=0.7, color="#D55E00")
        lims = [
            min(recent_df["fedora_time"].min(), recent_df[f"{key_other}_time"].min()),
            max(recent_df["fedora_time"].max(), recent_df[f"{key_other}_time"].max())
        ]
        ax.plot(lims, lims, '--', color='grey')
        ax.set_xlabel("Fedora Patch Introduction Date")
        ax.set_ylabel(f"{key_other.capitalize()} Patch Introduction Date")
        ax.set_title(f"{label} Patch Synchronization, 2022–2025")
        fig.autofmt_xdate(rotation=45)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, f"{label}_scatter_introduced_2021after.png"), dpi=300)
        plt.close(fig)
    else:
        print(f"No recent patches (since 2022) for {label}")

    # 4. Leader bar (who first)
    leader_counts = df['first'].value_counts()
    fig, ax = plt.subplots()
    bars = ax.bar(leader_counts.index, leader_counts.values, color=sns.color_palette("muted"))
    ax.set_ylabel("Number of Patches")
    ax.set_title(f"Patch Origin Distribution ({label})")
    for bar in bars:
        height = int(bar.get_height())
        ax.text(bar.get_x() + bar.get_width() / 2, height, str(height), ha='center', va='bottom', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"{label}_leader_bar.png"), dpi=300)
    plt.close(fig)

    # 只保留2022-2024年的补丁
    start_2022 = pd.Timestamp('2022-01-01')
    end_2024_11 = pd.Timestamp('2024-12-01')  # 不含12月
    # 确保时间列为datetime类型
    df["fedora_time"] = pd.to_datetime(df["fedora_time"], errors="coerce")
    df[f"{key_other}_time"] = pd.to_datetime(df[f"{key_other}_time"], errors="coerce")
    # 严格筛选
    df_2022_2024 = df[
        (df["fedora_time"] >= start_2022) & (df["fedora_time"] < end_2024_11) &
        (df[f"{key_other}_time"] >= start_2022) & (df[f"{key_other}_time"] < end_2024_11)
    ]
    print("筛选后最大fedora_time：", df_2022_2024["fedora_time"].max())
    print(f"筛选后最大{key_other}_time：", df_2022_2024[f"{key_other}_time"].max())
    if not df_2022_2024.empty:
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(df_2022_2024["fedora_time"], df_2022_2024[f"{key_other}_time"], s=10, alpha=0.7, color="#E69F00")
        lims = [
            min(df_2022_2024["fedora_time"].min(), df_2022_2024[f"{key_other}_time"].min()),
            max(df_2022_2024["fedora_time"].max(), df_2022_2024[f"{key_other}_time"].max())
        ]
        ax.plot(lims, lims, '--', color='grey')
        ax.set_xlabel("Fedora Patch Introduction Date")
        ax.set_ylabel(f"{key_other.capitalize()} Patch Introduction Date")
        ax.set_title(f"{label} Patch Synchronization, 2022–2024")
        # 设置x轴和y轴范围严格为2022-01-01到2024-11-30
        ax.set_xlim([start_2022, end_2024_11 - pd.Timedelta(days=1)])
        ax.set_ylim([start_2022, end_2024_11 - pd.Timedelta(days=1)])
        # 设置主刻度为每3个月
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1,4,7,10)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.yaxis.set_major_locator(mdates.MonthLocator(bymonth=(1,4,7,10)))
        ax.yaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        fig.autofmt_xdate(rotation=45)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, f"{label}_scatter_introduced_2022_2024.png"), dpi=300)
        plt.close(fig)
    else:
        print(f"No patches in 2022-2024 for {label}")

    # 输出复用补丁的中位引入时延
    if key_other == "openeuler":
        start_2022 = pd.Timestamp('2022-01-01')
        end_2024_11 = pd.Timestamp('2024-12-01')
        median_delay = df[(df["fedora_time"] >= start_2022) & (df["fedora_time"] < end_2024_11) &
                          (df[f"{key_other}_time"] >= start_2022) & (df[f"{key_other}_time"] < end_2024_11)]["abs_delay"].median()
        print(f"复用补丁的中位引入时延（2022-2024）: {median_delay:.1f} 天")
    else:
        median_delay = df["abs_delay"].median()
        print(f"复用补丁的中位引入时延: {median_delay:.1f} 天")

    print(f"All figures for {label} saved to {outdir}")

def batch_patch_intro_plots():
    for csvfile in glob.glob(os.path.join(OUTPUT_DIR, "*_patch_pair_intro_times.csv")):
        label = os.path.basename(csvfile).split("_patch_pair")[0]
        if "openEuler" in label:
            key_other = "openeuler"
        else:
            key_other = "debian"
        plot_patch_intro_analysis(csvfile, OUTPUT_DIR, label, key_other)

if __name__ == "__main__":
    main() # 先输出csv
    batch_patch_intro_plots() # 再批量画图
