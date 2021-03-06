'''
Aggregate data
'''

import argparse, os, sys, errno, subprocess, csv

run_identifier = "RUN_"

phenotypic_traits = ["not","nand","and","ornot","or","andnot","nor","xor","equals"]
even_traits = {"not", "and", "or", "nor", "equals"}
odd_traits = {"nand", "ornot", "andnot", "xor", "equals"}
even_profile = "101010101"
odd_profile = "010101011"
all_profile = "111111111"

"""
This is functionally equivalent to the mkdir -p [fname] bash command
"""
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def extract_params_cmd_log(path):
    content = None
    with open(path, "r") as fp:
        content = fp.read().strip()
    content = content.replace("./avida", "")
    params = [param.strip() for param in content.split("-set") if param.strip() != ""]
    cfg = {param.split(" ")[0]:param.split(" ")[1] for param in params}
    return cfg

def read_avida_dat_file(path):
    content = None
    with open(path, "r") as fp:
        content = fp.read().strip().split("\n")
    legend_start = 0
    legend_end = 0
    # Where does the legend table start?
    for line_i in range(0, len(content)):
        line = content[line_i].strip()
        if line == "# Legend:":         # Handles analyze mode detail files.
            legend_start = line_i + 1
            break
        if "#  1:" in line:             # Handles time.dat file.
            legend_start = line_i
            break
    # For each line in legend table, extract field
    fields = []
    for line_i in range(legend_start, len(content)):
        line = content[line_i].strip()
        if line == "":
            legend_end = line_i
            break
        fields.append( line.split(":")[-1].strip().lower().replace(" ", "_") )
    data = []
    for line_i in range(legend_end, len(content)):
        line = content[line_i].strip()
        if line == "": continue
        data_line = line.split(" ")
        if len(data_line) != len(fields):
            print("data fields mismatch!")
            print(fields)
            print(data_line)
            exit(-1)
        data.append({field:value for field,value in zip(fields, data_line)})
    return data

def simple_match_coeff(a, b):
    if len(a) != len(b):
        print(f"Length mismatch! {a} {b}")
        exit(-1)
    return sum(ai==bi for ai,bi in zip(a,b))

def main():
    parser = argparse.ArgumentParser(description="Run submission script.")
    parser.add_argument("--data_dir", type=str, help="Where is the base output directory for each run?")
    parser.add_argument("--dump", type=str, help="Where to dump this?", default=".")

    args = parser.parse_args()
    data_dir = args.data_dir
    dump_dir = args.dump

    if not os.path.exists(data_dir):
        print("Unable to find data directory.")
        exit(-1)

    mkdir_p(dump_dir)

    # Aggregate run directories.
    run_dirs = [run_dir for run_dir in os.listdir(data_dir) if run_identifier in run_dir]
    print(f"Found {len(run_dirs)} run directories.")

    # For each run directory:
    # - get id, get command line configuration settings
    summary_header = None
    summary_content_lines = []
    for run_dir in run_dirs:
        if "RUN_2596" in run_dir: continue
        print(f"processing {run_dir}")
        run_path = os.path.join(data_dir, run_dir)
        ############################################################
        # Extract commandline configuration settings (from cmd.log file)
        cmd_log_path = os.path.join(run_path, "cmd.log")
        cmd_params = extract_params_cmd_log(cmd_log_path)
        # Infer environmental change and change rate from events file
        chg_env = not "const" in cmd_params["EVENT_FILE"]
        chg_rate = cmd_params["EVENT_FILE"].split(".")[0].split("-")[-1] if chg_env else "u0"
        cmd_params["change_rate"] = chg_rate
        cmd_params["changing_env"] = str(int(chg_env))
        ############################################################

        # Extract time information
        time_data = read_avida_dat_file(os.path.join(run_path, "data", "time.dat"))
        tasks_data = read_avida_dat_file(os.path.join(run_path, "data", "tasks.dat"))

        # Extract environment information.

        doms_env_all = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_all", "final_dominant.dat"))
        doms_env_odd = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_odd", "final_dominant.dat"))
        doms_env_even = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_even", "final_dominant.dat"))
        # sort genotypes by update born
        doms_env_all.sort(key=lambda x: int(x["update_born"]))
        doms_env_odd.sort(key=lambda x: int(x["update_born"]))
        doms_env_even.sort(key=lambda x: int(x["update_born"]))

        if len(doms_env_all) != 2 and len(set([len(doms_env_all), len(doms_env_even), len(doms_env_odd)])) != 1:
            print("Unexpected number of genotypes in final_dominant data files.")
            exit(-1)

        info = {}

        # okay, this is all totally hacked... should think this through more for future experiments.
        # - maybe don't put both phases in the same final_dominant.gen file.
        info["phase_1_average_generation"] = time_data[-1]["average_generation"]
        info["phase_0_average_generation"] = [time_data[i]["average_generation"] for i in range(len(time_data)) if time_data[i]["update"] == "200000"][0]

        info["phase_1_pop_equals"] = int(tasks_data[-1]["equals"]) > 0
        info["phase_0_pop_equals"] = int([tasks_data[i]["equals"] for i in range(len(tasks_data)) if tasks_data[i]["update"] == "200000"][0]) > 0

        # Collect info on dominant genotypes for both phases.
        for phase_i in range(len(doms_env_all)):
            dom_env_even = doms_env_even[phase_i]
            dom_env_odd = doms_env_odd[phase_i]
            dom_env_all = doms_env_all[phase_i]

            # Collect dominant genotype data.
            genome_length = dom_env_all["genome_length"]

            phenotype_even = "".join([dom_env_even[trait] for trait in phenotypic_traits])
            phenotype_odd = "".join([dom_env_odd[trait] for trait in phenotypic_traits])
            phenotype_all = "".join([dom_env_all[trait] for trait in phenotypic_traits])
            phenotype_task_order = ";".join(phenotypic_traits)

            plastic_odd_even = phenotype_even != phenotype_odd
            equals_odd_even = dom_env_even["equals"] == "1" and dom_env_odd["equals"] == "1"
            equals_any = dom_env_even["equals"] == "1" or dom_env_odd["equals"] == "1" or dom_env_all["equals"] == "1"

            match_score_even = simple_match_coeff(phenotype_even, even_profile)
            match_score_odd = simple_match_coeff(phenotype_odd, odd_profile)
            match_score_all = simple_match_coeff(phenotype_all, all_profile)
            match_score_odd_even = match_score_even + match_score_odd

            info[f"phase_{phase_i}_genome_length"] = genome_length
            info[f"phase_{phase_i}_phenotype_even"] = phenotype_even
            info[f"phase_{phase_i}_phenotype_odd"] = phenotype_odd
            info[f"phase_{phase_i}_phenotype_all"] = phenotype_all
            info[f"phase_{phase_i}_phenotype_task_order"] = phenotype_task_order

            info[f"phase_{phase_i}_plastic_odd_even"] = plastic_odd_even

            info[f"phase_{phase_i}_equals_odd_even"] = equals_odd_even
            info[f"phase_{phase_i}_equals_any"] = equals_any

            info[f"phase_{phase_i}_match_score_even"] = match_score_even
            info[f"phase_{phase_i}_match_score_odd"] = match_score_odd
            info[f"phase_{phase_i}_match_score_all"] = match_score_all
            info[f"phase_{phase_i}_match_score_odd_even"] = match_score_odd_even

        lineage_env_all = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_all", "lineage_tasks.dat"))
        lineage_env_odd = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_odd", "lineage_tasks.dat"))
        lineage_env_even = read_avida_dat_file(os.path.join(run_path, "data", "analysis", "env_even", "lineage_tasks.dat"))
        if len({len(lineage_env_all), len(lineage_env_even), len(lineage_env_odd)}) != 1:
            print("lineage length mismatch!")
            exit(-1)

        info["lineage_length"] = len(lineage_env_all)

        # aggregate lineage information
        aggregate_lineage = []

        info["equals_odd_even_update"] = None
        info["equals_all_update"] = None
        info["equals_any_update"] = None
        info["plastic_odd_even_update"] = None

        for i in range(len(lineage_env_all)):
            update = lineage_env_all[i]["update_born"]
            info_i = {}
            info_i["phenotype_even"] = "".join([lineage_env_even[i][trait] for trait in phenotypic_traits])
            info_i["phenotype_odd"] = "".join([lineage_env_odd[i][trait] for trait in phenotypic_traits])
            info_i["plastic_odd_even"] = info_i["phenotype_even"] != info_i["phenotype_odd"]
            info_i["equals_odd_even"] = lineage_env_even[i]["equals"] == "1" and lineage_env_odd[i]["equals"] == "1"
            info_i["equals_all"] = lineage_env_all[i]["equals"] == "1"
            info_i["equals_any"] = lineage_env_even[i]["equals"] == "1" or lineage_env_odd[i]["equals"] == "1" or lineage_env_all[i]["equals"] == "1"
            info_i["match_score_even"] = simple_match_coeff(info_i["phenotype_even"], even_profile)
            info_i["match_score_odd"] = simple_match_coeff(info_i["phenotype_odd"], odd_profile)
            info_i["match_score_odd_even"] = info_i["match_score_odd"] + info_i["match_score_even"]

            aggregate_lineage.append(info_i)

            if (info["equals_odd_even_update"] == None) and (info_i["equals_odd_even"]):
                info["equals_odd_even_update"] = update

            if (info["equals_all_update"] == None) and (info_i["equals_all"]):
                info["equals_all_update"] = update

            if (info["equals_any_update"] == None) and info_i["equals_any"]:
                info["equals_any_update"] = update

            if (info["plastic_odd_even_update"] == None) and (info_i["plastic_odd_even"]):
                info["plastic_odd_even_update"] = update

        # Write to summary file.
        param_fields=list(cmd_params.keys())
        param_fields.sort()
        info_fields = list(info.keys())
        info_fields.sort()
        summary_fields = ",".join(param_fields + info_fields)
        if summary_header == None:
            summary_header = summary_fields
        elif summary_header != summary_fields:
            print("Header mismatch!")
            exit(-1)

        summary_line = [str(cmd_params[param]) for param in param_fields] + [str(info[field]) for field in info_fields]
        summary_content_lines.append(",".join(summary_line))

    # write out aggregate data
    with open(os.path.join(dump_dir, "aggregate.csv"), "w") as fp:
        out_content = summary_header + "\n" + "\n".join(summary_content_lines)
        fp.write(out_content)


if __name__ == "__main__":
    main()