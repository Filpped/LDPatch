import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from upsetplot import UpSet, from_contents

FILES = [
    ("relibrary/core/patch/rpm_patch_comparison_report.json", "Fedora-openEuler"),
    ("relibrary/core/patch/deb_rpm_patch_comparison_report.json", "Fedora-Debian")
]
OUTPUT_DIR = "data/patches/analysis_output"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def load_patch_json(json_path, fedora_key, other_key):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for pkg, info in data.items():
        if "error" in info:
            continue
        cp = info.get("common_patches", [])
        sf = info.get("same_function_different_content", [])
        uf = info.get(f"unique_{fedora_key}_patches", [])
        ud = info.get(f"unique_{other_key}_patches", [])
        rows.append({
            "package": pkg,
            "common": len(cp),
            "same_func_diff_content": len(sf),
            "unique_fedora": len(uf),
            "unique_other": len(ud),
            "has_patch": int(len(cp) + len(sf) + len(uf) + len(ud) > 0)
        })
    return pd.DataFrame(rows)

def save_fig(fig, outdir, name):
    path = os.path.join(outdir, f"{name}.png")
    fig.savefig(path, bbox_inches='tight', dpi=300)
    print(f"Saved: {path}")

def patch_category_bar(df, outdir, label):
    summary = {
        "Common": df['common'].astype(bool).sum(),
        "SameFuncDiffContent": df['same_func_diff_content'].astype(bool).sum(),
        "UniqueFedora": df['unique_fedora'].astype(bool).sum(),
        "UniqueOther": df['unique_other'].astype(bool).sum(),
        "NoPatch": (df[['common','same_func_diff_content','unique_fedora','unique_other']].sum(axis=1)==0).sum()
    }
    fig, ax = plt.subplots()
    bars = ax.bar(summary.keys(), summary.values(), color=sns.color_palette("Set2"))
    ax.set_title(f"Patch Category Distribution ({label})")
    for bar in bars:
        height = int(bar.get_height())
        ax.text(bar.get_x() + bar.get_width()/2, height, str(height), ha='center', va='bottom', fontsize=10)
    save_fig(fig, outdir, f"{label}_patch_category_bar")
    plt.close(fig)

def patch_count_hist(df, outdir, label):
    df['patch_count'] = df[['common','same_func_diff_content','unique_fedora','unique_other']].sum(axis=1)
    fig, ax = plt.subplots()
    df['patch_count'].hist(bins=20, ax=ax, color='#4C72B0')
    ax.set_title(f"Patch Count Distribution per Package ({label})")
    ax.set_xlabel("Total Patch Count")
    ax.set_ylabel("Package Count")
    save_fig(fig, outdir, f"{label}_patch_count_hist")
    plt.close(fig)

def top_n_packages(df, outdir, label, N=15):
    df['patch_count'] = df[['common','same_func_diff_content','unique_fedora','unique_other']].sum(axis=1)
    top = df.sort_values('patch_count', ascending=False).head(N)
    fig, ax = plt.subplots(figsize=(7,5))
    sns.barplot(y=top['package'], x=top['patch_count'], orient='h', ax=ax, color='#4C72B0')
    ax.set_title(f"Top {N} Packages by Patch Count ({label})")
    ax.set_xlabel("Total Patch Count")
    ax.set_ylabel("Package")
    save_fig(fig, outdir, f"{label}_top_{N}_packages")
    plt.close(fig)

def similarity_boxplot(json_path, outdir, label, other_key):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    sim_list = []
    for pkg, info in data.items():
        sims = [x['similarity'] for x in info.get("same_function_different_content", []) if "similarity" in x]
        sim_list.extend(sims)
    if sim_list:
        fig, ax = plt.subplots()
        sns.boxplot(x=sim_list, ax=ax, color='#4C72B0')
        ax.set_title(f"Similarity Distribution of Same-Function-Diff-Content Patches ({label})")
        ax.set_xlabel("Similarity")
        save_fig(fig, outdir, f"{label}_similarity_boxplot")
        plt.close(fig)

def upset_plot(json_path, outdir, label, fedora_key, other_key):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    sets = {
        f"Common": [],
        f"FedoraUnique": [],
        f"{other_key.capitalize()}Unique": []
    }
    for pkg, info in data.items():
        if info.get("common_patches"):
            sets["Common"].append(pkg)
        if info.get(f"unique_{fedora_key}_patches"):
            sets["FedoraUnique"].append(pkg)
        if info.get(f"unique_{other_key}_patches"):
            sets[f"{other_key.capitalize()}Unique"].append(pkg)
    contents = {k:v for k,v in sets.items() if v}
    if contents:
        fig = plt.figure()
        upset = UpSet(from_contents(contents), show_counts=True, sort_by="cardinality")
        upset.plot(fig=fig)
        plt.title(f"UpSet Plot of Patch Set Overlap ({label})")
        save_fig(fig, outdir, f"{label}_upset_plot")
        plt.close(fig)

def main_fixed():
    # Fedora vs openEuler
    json_rpm, label_rpm = FILES[0]
    json_deb, label_deb = FILES[1]
    # Fedora-openEuler
    df_rpm = load_patch_json(json_rpm, "fedora", "openeuler")
    patch_category_bar(df_rpm, OUTPUT_DIR, label_rpm)
    patch_count_hist(df_rpm, OUTPUT_DIR, label_rpm)
    top_n_packages(df_rpm, OUTPUT_DIR, label_rpm)
    similarity_boxplot(json_rpm, OUTPUT_DIR, label_rpm, "openeuler")
    upset_plot(json_rpm, OUTPUT_DIR, label_rpm, "fedora", "openeuler")
    df_rpm.to_csv(os.path.join(OUTPUT_DIR, f"{label_rpm}_patch_summary.csv"), index=False)
    # Fedora-Debian
    df_deb = load_patch_json(json_deb, "fedora", "debian")
    patch_category_bar(df_deb, OUTPUT_DIR, label_deb)
    patch_count_hist(df_deb, OUTPUT_DIR, label_deb)
    top_n_packages(df_deb, OUTPUT_DIR, label_deb)
    similarity_boxplot(json_deb, OUTPUT_DIR, label_deb, "debian")
    upset_plot(json_deb, OUTPUT_DIR, label_deb, "fedora", "debian")
    df_deb.to_csv(os.path.join(OUTPUT_DIR, f"{label_deb}_patch_summary.csv"), index=False)
    print("All analysis charts and tables have been generated in:", OUTPUT_DIR)

if __name__ == "__main__":
    main_fixed()
